"""
Distriliq Cape Town downstream sales connector.

Parses the Distriliq CPT Client Report Excel format:
  Sheet: "Client History"
  Format: pivot table — client rows with product sub-rows × monthly columns

Structure:
  Row 0:  Title (ignored)
  Row 1:  Description (ignored)
  Row 3:  Column headers — "Client / Wine", "Jul 25", "Aug 25", ..., "Jun 26"
  Row 4+: Data — alternating client rows and product rows

Client row:  bold name (WILLOUGHBY & CO), then monthly totals
Product row: wine name (Rose-Mary, Pecan Stream Sauv Blanc), monthly quantities

Strategy:
  - Track current client as we iterate rows
  - If row[0] looks like a product name (matches known product patterns), it's a product row
  - Otherwise it's a client row — update current_client
  - For each (client, product, month) cell with qty > 0, yield a sell-through row

Yields DISTRIBUTOR_SELL_THROUGH rows.
"""
from __future__ import annotations
import re
from typing import Iterator, Optional
import pandas as pd


SOURCE_CODE = 'DISTRILIQ_CPT'

MONTH_TO_NUM = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}


def detect(file_path: str) -> bool:
    """True if this looks like a Distriliq CPT report."""
    if not file_path.lower().endswith(('.xlsx', '.xls')):
        return False
    try:
        xl = pd.ExcelFile(file_path, engine='openpyxl')
        if 'Client History' not in xl.sheet_names:
            return False
        df = xl.parse('Client History', nrows=5, header=None)
        cell0 = str(df.iloc[0, 0] if not df.empty else '')
        return 'distriliq' in cell0.lower() or 'client history' in cell0.lower()
    except Exception:
        return False


def _parse_col_header(col_header: str) -> Optional[tuple[int, int]]:
    """
    Convert column header like 'Jul 25', 'Aug 25', ..., 'Jun 26'
    to (calendar_year, calendar_month).
    """
    s = str(col_header or '').strip().lower()
    m = re.match(r'([a-z]{3})\s+(\d{2})', s)
    if not m:
        return None
    month_abbr = m.group(1)
    year_2d = int(m.group(2))
    month_num = MONTH_TO_NUM.get(month_abbr)
    if not month_num:
        return None
    # Assume 20xx
    cal_year = 2000 + year_2d
    return cal_year, month_num


def _looks_like_product(name: str) -> bool:
    """Heuristic: a row is a product row (not a client row) if it looks like a wine name."""
    n = name.strip().lower()
    # Product rows tend to start with a known wine prefix
    product_signals = [
        'rose-mary', 'rosemary', 'rose mary',
        'pecan stream', 'pecan',
        'cabernet', 'cab sauv', 'cab ',
        'kevin arnold', 'k. arnold',
        'chardonnay', 'chenin',
        'jem ', 'jemima',
        'antigo', 'elgin', 'grenache',
        'heatherleigh', 'waterford',
        'mcc', 'cap class',
    ]
    return any(n.startswith(p) or p in n for p in product_signals)


def iter_rows(file_path: str) -> Iterator[dict]:
    """
    Yield one row per (client, product, month) cell with qty > 0.
    """
    xl = pd.ExcelFile(file_path, engine='openpyxl')
    if 'Client History' not in xl.sheet_names:
        return

    # Parse with no header — we'll extract headers from row 3
    df = xl.parse('Client History', header=None)
    if df.empty:
        return

    # Find the header row (row index 3 in the sample)
    header_row_idx = None
    for i, row in df.iterrows():
        val = str(row.iloc[0] if len(row) > 0 else '').strip().lower()
        if 'client' in val and 'wine' in val:
            header_row_idx = i
            break
    if header_row_idx is None:
        return

    # Extract column headers and parse month/year
    header_row = df.iloc[header_row_idx]
    month_cols: list[tuple[int, int, int]] = []  # (col_idx, cal_year, cal_month)
    for col_idx, val in enumerate(header_row):
        ym = _parse_col_header(str(val))
        if ym:
            month_cols.append((col_idx, ym[0], ym[1]))

    if not month_cols:
        return

    # Iterate data rows (below header)
    current_client: Optional[str] = None
    for row_idx, row in df.iloc[header_row_idx + 1:].iterrows():
        cell0 = str(row.iloc[0] if len(row) > 0 else '').strip()
        if not cell0 or cell0.lower() in ('nan', 'total', 'grand total'):
            continue

        if _looks_like_product(cell0):
            # Product row — yield sell-through for each month with qty > 0
            if not current_client:
                continue
            product_desc = cell0

            for col_idx, cal_year, cal_month in month_cols:
                try:
                    cell_val = row.iloc[col_idx] if col_idx < len(row) else None
                    qty = 0.0 if pd.isna(cell_val) else float(cell_val or 0)
                except (ValueError, TypeError):
                    qty = 0.0
                if qty <= 0:
                    continue

                raw_data = {
                    'drname':     current_client,
                    'debtor':     None,      # Distriliq report has no debtor code
                    'salgrpname': product_desc,
                    'stockitem':  '',
                    'bottles':    qty,
                    'net':        0,
                    'cal_year':   cal_year,
                    'cal_month':  cal_month,
                    'drgrpname':  'Distriliq Sell-Through',
                    'sareaname':  'Local - Western Cape',
                    'region':     'CPT',
                }

                yield {
                    # ── Standardized connector contract ─────────────────────
                    'client_name':      current_client,   # Distriliq client name → matcher
                    'client_code':      None,             # no debtor code in Distriliq report
                    'product_desc':     product_desc,     # wine name → product matcher
                    # ── Distriliq-specific fields ────────────────────────────
                    'drname':           current_client,
                    'debtor':           None,
                    'salgrp':           product_desc,
                    'stockitem':        '',
                    'bottles':          qty,
                    'net_val':          0.0,
                    'calendar_year':    cal_year,
                    'calendar_month':   cal_month,
                    'transaction_type': 'DISTRIBUTOR_SELL_THROUGH',
                    'distributor_id':   None,  # resolved by pipeline
                    'unit':             'BOTTLES',
                    'case_size':        None,
                    'stockunit':        None,
                    'region':           'CPT',
                    'raw_data':         raw_data,
                    'exclude':          False,
                    'exclusion_reason': None,
                }
        else:
            # Client row
            current_client = cell0
