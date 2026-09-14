"""
NGF SalesOut Connector.

Parses the NGF SalesOut Excel files (H1 FY26, Q3 FY26, Q4 FY26).
These contain transaction-level sell-through data from NGF to CPT clients.

File format:
- Worksheet: '4REP'
- Skip first 5 rows
- Columns: item, description, inv_no, debtor, debtor_name, date(YYMMDD), qty, extra
- Date format: YYMMDD (e.g. 250701 = 1 July 2025)
- Filter: debtor not starting with '-', qty > 0
- CAS001 = internal cash sale → EXCLUDE
- Transaction type: DISTRIBUTOR_SELL_THROUGH
- Distributor: NGF
- Region: CPT (all clients in these files are CPT/WC territory)

Source code: NGF_SALESOUT
"""
import hashlib
import pandas as pd
from datetime import datetime, date
from pathlib import Path
from typing import Iterator

# Debtor codes to explicitly exclude (not canonical clients)
EXCLUDE_DEBTOR_CODES = {'CAS001'}

# Source code for this connector
SOURCE_CODE = 'NGF_SALESOUT'
DISTRIBUTOR_CODE = 'NGF'
REGION = 'CPT'
TRANSACTION_TYPE = 'DISTRIBUTOR_SELL_THROUGH'


def file_hash(file_path: str) -> str:
    """SHA-256 hash of file contents for deduplication."""
    sha = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            sha.update(chunk)
    return sha.hexdigest()


def parse_date(date_raw) -> tuple[date | None, int | None, int | None]:
    """
    Parse YYMMDD date integer to (date, calendar_year, calendar_month).
    Returns (None, None, None) if unparseable.
    """
    try:
        d_str = str(int(date_raw)).zfill(6)
        yy, mm, dd = int(d_str[:2]), int(d_str[2:4]), int(d_str[4:6])
        year = 2000 + yy
        return date(year, mm, dd), year, mm
    except (ValueError, TypeError):
        return None, None, None


def identify_file(file_path: str) -> dict:
    """
    Identify an NGF SalesOut file and return metadata.
    Reads the 4REP worksheet to determine date range.
    """
    path = Path(file_path)
    try:
        xl = pd.ExcelFile(file_path)
        if '4REP' not in xl.sheet_names:
            return {"is_ngf_salesout": False, "reason": "No 4REP worksheet"}

        df = xl.parse('4REP', header=None, skiprows=5)
        if len(df.columns) < 7:
            return {"is_ngf_salesout": False, "reason": "Too few columns"}

        df.columns = ['item', 'description', 'inv_no', 'debtor',
                      'debtor_name', 'date_raw', 'qty', 'extra'][:len(df.columns)]

        # Parse dates to find period range
        df = df[df['debtor'].notna() & ~df['debtor'].astype(str).str.startswith('-')]
        df['qty'] = pd.to_numeric(df['qty'], errors='coerce').fillna(0)
        df = df[df['qty'] > 0]
        df['date_raw_int'] = pd.to_numeric(df['date_raw'], errors='coerce')
        df = df[df['date_raw_int'].notna()]

        dates = []
        for _, row in df.iterrows():
            d, y, m = parse_date(row['date_raw_int'])
            if d:
                dates.append(d)

        if not dates:
            return {"is_ngf_salesout": False, "reason": "No parseable dates"}

        period_from = min(dates)
        period_to = max(dates)
        unique_debtors = df['debtor'].nunique()
        total_rows = len(df)

        return {
            "is_ngf_salesout": True,
            "period_from": period_from.isoformat(),
            "period_to": period_to.isoformat(),
            "row_count": total_rows,
            "unique_debtors": unique_debtors,
            "confidence": 95,
        }
    except Exception as e:
        return {"is_ngf_salesout": False, "reason": str(e)}


def parse_rows(file_path: str) -> Iterator[dict]:
    """
    Parse all data rows from an NGF SalesOut file.
    Yields one dict per valid row.
    """
    xl = pd.ExcelFile(file_path)
    df = xl.parse('4REP', header=None, skiprows=5)
    df.columns = ['item', 'description', 'inv_no', 'debtor',
                  'debtor_name', 'date_raw', 'qty', 'extra'][:len(df.columns)]

    # Filter separator rows
    df = df[df['debtor'].notna() & ~df['debtor'].astype(str).str.startswith('-')]
    df['qty'] = pd.to_numeric(df['qty'], errors='coerce').fillna(0)
    df = df[df['qty'] > 0]
    df['date_raw_int'] = pd.to_numeric(df['date_raw'], errors='coerce')

    for idx, row in df.iterrows():
        debtor = str(row.get('debtor', '')).strip()
        debtor_name = str(row.get('debtor_name', '')).strip()
        description = str(row.get('description', '')).strip()
        qty = float(row.get('qty', 0))
        date_raw = row.get('date_raw_int')

        if not debtor or debtor == 'nan' or qty == 0:
            continue

        tx_date, cal_year, cal_month = parse_date(date_raw)

        # Build raw_data (immutable record of original row)
        raw_data = {
            "debtor": debtor,
            "debtor_name": debtor_name,
            "description": description,
            "date_raw": str(date_raw),
            "qty": qty,
            "inv_no": str(row.get('inv_no', '')),
            "item": str(row.get('item', '')),
        }

        yield {
            # ── Standardized connector contract ───────────────────────────
            "client_name":  debtor_name,  # NGF debtor name for matcher
            "client_code":  debtor,       # NGF debtor code for alias lookup
            "product_desc": description,  # product description for matcher
            # ── NGF-specific fields ───────────────────────────────────────
            "row_number": idx,
            "debtor": debtor,
            "debtor_name": debtor_name,
            "description": description,
            "qty": qty,
            "unit": "BOTTLES",  # NGF SalesOut always in bottles
            "case_size": None,  # Never in cases
            "tx_date": tx_date.isoformat() if tx_date else None,
            "calendar_year": cal_year,
            "calendar_month": cal_month,
            "source_code": SOURCE_CODE,
            "transaction_type": TRANSACTION_TYPE,
            "distributor_code": DISTRIBUTOR_CODE,
            "region": REGION,
            "raw_data": raw_data,
            # Exclusion flag for known internal codes
            "exclude": debtor.upper() in EXCLUDE_DEBTOR_CODES,
            "exclusion_reason": "INTERNAL_CASH_SALE_CODE" if debtor.upper() in EXCLUDE_DEBTOR_CODES else None,
        }
