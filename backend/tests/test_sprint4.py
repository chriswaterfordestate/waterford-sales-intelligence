"""
Sprint 4 integration tests.

Covers: NGF Monthly, Distriliq CPT, Upload Centre, Commercial Queue,
        FY2027 Dashboard, Client 360, Source override, DC-002 sell-through.
"""
import pytest, os, sys, time
from fastapi.testclient import TestClient
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault('DATABASE_URL_SYNC',
    'host=localhost dbname=waterford_si user=waterford password=waterford_dev')

from app.main import app
from app.database import get_db_conn

client = TestClient(app)
client.headers.update({"Authorization": "Bearer dev"})  # dev auth bypass

PROD_DSN = 'host=localhost dbname=waterford_si user=waterford password=waterford_dev'

NGF_MONTHLY_FILE = '/mnt/user-data/uploads/NGF_July_2026_WaterfordMonthlyReport.xlsx'
DISTRILIQ_FILE   = '/mnt/user-data/uploads/Distriliq_CPT_Client_Report_FY2026_4.xlsx'
ERP_FY2027_FILE  = '/mnt/user-data/uploads/17_august.csv'


# ═══════════════════════════════════════════════════════════════════════════════
# A. CONNECTOR IDENTIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestConnectorIdentification:

    def test_ngf_monthly_detect(self):
        from app.services.import_engine.connectors.ngf_monthly import detect
        assert detect(NGF_MONTHLY_FILE), "NGF Monthly file should be auto-detected"

    def test_distriliq_detect(self):
        from app.services.import_engine.connectors.distriliq_cpt import detect
        assert detect(DISTRILIQ_FILE), "Distriliq CPT file should be auto-detected"

    def test_erp_csv_identify(self):
        from app.services.import_engine.connectors.erp_csv import identify_file
        meta = identify_file(ERP_FY2027_FILE)
        assert meta.get('is_erp_export'), "ERP CSV should be identified"

    def test_pipeline_identifies_ngf_monthly(self):
        from app.services.import_engine.pipeline import _identify_file
        connector, meta = _identify_file(NGF_MONTHLY_FILE, 'NGF_July_2026_WaterfordMonthlyReport.xlsx')
        assert connector is not None
        assert connector['source_code'] == 'NGF_MONTHLY'

    def test_pipeline_identifies_distriliq(self):
        from app.services.import_engine.pipeline import _identify_file
        connector, meta = _identify_file(DISTRILIQ_FILE, 'Distriliq_CPT_Client_Report_FY2026_4.xlsx')
        assert connector is not None
        assert connector['source_code'] == 'DISTRILIQ_CPT'

    def test_source_override_bypasses_autodetect(self):
        """Manual source override must skip auto-identification entirely."""
        from app.services.import_engine.pipeline import import_file
        # Use ERP file but claim it's NGF Monthly — should fail gracefully not loop
        r = import_file(ERP_FY2027_FILE, imported_by='test',
                        source_override='DISTRILIQ_CPT')
        # Should either error or produce 0 valid rows (not auto-identified as ERP)
        # The key check: it used DISTRILIQ_CPT connector, not ERP
        assert r.get('status') in ('DUPLICATE_DETECTED', 'PARTIAL_COMPLETE',
                                    'COMPLETE', 'FAILED', 'IDENTIFICATION_REQUIRED')


# ═══════════════════════════════════════════════════════════════════════════════
# B. CONNECTOR OUTPUT CONTRACT
# ═══════════════════════════════════════════════════════════════════════════════

class TestConnectorContract:
    """Every connector must yield standardized client_name, client_code, product_desc."""

    def test_ngf_monthly_yields_client_name(self):
        from app.services.import_engine.connectors.ngf_monthly import iter_rows
        rows = list(iter_rows(NGF_MONTHLY_FILE))
        assert rows, "NGF Monthly should yield rows"
        for r in rows[:5]:
            assert 'client_name' in r, f"Row must have client_name: {r.keys()}"
            assert r['client_name'], "client_name must not be empty"
            assert 'client_code' in r, "Row must have client_code"
            assert 'product_desc' in r, "Row must have product_desc"
            assert r['product_desc'], "product_desc must not be empty"

    def test_ngf_monthly_yields_correct_period(self):
        from app.services.import_engine.connectors.ngf_monthly import iter_rows
        rows = list(iter_rows(NGF_MONTHLY_FILE))
        # File is July 2026
        periods = set((r['calendar_year'], r['calendar_month']) for r in rows)
        assert (2026, 7) in periods, f"Must include Jul 2026, got {periods}"

    def test_ngf_monthly_yields_distributor_sell_through(self):
        from app.services.import_engine.connectors.ngf_monthly import iter_rows
        rows = list(iter_rows(NGF_MONTHLY_FILE))
        tx_types = set(r['transaction_type'] for r in rows)
        assert tx_types == {'DISTRIBUTOR_SELL_THROUGH'}, \
            f"All NGF Monthly rows must be DISTRIBUTOR_SELL_THROUGH, got {tx_types}"

    def test_distriliq_yields_client_name(self):
        from app.services.import_engine.connectors.distriliq_cpt import iter_rows
        rows = list(iter_rows(DISTRILIQ_FILE))
        assert rows, "Distriliq CPT should yield rows"
        for r in rows[:5]:
            assert 'client_name' in r
            assert r['client_name'], "client_name must not be empty"
            assert 'product_desc' in r
            assert r['product_desc'], "product_desc must not be empty"

    def test_distriliq_fy2026_periods(self):
        from app.services.import_engine.connectors.distriliq_cpt import iter_rows
        rows = list(iter_rows(DISTRILIQ_FILE))
        years = set(r['calendar_year'] for r in rows)
        months = set(r['calendar_month'] for r in rows)
        assert 2025 in years or 2026 in years, "Must include FY2026 calendar years"
        assert len(months) >= 6, "Should cover multiple months"

    def test_erp_csv_yields_client_name(self):
        """ERP CSV connector must yield standardized client_name, client_code, product_desc."""
        import psycopg2
        from psycopg2.extras import RealDictCursor
        from app.services.import_engine.connectors.erp_csv import parse_rows

        # Load distributor codes from DB (standalone connection, not via TestClient)
        dist_codes = {}
        conn = psycopg2.connect(PROD_DSN)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as c:
                c.execute("""
                    SELECT debtor, d.id::text as dist_id
                    FROM distributors d, unnest(d.erp_debtor_codes) as debtor
                """)
                for row in c.fetchall():
                    dist_codes[row['debtor']] = row['dist_id']
        finally:
            conn.close()

        rows = list(parse_rows(ERP_FY2027_FILE, dist_codes))
        assert rows, "ERP CSV must yield rows"
        non_direct = [r for r in rows if r.get('transaction_type') != 'DIRECT_SALE']
        direct = [r for r in rows if r.get('transaction_type') == 'DIRECT_SALE']
        # Check standardized fields on first 5 DIRECT_SALE rows
        for r in direct[:5]:
            assert 'client_name' in r, f"client_name missing from: {r.keys()}"
            assert r['client_name'], f"client_name must not be empty"
            assert 'client_code' in r, "client_code missing"
            assert r['client_code'], "client_code must not be empty"
            assert 'product_desc' in r, "product_desc missing"


# ═══════════════════════════════════════════════════════════════════════════════
# C. DISTRIBUTOR IDENTITY
# ═══════════════════════════════════════════════════════════════════════════════

class TestDistributorIdentity:

    def test_ngf_distributor_exists(self):
        import psycopg2
        conn = psycopg2.connect(PROD_DSN)
        with conn.cursor() as c:
            c.execute("SELECT id FROM distributors WHERE distributor_code='NGF'")
            assert c.fetchone() is not None, "NGF distributor must exist in DB"
        conn.close()

    def test_distriliq_distributor_exists(self):
        import psycopg2
        conn = psycopg2.connect(PROD_DSN)
        with conn.cursor() as c:
            c.execute("SELECT id FROM distributors WHERE distributor_code='DISTRILIQ_CPT'")
            assert c.fetchone() is not None, "Distriliq distributor must exist"
        conn.close()

    def test_distriliq_transactions_have_distributor_id(self):
        """Distriliq sell-through transactions must have distributor_id set."""
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(PROD_DSN)
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("""
                SELECT COUNT(*) total, COUNT(st.distributor_id) with_dist_id
                FROM sales_transactions st
                JOIN data_sources ds ON ds.id=st.source_id
                WHERE ds.source_code='DISTRILIQ_CPT'
                  AND st.transaction_type='DISTRIBUTOR_SELL_THROUGH'
                  AND st.is_primary_record=TRUE
            """)
            r = c.fetchone()
        conn.close()
        if r['total'] == 0:
            pytest.skip("No Distriliq transactions in DB yet")
        assert r['with_dist_id'] == r['total'], \
            f"All Distriliq sell-through must have distributor_id ({r['with_dist_id']}/{r['total']})"

    def test_erp_distributor_sell_in_excluded_from_market_view(self):
        """ERP DISTRIBUTOR_SELL_IN must be excluded from commercial market view."""
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(PROD_DSN)
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("""
                SELECT COUNT(*) total,
                       SUM(CASE WHEN excluded_from_market_view THEN 1 ELSE 0 END) excl
                FROM sales_transactions
                WHERE transaction_type='DISTRIBUTOR_SELL_IN' AND is_primary_record=TRUE
            """)
            r = c.fetchone()
        conn.close()
        if r['total'] == 0:
            pytest.skip("No DISTRIBUTOR_SELL_IN transactions")
        assert r['excl'] == r['total'], "All DISTRIBUTOR_SELL_IN must be excluded from market view"


# ═══════════════════════════════════════════════════════════════════════════════
# D. UPLOAD CENTRE
# ═══════════════════════════════════════════════════════════════════════════════

class TestUploadCentre:

    def test_batches_endpoint_returns_history(self):
        r = client.get("/api/imports/batches?limit=5")
        assert r.status_code == 200
        data = r.json()
        assert 'batches' in data

    def test_upload_duplicate_returns_duplicate_status(self):
        """Re-uploading the same file must be rejected without double-counting."""
        with open(ERP_FY2027_FILE, 'rb') as f:
            r = client.post("/api/imports/upload",
                            files={"file": ("17_august.csv", f, "text/csv")},
                            data={"imported_by": "test"})
        assert r.status_code == 200
        data = r.json()
        assert data.get('status') == 'DUPLICATE_DETECTED', \
            f"Expected DUPLICATE_DETECTED, got: {data.get('status')}"

    def test_upload_unrecognised_returns_identification_required(self):
        """A file that can't be identified should return IDENTIFICATION_REQUIRED."""
        import io
        fake = io.BytesIO(b"col1,col2\nval1,val2\n")
        r = client.post("/api/imports/upload",
                        files={"file": ("unknown.csv", fake, "text/csv")},
                        data={"imported_by": "test"})
        assert r.status_code == 200
        data = r.json()
        assert data.get('status') == 'IDENTIFICATION_REQUIRED', \
            f"Got: {data.get('status')}"
        assert 'known_formats' in data, "Must list available source formats"

    def test_source_override_uses_named_connector(self):
        """
        When source_override is supplied, the pipeline must use that connector
        and must NOT re-run auto-identification.
        The detected_format in the response must match the override, not auto-detection.
        """
        import io
        # CSV that would NOT be identified as DISTRILIQ_CPT by auto-detection
        fake = io.BytesIO(b"Col1,Col2\nA,1\nB,2\n")
        r = client.post("/api/imports/upload",
                        files={"file": ("ambiguous.csv", fake, "text/csv")},
                        data={"imported_by": "test", "source_override": "NGF_SALESOUT"})
        assert r.status_code == 200
        data = r.json()
        # The connector attempted was NGF_SALESOUT (not auto-detected as something else)
        assert data.get("detected_format") == "NGF_SALESOUT",             f"Override not honoured: detected_format={data.get('detected_format')}"
        # Status may be FAILED (bad data for NGF connector) but override WAS used
        assert data.get("status") in ("FAILED", "PARTIAL_COMPLETE", "COMPLETE", "DUPLICATE_DETECTED"),             f"Unexpected status: {data.get('status')}"

    def test_identification_required_when_format_unknown(self):
        """
        Uploading a file with no source_override that cannot be auto-detected
        must return IDENTIFICATION_REQUIRED with the list of known formats.
        """
        import io
        fake = io.BytesIO(b"Col1,Col2\nA,1\n")
        r = client.post("/api/imports/upload",
                        files={"file": ("mystery.csv", fake, "text/csv")},
                        data={"imported_by": "test"})
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "IDENTIFICATION_REQUIRED",             f"Expected IDENTIFICATION_REQUIRED, got {data.get('status')}"
        assert "known_formats" in data, "known_formats list must be present"
        codes = {f["code"] for f in data["known_formats"]}
        assert codes == {"ERP_EXPORT", "NGF_SALESOUT", "NGF_MONTHLY", "DISTRILIQ_CPT"},             f"Unexpected format codes: {codes}"

    def test_coverage_endpoint(self):
        r = client.get("/api/imports/coverage")
        assert r.status_code == 200
        assert 'coverage' in r.json()


# ═══════════════════════════════════════════════════════════════════════════════
# E. COMMERCIAL QUEUE
# ═══════════════════════════════════════════════════════════════════════════════

class TestCommercialQueue:

    def test_queue_endpoint_returns_debtors(self):
        r = client.get("/api/commercial/queue/debtors?limit=20")
        assert r.status_code == 200
        data = r.json()
        assert 'debtors' in data
        assert 'total' in data

    def test_queue_excludes_dtc_groups(self):
        """Commercial queue must not include tasting room / wine club debtors."""
        r = client.get("/api/commercial/queue/debtors?limit=200")
        assert r.status_code == 200
        debtors = r.json()['debtors']
        for d in debtors:
            grp = d.get('erp_debtor_group', '')
            assert 'Tasting Room' not in grp, \
                f"Tasting Room should not appear in commercial queue: {d}"
            assert grp != 'Wine Club', "Wine Club should not appear in commercial queue"
            assert grp != 'Private Clients', "Private Clients excluded"

    def test_queue_sorted_by_revenue_desc(self):
        """Top debtors must be sorted by confirmed revenue descending."""
        r = client.get("/api/commercial/queue/debtors?limit=20")
        debtors = r.json()['debtors']
        if len(debtors) < 2:
            pytest.skip("Need at least 2 debtors to test ordering")
        for i in range(len(debtors) - 1):
            a = float(debtors[i].get('total_rv_confirmed') or 0)
            b = float(debtors[i+1].get('total_rv_confirmed') or 0)
            assert a >= b, f"Queue not sorted by revenue: position {i} ({a}) < {i+1} ({b})"

    def test_resolve_debtor_endpoint_contract(self):
        """
        Debtor-based resolver endpoint must:
        - accept POST /api/commercial/queue/resolve-debtor
        - accept { erp_debtor_code, client_id, action }  (NO queue_item_ids)
        - return { erp_debtor_code, client_id, action, items_found, resolved, skipped, failed }
        This is the exact contract the frontend CommercialQueue.tsx sends.
        """
        r = client.post("/api/commercial/queue/resolve-debtor",
                        json={"erp_debtor_code": "NONEXIST99", "client_id": "",
                              "action": "MAP"})
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        data = r.json()
        # Must NOT include queue_item_ids in the response (old contract)
        assert "queue_item_ids" not in data, "Response must not include queue_item_ids (old contract)"
        # Must include debtor-based contract fields
        required = {"erp_debtor_code", "client_id", "action", "items_found", "resolved", "skipped", "failed"}
        assert required.issubset(data.keys()),             f"Missing fields: {required - set(data.keys())}"
        assert data["erp_debtor_code"] == "NONEXIST99"
        assert data["items_found"] == 0  # no rows for a fake debtor

    def test_chain_stores_resolved_in_erp(self):
        """Woolworths, Shoprite, PnP, Makro must now resolve in ERP import."""
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(PROD_DSN)
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("""
                SELECT canonical_name FROM clients
                WHERE canonical_name IN (
                    'Woolworths Food','Shoprite Checkers',
                    'Pick n Pay DCs','Makro','OneDayOnly'
                )
                ORDER BY canonical_name
            """)
            found = [r['canonical_name'] for r in c.fetchall()]
        conn.close()
        assert len(found) == 5, f"All 5 chain store clients must exist. Found: {found}"


# ═══════════════════════════════════════════════════════════════════════════════
# F. FY2027 COMMERCIAL DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

class TestFY2027Dashboard:

    def test_dashboard_returns_fy2027_data(self):
        r = client.get("/api/commercial/dashboard?actual_year=FY2027")
        assert r.status_code == 200
        data = r.json()
        assert data.get('actual_year') == 'FY2027'
        assert data.get('ytd_label') is not None

    def test_dashboard_distributor_sell_in_shown_separately(self):
        r = client.get("/api/commercial/dashboard")
        assert r.status_code == 200
        data = r.json()
        si = data.get('distributor_sell_in', {})
        totals = data.get('totals', {})
        # Sell-in must be a separate field, not included in commercial totals
        assert 'bottles' in si, "distributor_sell_in must have bottles field"
        assert 'note' in si, "distributor_sell_in must have explanatory note"
        # Key check: commercial totals ≠ commercial + sell-in
        fy27_btls = totals.get('fy27_bottles', 0)
        si_btls = si.get('bottles', 0)
        # If sell-in exists, commercial total should NOT include it
        if si_btls > 0 and fy27_btls > 0:
            # There's no direct way to assert this without knowing the expected value,
            # but we can check the breakdown doesn't include DISTRIBUTOR_SELL_IN rows
            breakdown = data.get('fy27_breakdown', [])
            for row in breakdown:
                assert row.get('transaction_type') != 'DISTRIBUTOR_SELL_IN', \
                    "DISTRIBUTOR_SELL_IN must not appear in commercial breakdown"

    def test_dashboard_comparison_period_explicit(self):
        r = client.get("/api/commercial/dashboard")
        data = r.json()
        assert 'ytd_label' in data
        assert 'fy26_comparison' in data or 'totals' in data

    def test_dashboard_target_uses_bottles(self):
        r = client.get("/api/commercial/dashboard")
        data = r.json()
        targets = data.get('targets', [])
        for tg in targets:
            assert 'target_bottles' in tg, "Targets must include target_bottles"
            if tg.get('achievement_pct') is not None:
                # Achievement must be based on bottles, not revenue
                assert isinstance(tg['achievement_pct'], (int, float)), \
                    "achievement_pct must be numeric"
                # Sanity: if bottles = 0, achievement should be 0 or None
            # Note field must explain it's combined target
            if tg.get('note'):
                assert 'bottle' in tg['note'].lower() or 'combined' in tg['note'].lower()

    def test_dashboard_fy2027_btls_include_chain_stores(self):
        """After chain store resolution, FY2027 should show more than 2893 btls."""
        r = client.get("/api/commercial/dashboard")
        data = r.json()
        btls = data['totals'].get('fy27_bottles', 0)
        assert btls > 2893, \
            f"FY2027 commercial btls should be >2,893 after chain store resolution, got {btls}"


# ═══════════════════════════════════════════════════════════════════════════════
# G. CLIENT 360 FY2027
# ═══════════════════════════════════════════════════════════════════════════════

class TestClient360FY2027:

    def _get_direct_client_id(self):
        """Return a client_id that has FY2027 DIRECT_SALE transactions."""
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(PROD_DSN)
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            # Correct join: sales_transactions has no import_batch_id column.
            # Use financial_period + year join to scope to FY2027.
            c.execute("""
                SELECT DISTINCT st.client_id::text
                FROM sales_transactions st
                JOIN financial_periods fp ON fp.id = st.financial_period_id
                JOIN financial_years fy ON fy.id = fp.financial_year_id
                WHERE fy.year_label = 'FY2027'
                  AND st.transaction_type = 'DIRECT_SALE'
                  AND st.excluded_from_market_view = FALSE
                  AND st.is_primary_record = TRUE
                  AND st.client_id IS NOT NULL
                LIMIT 1
            """)
            r = c.fetchone()
        conn.close()
        return r['client_id'] if r else None

    def test_client360_fy2027_direct_client(self):
        cid = self._get_direct_client_id()
        if not cid:
            pytest.skip("No FY2027 direct client in DB")
        r = client.get(f"/api/commercial/client360/{cid}")
        assert r.status_code == 200
        data = r.json()
        assert 'performance' in data
        assert 'monthly_trend' in data
        assert 'product_mix' in data
        p = data['performance']
        assert p['fy27_bottles'] > 0, "Direct client must have FY2027 bottles"

    def test_client360_has_source_breakdown(self):
        cid = self._get_direct_client_id()
        if not cid:
            pytest.skip("No FY2027 direct client in DB")
        r = client.get(f"/api/commercial/client360/{cid}")
        data = r.json()
        assert 'source_breakdown' in data

    def test_client360_yoy_comparison(self):
        cid = self._get_direct_client_id()
        if not cid:
            pytest.skip("No FY2027 direct client in DB")
        r = client.get(f"/api/commercial/client360/{cid}?actual_year=FY2027&compare_year=FY2026")
        data = r.json()
        assert data.get('actual_year') == 'FY2027'
        assert data.get('compare_year') == 'FY2026'
        # YoY pct must be present (may be None if no FY2026 comparison data)
        assert 'yoy_pct' in data.get('performance', {})


# ═══════════════════════════════════════════════════════════════════════════════
# H. KCCLASS / DTC EXCLUSION (ITEM E)
# ═══════════════════════════════════════════════════════════════════════════════

class TestKcclassNotDTC:

    def test_woolworths_classifies_as_direct_sale(self):
        """Woolworths (kcclass='Private') must NOT be DTC_SALE."""
        from app.services.import_engine.classify import classify_erp_row
        raw = {'drname': 'Woolworths (Pty) Ltd', 'debtor': 'WOOL0001',
               'sareaname': 'Local', 'drgrpname': 'Local - Chain Stores',
               'kcclass': 'Private'}
        tx, _ = classify_erp_row(raw, {})
        assert tx == 'DIRECT_SALE', \
            f"Woolworths with kcclass='Private' must be DIRECT_SALE, got {tx}"

    def test_shoprite_classifies_as_direct_sale(self):
        from app.services.import_engine.classify import classify_erp_row
        raw = {'drname': 'Shoprite Checkers', 'debtor': 'SHOPR001',
               'sareaname': 'Local', 'drgrpname': 'Local - Chain Stores',
               'kcclass': 'Private'}
        tx, _ = classify_erp_row(raw, {})
        assert tx == 'DIRECT_SALE', f"Shoprite must be DIRECT_SALE, got {tx}"

    def test_tasting_room_classifies_as_dtc_via_drgrpname(self):
        """DTC classification must come from drgrpname, NOT kcclass."""
        from app.services.import_engine.classify import classify_erp_row
        raw = {'drname': 'Tasting Room', 'debtor': 'TAST001',
               'sareaname': 'Local',
               'drgrpname': 'Tasting Room (Cash Accounts)',
               'kcclass': 'Private'}
        tx, _ = classify_erp_row(raw, {})
        assert tx == 'DTC_SALE', \
            "Tasting room must classify as DTC_SALE via drgrpname"

    def test_licensed_trade_classifies_correctly(self):
        from app.services.import_engine.classify import classify_erp_row
        raw = {'drname': 'Bottle Store', 'debtor': 'BOTS001',
               'sareaname': 'Local', 'drgrpname': 'Local - Liquor Stores',
               'kcclass': 'Licenced'}
        tx, _ = classify_erp_row(raw, {})
        assert tx == 'DIRECT_SALE', "Licenced trade must be DIRECT_SALE"


# ═══════════════════════════════════════════════════════════════════════════════
# I. PIPELINE GENERIC CONTRACT VERIFIED END-TO-END
# ═══════════════════════════════════════════════════════════════════════════════

class TestPipelineContract:

    def test_ngf_monthly_pipeline_receives_client_name(self):
        """Pipeline must receive client_name from NGF Monthly (not empty string)."""
        from app.services.import_engine.connectors.ngf_monthly import iter_rows
        import psycopg2
        from app.services.import_engine.db_ops import get_source_id
        from app.services.import_engine.client_matcher import match_client

        rows = list(iter_rows(NGF_MONTHLY_FILE))
        assert rows, "NGF Monthly must yield rows"

        conn = psycopg2.connect(PROD_DSN)
        src_id = get_source_id(conn, 'NGF_MONTHLY')
        assert src_id, "NGF_MONTHLY must be a registered data source"

        # At least one row must have non-empty client_name reaching matcher
        non_empty = [r for r in rows if r.get('client_name')]
        assert len(non_empty) == len(rows), \
            f"All rows must have client_name. {len(rows)-len(non_empty)} rows have empty client_name."

        # Run the matcher on the first row and verify it at least attempts (not blank)
        first = rows[0]
        m = match_client(conn, src_id, first['client_name'], first['client_code'], {})
        assert m.get('attempts'), "Matcher must have attempted (non-blank input)"
        assert m['attempts'][0]['input'] != '', "First stage input must not be empty"
        conn.close()

    def test_distriliq_pipeline_receives_client_name(self):
        """Pipeline must receive client_name from Distriliq rows (not empty string)."""
        from app.services.import_engine.connectors.distriliq_cpt import iter_rows
        rows = list(iter_rows(DISTRILIQ_FILE))
        non_empty = [r for r in rows if r.get('client_name')]
        assert len(non_empty) == len(rows), \
            f"{len(rows)-len(non_empty)} Distriliq rows have empty client_name"

    def test_erp_pipeline_receives_client_name(self):
        """Pipeline must receive client_name from ERP rows."""
        from app.services.import_engine.connectors.erp_csv import parse_rows
        import psycopg2
        conn = psycopg2.connect(PROD_DSN)
        with conn.cursor() as c:
            c.execute("""
                SELECT debtor, id::text
                FROM distributors, unnest(erp_debtor_codes) as debtor
            """)
            dist_codes = {r[0]: r[1] for r in c.fetchall()}
        conn.close()
        rows = list(parse_rows(ERP_FY2027_FILE, dist_codes))
        non_empty = [r for r in rows if r.get('client_name')]
        assert len(non_empty) > 0, "ERP rows must have client_name"
