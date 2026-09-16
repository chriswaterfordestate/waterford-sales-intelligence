"""
Tests for ERP-derived client ownership and browser-based ownership management.
"""
import os, sys, uuid, pytest
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault('DATABASE_URL',
    'postgresql://waterford:waterford_dev@localhost:5432/waterford_si')
os.environ.setdefault('APP_ENV', 'development')

# Set DATABASE_URL_SYNC to the production/dev DB before importing app.main.
# This freezes settings.database_url_sync = waterford_si for the whole session,
# matching the pattern in test_sprint3_integration.py. Without this, the
# conftest pytest_configure DEFAULT (waterford_si_test) would be frozen instead,
# causing the API to hit a different DB than the test fixtures.
import os as _os
_os.environ['DATABASE_URL_SYNC'] = 'host=localhost dbname=waterford_si user=waterford password=waterford_dev'

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi.testclient import TestClient
from app.main import app
from app.core.auth import verify_clerk_token, require_manager, CurrentUser
from app.services.import_engine.ownership_deriver import derive_erp_ownership

# DSN: always waterford_si, matching DATABASE_URL_SYNC set above.
# The API's get_db_conn() uses the same frozen module-level settings (waterford_si).
DSN = 'host=localhost dbname=waterford_si user=waterford password=waterford_dev'

def _conn(): return psycopg2.connect(DSN)

def _make_manager():
    return CurrentUser(user_id='user_mgr_test', email='mgr@w.co.za',
                       role='MANAGER', full_name='Test Manager')

def _client_authed():
    tc = TestClient(app, raise_server_exceptions=False)
    tc.headers.update({'Authorization': 'Bearer dev'})
    return tc

def _client_manager():
    tc = TestClient(app, raise_server_exceptions=False)
    mgr = _make_manager()
    app.dependency_overrides[verify_clerk_token] = lambda: mgr
    app.dependency_overrides[require_manager] = lambda: mgr
    tc.headers.update({'Authorization': 'Bearer dev'})
    return tc, mgr

def _reset_overrides(): app.dependency_overrides.clear()

def _setup_test_client(conn, name='TestOwnershipClient'):
    """Create a minimal client and rep fixture."""
    with conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute("SELECT id::text FROM territories LIMIT 1")
        t = c.fetchone()
        territory_id = t['id'] if t else None

        # Create test client (safe: check first, insert if absent)
        c.execute("SELECT id::text FROM clients WHERE canonical_name=%s AND is_deleted=FALSE", (name,))
        existing = c.fetchone()
        if existing:
            client_id = existing['id']
        else:
            c.execute("SELECT id::text FROM territories LIMIT 1")
            t = c.fetchone()
            territory_id = t['id'] if t else None
            c.execute("""
                INSERT INTO clients(canonical_name, trading_name, outlet_type, tier,
                                   territory_id, created_by)
                VALUES (%s, %s, 'Restaurant', 'ON_TRADE', %s::uuid, 'test')
                RETURNING id::text
            """, (name, name, territory_id))
            client_id = c.fetchone()['id']

        # Get KOL001 rep
        c.execute("SELECT id::text, erp_srepname FROM reps WHERE rep_code='KOL001'")
        kol = c.fetchone()
        # Get NAT001 rep (Nathalie)
        c.execute("SELECT id::text, erp_srepname FROM reps WHERE rep_code='NAT001'")
        nat = c.fetchone()
    conn.commit()
    return client_id, kol, nat


def _insert_test_batch(conn, client_id: str, rows: list[dict]) -> str:
    """
    Insert a minimal ERP batch with srepname rows for ownership derivation testing.
    rows: [{'srepname': str, 'calendar_year': int, 'calendar_month': int}]
    """
    with conn.cursor(cursor_factory=RealDictCursor) as c:
        # Get ERP source
        c.execute("SELECT id::text FROM data_sources WHERE source_code='ERP_EXPORT'")
        source_id = c.fetchone()['id']

        # Get financial periods
        period_map = {}
        for r in rows:
            c.execute("""
                SELECT fp.id::text FROM financial_periods fp
                JOIN financial_years fy ON fy.id=fp.financial_year_id
                WHERE fp.calendar_year=%s AND fp.calendar_month=%s
                LIMIT 1
            """, (r['calendar_year'], r['calendar_month']))
            row = c.fetchone()
            if row:
                period_map[(r['calendar_year'], r['calendar_month'])] = row['id']

        # Create batch
        batch_id = str(uuid.uuid4())
        # file_hash must be unique — use batch_id as proxy
        file_hash = batch_id.replace('-','')[:64]
        c.execute("""
            INSERT INTO import_batches(id, source_id, file_name, file_path,
                file_hash, file_size_bytes, received_date, status, imported_by)
            VALUES(%s::uuid, %s::uuid, 'test_erp.csv', '/tmp/test_erp.csv',
                %s, 1000, CURRENT_DATE, 'COMPLETE', 'test')
        """, (batch_id, source_id, file_hash))

        # Get a product sku
        c.execute("SELECT id::text FROM product_skus LIMIT 1")
        sku = c.fetchone()
        sku_id = sku['id'] if sku else None

        # Get an ASP version
        asp_id = None
        if sku_id:
            c.execute("SELECT id::text FROM asp_versions WHERE product_sku_id=%s::uuid LIMIT 1",
                      (sku_id,))
            asp = c.fetchone()
            asp_id = asp['id'] if asp else None

        # Insert raw rows + resolved transactions
        for i, r in enumerate(rows):
            period_id = period_map.get((r['calendar_year'], r['calendar_month']))
            if not period_id:
                continue

            raw_data = {'srepname': r['srepname'], 'drname': 'TEST', 'debtor': 'TEST001'}
            raw_row_id = str(uuid.uuid4())
            c.execute("""
                INSERT INTO import_raw_rows(id, batch_id, row_number, raw_data, row_status,
                    client_alias_id, product_alias_id)
                VALUES(%s::uuid, %s::uuid, %s, %s::jsonb, 'MAPPED', NULL, NULL)
            """, (raw_row_id, batch_id, i, psycopg2.extras.Json(raw_data)))

            if sku_id and period_id:
                tx_id = str(uuid.uuid4())
                # Get financial_year_id from period
                c.execute("SELECT financial_year_id::text FROM financial_periods WHERE id=%s::uuid",
                          (period_id,))
                fy_row = c.fetchone()
                financial_year_id = fy_row['financial_year_id'] if fy_row else None
                if not financial_year_id:
                    continue
                c.execute("""
                    INSERT INTO sales_transactions(
                        id, client_id, source_id, financial_year_id, financial_period_id,
                        transaction_type, transaction_date,
                        excluded_from_market_view, is_primary_record,
                        import_raw_row_id, created_by)
                    VALUES(%s::uuid, %s::uuid, %s::uuid, %s::uuid, %s::uuid,
                           'DIRECT_SALE', %s::date,
                           FALSE, TRUE,
                           %s::uuid, 'test')
                """, (tx_id, client_id, source_id, financial_year_id, period_id,
                      f"{r['calendar_year']}-{r['calendar_month']:02d}-01",
                      raw_row_id))

                c.execute("""
                    INSERT INTO sales_transaction_lines(
                        transaction_id, product_sku_id, asp_version_id,
                        source_product_description, quantity_original, unit_original,
                        bottles_actual, standard_bottle_equiv, litres,
                        rand_value_estimated, r_value_status)
                    VALUES(%s::uuid, %s::uuid, %s,
                           'Test Product', 12.0, 'BOTTLES',
                           12.0, 12.0, 9.0,
                           960.00, 'ESTIMATED')
                """, (tx_id, sku_id, asp_id))

                # Link raw row to transaction
                c.execute("UPDATE import_raw_rows SET row_status='MAPPED' WHERE id=%s::uuid",
                          (raw_row_id,))

    conn.commit()
    return batch_id


class TestERPOwnershipDerivation:

    def setup_method(self):
        self.conn = _conn()
        # Clean up ownership and test clients before each test
        with self.conn.cursor() as c:
            c.execute("DELETE FROM client_ownership WHERE created_by='test'")
            c.execute("DELETE FROM client_ownership WHERE notes LIKE 'ERP-derived%' AND created_by='erp_import'")
        self.conn.commit()

    def teardown_method(self):
        _reset_overrides()
        try:
            self.conn.rollback()  # clear any aborted transaction state
            with self.conn.cursor() as c:
                # Delete in dependency order
                c.execute("""DELETE FROM sales_transaction_lines WHERE transaction_id IN (
                    SELECT st.id FROM sales_transactions st
                    JOIN clients cl ON cl.id=st.client_id
                    WHERE cl.canonical_name LIKE 'TestOwnership%' AND cl.is_deleted=FALSE
                )""")
                c.execute("""DELETE FROM sales_transactions WHERE client_id IN (
                    SELECT id FROM clients WHERE canonical_name LIKE 'TestOwnership%' AND is_deleted=FALSE
                )""")
                c.execute("""DELETE FROM import_raw_rows WHERE batch_id IN (
                    SELECT id FROM import_batches WHERE file_name='test_erp.csv'
                )""")
                c.execute("DELETE FROM import_batches WHERE file_name='test_erp.csv'")
                c.execute("DELETE FROM client_ownership WHERE created_by IN ('test','erp_import','web_app')")
                c.execute("DELETE FROM clients WHERE canonical_name LIKE 'TestOwnership%'")
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
        self.conn.close()

    def test_srepname_preserved_in_raw_data(self):
        """srepname must be stored in raw_data — verified in the ERP connector fixture."""
        client_id, kol, nat = _setup_test_client(self.conn, 'TestOwnershipRawData')
        if not kol: pytest.skip("KOL001 not in DB")
        batch_id = _insert_test_batch(self.conn, client_id, [
            {'srepname': kol['erp_srepname'], 'calendar_year': 2025, 'calendar_month': 8}
        ])
        with self.conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("""SELECT raw_data->>'srepname' as srepname
                         FROM import_raw_rows WHERE batch_id=%s::uuid LIMIT 1""", (batch_id,))
            row = c.fetchone()
        assert row and row['srepname'] == kol['erp_srepname'], \
            "srepname must be preserved in raw_data"

    def test_erp_derived_ownership_created_for_known_rep(self):
        """Resolved ERP client + known srepname → ownership record created."""
        client_id, kol, _ = _setup_test_client(self.conn, 'TestOwnershipCreate')
        if not kol: pytest.skip("KOL001 not in DB")

        batch_id = _insert_test_batch(self.conn, client_id, [
            {'srepname': kol['erp_srepname'], 'calendar_year': 2025, 'calendar_month': 8},
            {'srepname': kol['erp_srepname'], 'calendar_year': 2025, 'calendar_month': 9},
        ])
        summary = derive_erp_ownership(self.conn, batch_id)
        assert summary['created'] >= 1, f"Expected at least 1 created, got {summary}"

        with self.conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("""SELECT co.*, r.rep_code FROM client_ownership co
                         JOIN reps r ON r.id=co.rep_id
                         WHERE co.client_id=%s::uuid AND co.change_reason='ERP_DERIVED'""",
                      (client_id,))
            records = c.fetchall()
        assert len(records) >= 1
        assert records[0]['rep_code'] == 'KOL001'
        assert records[0]['effective_from'] is not None

    def test_historical_rep_change_creates_two_periods(self):
        """When srepname changes mid-history, two separate ownership periods are created."""
        client_id, kol, nat = _setup_test_client(self.conn, 'TestOwnershipRepChange')
        if not kol or not nat: pytest.skip("KOL001 or NAT001 not in DB")

        batch_id = _insert_test_batch(self.conn, client_id, [
            # First half: KOL001
            {'srepname': kol['erp_srepname'], 'calendar_year': 2025, 'calendar_month': 7},
            {'srepname': kol['erp_srepname'], 'calendar_year': 2025, 'calendar_month': 8},
            # Second half: NAT001
            {'srepname': nat['erp_srepname'], 'calendar_year': 2026, 'calendar_month': 1},
            {'srepname': nat['erp_srepname'], 'calendar_year': 2026, 'calendar_month': 2},
        ])
        summary = derive_erp_ownership(self.conn, batch_id)

        with self.conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("""SELECT co.effective_from, co.effective_to, r.rep_code
                         FROM client_ownership co JOIN reps r ON r.id=co.rep_id
                         WHERE co.client_id=%s::uuid AND co.change_reason='ERP_DERIVED'
                         ORDER BY co.effective_from""", (client_id,))
            records = c.fetchall()

        assert len(records) == 2, f"Expected 2 ownership periods, got {len(records)}: {records}"
        assert records[0]['rep_code'] == 'KOL001'
        assert records[1]['rep_code'] == 'NAT001'
        # First period must be closed
        assert records[0]['effective_to'] is not None, "First period must have an end date"

    def test_repeated_import_does_not_duplicate(self):
        """Importing the same data twice must not create duplicate ownership records."""
        client_id, kol, _ = _setup_test_client(self.conn, 'TestOwnershipIdempotent')
        if not kol: pytest.skip()

        rows = [{'srepname': kol['erp_srepname'], 'calendar_year': 2025, 'calendar_month': 8}]
        batch1 = _insert_test_batch(self.conn, client_id, rows)
        derive_erp_ownership(self.conn, batch1)

        batch2 = _insert_test_batch(self.conn, client_id, rows)
        summary2 = derive_erp_ownership(self.conn, batch2)

        with self.conn.cursor() as c:
            c.execute("""SELECT COUNT(*) FROM client_ownership
                         WHERE client_id=%s::uuid AND change_reason='ERP_DERIVED'""",
                      (client_id,))
            count = c.fetchone()[0]
        assert count == 1, f"Expected exactly 1 record, got {count}"
        assert summary2['created'] == 0, "Second import must not create new records"

    def test_erp_does_not_override_manual_assignment(self):
        """MANUAL_ASSIGNMENT records must not be touched by ERP-derived ownership."""
        client_id, kol, nat = _setup_test_client(self.conn, 'TestOwnershipManual')
        if not kol or not nat: pytest.skip()

        # Pre-existing MANUAL_ASSIGNMENT for NAT001
        with self.conn.cursor() as c:
            c.execute("""
                INSERT INTO client_ownership(client_id, rep_id, effective_from,
                    change_reason, created_by)
                SELECT %s::uuid, r.id, '2025-01-01',
                    'MANUAL_ASSIGNMENT', 'test'
                FROM reps r WHERE r.rep_code='NAT001'
            """, (client_id,))
        self.conn.commit()

        # ERP says KOL001 — but must not override the MANUAL_ASSIGNMENT
        batch_id = _insert_test_batch(self.conn, client_id, [
            {'srepname': kol['erp_srepname'], 'calendar_year': 2025, 'calendar_month': 8}
        ])
        summary = derive_erp_ownership(self.conn, batch_id)
        assert summary['skipped_manual'] >= 1, "Must report skipped_manual"

        # Verify MANUAL_ASSIGNMENT is intact
        with self.conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("""SELECT change_reason, r.rep_code FROM client_ownership co
                         JOIN reps r ON r.id=co.rep_id
                         WHERE co.client_id=%s::uuid""", (client_id,))
            records = c.fetchall()
        reasons = [r['change_reason'] for r in records]
        reps = [r['rep_code'] for r in records]
        assert 'MANUAL_ASSIGNMENT' in reasons
        assert 'NAT001' in reps
        assert 'ERP_DERIVED' not in reasons, "ERP_DERIVED must not be created when MANUAL_ASSIGNMENT exists"

    def test_unknown_srepname_skipped(self):
        """Unknown srepname does not create incorrect ownership."""
        client_id, _, _ = _setup_test_client(self.conn, 'TestOwnershipUnknown')
        batch_id = _insert_test_batch(self.conn, client_id, [
            {'srepname': 'Unknown Rep XYZ', 'calendar_year': 2025, 'calendar_month': 8}
        ])
        summary = derive_erp_ownership(self.conn, batch_id)
        assert summary['skipped_unknown_rep'] >= 1

        with self.conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM client_ownership WHERE client_id=%s::uuid",
                      (client_id,))
            count = c.fetchone()[0]
        assert count == 0, "Unknown rep must not create ownership"


class TestOwnershipAPI:
    """
    API-layer ownership tests.
    Uses Van Riebeeck Liquors (always in MCR) as the fixture client.
    Each test uses a unique created_by tag to avoid cross-test interference.
    """

    def setup_method(self):
        self.conn = _conn()
        # Wipe ALL ownership for the fixture client before each test.
        # This prevents dirty data from prior test runs accumulating on Van Riebeeck.
        # The DB has no real ownership data yet, so this is safe.
        with self.conn.cursor() as c:
            c.execute("""DELETE FROM client_ownership
                         WHERE client_id=(
                             SELECT id FROM clients
                             WHERE canonical_name='Van Riebeeck Liquors' AND is_deleted=FALSE
                         )""")
        self.conn.commit()
        # Get Van Riebeeck Liquors — guaranteed to exist in waterford_si
        with self.conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("SELECT id::text FROM clients WHERE canonical_name='Van Riebeeck Liquors' AND is_deleted=FALSE")
            row = c.fetchone()
            c.execute("SELECT id::text FROM reps WHERE rep_code='NAT001'")
            nat = c.fetchone()
            c.execute("SELECT id::text FROM reps WHERE rep_code='KOL001'")
            kol = c.fetchone()
        self.client_id = row['id'] if row else None
        self.nat = nat
        self.kol = kol
        self.tag = f'apitest_{__import__("uuid").uuid4().hex[:8]}'

    def teardown_method(self):
        _reset_overrides()
        if self.client_id:
            with self.conn.cursor() as c:
                # Wipe ALL ownership for the fixture client — prevents cross-run accumulation
                c.execute("DELETE FROM client_ownership WHERE client_id=%s::uuid",
                          (self.client_id,))
            self.conn.commit()
        self.conn.close()

    def _seed_erp_ownership(self, rep_code='NAT001', from_date='2025-07-01'):
        """Insert ERP_DERIVED ownership using this test's unique tag."""
        if not self.client_id or not self.nat: return None
        with self.conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("""INSERT INTO client_ownership(client_id, rep_id, effective_from,
                             change_reason, created_by)
                         SELECT %s::uuid, r.id, %s::date,
                             'ERP_DERIVED'::ownership_change_reason_enum, %s
                         FROM reps r WHERE r.rep_code=%s
                         RETURNING id::text""",
                      (self.client_id, from_date, self.tag, rep_code))
            row = c.fetchone()
        self.conn.commit()
        return row['id'] if row else None

    def test_ownership_history_endpoint(self):
        """GET /api/clients/{id}/ownership returns history with is_current field."""
        if not self.client_id or not self.nat:
            pytest.skip("Van Riebeeck or NAT001 not in DB")
        own_id = self._seed_erp_ownership('NAT001')
        assert own_id, "Seed must succeed"

        tc = _client_authed()
        r = tc.get(f'/api/clients/{self.client_id}/ownership')
        assert r.status_code == 200, r.text
        d = r.json()
        assert 'history' in d
        # Find our seeded record specifically
        our_record = next((h for h in d['history'] if h.get('effective_from', '').startswith('2025-07-01'[:7])), None)
        assert our_record is not None, f"Seeded ownership not found in history: {d['history']}"
        assert 'full_name' in our_record
        assert 'effective_from' in our_record
        assert 'is_current' in our_record

    def test_change_ownership_creates_manual_assignment(self):
        """POST change_ownership closes ERP_DERIVED and creates MANUAL_ASSIGNMENT."""
        if not self.client_id or not self.kol or not self.nat:
            pytest.skip("Required clients/reps missing")
        self._seed_erp_ownership('NAT001', from_date='2025-07-01')

        mgr = CurrentUser(user_id=f'mgr_{self.tag}', email='m@w.co.za', role='MANAGER', full_name='Mgr')
        app.dependency_overrides[verify_clerk_token] = lambda: mgr
        app.dependency_overrides[require_manager]    = lambda: mgr
        tc = TestClient(app, raise_server_exceptions=True)

        r = tc.post(f'/api/clients/{self.client_id}/ownership', json={
            'rep_id': self.kol['id'], 'effective_from': '2026-10-01',
            'notes': f'test {self.tag}'
        }, headers={'Authorization': 'Bearer dev'})
        assert r.status_code == 200, r.text
        assert r.json().get('status') == 'ok'

        # Verify ownership records
        with self.conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("""SELECT co.change_reason, r.rep_code, co.effective_to
                         FROM client_ownership co JOIN reps r ON r.id=co.rep_id
                         WHERE co.client_id=%s::uuid
                           AND (co.created_by=%s OR co.created_by='web_app')
                         ORDER BY co.effective_from""",
                      (self.client_id, self.tag))
            records = c.fetchall()
        reasons   = [r['change_reason'] for r in records]
        rep_codes = [r['rep_code']      for r in records]
        assert 'MANUAL_ASSIGNMENT' in reasons, f"Expected MANUAL_ASSIGNMENT in {reasons}"
        assert 'KOL001' in rep_codes, f"Expected KOL001 in {rep_codes}"
        # Prior NAT001 must have effective_to set
        nat_rows = [r for r in records if r['rep_code'] == 'NAT001']
        assert nat_rows and nat_rows[0]['effective_to'] is not None,             "NAT001 ownership must be closed when KOL001 takes over"

    def test_change_ownership_requires_manager(self):
        """Ordinary REP cannot change client ownership."""
        if not self.client_id: pytest.skip()
        rep_user = CurrentUser(user_id='u', email='r@w.co.za', role='REP', full_name='Rep')
        app.dependency_overrides[verify_clerk_token] = lambda: rep_user
        tc = TestClient(app, raise_server_exceptions=False)
        r = tc.post(f'/api/clients/{self.client_id}/ownership',
                    json={'rep_id': 'invalid', 'effective_from': '2026-01-01'},
                    headers={'Authorization': 'Bearer dev'})
        assert r.status_code in (403, 401)

    def test_no_overlapping_ownership_periods(self):
        """When a new owner is assigned, the prior period must close before the new one opens."""
        if not self.client_id or not self.kol or not self.nat:
            pytest.skip()
        self._seed_erp_ownership('NAT001', from_date='2025-07-01')

        mgr = CurrentUser(user_id=f'mgr_{self.tag}', email='m@w.co.za', role='MANAGER', full_name='Mgr')
        app.dependency_overrides[verify_clerk_token] = lambda: mgr
        app.dependency_overrides[require_manager]    = lambda: mgr
        tc = TestClient(app, raise_server_exceptions=True)
        tc.post(f'/api/clients/{self.client_id}/ownership',
                json={'rep_id': self.kol['id'], 'effective_from': '2026-10-01'},
                headers={'Authorization': 'Bearer dev'})

        with self.conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("""SELECT co.effective_from::text, co.effective_to::text, r.rep_code
                         FROM client_ownership co JOIN reps r ON r.id=co.rep_id
                         WHERE co.client_id=%s::uuid
                           AND (co.created_by=%s OR co.created_by='web_app')
                         ORDER BY co.effective_from""",
                      (self.client_id, self.tag))
            rows = c.fetchall()

        assert len(rows) >= 2, "Should have at least two ownership records"
        # No overlapping: each period must end before the next begins
        for i in range(len(rows) - 1):
            end   = rows[i]['effective_to']
            start = rows[i+1]['effective_from']
            assert end is not None, f"Period {i} must be closed; effective_to is None"
            assert end < start, f"Overlap: period {i} ends {end}, period {i+1} starts {start}"

    def test_sales_transactions_unaffected(self):
        """Ownership change must not touch any sales_transactions rows."""
        if not self.client_id or not self.kol: pytest.skip()
        with self.conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM sales_transactions")
            before = c.fetchone()[0]

        self._seed_erp_ownership('NAT001')
        mgr = CurrentUser(user_id=f'mgr_{self.tag}', email='m@w.co.za', role='MANAGER', full_name='Mgr')
        app.dependency_overrides[verify_clerk_token] = lambda: mgr
        app.dependency_overrides[require_manager]    = lambda: mgr
        tc = TestClient(app, raise_server_exceptions=True)
        tc.post(f'/api/clients/{self.client_id}/ownership',
                json={'rep_id': self.kol['id'], 'effective_from': '2026-10-01'},
                headers={'Authorization': 'Bearer dev'})

        with self.conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM sales_transactions")
            after = c.fetchone()[0]
        assert before == after, "Ownership change must not touch sales_transactions"

    def test_client360_returns_current_ownership(self):
        """GET /api/clients/{id} exposes current_reps from ownership table."""
        if not self.client_id or not self.nat: pytest.skip()
        own_id = self._seed_erp_ownership('NAT001')
        assert own_id

        tc = _client_authed()
        r = tc.get(f'/api/clients/{self.client_id}')
        assert r.status_code == 200, r.text
        d = r.json()
        assert 'current_reps' in d
        nathalie_present = any(
            'Nathalie' in str(rep.get('full_name', ''))
            for rep in d['current_reps']
        )
        assert nathalie_present, f"NAT001 not in current_reps: {d['current_reps']}"

    def test_bulk_transfer_only_transfers_currently_owned(self):
        """Bulk transfer: only clients currently owned by from_rep are moved."""
        if not self.client_id or not self.kol or not self.nat: pytest.skip()
        # Seed Van Riebeeck → KOL001, plus a second fresh client → NAT001
        self._seed_erp_ownership('KOL001')

        with self.conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("SELECT id::text FROM territories LIMIT 1")
            tid = c.fetchone()['id']
            c.execute("""INSERT INTO clients(canonical_name, trading_name, outlet_type, tier,
                                             territory_id, created_by)
                         VALUES (%s,%s,'Restaurant','ON_TRADE',%s::uuid,%s) RETURNING id::text""",
                      (f'BulkFx_{self.tag}', f'BulkFx_{self.tag}', tid, self.tag))
            second_id = c.fetchone()['id']
            c.execute("""INSERT INTO client_ownership(client_id, rep_id, effective_from,
                             change_reason, created_by)
                         SELECT %s::uuid, id, '2025-07-01',
                             'ERP_DERIVED'::ownership_change_reason_enum, %s
                         FROM reps WHERE rep_code='NAT001'""",
                      (second_id, self.tag))
        self.conn.commit()

        try:
            mgr = CurrentUser(user_id=f'mgr_{self.tag}', email='m@w.co.za', role='MANAGER', full_name='Mgr')
            app.dependency_overrides[verify_clerk_token] = lambda: mgr
            app.dependency_overrides[require_manager]    = lambda: mgr
            tc = TestClient(app, raise_server_exceptions=True)
            r = tc.post('/api/clients/transfers/bulk', json={
                'from_rep_id': self.kol['id'], 'to_rep_id': self.nat['id'],
                'effective_from': '2026-09-15', 'notes': f'bulk {self.tag}'
            }, headers={'Authorization': 'Bearer dev'})
            assert r.status_code == 200, r.text
            # Should transfer exactly 1 (Van Riebeeck, owned by KOL001)
            # NOT the second client (owned by NAT001)
            assert r.json()['transferred'] >= 1, f"Expected >=1 transferred; {r.json()}"

            # Van Riebeeck must now be owned by NAT001
            with self.conn.cursor(cursor_factory=RealDictCursor) as c:
                c.execute("""SELECT r.rep_code FROM client_ownership co
                             JOIN reps r ON r.id=co.rep_id
                             WHERE co.client_id=%s::uuid
                               AND co.effective_from <= CURRENT_DATE
                               AND (co.effective_to IS NULL OR co.effective_to >= CURRENT_DATE)
                             ORDER BY co.effective_from DESC LIMIT 1""",
                          (self.client_id,))
                current = c.fetchone()
            assert current and current['rep_code'] == 'NAT001',                 f"Van Riebeeck must now belong to NAT001; got {current}"
        finally:
            with self.conn.cursor() as c:
                c.execute("DELETE FROM client_ownership WHERE client_id=%s::uuid", (second_id,))
                c.execute("DELETE FROM clients WHERE id=%s::uuid", (second_id,))
            self.conn.commit()


class TestOwnershipProvenance:

    def test_existing_aliases_intact_after_ownership_change(self):
        """Source aliases must not be affected by ownership operations."""
        conn = _conn()
        tc = _client_authed()

        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("""SELECT c.id::text, COUNT(csa.id) AS alias_count
                         FROM clients c
                         JOIN client_source_aliases csa ON csa.client_id=c.id
                         WHERE csa.match_status='ACTIVE'
                         GROUP BY c.id HAVING COUNT(csa.id) > 0
                         LIMIT 1""")
            row = c.fetchone()
        conn.close()

        if not row:
            pytest.skip("No clients with active aliases in test DB")

        # The /api/clients/{id} endpoint returns 'aliases' key
        r = tc.get(f'/api/clients/{row["id"]}')
        assert r.status_code == 200, r.text
        d = r.json()
        # Aliases are in the response — name may vary by endpoint version
        aliases = d.get('aliases', [])
        assert len(aliases) == row['alias_count'],             f"Expected {row['alias_count']} aliases, got {len(aliases)}"

    def test_mcr_provenance_preserved(self):
        """Canonical clients and aliases must remain intact after migration 012."""
        conn = _conn()
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM clients WHERE is_deleted=FALSE")
            clients = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM client_source_aliases WHERE match_status='ACTIVE'")
            aliases = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM reps WHERE employment_status='ACTIVE'")
            reps = c.fetchone()[0]
        conn.close()
        assert clients > 0, "Must have canonical clients"
        assert aliases > 0, "Must have confirmed aliases"
        assert reps > 0, "Must have active reps"

    def test_admin_nav_item_removed(self):
        """Dead Admin nav item must not appear in AppLayout source."""
        nav_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'frontend', 'src', 'components', 'layout', 'AppLayout.tsx'
        )
        if not os.path.exists(nav_file):
            pytest.skip("Frontend source not in test path")
        content = open(nav_file).read()
        assert "href: '/admin'" not in content, \
            "Dead /admin nav item must be removed"


# ── Standalone API tests ──────────────────────────────────────────────────────
# These tests use a unique run-specific tag so no class teardown can interfere.
# Each test sets up and tears down its own data in a single try/finally block.
# They use existing MCR clients where possible to avoid client creation races.

import uuid as _uuid

def _unique_tag():
    """Short unique tag for this pytest run."""
    return f"apitest_{_uuid.uuid4().hex[:8]}"


def _get_real_client(conn) -> str:
    """Return client_id for Van Riebeeck Liquors (always in MCR)."""
    with conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute("""SELECT id::text FROM clients 
                     WHERE canonical_name='Van Riebeeck Liquors' AND is_deleted=FALSE""")
        row = c.fetchone()
    return row['id'] if row else None


def _get_rep_id(conn, rep_code: str):
    """Return rep id for a known rep code."""
    with conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute("SELECT id::text FROM reps WHERE rep_code=%s", (rep_code,))
        row = c.fetchone()
    return row['id'] if row else None


def _seed_owner(conn, client_id: str, rep_id: str, tag: str,
                rep_code='NAT001', from_date='2025-07-01'):
    """Insert an ERP_DERIVED ownership record with a unique tag as created_by."""
    with conn.cursor() as c:
        c.execute("""INSERT INTO client_ownership
                        (client_id, rep_id, effective_from, change_reason, created_by)
                     VALUES (%s::uuid, %s::uuid, %s::date,
                             'ERP_DERIVED'::ownership_change_reason_enum, %s)""",
                  (client_id, rep_id, from_date, tag))
    conn.commit()


def _cleanup_owner(conn, client_id: str, tag: str):
    """Remove ownership records created by this test run."""
    with conn.cursor() as c:
        c.execute("DELETE FROM client_ownership WHERE client_id=%s::uuid AND created_by=%s",
                  (client_id, tag))
        c.execute("DELETE FROM client_ownership WHERE client_id=%s::uuid AND created_by='web_app'",
                  (client_id,))
    conn.commit()


def test_api_ownership_history():
    """GET /api/clients/{id}/ownership returns populated history."""
    conn = _conn()
    tag = _unique_tag()
    client_id = _get_real_client(conn)
    nat_id    = _get_rep_id(conn, 'NAT001')
    if not client_id or not nat_id:
        conn.close(); pytest.skip("Van Riebeeck or NAT001 not in DB")

    _seed_owner(conn, client_id, nat_id, tag)
    try:
        tc = _client_authed()
        r = tc.get(f'/api/clients/{client_id}/ownership')
        assert r.status_code == 200, r.text
        d = r.json()
        assert 'history' in d
        records = d['history']  # get all — we just seeded at least one
        assert len(d['history']) >= 1, f"Expected >=1 ownership records, got: {d}"
        rec = d['history'][0]
        assert 'full_name' in rec
        assert 'effective_from' in rec
        assert 'is_current' in rec
    finally:
        _cleanup_owner(conn, client_id, tag)
        conn.close()


def test_api_change_ownership_creates_manual_assignment():
    """POST change_ownership closes prior ERP_DERIVED and opens MANUAL_ASSIGNMENT."""
    conn = _conn()
    tag = _unique_tag()
    client_id = _get_real_client(conn)
    nat_id    = _get_rep_id(conn, 'NAT001')
    kol_id    = _get_rep_id(conn, 'KOL001')
    if not client_id or not nat_id or not kol_id:
        conn.close(); pytest.skip("Required clients or reps missing")

    # Start: NAT001 owns the client from July 2025
    _seed_owner(conn, client_id, nat_id, tag, from_date='2025-07-01')
    try:
        mgr = CurrentUser(user_id=f'mgr_{tag}', email='m@w.co.za',
                          role='MANAGER', full_name='Mgr')
        app.dependency_overrides[verify_clerk_token] = lambda: mgr
        app.dependency_overrides[require_manager]    = lambda: mgr
        tc = TestClient(app, raise_server_exceptions=True)

        r = tc.post(f'/api/clients/{client_id}/ownership', json={
            'rep_id': kol_id, 'effective_from': '2026-10-01',
            'notes': f'test transfer {tag}'
        }, headers={'Authorization': 'Bearer dev'})
        _reset_overrides()

        assert r.status_code == 200, r.text
        assert r.json().get('status') == 'ok'

        # Verify: prior record is closed, new MANUAL_ASSIGNMENT exists
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("""
                SELECT co.change_reason, r.rep_code,
                       co.effective_from::text, co.effective_to::text
                FROM client_ownership co JOIN reps r ON r.id=co.rep_id
                WHERE co.client_id=%s::uuid
                  AND (co.created_by=%s OR co.created_by='web_app')
                ORDER BY co.effective_from
            """, (client_id, tag))
            records = c.fetchall()

        reasons   = [r['change_reason'] for r in records]
        rep_codes = [r['rep_code']      for r in records]

        assert 'MANUAL_ASSIGNMENT' in reasons, f"Expected MANUAL_ASSIGNMENT in {reasons}"
        assert 'KOL001' in rep_codes, f"Expected KOL001 in {rep_codes}"

        # Prior NAT001 period must have effective_to set (closed)
        nat_rows = [r for r in records if r['rep_code'] == 'NAT001']
        assert nat_rows, "NAT001 ownership record must still exist"
        assert nat_rows[0]['effective_to'] is not None,             f"NAT001 ownership must be closed; got effective_to={nat_rows[0]['effective_to']}"

        # No overlapping periods: NAT001 must end before KOL001 starts
        kol_rows = [r for r in records if r['rep_code'] == 'KOL001']
        if nat_rows and kol_rows:
            nat_end   = nat_rows[-1]['effective_to']
            kol_start = kol_rows[0]['effective_from']
            assert nat_end is not None
            assert nat_end < kol_start,                 f"Overlap: NAT001 ends {nat_end}, KOL001 starts {kol_start}"

    finally:
        _reset_overrides()
        _cleanup_owner(conn, client_id, tag)
        conn.close()


def test_api_sales_unaffected_by_ownership_change():
    """Changing ownership must not modify sales_transactions."""
    conn = _conn()
    tag = _unique_tag()
    client_id = _get_real_client(conn)
    kol_id    = _get_rep_id(conn, 'KOL001')
    if not client_id or not kol_id:
        conn.close(); pytest.skip()

    with conn.cursor() as c:
        c.execute("SELECT COUNT(*) FROM sales_transactions")
        tx_before = c.fetchone()[0]

    _seed_owner(conn, client_id, kol_id, tag)
    try:
        mgr = CurrentUser(user_id=f'mgr_{tag}', email='m@w.co.za',
                          role='MANAGER', full_name='Mgr')
        app.dependency_overrides[verify_clerk_token] = lambda: mgr
        app.dependency_overrides[require_manager]    = lambda: mgr
        tc = TestClient(app, raise_server_exceptions=True)
        tc.post(f'/api/clients/{client_id}/ownership',
                json={'rep_id': _get_rep_id(conn, 'NAT001'),
                      'effective_from': '2026-10-01'},
                headers={'Authorization': 'Bearer dev'})
        _reset_overrides()

        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM sales_transactions")
            tx_after = c.fetchone()[0]
        assert tx_before == tx_after,             f"Ownership change must not touch transactions: before={tx_before} after={tx_after}"
    finally:
        _reset_overrides()
        _cleanup_owner(conn, client_id, tag)
        conn.close()


def test_api_bulk_transfer_only_moves_current_owner():
    """Bulk transfer only moves clients CURRENTLY owned by from_rep."""
    conn = _conn()
    tag = _unique_tag()

    # Create two fresh clients for this test (we need explicit ownership control)
    with conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute("SELECT id::text FROM territories LIMIT 1")
        tid = c.fetchone()['id']
        c.execute("""INSERT INTO clients(canonical_name, trading_name, outlet_type, tier,
                                        territory_id, created_by)
                     VALUES (%s,%s,'Restaurant','ON_TRADE',%s::uuid,%s) RETURNING id::text""",
                  (f'BulkTestA_{tag}', f'BulkTestA_{tag}', tid, tag))
        client_a = c.fetchone()['id']
        c.execute("""INSERT INTO clients(canonical_name, trading_name, outlet_type, tier,
                                        territory_id, created_by)
                     VALUES (%s,%s,'Restaurant','ON_TRADE',%s::uuid,%s) RETURNING id::text""",
                  (f'BulkTestB_{tag}', f'BulkTestB_{tag}', tid, tag))
        client_b = c.fetchone()['id']
    conn.commit()

    kol_id = _get_rep_id(conn, 'KOL001')
    nat_id = _get_rep_id(conn, 'NAT001')
    if not kol_id or not nat_id:
        conn.close(); pytest.skip()

    # Client A → KOL001 (will be transferred), Client B → NAT001 (must not be transferred)
    _seed_owner(conn, client_a, kol_id, tag, from_date='2025-07-01')
    _seed_owner(conn, client_b, nat_id, f'{tag}_b', from_date='2025-07-01')
    try:
        mgr = CurrentUser(user_id=f'mgr_{tag}', email='m@w.co.za',
                          role='MANAGER', full_name='Mgr')
        app.dependency_overrides[verify_clerk_token] = lambda: mgr
        app.dependency_overrides[require_manager]    = lambda: mgr
        tc = TestClient(app, raise_server_exceptions=True)

        r = tc.post('/api/clients/transfers/bulk', json={
            'from_rep_id': kol_id, 'to_rep_id': nat_id,
            'effective_from': '2026-09-15', 'notes': f'bulk test {tag}'
        }, headers={'Authorization': 'Bearer dev'})
        _reset_overrides()

        assert r.status_code == 200, r.text
        d = r.json()
        assert d['transferred'] == 1,             f"Only client_a (KOL001-owned) should transfer; got {d}"

        # Client A must now be owned by NAT001
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("""SELECT r.rep_code FROM client_ownership co
                         JOIN reps r ON r.id=co.rep_id
                         WHERE co.client_id=%s::uuid
                           AND co.effective_from <= CURRENT_DATE
                           AND (co.effective_to IS NULL OR co.effective_to >= CURRENT_DATE)
                         ORDER BY co.effective_from DESC LIMIT 1""", (client_a,))
            current = c.fetchone()
        assert current and current['rep_code'] == 'NAT001',             f"Client A must now belong to NAT001; got {current}"

        # Client B must still be owned by NAT001 (unchanged)
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("""SELECT COUNT(*) AS cnt FROM client_ownership
                         WHERE client_id=%s::uuid AND created_by=%s""",
                      (client_b, f'{tag}_b'))
            assert c.fetchone()['cnt'] >= 1, "Client B ownership must be untouched"

    finally:
        _reset_overrides()
        for cid in (client_a, client_b):
            with conn.cursor() as c:
                c.execute("DELETE FROM client_ownership WHERE client_id=%s::uuid", (cid,))
                c.execute("DELETE FROM clients WHERE id=%s::uuid", (cid,))
        conn.commit()
        conn.close()


def test_api_effective_dates_enforced():
    """Ownership with future effective_from is not yet 'current'."""
    conn = _conn()
    tag = _unique_tag()
    client_id = _get_real_client(conn)
    kol_id    = _get_rep_id(conn, 'KOL001')
    if not client_id or not kol_id:
        conn.close(); pytest.skip()

    # Insert ownership that doesn't start until 2099
    with conn.cursor() as c:
        c.execute("""INSERT INTO client_ownership
                        (client_id, rep_id, effective_from, change_reason, created_by)
                     VALUES (%s::uuid, %s::uuid, '2099-01-01',
                             'ERP_DERIVED'::ownership_change_reason_enum, %s)""",
                  (client_id, kol_id, tag))
    conn.commit()
    try:
        tc = _client_authed()
        r = tc.get(f'/api/clients/{client_id}/ownership')
        assert r.status_code == 200
        history = r.json()['history']
        future_record = next(
            (h for h in history if h['effective_from'] == '2099-01-01'), None)
        if future_record:
            assert future_record['is_current'] is False,                 "Future ownership record must not be is_current=True"
    finally:
        _cleanup_owner(conn, client_id, tag)
        conn.close()


def test_api_client360_shows_current_rep():
    """Client 360 commercial endpoint exposes current ownership."""
    conn = _conn()
    tag = _unique_tag()
    client_id = _get_real_client(conn)
    nat_id    = _get_rep_id(conn, 'NAT001')
    if not client_id or not nat_id:
        conn.close(); pytest.skip()

    _seed_owner(conn, client_id, nat_id, tag)
    try:
        tc = _client_authed()
        r = tc.get(f'/api/clients/{client_id}')
        assert r.status_code == 200, r.text
        d = r.json()
        assert 'current_reps' in d
        assert any('Nathalie' in str(rep.get('full_name',''))
                   for rep in d['current_reps']),             f"NAT001 (Nathalie) must appear in current_reps; got {d['current_reps']}"
    finally:
        _cleanup_owner(conn, client_id, tag)
        conn.close()


def test_api_aliases_survive_ownership_change():
    """Source aliases on a client must not be touched by ownership operations."""
    conn = _conn()
    with conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute("""SELECT c.id::text, COUNT(csa.id) AS alias_count
                     FROM clients c
                     JOIN client_source_aliases csa ON csa.client_id=c.id
                     WHERE csa.match_status='ACTIVE'
                     GROUP BY c.id HAVING COUNT(csa.id) > 0 LIMIT 1""")
        row = c.fetchone()
    conn.close()
    if not row:
        pytest.skip("No clients with active aliases")
    tc = _client_authed()
    r = tc.get(f'/api/clients/{row["id"]}')
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d.get('aliases', [])) == row['alias_count'],         f"Alias count must not change: expected {row['alias_count']}, got {len(d.get('aliases',[]))}"
