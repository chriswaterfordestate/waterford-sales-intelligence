"""
Database operations for the import pipeline.
Uses synchronous psycopg2 for pipeline operations (simpler than asyncpg for batch inserts).
All operations are transactional — a batch either fully completes or fully rolls back.
"""
import psycopg2
import psycopg2.extras
import os
import json
from typing import Optional

# Module-level DSN: set once at import time from settings.
# The conftest per-test DATABASE_URL_SYNC fixture does NOT affect this value.
# Tests that need a different DB must pass their own connection explicitly.
from app.config import settings as _cfg_settings
_DSN = _cfg_settings.database_url_sync


def get_conn():
    conn = psycopg2.connect(_DSN)
    psycopg2.extras.register_uuid()
    return conn


def q(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def q1(conn, sql, params=None):
    rows = q(conn, sql, params)
    return rows[0] if rows else None


def s(conn, sql, params=None):
    row = q1(conn, sql, params)
    return row[0] if row else None


def run(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params)


def run_many(conn, sql, rows):
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, rows, page_size=500)


# ── Lookup helpers ─────────────────────────────────────────────────────────────

def get_source_id(conn, source_code: str) -> Optional[str]:
    return s(conn, "SELECT id::text FROM data_sources WHERE source_code=%s", (source_code,))


def get_financial_period(conn, calendar_year: int, calendar_month: int) -> Optional[dict]:
    row = q1(conn, """
        SELECT id::text, financial_year_id::text, period_number, period_name
        FROM financial_periods
        WHERE calendar_year=%s AND calendar_month=%s
    """, (calendar_year, calendar_month))
    if row:
        return {"id": row[0], "year_id": row[1], "number": row[2], "name": row[3]}
    return None


def get_distributor_id(conn, dist_code: str) -> Optional[str]:
    return s(conn, "SELECT id::text FROM distributors WHERE distributor_code=%s", (dist_code,))


def get_sku_asp(conn, sku_id: str, transaction_date: str) -> Optional[dict]:
    """Get active ASP for a SKU on a given date."""
    row = q1(conn, """
        SELECT id::text, asp_value
        FROM asp_versions
        WHERE product_sku_id=%s::uuid
          AND effective_from <= %s::date
          AND (effective_to IS NULL OR effective_to >= %s::date)
          AND is_approved = TRUE
        ORDER BY effective_from DESC LIMIT 1
    """, (sku_id, transaction_date, transaction_date))
    if row:
        return {"asp_version_id": row[0], "asp_value": float(row[1])}
    return None


def get_sku_info(conn, sku_id: str) -> Optional[dict]:
    """Get SKU bottle conversion factors."""
    row = q1(conn, """
        SELECT bottle_size_ml, standard_bottle_equivalent
        FROM product_skus WHERE id=%s::uuid
    """, (sku_id,))
    if row:
        return {"bottle_size_ml": row[0], "sbe": float(row[1])}
    return None


# ── Client matching queries ────────────────────────────────────────────────────

def find_alias_by_code(conn, source_id: str, source_code: str) -> Optional[str]:
    """Stage 1: Exact source_code match."""
    return s(conn, """
        SELECT client_id::text FROM client_source_aliases
        WHERE source_id=%s::uuid AND source_code=%s
          AND match_confidence='CONFIRMED' AND match_status='ACTIVE'
          AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
    """, (source_id, source_code))


def find_alias_by_name(conn, source_id: str, source_name: str) -> Optional[str]:
    """Stage 2: Exact source_name match (case-insensitive)."""
    return s(conn, """
        SELECT client_id::text FROM client_source_aliases
        WHERE source_id=%s::uuid AND LOWER(source_name)=LOWER(%s)
          AND match_confidence='CONFIRMED' AND match_status='ACTIVE'
          AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
    """, (source_id, source_name))


def find_aliases_all(conn, source_id: str):
    """Load all CONFIRMED aliases for this source — used for fuzzy matching."""
    return q(conn, """
        SELECT client_id::text, source_name, source_code
        FROM client_source_aliases
        WHERE source_id=%s::uuid
          AND match_confidence='CONFIRMED' AND match_status='ACTIVE'
          AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
    """, (source_id,))


# ── Product matching queries ───────────────────────────────────────────────────

def find_product_alias_by_description(conn, source_id: str, description: str) -> Optional[str]:
    """Exact match on source description (case-insensitive)."""
    return s(conn, """
        SELECT product_sku_id::text FROM product_source_aliases
        WHERE source_id=%s::uuid AND LOWER(source_description)=LOWER(%s)
          AND match_confidence='CONFIRMED' AND is_active=TRUE
    """, (source_id, description))


def get_all_product_aliases(conn, source_id: str):
    """Load all confirmed product aliases for fuzzy matching."""
    return q(conn, """
        SELECT product_sku_id::text, source_description
        FROM product_source_aliases
        WHERE source_id=%s::uuid AND match_confidence='CONFIRMED' AND is_active=TRUE
    """, (source_id,))


# ── DC rule queries ────────────────────────────────────────────────────────────

def check_direct_sale_exists(conn, client_id: str, period_id: str) -> Optional[str]:
    """DC-002: Check if a DIRECT_SALE exists for same client+period."""
    return s(conn, """
        SELECT id::text FROM sales_transactions
        WHERE client_id=%s::uuid AND financial_period_id=%s::uuid
          AND transaction_type='DIRECT_SALE' AND is_primary_record=TRUE
        LIMIT 1
    """, (client_id, period_id))


def check_sell_through_exists(conn, client_id: str, period_id: str) -> int:
    """Return count of active (not yet excluded) DISTRIBUTOR_SELL_THROUGH rows
    for this client+period. Used by DC-002 to decide whether exclusion is needed."""
    return s(conn, """
        SELECT COUNT(*) FROM sales_transactions
        WHERE client_id=%s::uuid AND financial_period_id=%s::uuid
          AND transaction_type='DISTRIBUTOR_SELL_THROUGH' AND is_primary_record=TRUE
          AND excluded_from_market_view=FALSE
    """, (client_id, period_id)) or 0


# ── Batch management ───────────────────────────────────────────────────────────

def create_batch(conn, source_id, file_name, file_hash, file_size, received_date,
                 period_from, period_to, report_type, report_version,
                 is_cumulative, imported_by) -> str:
    row = q1(conn, """
        INSERT INTO import_batches
        (source_id, file_name, file_path, file_hash, file_size_bytes, received_date,
         period_from, period_to, report_type, report_version, is_cumulative,
         imported_by, status)
        VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'INGESTING_RAW')
        RETURNING id::text
    """, (source_id, file_name, f"/imports/{file_name}", file_hash,
          file_size, received_date, period_from, period_to, report_type,
          report_version, is_cumulative, imported_by))
    return row[0]


def update_batch_status(conn, batch_id: str, status: str, **kwargs):
    sets = ["status=%s"]
    vals = [status]
    for k, v in kwargs.items():
        sets.append(f"{k}=%s")
        vals.append(v)
    vals.append(batch_id)
    run(conn, f"UPDATE import_batches SET {', '.join(sets)} WHERE id=%s::uuid", vals)


def check_duplicate_batch(conn, file_hash: str) -> Optional[str]:
    return s(conn, """
        SELECT id::text FROM import_batches
        WHERE file_hash=%s AND status NOT IN ('FAILED')
        LIMIT 1
    """, (file_hash,))


def insert_raw_row(conn, batch_id, row_number, raw_data, row_status='PENDING',
                   client_alias_id=None, product_alias_id=None,
                   case_size_required=False, mapping_error=None,
                   exclusion_reason=None, matching_attempts=None) -> str:
    row = q1(conn, """
        INSERT INTO import_raw_rows
        (batch_id, row_number, raw_data, row_status, client_alias_id, product_alias_id,
         case_size_required, mapping_error, exclusion_reason, matching_attempts)
        VALUES (%s::uuid, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s::jsonb)
        RETURNING id::text
    """, (batch_id, row_number, json.dumps(raw_data), row_status,
          client_alias_id, product_alias_id, case_size_required,
          mapping_error, exclusion_reason,
          json.dumps(matching_attempts) if matching_attempts else None))
    return row[0]


def update_raw_row(conn, row_id: str, **kwargs):
    sets, vals = [], []
    for k, v in kwargs.items():
        if k in ('raw_data', 'matching_attempts') and v is not None:
            sets.append(f"{k}=%s::jsonb")
            vals.append(json.dumps(v))
        else:
            sets.append(f"{k}=%s")
            vals.append(v)
    vals.append(row_id)
    run(conn, f"UPDATE import_raw_rows SET {', '.join(sets)} WHERE id=%s::uuid", vals)


def create_queue_item(conn, batch_id, raw_row_id, issue_type, severity, source_value,
                      suggested_resolution=None, can_bulk_approve=False) -> str:
    row = q1(conn, """
        INSERT INTO import_queue_items
        (import_batch_id, import_raw_row_id, issue_type, severity, status,
         source_value, suggested_resolution, can_bulk_approve)
        VALUES (%s::uuid, %s::uuid, %s, %s, 'OPEN', %s, %s::jsonb, %s)
        RETURNING id::text
    """, (batch_id, raw_row_id, issue_type, severity, source_value,
          json.dumps(suggested_resolution) if suggested_resolution else None,
          can_bulk_approve))
    return row[0]


def create_transaction(conn, batch_id, raw_row_id, source_id, tx_type, tx_date,
                       year_id, period_id, client_id, distributor_id=None,
                       territory_id=None, source_ref=None, dedup_key=None,
                       excluded=False, exclusion_rule=None, exclusion_context=None) -> str:
    import datetime
    row = q1(conn, """
        INSERT INTO sales_transactions
        (import_raw_row_id, source_id, transaction_type, transaction_date,
         financial_year_id, financial_period_id, client_id, distributor_id,
         territory_id, source_ref, dedup_key, is_primary_record,
         excluded_from_market_view, exclusion_rule, exclusion_context,
         exclusion_evaluated_at)
        VALUES (%s::uuid, %s::uuid, %s, %s, %s::uuid, %s::uuid, %s::uuid,
                %s, %s, %s, %s, TRUE, %s, %s, %s::jsonb, %s)
        RETURNING id::text
    """, (raw_row_id, source_id, tx_type, tx_date, year_id, period_id,
          client_id,
          distributor_id,
          territory_id,
          source_ref, dedup_key, excluded, exclusion_rule,
          json.dumps(exclusion_context) if exclusion_context else None,
          datetime.datetime.utcnow() if excluded else None))
    return row[0]


def create_transaction_line(conn, tx_id, sku_id, vintage, src_desc, src_code,
                            qty_orig, unit_orig, case_size_actual,
                            bottles_actual, sbe, litres,
                            rv_confirmed=None, rv_estimated=None, rv_status='MISSING',
                            asp_version_id=None, raw_data=None):
    run(conn, """
        INSERT INTO sales_transaction_lines
        (transaction_id, product_sku_id, vintage, source_product_description,
         source_product_code, quantity_original, unit_original, case_size_actual,
         bottles_actual, standard_bottle_equiv, litres,
         rand_value_confirmed, rand_value_estimated, r_value_status,
         asp_version_id, raw_data)
        VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s::jsonb)
    """, (tx_id, sku_id, vintage, src_desc, src_code, qty_orig, unit_orig,
          case_size_actual, bottles_actual, sbe, litres,
          rv_confirmed, rv_estimated, rv_status,
          asp_version_id,
          json.dumps(raw_data) if raw_data else None))


def upsert_coverage(conn, source_id, region, period_id, status, batch_id=None, notes=None):
    run(conn, """
        INSERT INTO data_coverage
        (source_id, region, financial_period_id, coverage_status, import_batch_id,
         notes, last_evaluated_at)
        VALUES (%s::uuid, %s, %s::uuid, %s, %s, %s, NOW())
        ON CONFLICT (source_id, region, financial_period_id)
        DO UPDATE SET
            coverage_status = EXCLUDED.coverage_status,
            import_batch_id = EXCLUDED.import_batch_id,
            notes = EXCLUDED.notes,
            last_evaluated_at = NOW()
    """, (source_id, region, period_id, status, batch_id, notes))


def get_distributor_erp_codes(conn) -> dict:
    """Returns {erp_debtor_code: distributor_id} for all distributors."""
    rows = q(conn, "SELECT erp_debtor_codes, id::text FROM distributors")
    result = {}
    for codes_arr, dist_id in rows:
        if codes_arr:
            for code in codes_arr:
                result[code.upper()] = dist_id
    return result
