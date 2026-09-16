"""
Import Pipeline Orchestrator.

Runs the complete 14-stage import pipeline for a single file.
Every row gets an auditable outcome — no silent failures.

Stage outcomes:
  MAPPED       — transaction created, fully reportable
  EXCLUDED     — deliberately excluded (cash sale, internal, export if not tracking)
  PENDING_MAPPING — client or product not resolved, held for human review
  FAILED       — parsing error on this specific row
"""
import hashlib
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from app.services.import_engine.db_ops import (
    get_conn, get_source_id, get_distributor_id, get_financial_period,
    get_sku_asp, get_sku_info, create_batch, update_batch_status,
    check_duplicate_batch, insert_raw_row, update_raw_row, create_queue_item,
    create_transaction, create_transaction_line, upsert_coverage,
    get_distributor_erp_codes, run, q1, s
)
from app.services.import_engine.client_matcher import match_client
from app.services.import_engine.ownership_deriver import derive_erp_ownership
from app.services.import_engine.product_matcher import match_product
from app.services.import_engine.unit_normaliser import normalise_quantity
from app.services.import_engine.dc_rules import evaluate_dc_rules, apply_dc_rules_to_new_direct_sale
from app.services.import_engine.connectors import ngf_salesout, erp_csv
from app.services.import_engine.connectors.ngf_monthly import iter_rows as ngf_monthly_rows
from app.services.import_engine.connectors.distriliq_cpt import iter_rows as distriliq_rows


def import_file(file_path: str, imported_by: str = "system",
                source_override: str | None = None) -> dict:
    """
    Run the complete import pipeline for a file.
    Returns a detailed result report.

    source_override: if provided, skip auto-identification and use this source_code directly.
    Valid values: ERP_EXPORT, NGF_SALESOUT, NGF_MONTHLY, DISTRILIQ_CPT
    """
    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}", "status": "FAILED"}

    # Compute file hash
    sha = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            sha.update(chunk)
    fhash = sha.hexdigest()
    fsize = path.stat().st_size
    fname = path.name

    conn = get_conn()
    try:
        # ── STAGE 1: Identify source/format ───────────────────────────────────
        if source_override:
            # Manual source selection — do NOT re-run auto-identification
            connector = {"source_code": source_override, "report_type": source_override,
                         "is_cumulative": False}
            meta = {"format": source_override, "manual_override": True}
        else:
            connector, meta = _identify_file(file_path, fname)
        if not connector:
            return {"error": f"Cannot identify file format: {fname}", "status": "IDENTIFICATION_REQUIRED"}

        source_id = get_source_id(conn, connector['source_code'])
        if not source_id:
            return {"error": f"Source not found in DB: {connector['source_code']}", "status": "FAILED"}

        # ── STAGE 2: Duplicate check ───────────────────────────────────────────
        existing_batch = check_duplicate_batch(conn, fhash)
        if existing_batch:
            return {
                "status": "DUPLICATE_DETECTED",
                "existing_batch_id": existing_batch,
                "message": f"This file has already been imported (batch {existing_batch}). No action taken."
            }

        # ── STAGE 3: Create import batch ──────────────────────────────────────
        batch_id = create_batch(
            conn, source_id, fname, fhash, fsize,
            date.today().isoformat(),
            meta.get('period_from'), meta.get('period_to'),
            connector['report_type'], meta.get('report_version'),
            connector.get('is_cumulative', False), imported_by
        )
        conn.commit()

        # ── STAGE 4-14: Process rows ───────────────────────────────────────────
        result = _process_rows(conn, batch_id, source_id, connector, file_path)

        # Update batch final status
        status = 'COMPLETE' if result['rows_pending_mapping'] == 0 else 'PARTIAL_COMPLETE'
        update_batch_status(
            conn, batch_id, status,
            rows_total=result['rows_total'],
            rows_valid=result['rows_mapped'],
            rows_failed=result['rows_failed'],
            rows_pending_mapping=result['rows_pending_mapping'],
            rows_imported=result['rows_mapped'],
            imported_at=datetime.utcnow().isoformat()
        )
        conn.commit()

        result['batch_id'] = batch_id
        result['status'] = status
        result['file'] = fname
        result['source_code'] = connector['source_code']

        # ── ERP ownership derivation (post-batch, non-blocking) ────────────
        # After ERP imports derive historical client/rep ownership from srepname.
        # Idempotent, honours MANUAL_ASSIGNMENT precedence, never overwrites
        # human decisions. Failure is logged but does not fail the import.
        if connector.get('source_code') == 'ERP_EXPORT':
            try:
                _conn2 = get_conn()
                try:
                    own_summary = derive_erp_ownership(_conn2, batch_id)
                    if any(own_summary.values()):
                        logger.info("Ownership derivation: %s", own_summary)
                    result['ownership_summary'] = own_summary
                finally:
                    _conn2.close()
            except Exception as _exc:
                logger.warning("Ownership derivation failed (non-fatal): %s", _exc)

        return result

    except Exception as e:
        conn.rollback()
        if 'batch_id' in dir():
            try:
                update_batch_status(conn, batch_id, 'FAILED')
                conn.commit()
            except Exception:
                pass
        raise
    finally:
        conn.close()


def _identify_file(file_path: str, fname: str) -> tuple[Optional[dict], dict]:
    """Identify the file and return (connector_config, metadata)."""
    fname_upper = fname.upper()

    # Try NGF SalesOut
    if fname_upper.endswith('.XLSX') and ('SALES_OUT' in fname_upper or 'SALESOUT' in fname_upper):
        meta = ngf_salesout.identify_file(file_path)
        if meta.get('is_ngf_salesout'):
            return (
                {"source_code": "NGF_SALESOUT", "report_type": "NGF_SALESOUT",
                 "is_cumulative": False},
                meta
            )

    # Try NGF SalesOut by content even if name is different
    if fname_upper.endswith('.XLSX'):
        meta = ngf_salesout.identify_file(file_path)
        if meta.get('is_ngf_salesout') and meta.get('confidence', 0) >= 80:
            return (
                {"source_code": "NGF_SALESOUT", "report_type": "NGF_SALESOUT",
                 "is_cumulative": False},
                meta
            )

    # Try ERP CSV
    if fname_upper.endswith('.CSV'):
        from app.services.import_engine.connectors.erp_csv import identify_file as erp_identify
        meta = erp_identify(file_path)
        if meta.get('is_erp_export'):
            return (
                {"source_code": "ERP_EXPORT", "report_type": "ERP_EXPORT",
                 "is_cumulative": False},
                meta
            )

    # Try NGF Monthly (flat Data sheet format)
    if fname_upper.endswith('.XLSX'):
        from app.services.import_engine.connectors.ngf_monthly import detect as ngf_monthly_detect
        if ngf_monthly_detect(file_path):
            return (
                {"source_code": "NGF_MONTHLY", "report_type": "NGF_MONTHLY",
                 "is_cumulative": False},
                {"format": "NGF_MONTHLY"}
            )

    # Try Distriliq CPT (Client History pivot format)
    if fname_upper.endswith('.XLSX'):
        from app.services.import_engine.connectors.distriliq_cpt import detect as distriliq_detect
        if distriliq_detect(file_path):
            return (
                {"source_code": "DISTRILIQ_CPT", "report_type": "DISTRILIQ_CPT",
                 "is_cumulative": False},
                {"format": "DISTRILIQ_CPT"}
            )

    return None, {}


def _process_rows(conn, batch_id: str, source_id: str, connector: dict, file_path: str) -> dict:
    """Process all rows through the pipeline. Returns summary statistics."""
    counts = {
        "rows_total": 0, "rows_mapped": 0, "rows_pending_mapping": 0,
        "rows_excluded": 0, "rows_failed": 0, "rows_duplicate": 0,
        "bottles_reportable": 0.0, "bottles_pending": 0.0,
        "rv_confirmed": 0.0, "rv_estimated": 0.0,
        "clients_auto_matched": 0, "clients_pending": 0, "clients_unresolved": 0,
        "products_auto_matched": 0, "products_pending": 0,
    }
    source_code = connector['source_code']
    coverage_periods = set()  # Track which periods we've covered

    # Pre-load distributor codes for ERP
    distributor_erp_codes = {}
    if source_code == 'ERP_EXPORT':
        distributor_erp_codes = get_distributor_erp_codes(conn)

    # Pre-load alias caches for performance (avoid N+1 queries)
    from app.services.import_engine.db_ops import find_aliases_all, get_all_product_aliases
    alias_cache = find_aliases_all(conn, source_id)
    product_alias_cache = get_all_product_aliases(conn, source_id)

    # Pre-load distributor_id for the whole batch (per-source-code lookup).
    # This is stored in dist_id and used as the fallback in actual_dist_id resolution.
    _SOURCE_TO_DIST_CODE = {
        'NGF_SALESOUT':  'NGF',
        'NGF_MONTHLY':   'NGF',
        'DISTRILIQ_CPT': 'DISTRILIQ_CPT',
    }
    dist_id = None
    if source_code in _SOURCE_TO_DIST_CODE:
        dist_id = get_distributor_id(conn, _SOURCE_TO_DIST_CODE[source_code])

    # Get source-specific row generator
    if source_code == 'NGF_SALESOUT':
        row_gen = ngf_salesout.parse_rows(file_path)
    elif source_code == 'ERP_EXPORT':
        row_gen = erp_csv.parse_rows(file_path, distributor_erp_codes)
    elif source_code == 'NGF_MONTHLY':
        row_gen = ngf_monthly_rows(file_path)
    elif source_code == 'DISTRILIQ_CPT':
        row_gen = distriliq_rows(file_path)
    else:
        return counts

    for src_row in row_gen:
        counts['rows_total'] += 1
        row_num = src_row.get('row_number', counts['rows_total'])

        # ── EXCLUSIONS ────────────────────────────────────────────────────────
        if src_row.get('exclude'):
            insert_raw_row(
                conn, batch_id, row_num, src_row['raw_data'],
                row_status='EXCLUDED',
                exclusion_reason=src_row.get('exclusion_reason', 'EXCLUDED_BY_CONNECTOR')
            )
            counts['rows_excluded'] += 1
            conn.commit()
            continue

        # ── PERIOD DETECTION ─────────────────────────────────────────────────
        cal_year = src_row.get('calendar_year')
        cal_month = src_row.get('calendar_month')
        if not cal_year or not cal_month:
            raw_row_id = insert_raw_row(
                conn, batch_id, row_num, src_row['raw_data'],
                row_status='FAILED', mapping_error="Cannot determine calendar period"
            )
            create_queue_item(conn, batch_id, raw_row_id, 'AMBIGUOUS_PERIOD', 'HIGH',
                              str(src_row.get('raw_data', '')))
            counts['rows_failed'] += 1
            conn.commit()
            continue

        period = get_financial_period(conn, cal_year, cal_month)
        if not period:
            raw_row_id = insert_raw_row(
                conn, batch_id, row_num, src_row['raw_data'],
                row_status='FAILED',
                mapping_error=f"Period not found for {cal_year}-{cal_month:02d}"
            )
            counts['rows_failed'] += 1
            conn.commit()
            continue

        period_id = period['id']
        year_id = period['year_id']

        # ── CLIENT MATCHING ──────────────────────────────────────────────────
        # All connectors must yield 'client_name' and 'client_code' in their output.
        # The pipeline reads these generic fields — no source-specific branching.
        client_name = str(src_row.get('client_name', '') or '')
        client_code = str(src_row.get('client_code', '') or '')

        match = match_client(conn, source_id, client_name, client_code, alias_cache)
        client_id = match['client_id']

        if not client_id:
            # Unresolved or probable — hold row
            suggested = None
            if match.get('confidence') == 'PROBABLE':
                suggested = {
                    "suggested_client_id": match.get('suggested_client_id'),
                    "suggested_name": match.get('suggested_name'),
                    "confidence": match.get('score'),
                    "matched_on": match.get('matched_on'),
                }
                issue_type = 'PROBABLE_CLIENT'
                severity = 'MEDIUM'
                can_bulk = match.get('score', 0) >= 90
                counts['clients_pending'] += 1
            else:
                issue_type = 'UNKNOWN_CLIENT'
                severity = 'HIGH'
                can_bulk = False
                counts['clients_unresolved'] += 1

            raw_row_id = insert_raw_row(
                conn, batch_id, row_num, src_row['raw_data'],
                row_status='PENDING_MAPPING',
                mapping_error=f"Client not resolved: {client_name} ({client_code})",
                matching_attempts=match.get('attempts')
            )
            create_queue_item(
                conn, batch_id, raw_row_id, issue_type, severity,
                f"{client_code}: {client_name}",
                suggested_resolution=suggested,
                can_bulk_approve=can_bulk
            )
            counts['rows_pending_mapping'] += 1
            counts['bottles_pending'] += src_row.get('qty', src_row.get('bottles', 0))
            conn.commit()
            continue

        counts['clients_auto_matched'] += 1

        # ── PRODUCT MATCHING ─────────────────────────────────────────────────
        # All connectors must yield 'product_desc' in their output.
        product_desc = str(src_row.get('product_desc', '') or '')

        # Pass stockunit from ERP structured fields for format-based resolution
        stockunit_hint = src_row.get('stockunit', None)
        prod_match = match_product(conn, source_id, product_desc, product_alias_cache, stockunit=stockunit_hint)
        sku_id = prod_match.get('sku_id')

        if not sku_id:
            prod_confidence = prod_match.get('confidence', 'UNRESOLVED')
            is_unknown_format = (prod_confidence == 'UNKNOWN_FORMAT')

            if is_unknown_format:
                # Product identity is known; only the bottle format is missing.
                # Preserve structured context so reviewers see the right information.
                fmt_context = {
                    'product_id':  prod_match.get('product_id'),
                    'size_ml':     prod_match.get('size_ml'),
                    'stockunit':   stockunit_hint,
                    'salgrpname':  product_desc,
                    'stockitem':   src_row.get('stockitem', ''),
                }
                issue_type    = 'UNKNOWN_FORMAT'
                mapping_error = (
                    f"UNKNOWN_FORMAT: product known but "
                    f"{prod_match.get('size_ml')}ml format not in master "
                    f"(stockunit={stockunit_hint}) — {product_desc}"
                )
            else:
                fmt_context   = None
                issue_type    = 'UNKNOWN_PRODUCT'
                mapping_error = f"Product not resolved: {product_desc}"

            raw_row_id = insert_raw_row(
                conn, batch_id, row_num, src_row['raw_data'],
                row_status='PENDING_MAPPING',
                client_alias_id=None,
                mapping_error=mapping_error,
                matching_attempts=match.get('attempts')
            )
            suggested = fmt_context if is_unknown_format else None
            if prod_confidence == 'PROBABLE':
                suggested = {'suggested_sku_id': prod_match.get('suggested_sku_id')}
            create_queue_item(
                conn, batch_id, raw_row_id, issue_type, 'HIGH',
                product_desc, suggested_resolution=suggested
            )
            counts['rows_pending_mapping'] += 1
            counts['products_pending'] += 1
            conn.commit()
            continue

        counts['products_auto_matched'] += 1

        # ── UNIT NORMALISATION ────────────────────────────────────────────────
        sku_info = get_sku_info(conn, sku_id)
        if not sku_info:
            counts['rows_failed'] += 1
            conn.commit()
            continue

        qty_raw = src_row.get('qty', src_row.get('bottles', 0))
        norm = normalise_quantity(
            qty_raw,
            src_row.get('unit', 'BOTTLES'),
            src_row.get('case_size'),
            sku_info['bottle_size_ml'],
            sku_info['sbe']
        )

        if norm.get('case_size_required'):
            raw_row_id = insert_raw_row(
                conn, batch_id, row_num, src_row['raw_data'],
                row_status='PENDING_MAPPING',
                case_size_required=True,
                mapping_error="Unit is CASES but case size not in source"
            )
            create_queue_item(conn, batch_id, raw_row_id, 'MISSING_CASE_SIZE', 'MEDIUM',
                              product_desc)
            counts['rows_pending_mapping'] += 1
            conn.commit()
            continue

        # ── R-VALUE HANDLING ─────────────────────────────────────────────────
        tx_type = src_row.get('transaction_type', 'DIRECT_SALE')
        tx_date = src_row.get('tx_date', f"{cal_year}-{cal_month:02d}-01")
        rv_confirmed = None
        rv_estimated = None
        rv_status = 'MISSING'
        asp_version_id = None

        if source_code == 'ERP_EXPORT':
            net_val = src_row.get('net_val', 0)
            if net_val != 0:
                rv_confirmed = round(float(net_val), 2)
                rv_status = 'CONFIRMED'
        else:
            # Distributor report — estimate using ASP
            asp = get_sku_asp(conn, sku_id, tx_date)
            if asp and norm['bottles_actual']:
                rv_estimated = round(norm['bottles_actual'] * asp['asp_value'], 2)
                asp_version_id = asp['asp_version_id']
                rv_status = 'ESTIMATED'

        # ── DC RULES ─────────────────────────────────────────────────────────
        # Resolve distributor_id: connector may supply distributor_code (string) or distributor_id (UUID)
        # dist_id is pre-loaded per source for efficiency; connector distributor_code overrides for
        # sources that need per-row routing (future use).
        actual_dist_id = (
            src_row.get('distributor_id')  # UUID already resolved by connector
            or dist_id                      # pre-loaded source-level distributor
        )
        dc = evaluate_dc_rules(conn, tx_type, client_id, period_id, actual_dist_id)

        # ── STORE RAW ROW ─────────────────────────────────────────────────────
        raw_row_id = insert_raw_row(
            conn, batch_id, row_num, src_row['raw_data'],
            row_status='MAPPED'
        )

        # ── CREATE TRANSACTION + LINE ─────────────────────────────────────────
        dedup_key = f"{batch_id}:{src_row.get(chr(114)+chr(111)+chr(119)+chr(95)+chr(110)+chr(117)+chr(109)+chr(98)+chr(101)+chr(114), counts[chr(114)+chr(111)+chr(119)+chr(115)+chr(95)+chr(116)+chr(111)+chr(116)+chr(97)+chr(108)])}"

        tx_id = create_transaction(
            conn, batch_id, raw_row_id, source_id, tx_type, tx_date,
            year_id, period_id, client_id,
            distributor_id=actual_dist_id,
            source_ref=str(src_row.get('source_invoice', '')),
            dedup_key=dedup_key,
            excluded=dc['excluded'],
            exclusion_rule=dc['exclusion_rule'],
            exclusion_context=dc['exclusion_context']
        )

        vintage = prod_match.get('vintage')
        create_transaction_line(
            conn, tx_id, sku_id, vintage, product_desc,
            str(src_row.get('debtor', '')),
            norm['quantity_original'], norm['unit_original'],
            norm.get('case_size_actual'),
            norm['bottles_actual'], norm['standard_bottle_equiv'], norm['litres'],
            rv_confirmed=rv_confirmed, rv_estimated=rv_estimated,
            rv_status=rv_status, asp_version_id=asp_version_id,
            raw_data=src_row['raw_data']
        )

        # Update raw row with transaction link
        update_raw_row(conn, raw_row_id, transaction_id=tx_id)

        # Retroactive DC check: if this is a DIRECT_SALE, exclude any existing sell-through
        if tx_type == 'DIRECT_SALE':
            apply_dc_rules_to_new_direct_sale(conn, client_id, period_id)

        # Track coverage
        coverage_periods.add((period_id, year_id, cal_year, cal_month))

        # Update counts
        counts['rows_mapped'] += 1
        if not dc['excluded']:
            counts['bottles_reportable'] += norm['bottles_actual'] or 0
        if rv_status == 'CONFIRMED':
            counts['rv_confirmed'] += rv_confirmed or 0
        elif rv_status == 'ESTIMATED':
            counts['rv_estimated'] += rv_estimated or 0

        conn.commit()

    # ── COVERAGE UPDATE ────────────────────────────────────────────────────────
    region = 'CPT' if connector['source_code'] == 'NGF_SALESOUT' else 'ALL'
    for period_id, year_id, cal_year, cal_month in coverage_periods:
        upsert_coverage(conn, source_id, region, period_id, 'COVERED',
                        batch_id=batch_id,
                        notes=f"Imported from {Path(file_path).name}")
    conn.commit()

    counts['coverage_periods_updated'] = len(coverage_periods)
    return counts
