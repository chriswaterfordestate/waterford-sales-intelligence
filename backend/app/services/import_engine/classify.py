"""
ERP transaction classification — shared between initial import and retroactive resolution.

This module contains the canonical logic for determining transaction type
from ERP raw data. It is the single source of truth for:
  - erp_csv.py (initial import)
  - retroactive_resolve.py (queue resolution after client is confirmed)

A row that resolves later must produce the same tx_type as the same row
would have produced if its client had been known during the original import.
That is the core invariant this module enforces.
"""
from __future__ import annotations
from typing import Optional
from .db_ops import get_distributor_erp_codes

# ── Constants (kept in sync with erp_csv.py) ─────────────────────────────────
# DTC groups — exclude from commercial/territory market views.
# These represent direct-to-consumer, private client, tasting room, and staff activity.
# 'CPRI' is the ERP debtor category used for private/DTC accounts (e.g. ZCAP, ZZXXX debtors).
# Transactions classified as DTC_SALE are excluded from commercial reporting by TX-TYPE.
DTC_GROUPS = {
    # Consumer/private
    'Wine Club', 'DTC', 'Private Clients', 'Society', 'Staff', 'Cellar Door',
    'Tasting Room (Cash Accounts)', 'Tasting Room - Tour Operators', 'Online Clients',
    'Legacy Members', 'Private Clients',
    # Internal Waterford accounts — excluded from commercial market view
    'Internal - Samples', 'Internal - Samples Lab Testing', 'Internal - Promotions',
    'Internal - Entertainment', 'Internal - Donations & Gifts', 'Internal - Harvest Festival',
    'Internal - Incentives', 'Internal - Stock Accounts', 'Internal - Competitions',
    'Internal - Staff Allocations', 'Internal - Wine Shows & Exhibi',
    'Staff Accounts',
    # Non-wine / non-commercial transfers
    'Non Wine Sales Accounts', 'Bulk Wine & Grape Sales', 'Transfer - Non-Bonded Location',
}

# ERP drgrpname prefixes that indicate private/DTC accounts.
# These supplement DTC_GROUPS for classification when exact group name doesn't match.
DTC_DRGRP_PREFIXES = ('Private', 'Wine Club', 'Cellar', 'Tasting Room', 'Online', 'Staff', 'Legacy', 'Internal')

# ERP FIELD NOTE — kcclass:
# kcclass='Private' in EzyWine CANNOT be used for DTC/CPRI classification.
# It applies to commercial chain stores (Woolworths, Shoprite, PnP, Makro),
# distributors, and many other commercial accounts, not only private/DTC buyers.
#
# DTC classification uses drgrpname membership in DTC_GROUPS only.
# Cellar door / C/DOOR rows are excluded at the connector level via
# SALE_SOURCES={'INVOICE','M/ORDER'} before classification runs.
#
# kcclass IS preserved in raw_data for provenance / audit — do not remove it.

# ERP drgrpname values that indicate export transactions regardless of debtor name
EXPORT_DRGROUPS = {
    'Export - EUR', 'Export - USD', 'Export - ZAR', 'Export - GBP',
    'Private Client - Exports',
}

EXPORT_DEBTORS = {
    'Unique Holland Wijnimport B.V.', 'RAKQ Limited', 'SA Wineimport ApS',
    'CAPE ARDOR LLC', 'Namibia Wine Merchants Pty Ltd', 'Eastern Trading',
    'LSG Skychefs SA (Pty)Ltd KENYA', 'MBM Resource Trading Int Ltd',
    'Under the Influence (Pty) Ltd',  # Note: BONDED Under the Influence (UNDE0002) is DOMESTIC — NOT export
    'WoW Beverages Ltd', 'CAPREO GmbH', 'Cassidy Wines Ltd',
    'Indian Ocean Export Co Pty Ltd'
}


def classify_erp_row(
    raw_data: dict,
    distributor_erp_codes: dict,
) -> tuple[str, Optional[str]]:
    """
    Determine (transaction_type, distributor_id) for one ERP raw row.

    Args:
        raw_data:               The JSONB raw_data dict stored in import_raw_rows.
        distributor_erp_codes:  {DEBTOR_CODE_UPPER: distributor_id_str} from DB.

    Returns:
        (tx_type, distributor_id | None)

    Priority:
        1. Export (drname in EXPORT_DEBTORS or sareaname contains 'export')
        2. DTC    (drgrpname in DTC_GROUPS)
        3. Distributor sell-in (debtor code maps to a known distributor)
        4. Direct sale (default)
    """
    drname = str(raw_data.get('drname', '') or '').strip()
    debtor = str(raw_data.get('debtor', '') or '').strip()
    sarea  = str(raw_data.get('sareaname', '') or '').strip()
    drgrp  = str(raw_data.get('drgrpname', '') or '').strip()

    debtor_upper  = debtor.upper()
    distributor_id = distributor_erp_codes.get(debtor_upper)

    if drname in EXPORT_DEBTORS or 'export' in sarea.lower() or drgrp in EXPORT_DRGROUPS:
        return 'EXPORT_SALE', None

    # DTC_SALE: Wine Club, Cellar Door, Private Clients, Tasting Room, Staff, Legacy Members
    # Use drgrpname only — kcclass='Private' in EzyWine applies broadly to commercial accounts
    # (chain stores, liquor stores) and is NOT a reliable DTC signal. Cellar door/C/DOOR
    # rows are already excluded at the connector level by SALE_SOURCES filtering.
    if drgrp in DTC_GROUPS or any(drgrp.startswith(p) for p in DTC_DRGRP_PREFIXES):
        return 'DTC_SALE', None

    if distributor_id:
        return 'DISTRIBUTOR_SELL_IN', distributor_id
    return 'DIRECT_SALE', None


def classify_erp_row_from_db(conn, raw_data: dict) -> tuple[str, Optional[str]]:
    """
    Convenience: load distributor codes from DB then classify.
    Use this in retroactive resolution where the distributor table may have changed.
    """
    dist_codes = get_distributor_erp_codes(conn)
    return classify_erp_row(raw_data, dist_codes)
