"""
Sprint 1 Acceptance Gate — 14 tests using synchronous psycopg2.
"""
import pytest
import psycopg2
import os

TEST_DSN = os.getenv(
    "TEST_DSN",
    "host=localhost dbname=waterford_si_test user=waterford password=waterford_dev"
)


@pytest.fixture(scope="session")
def db():
    conn = psycopg2.connect(TEST_DSN)
    conn.autocommit = True
    yield conn
    conn.close()


def q(db, sql, p=None):
    with db.cursor() as cur:
        cur.execute(sql, p)
        return cur.fetchall()


def s(db, sql, p=None):
    r = q(db, sql, p)
    return r[0][0] if r else None


def test_T01_coverage_ngf_salesout_cpt_jul25(db):
    rows = q(db, """
        SELECT dc.coverage_status FROM data_coverage dc
        JOIN data_sources ds ON ds.id=dc.source_id
        JOIN financial_periods fp ON fp.id=dc.financial_period_id
        WHERE ds.source_code='NGF_SALESOUT' AND dc.region='CPT'
          AND fp.period_number=1
          AND fp.financial_year_id=(SELECT id FROM financial_years WHERE year_label='FY2026')
    """)
    assert rows, "NGF SalesOut CPT Jul 25 coverage record must exist"
    assert rows[0][0] in ('MISSING','COVERED')


def test_T02_jhb_ngf_monthly_jul25_is_missing(db):
    rows = q(db, """
        SELECT dc.coverage_status, dc.notes FROM data_coverage dc
        JOIN data_sources ds ON ds.id=dc.source_id
        JOIN financial_periods fp ON fp.id=dc.financial_period_id
        WHERE ds.source_code='NGF_MONTHLY' AND dc.region='JHB'
          AND fp.period_number=1
          AND fp.financial_year_id=(SELECT id FROM financial_years WHERE year_label='FY2026')
    """)
    assert rows, "NGF Monthly JHB Jul 25 coverage must exist"
    assert rows[0][0]=='MISSING', f"Got {rows[0][0]}"
    assert any(w in (rows[0][1] or '').lower() for w in ['does not exist','unavailable','not exist'])


def test_T03_kzn_ngf_monthly_jul25_is_missing(db):
    rows = q(db, """
        SELECT dc.coverage_status FROM data_coverage dc
        JOIN data_sources ds ON ds.id=dc.source_id
        JOIN financial_periods fp ON fp.id=dc.financial_period_id
        WHERE ds.source_code='NGF_MONTHLY' AND dc.region='KZN'
          AND fp.period_number=1
          AND fp.financial_year_id=(SELECT id FROM financial_years WHERE year_label='FY2026')
    """)
    assert rows, "NGF Monthly KZN Jul 25 coverage must exist"
    assert rows[0][0]=='MISSING', f"Got {rows[0][0]}"


def test_T04_exclusion_constraint_requires_rule_and_timestamp(db):
    with pytest.raises(psycopg2.Error):
        with db.cursor() as cur:
            cur.execute("""
                INSERT INTO sales_transactions
                (id,import_raw_row_id,source_id,transaction_type,transaction_date,
                 financial_year_id,financial_period_id,client_id,
                 excluded_from_market_view,is_primary_record)
                VALUES(
                  gen_random_uuid(),gen_random_uuid(),
                  (SELECT id FROM data_sources WHERE source_code='ERP_EXPORT'),
                  'DIRECT_SALE','2026-07-15',
                  (SELECT id FROM financial_years WHERE year_label='FY2027'),
                  (SELECT id FROM financial_periods WHERE period_number=1
                   AND financial_year_id=(SELECT id FROM financial_years WHERE year_label='FY2027')),
                  (SELECT id FROM clients WHERE canonical_name='The Fat Butcher'),
                  TRUE, TRUE)
            """)
    db.rollback()


def test_T05_sales_transactions_has_no_rep_id_column(db):
    row = s(db, """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name='sales_transactions' AND column_name='rep_id'
    """)
    assert row is None, "rep_id must NOT exist on sales_transactions"


def test_T06_rep_attribution_query_executes(db):
    rows = q(db, """
        SELECT co.rep_id, r.full_name FROM client_ownership co
        JOIN reps r ON r.id=co.rep_id
        WHERE co.client_id=(SELECT id FROM clients WHERE canonical_name='The Fat Butcher')
          AND co.effective_from<='2026-07-15'
          AND (co.effective_to IS NULL OR co.effective_to>='2026-07-15')
        LIMIT 1
    """)
    assert rows is not None  # Structural: query must execute


def test_T07_confirmed_alias_requires_confirmed_by(db):
    with pytest.raises(psycopg2.Error):
        with db.cursor() as cur:
            cur.execute("""
                INSERT INTO client_source_aliases
                (id,client_id,source_id,source_name,source_code,
                 match_confidence,match_status,matched_by,confirmed_by)
                VALUES(
                  gen_random_uuid(),
                  (SELECT id FROM clients WHERE canonical_name='The Fat Butcher'),
                  (SELECT id FROM data_sources WHERE source_code='ERP_EXPORT'),
                  'Test Alias',NULL,
                  'CONFIRMED','ACTIVE','system',NULL)
            """)
    db.rollback()


def test_T08_case_size_required_column_exists(db):
    rows = q(db, """
        SELECT column_name, data_type FROM information_schema.columns
        WHERE table_schema='public' AND table_name='import_raw_rows'
          AND column_name='case_size_required'
    """)
    assert rows, "case_size_required must exist on import_raw_rows"
    assert 'bool' in rows[0][1].lower(), f"Must be boolean, got {rows[0][1]}"


def test_T09_vdp_fy2026_coverage_is_not_applicable(db):
    count = s(db, """
        SELECT COUNT(*) FROM data_coverage dc
        JOIN data_sources ds ON ds.id=dc.source_id
        JOIN financial_periods fp ON fp.id=dc.financial_period_id
        WHERE ds.source_code='VDP_WEEKLY_PDF'
          AND fp.financial_year_id=(SELECT id FROM financial_years WHERE year_label='FY2026')
          AND dc.coverage_status='NOT_APPLICABLE'
    """)
    assert count==12, f"All 12 FY26 VDP periods must be NOT_APPLICABLE, found {count}"


def test_T10_invalid_transaction_type_rejected(db):
    with pytest.raises(psycopg2.Error):
        with db.cursor() as cur:
            cur.execute("""
                INSERT INTO sales_transactions
                (id,import_raw_row_id,source_id,transaction_type,transaction_date,
                 financial_year_id,financial_period_id,client_id)
                VALUES(gen_random_uuid(),gen_random_uuid(),
                  (SELECT id FROM data_sources WHERE source_code='ERP_EXPORT'),
                  'INVALID_TYPE','2026-07-15',
                  (SELECT id FROM financial_years WHERE year_label='FY2027'),
                  (SELECT id FROM financial_periods WHERE period_number=1
                   AND financial_year_id=(SELECT id FROM financial_years WHERE year_label='FY2027')),
                  (SELECT id FROM clients WHERE canonical_name='The Fat Butcher'))
            """)
    db.rollback()


def test_T11_estimated_rvalue_check_constraint_exists(db):
    count = s(db, """
        SELECT COUNT(*) FROM information_schema.check_constraints
        WHERE constraint_schema='public' AND check_clause LIKE '%asp_version_id%'
    """)
    assert count>=1, "CHECK constraint for asp_version_id on ESTIMATED rows must exist"


def test_T12_fy2027_gau_targets_seeded(db):
    rows = q(db, """
        SELECT fp.period_number, t.target_bottles, t.target_rand_value
        FROM targets t
        JOIN financial_periods fp ON fp.id=t.financial_period_id
        JOIN target_sets ts ON ts.id=t.target_set_id
        JOIN territories terr ON terr.id=t.territory_id
        WHERE ts.financial_year_id=(SELECT id FROM financial_years WHERE year_label='FY2027')
          AND terr.territory_code='GAU' AND t.rep_id IS NULL
        ORDER BY fp.period_number
    """)
    assert len(rows)>=2, f"Must have 2+ GAU targets, found {len(rows)}"
    jul = next((r for r in rows if r[0]==1), None)
    aug = next((r for r in rows if r[0]==2), None)
    assert jul and float(jul[1])==3557, f"July target must be 3557, got {jul}"
    assert aug and float(aug[1])==3953, f"August target must be 3953, got {aug}"
    assert float(jul[2])==657045 and float(aug[2])==784286


def test_T13_provenance_join_chain_executes(db):
    rows = q(db, """
        SELECT st.id,irr.id,irr.raw_data,ib.file_name,ib.file_hash,ds.source_code
        FROM sales_transactions st
        JOIN import_raw_rows irr ON irr.id=st.import_raw_row_id
        JOIN import_batches ib ON ib.id=irr.batch_id
        JOIN data_sources ds ON ds.id=ib.source_id
        LIMIT 0
    """)
    assert rows==[]  # No data yet — structural test only


def test_T14_distributor_entity_id_on_clients(db):
    rows = q(db, """
        SELECT column_name, is_nullable FROM information_schema.columns
        WHERE table_schema='public' AND table_name='clients'
          AND column_name='distributor_entity_id'
    """)
    assert rows, "distributor_entity_id must exist on clients"
    assert rows[0][1]=='YES', "distributor_entity_id must be nullable"
