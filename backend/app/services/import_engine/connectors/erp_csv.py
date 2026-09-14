"""
ERP CSV Connector.

Parses EzyWine CSV exports from Waterford Estate.
Determines transaction type based on debtor identity.

Transaction type logic:
  debtor in DISTRIBUTOR_ERP_CODES → DISTRIBUTOR_SELL_IN
  drgrpname in DTC_GROUPS → DTC_SALE
  sareaname contains 'Export' or debtor in EXPORT_DEBTORS → EXPORT_SALE
  Otherwise → DIRECT_SALE

Source code: ERP_EXPORT
"""
import hashlib
import pandas as pd
from datetime import date
from typing import Iterator
from app.services.import_engine.classify import classify_erp_row, DTC_GROUPS, EXPORT_DEBTORS

SOURCE_CODE = 'ERP_EXPORT'

# DTC_GROUPS and EXPORT_DEBTORS imported from classify.py (single source of truth)

# Internal/promotional accounts to exclude (not commercial sales)
INTERNAL_ACCOUNTS = {
    'WF:Stock used in tasting room', 'WF:Staff allocations', 'WF:Wine Drive Costs',
    'WF:Promotions - Koliswa', 'WF:Promotions - Society', 'WF:Promotions - Sergio',
    'WF:Promotions- Gauteng Sandile', 'WF:Promotions - Trade JHB',
    'WF:Samples - Trade Jhb', 'Private client: Jhb Trade',
    'FNB A division of FirstRand', 'RMB - A Division of FirstRand',
    'Jonathan Ball Publishers', 'WIPSA'
}

# These ERP sources produce actual sales
SALE_SOURCES = {'INVOICE', 'M/ORDER'}


def file_hash(file_path: str) -> str:
    sha = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            sha.update(chunk)
    return sha.hexdigest()


def finmth_to_calendar(finmth: int, finyear: int) -> tuple[int, int]:
    """
    Convert ERP finmth (1=July, 12=June) to (calendar_year, calendar_month).
    FY2026: finmth 1 = July 2025, finmth 7 = January 2026, finmth 12 = June 2026
    """
    # finmth 1-6 = July-Dec of (finyear-1), finmth 7-12 = Jan-June of finyear
    if finmth <= 6:
        cal_year = finyear - 1
        cal_month = finmth + 6  # 1→7, 2→8, ..., 6→12
    else:
        cal_year = finyear
        cal_month = finmth - 6  # 7→1, 8→2, ..., 12→6
    return cal_year, cal_month


def identify_file(file_path: str) -> dict:
    """Identify an ERP CSV export file."""
    try:
        df = pd.read_csv(file_path, encoding='latin1', low_memory=False, nrows=5)
        cols = set(df.columns)
        required = {'drname', 'debtor', 'bottles', 'grossval', 'finmth', 'source'}
        if required.issubset(cols):
            full = pd.read_csv(file_path, encoding='latin1', low_memory=False)
            years = sorted(full['finyear'].dropna().unique().tolist()) if 'finyear' in full.columns else []
            return {
                "is_erp_export": True,
                "confidence": 95,
                "financial_years": [int(y) for y in years],
                "row_count": len(full),
            }
        return {"is_erp_export": False, "reason": f"Missing columns: {required - cols}"}
    except Exception as e:
        return {"is_erp_export": False, "reason": str(e)}


def parse_rows(file_path: str, distributor_erp_codes: dict) -> Iterator[dict]:
    """
    Parse all commercial rows from an ERP CSV.
    distributor_erp_codes: {DEBTOR_CODE: distributor_id} from DB
    """
    df = pd.read_csv(file_path, encoding='latin1', low_memory=False)

    # Only actual sale transactions
    df = df[df['source'].isin(SALE_SOURCES)]
    df['bottles'] = pd.to_numeric(df['bottles'], errors='coerce').fillna(0)
    df['grossval'] = pd.to_numeric(df['grossval'], errors='coerce').fillna(0)
    df['discval'] = pd.to_numeric(df.get('discval', 0), errors='coerce').fillna(0)
    df['Net'] = df['grossval'] - df['discval']

    for idx, row in df.iterrows():
        drname  = str(row.get('drname', '')).strip()
        debtor  = str(row.get('debtor', '')).strip()
        finmth  = int(row.get('finmth', 0)) if pd.notna(row.get('finmth')) else None
        finyear = int(row.get('finyear', 0)) if pd.notna(row.get('finyear')) else None
        bottles = float(row.get('bottles', 0))
        net_val = float(row.get('Net', 0))
        salgrp  = str(row.get('salgrpname', '')).strip()
        sarea   = str(row.get('sareaname', '')).strip()
        srep    = str(row.get('srepname', '')).strip()
        drgrp   = str(row.get('drgrpname', '')).strip()
        # kcclass is the ERP customer classification field:
        #   'Private'  = private individual / DTC / tasting room (CPRI category)
        #   'Export'   = export customer
        #   'Licenced' = licensed trade (bottle stores, restaurants)
        kcclass = str(row.get('kcclass', '') or '').strip()

        if not drname or drname == 'nan':
            continue
        if not finmth or not finyear:
            continue

        # Determine exclusion
        if drname in INTERNAL_ACCOUNTS:
            yield {
                "row_number": idx, "drname": drname, "debtor": debtor,
                "salgrp": salgrp, "bottles": bottles, "net_val": net_val,
                "finmth": finmth, "finyear": finyear,
                "exclude": True, "exclusion_reason": "INTERNAL_ACCOUNT",
                "raw_data": {k: str(v) for k, v in row.items()},
                "transaction_type": None, "distributor_id": None,
                "calendar_year": None, "calendar_month": None,
            }
            continue

        # Classify transaction type via shared classify module (also used by retroactive resolver)
        row_raw_data_for_classify = {
            'drname': drname, 'debtor': debtor,
            'sareaname': sarea, 'drgrpname': drgrp,
            'kcclass': kcclass,   # CPRI/Private classification field
        }
        tx_type, distributor_id = classify_erp_row(row_raw_data_for_classify, distributor_erp_codes)

        cal_year, cal_month = finmth_to_calendar(finmth, finyear)

        # Structured ERP fields for product resolution and provenance
        stockitem = str(row.get('stockitem', '') or '').strip()   # Vintage ERP SKU (e.g. L25WFRM1.5)
        stkdesc1  = str(row.get('stkdesc1',  '') or '').strip()   # Human-readable stock description
        stockunit = str(row.get('stockunit', '') or '').strip()   # Format unit: B750, B375, B500, B1.5, B3.0 etc.
        litres_row = float(row.get('litres', 0) or 0)             # Total litres for this row

        raw_data = {
            "drname": drname, "debtor": debtor, "finmth": finmth,
            "finyear": finyear, "bottles": bottles,
            "grossval": float(row.get('grossval', 0)),
            "discval":  float(row.get('discval',  0)), "net": net_val,
            "salgrpname": salgrp, "sareaname": sarea, "srepname": srep,
            "drgrpname": drgrp, "source": str(row.get('source', '')),
            "invnum":  str(row.get('invnum', '')),
            "kcclass": kcclass,  # ERP customer class — 'Private'=DTC/CPRI, 'Licenced'=trade
            # Structured product fields (critical for format resolution without regex)
            "stockitem":  stockitem,   # Vintage ERP SKU — provenance only, NOT for canonical matching
            "stkdesc1":   stkdesc1,    # Human-readable: "2024 PS Chenin Blanc 750mL"
            "stockunit":  stockunit,   # Format: B750, B375, B500, B1.5, B3.0, B5L, B18L
            "litres_row": litres_row,  # Total litres = bottles × size_ml/1000
        }

        yield {
            # ── Standardized connector contract (read by pipeline generically) ─
            "client_name":       drname,   # ERP debtor display name
            "client_code":       debtor,   # ERP debtor code for alias lookup
            "product_desc":      salgrp,   # salgrpname → product matcher
            # ── ERP-specific fields ──────────────────────────────────────────
            "row_number": idx,
            "drname": drname,
            "debtor": debtor,
            "salgrp": salgrp,
            "bottles": bottles,
            "net_val": net_val,
            "finmth": finmth,
            "finyear": finyear,
            "calendar_year": cal_year,
            "calendar_month": cal_month,
            "transaction_type": tx_type,
            "distributor_id": distributor_id,
            "source_invoice": str(row.get('invnum', '')),
            "srepname": srep,
            "raw_data": raw_data,
            "exclude": False,
            "exclusion_reason": None,
            "unit": "BOTTLES",
            "case_size": None,
            "stockunit":  stockunit,
            "stockitem":  stockitem,
            "litres_row": litres_row,
        }
