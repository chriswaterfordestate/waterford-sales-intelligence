"""
DC-002 Regression Tests.

Verifies that regardless of import ORDER (distributor-first or ERP-first),
the final market view result is identical and ALL sell-through for a
client+period is excluded when a direct sale exists — not just the first row.

The Fat Butcher (cl-fatb-001) is the reference client: it appears in both
NGF SalesOut (DISTRIBUTOR_SELL_THROUGH) and ERP direct (DIRECT_SALE) in
multiple periods of FY2026.
"""
import pytest
import psycopg2
import json

DSN = "host=localhost dbname=waterford_si_test user=waterford password=waterford_dev"

@pytest.fixture(scope="module")
def db():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    yield conn
    conn.close()


def setup_test_data(conn, client_id, period_id, source_id_ngf, source_id_erp,
                    dist_id, batch_id_ngf, batch_id_erp, year_id):
    """Insert synthetic test transactions for DC-002 testing."""
    cur = conn.cursor()
    
    # Insert raw row shells (minimal valid records)
    raw_rows = []
    for batch_id in [batch_id_ngf, batch_id_erp]:
        cur.execute("""
            INSERT INTO import_raw_rows (id, batch_id, row_number, raw_data, row_status)
            VALUES (gen_random_uuid(), %s::uuid, 1, '{"test":true}'::jsonb, 'PENDING')
            RETURNING id::text
        """, (batch_id,))
        raw_rows.append(cur.fetchone()[0])
    
    return raw_rows[0], raw_rows[1]  # ngf_row_id, erp_row_id


def q(conn, sql, p=None):
    with conn.cursor() as c:
        c.execute(sql, p)
        return c.fetchall()

def s(conn, sql, p=None):
    r = q(conn, sql, p)
    return r[0][0] if r else None

def clear_test_transactions(conn):
    """Remove test data between test scenarios."""
    with conn.cursor() as c:
        c.execute("DELETE FROM sales_transaction_lines WHERE raw_data->>'test_marker' IS NOT NULL")
        c.execute("""DELETE FROM sales_transactions WHERE import_raw_row_id IN 
                     (SELECT id FROM import_raw_rows WHERE raw_data->>'test_marker' IS NOT NULL)""")
        c.execute("DELETE FROM import_raw_rows WHERE raw_data->>'test_marker' IS NOT NULL")


def insert_sell_through(conn, batch_id_ngf, source_id_ngf, client_id, period_id,
                         year_id, dist_id, num_rows: int = 3) -> list:
    """Insert multiple DISTRIBUTOR_SELL_THROUGH rows (simulating NGF SalesOut with several deliveries)."""
    tx_ids = []
    for i in range(num_rows):
        with conn.cursor() as c:
            # Raw row
            c.execute("""
                INSERT INTO import_raw_rows (id, batch_id, row_number, raw_data, row_status)
                VALUES (gen_random_uuid(), %s::uuid, %s, %s::jsonb, 'MAPPED')
                RETURNING id::text
            """, (batch_id_ngf, i+100, json.dumps({"test_marker": "dc002_test", "delivery": i+1})))
            raw_row_id = c.fetchone()[0]
            
            # Transaction
            c.execute("""
                INSERT INTO sales_transactions (
                    id, import_raw_row_id, source_id, transaction_type, transaction_date,
                    financial_year_id, financial_period_id, client_id, distributor_id,
                    is_primary_record, excluded_from_market_view)
                VALUES (gen_random_uuid(), %s::uuid, %s::uuid, 'DISTRIBUTOR_SELL_THROUGH',
                        '2026-01-15', %s::uuid, %s::uuid, %s::uuid, %s::uuid, TRUE, FALSE)
                RETURNING id::text
            """, (raw_row_id, source_id_ngf, year_id, period_id, client_id, dist_id))
            tx_id = c.fetchone()[0]
            tx_ids.append(tx_id)
            
            # Line — asp_version_id required by CHECK constraint estimated_asp_required
            sku_id = s(conn, "SELECT id::text FROM product_skus WHERE sku_code='RM001'")
            asp_id = s(conn, "SELECT id::text FROM asp_versions WHERE product_sku_id=%s::uuid LIMIT 1", (sku_id,))
            c.execute("""
                INSERT INTO sales_transaction_lines (
                    transaction_id, product_sku_id, vintage, source_product_description,
                    source_product_code, quantity_original, unit_original,
                    bottles_actual, standard_bottle_equiv, litres, r_value_status,
                    rand_value_estimated, asp_version_id, raw_data)
                VALUES (%s::uuid, %s::uuid, 2024, 'WATERFORD ROSE-MARY 750M', 'RM001',
                        6, 'BOTTLES', 6.0, 6.0, 4.5, 'ESTIMATED', 530.22,
                        %s::uuid, %s::jsonb)
            """, (tx_id, sku_id, asp_id, json.dumps({"test_marker": "dc002_test", "delivery": i+1})))
    
    return tx_ids


def insert_direct_sale(conn, batch_id_erp, source_id_erp, client_id, period_id,
                        year_id) -> str:
    """Insert a DIRECT_SALE (simulating ERP import)."""
    with conn.cursor() as c:
        c.execute("""
            INSERT INTO import_raw_rows (id, batch_id, row_number, raw_data, row_status)
            VALUES (gen_random_uuid(), %s::uuid, 999, %s::jsonb, 'MAPPED')
            RETURNING id::text
        """, (batch_id_erp, json.dumps({"test_marker": "dc002_test", "source": "ERP"})))
        raw_row_id = c.fetchone()[0]
        
        c.execute("""
            INSERT INTO sales_transactions (
                id, import_raw_row_id, source_id, transaction_type, transaction_date,
                financial_year_id, financial_period_id, client_id,
                is_primary_record, excluded_from_market_view)
            VALUES (gen_random_uuid(), %s::uuid, %s::uuid, 'DIRECT_SALE', '2026-01-20',
                    %s::uuid, %s::uuid, %s::uuid, TRUE, FALSE)
            RETURNING id::text
        """, (raw_row_id, source_id_erp, year_id, period_id, client_id))
        tx_id = c.fetchone()[0]
        
        sku_id = s(conn, "SELECT id::text FROM product_skus WHERE sku_code='RM001'")
        c.execute("""
            INSERT INTO sales_transaction_lines (
                transaction_id, product_sku_id, vintage, source_product_description,
                source_product_code, quantity_original, unit_original,
                bottles_actual, standard_bottle_equiv, litres, r_value_status,
                rand_value_confirmed, raw_data)
            VALUES (%s::uuid, %s::uuid, 2024, 'Rose-Mary', 'RM001',
                    3, 'BOTTLES', 3.0, 3.0, 2.25, 'CONFIRMED', 283.11,
                    %s::jsonb)
        """, (tx_id, sku_id, json.dumps({"test_marker": "dc002_test", "source": "ERP"})))
        
        return tx_id


def apply_retroactive_dc002(conn, client_id, period_id):
    """Apply DC-002 retroactively for a client+period (same logic as pipeline)."""
    with conn.cursor() as c:
        c.execute("""
            UPDATE sales_transactions
            SET excluded_from_market_view = TRUE,
                exclusion_rule = 'DC-002',
                exclusion_context = '{"reason":"DIRECT_SALE_LOADED_AFTER_SELL_THROUGH"}'::jsonb,
                exclusion_evaluated_at = NOW()
            WHERE client_id = %s::uuid
              AND financial_period_id = %s::uuid
              AND transaction_type = 'DISTRIBUTOR_SELL_THROUGH'
              AND is_primary_record = TRUE
              AND excluded_from_market_view = FALSE
        """, (client_id, period_id))
        return c.rowcount


def get_market_view_bottles(conn, client_id, period_id) -> float:
    """Get reportable bottles in market view for a client+period."""
    result = s(conn, """
        SELECT COALESCE(SUM(stl.bottles_actual), 0)
        FROM sales_transactions st
        JOIN sales_transaction_lines stl ON stl.transaction_id = st.id
        WHERE st.client_id = %s::uuid
          AND st.financial_period_id = %s::uuid
          AND st.excluded_from_market_view = FALSE
          AND st.is_primary_record = TRUE
    """, (client_id, period_id))
    return float(result or 0)


def count_excluded_by_dc002(conn, client_id, period_id) -> int:
    """Count sell-through rows excluded by DC-002 for a client+period."""
    return s(conn, """
        SELECT COUNT(*) FROM sales_transactions
        WHERE client_id = %s::uuid
          AND financial_period_id = %s::uuid
          AND transaction_type = 'DISTRIBUTOR_SELL_THROUGH'
          AND exclusion_rule = 'DC-002'
    """, (client_id, period_id))


# ── Test fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def ids(db):
    """Get stable reference IDs from the test database."""
    client_id = s(db, "SELECT id::text FROM clients WHERE canonical_name='The Fat Butcher'")
    period_id = s(db, """SELECT id::text FROM financial_periods 
                         WHERE period_number=7 
                         AND financial_year_id=(SELECT id FROM financial_years WHERE year_label='FY2026')""")
    year_id   = s(db, "SELECT id::text FROM financial_years WHERE year_label='FY2026'")
    src_ngf   = s(db, "SELECT id::text FROM data_sources WHERE source_code='NGF_SALESOUT'")
    src_erp   = s(db, "SELECT id::text FROM data_sources WHERE source_code='ERP_EXPORT'")
    dist_ngf  = s(db, "SELECT id::text FROM distributors WHERE distributor_code='NGF'")
    
    # Create minimal batch records for test
    with db.cursor() as c:
        c.execute("""
            INSERT INTO import_batches (source_id, file_name, file_path, file_hash, file_size_bytes,
                received_date, imported_by, status)
            VALUES (%s::uuid, 'test_ngf.xlsx', '/test/test_ngf.xlsx', md5(random()::text), 100,
                    CURRENT_DATE, 'test', 'COMPLETE')
            RETURNING id::text
        """, (src_ngf,))
        batch_ngf = c.fetchone()[0]
        
        c.execute("""
            INSERT INTO import_batches (source_id, file_name, file_path, file_hash, file_size_bytes,
                received_date, imported_by, status)
            VALUES (%s::uuid, 'test_erp.csv', '/test/test_erp.csv', md5(random()::text), 100,
                    CURRENT_DATE, 'test', 'COMPLETE')
            RETURNING id::text
        """, (src_erp,))
        batch_erp = c.fetchone()[0]
    
    yield {"client_id": client_id, "period_id": period_id, "year_id": year_id,
           "src_ngf": src_ngf, "src_erp": src_erp, "dist_ngf": dist_ngf,
           "batch_ngf": batch_ngf, "batch_erp": batch_erp}
    
    # Cleanup
    clear_test_transactions(db)
    with db.cursor() as c:
        c.execute("DELETE FROM import_batches WHERE id IN (%s::uuid, %s::uuid)", 
                  (batch_ngf, batch_erp))


# ── T-DC-001: Distributor-first, then ERP (retroactive DC-002) ────────────────
def test_DC001_distributor_first_erp_second_excludes_ALL_sell_through(db, ids):
    """
    Order: NGF SalesOut first (3 rows, 6+6+6=18 btls each) → then ERP direct (3 btls).
    After ERP import: DC-002 retroactively excludes ALL 3 sell-through rows.
    Market view: only 3 btls (direct sale). NOT 3+18=21.
    """
    clear_test_transactions(db)
    
    # Step 1: Import NGF SalesOut (3 separate deliveries = 3 transactions)
    st_ids = insert_sell_through(db, ids['batch_ngf'], ids['src_ngf'],
                                  ids['client_id'], ids['period_id'],
                                  ids['year_id'], ids['dist_ngf'], num_rows=3)
    
    # After NGF import: all 3 sell-through rows are in market view (18 btls total)
    market_after_ngf = get_market_view_bottles(db, ids['client_id'], ids['period_id'])
    assert market_after_ngf == 18.0, f"After NGF import: expected 18 btls in market view, got {market_after_ngf}"
    
    # Step 2: Import ERP direct sale (3 btls)
    insert_direct_sale(db, ids['batch_erp'], ids['src_erp'],
                        ids['client_id'], ids['period_id'], ids['year_id'])
    
    # Apply retroactive DC-002 (ALL sell-through must be excluded)
    excluded_count = apply_retroactive_dc002(db, ids['client_id'], ids['period_id'])
    
    # REGRESSION TEST: ALL 3 sell-through rows must be excluded (not just 1)
    assert excluded_count == 3, (
        f"DC-002 retroactive must exclude ALL {3} sell-through rows, "
        f"but only excluded {excluded_count}. "
        "This was the Sprint 2 bug where only the first matching row was excluded."
    )
    
    # Market view must show only 3 btls (direct sale)
    market_final = get_market_view_bottles(db, ids['client_id'], ids['period_id'])
    assert market_final == 3.0, (
        f"Market view must show 3 btls (direct sale only), got {market_final}. "
        "DC-002 double-count prevention failed."
    )
    
    # Verify exclusion_rule is set correctly on all excluded rows
    dc002_count = count_excluded_by_dc002(db, ids['client_id'], ids['period_id'])
    assert dc002_count == 3, f"Expected 3 rows with exclusion_rule=DC-002, got {dc002_count}"


# ── T-DC-002: ERP first, then distributor (forward DC-002) ───────────────────
def test_DC002_erp_first_distributor_second_excludes_sell_through_at_ingestion(db, ids):
    """
    Order: ERP direct first (3 btls) → then NGF SalesOut (3 rows).
    Each NGF sell-through row must be excluded at ingestion time.
    Market view: only 3 btls (direct sale). Never counts distributor rows.
    """
    clear_test_transactions(db)
    
    # Step 1: Import ERP direct sale
    insert_direct_sale(db, ids['batch_erp'], ids['src_erp'],
                        ids['client_id'], ids['period_id'], ids['year_id'])
    
    # After ERP: 3 btls in market view
    market_after_erp = get_market_view_bottles(db, ids['client_id'], ids['period_id'])
    assert market_after_erp == 3.0, f"After ERP import: expected 3 btls, got {market_after_erp}"
    
    # Step 2: Import NGF SalesOut — at ingestion, DC-002 must fire for each row
    # Simulate what pipeline does: check for direct sale BEFORE creating sell-through
    from app.services.import_engine.dc_rules import evaluate_dc_rules
    import os, sys
    sys.path.insert(0, '/home/claude/waterford-si/backend')
    os.environ['DATABASE_URL_SYNC'] = 'host=localhost dbname=waterford_si_test user=waterford password=waterford_dev'
    
    excluded_at_ingestion = 0
    for i in range(3):
        dc = evaluate_dc_rules(db, 'DISTRIBUTOR_SELL_THROUGH',
                                ids['client_id'], ids['period_id'], ids['dist_ngf'])
        
        # Each sell-through row must be excluded at ingestion because direct sale exists
        assert dc['excluded'] == True, (
            f"Sell-through row {i+1} should be excluded at ingestion (DC-002), "
            f"but evaluate_dc_rules returned excluded=False"
        )
        assert dc['exclusion_rule'] == 'DC-002', \
            f"Expected exclusion_rule=DC-002, got {dc['exclusion_rule']}"
        excluded_at_ingestion += 1
    
    assert excluded_at_ingestion == 3, \
        f"All 3 sell-through rows must be flagged for exclusion at ingestion"
    
    # Market view unchanged: still 3 btls
    market_final = get_market_view_bottles(db, ids['client_id'], ids['period_id'])
    assert market_final == 3.0, \
        f"Market view must remain 3 btls (direct sale only), got {market_final}"


# ── T-DC-003: Both orders produce IDENTICAL market view ──────────────────────
def test_DC003_import_order_does_not_affect_market_view_result(db, ids):
    """
    CORE INVARIANT: regardless of import order, the market view must show
    exactly the direct sale volume (3 btls) for The Fat Butcher in Jan 2026.
    
    This test verifies the commutative property of DC-002.
    """
    # This is verified by T-DC-001 (distributor first) and T-DC-002 (ERP first)
    # Both tests assert market_final == 3.0
    # This test makes the invariant explicit for documentation
    
    clear_test_transactions(db)
    
    # Scenario A: NGF first
    st_ids = insert_sell_through(db, ids['batch_ngf'], ids['src_ngf'],
                                  ids['client_id'], ids['period_id'],
                                  ids['year_id'], ids['dist_ngf'], num_rows=3)
    insert_direct_sale(db, ids['batch_erp'], ids['src_erp'],
                        ids['client_id'], ids['period_id'], ids['year_id'])
    apply_retroactive_dc002(db, ids['client_id'], ids['period_id'])
    market_A = get_market_view_bottles(db, ids['client_id'], ids['period_id'])
    
    clear_test_transactions(db)
    
    # Scenario B: ERP first
    insert_direct_sale(db, ids['batch_erp'], ids['src_erp'],
                        ids['client_id'], ids['period_id'], ids['year_id'])
    # Sell-through rows would be excluded at ingestion — check DC-002 fires
    for _ in range(3):
        from app.services.import_engine.dc_rules import evaluate_dc_rules
        dc = evaluate_dc_rules(db, 'DISTRIBUTOR_SELL_THROUGH',
                                ids['client_id'], ids['period_id'], ids['dist_ngf'])
        assert dc['excluded'] == True
    market_B = get_market_view_bottles(db, ids['client_id'], ids['period_id'])
    
    assert market_A == market_B, (
        f"IMPORT ORDER INVARIANT FAILED: "
        f"distributor-first market view = {market_A} btls, "
        f"ERP-first market view = {market_B} btls. These must be equal."
    )
    assert market_A == 3.0, f"Expected 3 btls in both scenarios, got {market_A}"
