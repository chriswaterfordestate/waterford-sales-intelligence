"""
Retroactive row resolution service.

Core invariant:
    Importing a row with its alias ALREADY KNOWN must produce the same
    transaction/line/DC state as importing it UNKNOWN_CLIENT first and
    resolving the alias afterward.

This module is the single point of retroactive resolution.
It shares the same classification, DC rules, and transaction creation
logic as the initial import pipeline. There is no separate mini-pipeline.
"""
from __future__ import annotations
import logging
from typing import Optional
from psycopg2.extras import RealDictCursor

from .classify import classify_erp_row_from_db
from .dc_rules import evaluate_dc_rules
from .product_matcher import match_product
from .unit_normaliser import normalise_quantity
from .db_ops import (
    s, q, run, get_sku_info, get_sku_asp,
    create_transaction, create_transaction_line,
    get_distributor_erp_codes,
)
from .connectors.erp_csv import finmth_to_calendar

logger = logging.getLogger(__name__)


def _get_pending_raw_row(conn, raw_row_id: str) -> Optional[dict]:
    """Fetch a PENDING_MAPPING raw row. Returns None if already mapped."""
    rows = q(conn, """
        SELECT irr.id::text, irr.raw_data, irr.row_status,
               b.id::text as batch_id, b.source_id::text
        FROM import_raw_rows irr
        JOIN import_batches b ON b.id = irr.batch_id
        WHERE irr.id = %s::uuid
    """, (raw_row_id,))
    return dict(zip(['id','raw_data','row_status','batch_id','source_id'], rows[0])) if rows else None


def resolve_raw_row(
    conn,
    raw_row_id: str,
    confirmed_client_id: str,
) -> dict:
    """
    Resolve one PENDING_MAPPING row retroactively.

    Steps (mirrors pipeline.py exactly):
    1. Read raw row + source context
    2. Classify tx_type via classify_erp_row_from_db (same as initial import)
    3. Re-attempt product matching (product may have been resolved since import)
    4. Apply DC rules (DC-001 through DC-006) — same logic as pipeline
    5. Normalise quantity
    6. Create sales_transaction + sales_transaction_line
    7. Mark raw row as MAPPED

    Returns status dict with outcome.
    """
    row_data = _get_pending_raw_row(conn, raw_row_id)
    if not row_data:
        return {'status': 'skipped', 'reason': 'row not found'}
    if row_data['row_status'] == 'MAPPED':
        return {'status': 'skipped', 'reason': 'already mapped'}

    raw          = row_data['raw_data']
    batch_id     = row_data['batch_id']
    source_id    = row_data['source_id']

    # ── Step 1: Reconstruct source context from raw_data ─────────────────────
    finmth  = int(raw.get('finmth', 1)  or 1)
    finyear = int(raw.get('finyear', 2026) or 2026)
    bottles = float(raw.get('bottles', 0) or 0)
    net_val = float(raw.get('net', 0) or 0)

    cal_year, cal_month = finmth_to_calendar(finmth, finyear)
    tx_date = f"{cal_year}-{cal_month:02d}-15"

    # ── Step 2: Transaction type via shared classification ────────────────────
    # This is THE canonical classification — same function as initial import.
    tx_type, distributor_id = classify_erp_row_from_db(conn, raw)

    # ── Step 3: Financial period lookup ──────────────────────────────────────
    period_id = s(conn, """
        SELECT fp.id::text FROM financial_periods fp
        JOIN financial_years fy ON fy.id = fp.financial_year_id
        WHERE fp.calendar_year = %s AND fp.calendar_month = %s
    """, (cal_year, cal_month))
    year_id = s(conn, """
        SELECT fp.financial_year_id::text FROM financial_periods fp
        WHERE fp.calendar_year = %s AND fp.calendar_month = %s LIMIT 1
    """, (cal_year, cal_month))
    if not period_id:
        return {'status': 'skipped', 'reason': f'no period for {cal_year}-{cal_month:02d}'}

    # ── Step 4: Product matching (same as pipeline) ───────────────────────────
    salgrpname = str(raw.get('salgrpname', '') or '')
    stockunit  = str(raw.get('stockunit',  '') or '') or None
    prod = match_product(conn, source_id, salgrpname, stockunit=stockunit)
    sku_id = prod.get('sku_id')
    if not sku_id:
        return {
            'status': 'skipped',
            'reason': f'product still unresolved ({prod.get("confidence")}): {salgrpname}',
            'product_confidence': prod.get('confidence'),
        }

    # ── Step 5: DC rules — delegate entirely to evaluate_dc_rules() ─────────
    # evaluate_dc_rules() is the canonical exclusion logic used by both initial
    # import and retroactive resolution. Do NOT maintain a separate list here.
    # TX-TYPE covers: DISTRIBUTOR_SELL_IN, EXPORT_SALE, DTC_SALE (all out of scope
    # for commercial market view). DC-002 covers: sell-through dedup.
    dc = evaluate_dc_rules(conn, tx_type, confirmed_client_id, period_id, distributor_id)
    tx_excluded       = dc.get('excluded', False)
    exclusion_rule    = dc.get('exclusion_rule')
    exclusion_context = dc.get('exclusion_context')

    # ── Step 6: For DIRECT_SALE entering the market view, apply retroactive DC-002 ──
    # When a DIRECT_SALE arrives after distributor sell-through rows, exclude them all.
    if tx_type == 'DIRECT_SALE' and not tx_excluded:
        from .dc_rules import apply_dc_rules_to_new_direct_sale
        apply_dc_rules_to_new_direct_sale(conn, confirmed_client_id, period_id)

    # ── Step 7: Quantity normalisation ────────────────────────────────────────
    sku_info = get_sku_info(conn, sku_id)
    if not sku_info:
        return {'status': 'failed', 'reason': f'SKU info not found for {sku_id}'}

    sbe           = float(sku_info['sbe'])
    size_ml       = int(sku_info['bottle_size_ml'])
    norm = normalise_quantity(bottles, 'BOTTLES', None, size_ml, sbe)
    bottles_actual = float(norm.get('bottles_actual') or bottles)
    std_btl_equiv  = round(bottles_actual * sbe, 3)
    litres         = round(bottles_actual * size_ml / 1000.0, 3)

    # ── Step 8: R-value status ────────────────────────────────────────────────
    if net_val and net_val != 0:
        r_status      = 'CONFIRMED'
        rand_confirmed = net_val
        rand_estimated = None
        asp_version_id = None
    else:
        asp = get_sku_asp(conn, sku_id, tx_date)
        if asp:
            r_status       = 'ESTIMATED'
            rand_confirmed = None
            rand_estimated = round(bottles_actual * asp['asp_value'], 2)
            asp_version_id = asp['id']
        else:
            r_status       = 'MISSING'
            rand_confirmed = None
            rand_estimated = None
            asp_version_id = None

    # ── Step 9: Create transaction + line ────────────────────────────────────
    tx_id = create_transaction(
        conn, batch_id, raw_row_id, source_id,
        tx_type, tx_date, year_id, period_id, confirmed_client_id,
        distributor_id=distributor_id,
        excluded=tx_excluded,
        exclusion_rule=exclusion_rule,
        exclusion_context=exclusion_context,
    )
    create_transaction_line(
        conn, tx_id, sku_id, prod.get('vintage'),
        salgrpname, raw.get('stockitem', ''),
        bottles_actual, 'BOTTLES', None,
        bottles_actual, std_btl_equiv, litres,
        rv_confirmed=rand_confirmed,
        rv_estimated=rand_estimated,
        rv_status=r_status,
        asp_version_id=asp_version_id,
    )

    # ── Step 10: Mark raw row MAPPED ─────────────────────────────────────────
    run(conn, """
        UPDATE import_raw_rows
        SET row_status = 'MAPPED', transaction_id = %s::uuid
        WHERE id = %s::uuid
    """, (tx_id, raw_row_id))

    return {
        'status':         'resolved',
        'tx_id':          tx_id,
        'tx_type':        tx_type,
        'excluded':       tx_excluded,
        'exclusion_rule': exclusion_rule,
        'bottles':        bottles_actual,
        'r_status':       r_status,
    }


def resolve_debtor_alias(
    conn,
    debtor_code: str,
    canonical_client_id: str,
    source_code: str = 'ERP_EXPORT',
    confirmed_by: str = 'queue_resolution',
) -> dict:
    """
    Register a client alias for a debtor code and resolve all pending rows for it.
    
    Backend validates that every resolved row actually has this debtor_code in its
    raw_data — never trusts a frontend-supplied list of row IDs.
    
    Returns summary of resolution.
    """
    erp_source_id = s(conn, "SELECT id::text FROM data_sources WHERE source_code=%s", (source_code,))
    if not erp_source_id:
        return {'error': f'Data source {source_code} not found'}

    canonical = s(conn, "SELECT canonical_name FROM clients WHERE id=%s::uuid AND is_deleted=FALSE",
                  (canonical_client_id,))
    if not canonical:
        return {'error': f'Client {canonical_client_id} not found'}

    # Register alias if not already present
    existing = s(conn, """
        SELECT id FROM client_source_aliases
        WHERE client_id=%s::uuid AND source_id=%s::uuid AND source_code=%s
    """, (canonical_client_id, erp_source_id, debtor_code))

    if not existing:
        run(conn, """
            INSERT INTO client_source_aliases
                (client_id, source_id, source_name, source_code,
                 match_confidence, match_status, matched_by, confirmed_by, confirmed_at)
            VALUES (%s::uuid, %s::uuid,
                    (SELECT drname FROM (
                        SELECT irr.raw_data->>'drname' as drname
                        FROM import_raw_rows irr
                        JOIN import_batches b ON b.id=irr.batch_id
                        JOIN data_sources ds ON ds.id=b.source_id
                        WHERE ds.source_code=%s AND irr.raw_data->>'debtor'=%s
                        LIMIT 1
                    ) sub),
                    %s, 'CONFIRMED', 'ACTIVE', 'queue_resolution', %s, NOW())
        """, (canonical_client_id, erp_source_id, source_code, debtor_code,
              debtor_code, confirmed_by))
        alias_registered = True
    else:
        alias_registered = False

    # Find all PENDING_MAPPING rows for this debtor — BACKEND validates debtor_code from raw_data
    pending_rows = q(conn, """
        SELECT irr.id::text as raw_row_id
        FROM import_raw_rows irr
        JOIN import_batches b ON b.id = irr.batch_id
        JOIN data_sources ds ON ds.id = b.source_id
        WHERE ds.source_code = %s
          AND irr.row_status = 'PENDING_MAPPING'
          AND irr.raw_data->>'debtor' = %s
    """, (source_code, debtor_code))

    resolved = 0; skipped = 0; failed = 0; errors = []

    for (raw_row_id,) in pending_rows:
        try:
            result = resolve_raw_row(conn, raw_row_id, canonical_client_id)
            if result['status'] == 'resolved':
                resolved += 1
                # Mark queue item resolved
                run(conn, """
                    UPDATE import_queue_items
                    SET status='RESOLVED', resolved_by=%s, resolved_at=NOW(),
                        resolution_type='ACCEPTED',
                        resolution_notes=%s
                    WHERE import_raw_row_id=%s::uuid AND status='OPEN'
                """, (confirmed_by, f'Resolved to: {canonical}', raw_row_id))
            elif result['status'] == 'skipped':
                skipped += 1
            else:
                failed += 1
                errors.append(result.get('reason', 'unknown'))
        except Exception as e:
            failed += 1
            errors.append(str(e))
            logger.exception(f"Error resolving raw_row {raw_row_id}")

    return {
        'canonical_client':  canonical,
        'debtor_code':       debtor_code,
        'alias_registered':  alias_registered,
        'total_pending':     len(pending_rows),
        'resolved':          resolved,
        'skipped':           skipped,
        'failed':            failed,
        'errors':            errors[:5],
    }
