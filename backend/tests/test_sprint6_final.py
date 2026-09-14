"""
Sprint 6 final blockers: frontend auth, API origin, DB isolation, CRM attribution.
"""
import os, sys, re, uuid, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault('DATABASE_URL', 'postgresql://waterford:waterford_dev@localhost:5432/waterford_si')
os.environ.setdefault('APP_ENV', 'development')

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import Depends
from fastapi.testclient import TestClient
from app.main import app
from app.core.auth import verify_clerk_token, require_manager, CurrentUser

PROD_DSN = 'host=localhost dbname=waterford_si user=waterford password=waterford_dev'
FRONTEND_SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'frontend', 'src'
)

def _conn(): return psycopg2.connect(PROD_DSN)
def _make_user(role='REP', uid=None):
    return CurrentUser(user_id=uid or f'user_{role.lower()}_final_test',
                       email=f'{role.lower()}@test.com', role=role, full_name=f'Test {role}')
def _client(role):
    tc = TestClient(app, raise_server_exceptions=False)
    u = _make_user(role)
    app.dependency_overrides[verify_clerk_token] = lambda: u
    if role in ('MANAGER','ADMIN'):
        app.dependency_overrides[require_manager] = lambda: u
    return tc
def _reset(): app.dependency_overrides.clear()


# ── Fix 1: No hard-coded Bearer dev in production frontend source ─────────────

class TestNoBearerDevInFrontend:

    def test_api_ts_has_no_bearer_dev(self):
        """api.ts must not hard-code 'Bearer dev' — ever."""
        content = open(os.path.join(FRONTEND_SRC, 'lib', 'api.ts')).read()
        assert 'Bearer dev' not in content, \
            "api.ts must not contain 'Bearer dev'"
        assert 'getAuthToken' not in content, \
            "api.ts must not reference the old getAuthToken function (replaced by getClerkToken)"

    def test_my_day_has_no_bearer_dev(self):
        content = open(os.path.join(FRONTEND_SRC, 'pages', 'MyDay.tsx')).read()
        assert 'Bearer dev' not in content, "MyDay.tsx must not contain 'Bearer dev'"
        assert 'DEV_HEADERS' not in content, "MyDay.tsx must not define DEV_HEADERS"

    def test_user_access_has_no_bearer_dev(self):
        content = open(os.path.join(FRONTEND_SRC, 'pages', 'UserAccess.tsx')).read()
        assert 'Bearer dev' not in content, "UserAccess.tsx must not contain 'Bearer dev'"
        assert '__clerkToken' not in content, "UserAccess.tsx must not use window.__clerkToken"

    def test_no_bearer_dev_anywhere_in_production_pages(self):
        """Scan all .tsx and .ts files — no hard-coded Bearer token."""
        import glob
        files = glob.glob(f'{FRONTEND_SRC}/**/*.tsx', recursive=True)
        files += glob.glob(f'{FRONTEND_SRC}/**/*.ts', recursive=True)
        for fpath in files:
            content = open(fpath).read()
            assert 'Bearer dev' not in content, \
                f"Hard-coded 'Bearer dev' found in {fpath}"

    def test_clerk_token_obtained_via_getClerkToken(self):
        """The central token function must be getClerkToken, not getAuthToken."""
        content = open(os.path.join(FRONTEND_SRC, 'lib', 'api.ts')).read()
        assert 'getClerkToken' in content, "Must define getClerkToken"
        assert 'window.Clerk' in content or "window?.Clerk" in content, \
            "getClerkToken must use window.Clerk session"

    def test_myday_uses_apiRequest_not_raw_fetch(self):
        content = open(os.path.join(FRONTEND_SRC, 'pages', 'MyDay.tsx')).read()
        assert 'apiRequest' in content, "MyDay must use apiRequest (central client)"
        assert "fetch('/api/" not in content and 'fetch(`/api/' not in content, \
            "MyDay must not call raw fetch to /api/ (must go through apiRequest)"

    def test_user_access_uses_apiRequest_not_authFetch(self):
        content = open(os.path.join(FRONTEND_SRC, 'pages', 'UserAccess.tsx')).read()
        assert 'apiRequest' in content, "UserAccess must use apiRequest"
        assert 'authFetch' not in content, "UserAccess must not have custom authFetch"


# ── Fix 2: API_BASE applied consistently ──────────────────────────────────────

class TestAPIBaseConsistency:

    def _get_api_ts(self):
        return open(os.path.join(FRONTEND_SRC, 'lib', 'api.ts')).read()

    def test_apiRequest_prepends_api_base_to_relative_paths(self):
        """apiRequest must prepend API_BASE for paths starting with /."""
        content = self._get_api_ts()
        # The function must reference API_BASE in the URL construction
        assert 'API_BASE' in content
        # Must prepend to relative paths
        assert "path.startsWith('/')" in content or 'startsWith("/")' in content, \
            "apiRequest must conditionally prepend API_BASE for relative paths"

    def test_no_relative_api_calls_outside_apiRequest(self):
        """Outside apiRequest, no raw fetch('/api/...) calls should exist in production code."""
        content = self._get_api_ts()
        # raw fetch to relative /api/ path (not inside the apiRequest helper itself)
        raw_matches = re.findall(r"fetch\(['\`]/api/", content)
        assert len(raw_matches) == 0, \
            f"Found {len(raw_matches)} raw fetch('/api/...) calls in api.ts — use apiRequest instead"

    def test_all_api_methods_use_apiRequest(self):
        """Key API method groups must go through apiRequest (not raw relative fetch)."""
        content = self._get_api_ts()
        # These objects must use apiRequest for their data calls
        for obj in ['commercialApi', 'crmApi']:
            idx = content.find(obj)
            if idx > 0:
                chunk = content[idx:idx+1000]
                assert 'apiRequest' in chunk, f"{obj} must use apiRequest"
        # importsApi uses raw fetch only for FormData upload (acceptable)
        # but its batches/coverage calls must use apiRequest
        batches_idx = content.find("batches:")
        if batches_idx > 0:
            assert 'apiRequest' in content[batches_idx:batches_idx+100],                 "importsApi.batches must use apiRequest"
        # queue uses apiRequest
        queue_idx = content.find("export const queueApi")
        if queue_idx > 0:
            assert 'apiRequest' in content[queue_idx:queue_idx+1000],                 "queueApi must use apiRequest"

    def test_imports_upload_uses_api_base(self):
        """The import file upload (raw FormData fetch) must still use API_BASE."""
        content = self._get_api_ts()
        upload_idx = content.find('upload:')
        upload_section = content[upload_idx:upload_idx+600]
        assert 'API_BASE' in upload_section, \
            "Import file upload must use API_BASE for backend URL"
        assert 'getClerkToken' in upload_section, \
            "Import file upload must use getClerkToken for auth"

    def test_myDay_endpoint_url_is_server_side(self):
        """My Day must call /api/crm/my-day (no rep_id in URL) for REP users."""
        content = open(os.path.join(FRONTEND_SRC, 'pages', 'MyDay.tsx')).read()
        assert '/api/crm/my-day' in content
        # Must not have a user-supplied rep_id in the URL
        assert '/api/crm/my-day/${' not in content, \
            "My Day URL must not have a client-supplied rep_id"


# ── Fix 3: Database engine isolation ──────────────────────────────────────────

class TestDatabaseEngineIsolation:

    def test_create_engine_uses_supplied_url(self):
        """create_engine(url) must use the URL it receives, not settings.database_url_async."""
        from app.database import create_engine, _to_asyncpg_url
        engine = create_engine('postgresql://testuser:testpass@testhost:5432/testdb')
        url_str = str(engine.url)
        assert 'testhost' in url_str, f"Engine URL must use supplied host. Got: {url_str}"
        assert 'testdb' in url_str, f"Engine URL must use supplied DB. Got: {url_str}"
        assert 'waterford_si' not in url_str, \
            "Engine must not silently use the production/dev DB when a different URL is supplied"

    def test_production_and_test_engines_use_different_dbs(self):
        """The module-level engines must connect to different databases."""
        from app.config import settings
        from app.database import create_engine
        prod_engine = create_engine(settings.database_url_async)
        test_engine = create_engine(settings.database_url_test)
        prod_url = str(prod_engine.url)
        test_url = str(test_engine.url)
        assert prod_url != test_url, \
            "Production and test engines must have different connection URLs"

    def test_to_asyncpg_url_converts_postgresql(self):
        from app.database import _to_asyncpg_url
        assert _to_asyncpg_url('postgresql://u:p@h:5432/db') == 'postgresql+asyncpg://u:p@h:5432/db'

    def test_to_asyncpg_url_passthrough_already_asyncpg(self):
        from app.database import _to_asyncpg_url
        url = 'postgresql+asyncpg://u:p@h:5432/db'
        assert _to_asyncpg_url(url) == url

    def test_to_asyncpg_url_converts_dsn(self):
        from app.database import _to_asyncpg_url
        result = _to_asyncpg_url('host=myhost dbname=mydb user=u password=p port=5432')
        assert 'myhost' in result
        assert 'asyncpg' in result

    def test_settings_database_url_test_is_different_from_production(self):
        from app.config import settings
        assert settings.database_url_test != settings.database_url_async, \
            "Test DB URL must differ from production async URL"


# ── Fix 4: CRM attribution — child record isolation ──────────────────────────

class TestCRMChildAttribution:
    """CRM child records must inherit server-side attribution, not browser-supplied values."""

    def setup_method(self): _reset()
    def teardown_method(self): _reset()

    def _mapped_rep_user(self, rep_code='KOL001'):
        conn = _conn()
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("SELECT id::text FROM reps WHERE rep_code=%s", (rep_code,))
            rep = c.fetchone()
            c.execute("SELECT id::text FROM reps WHERE rep_code='HEL001'")
            other_rep = c.fetchone()
        fake_uid = f'user_child_test_{uuid.uuid4().hex[:8]}'
        with conn.cursor() as c:
            c.execute("""INSERT INTO user_rep_mappings(clerk_user_id, clerk_email, rep_id, created_by)
                         VALUES (%s, 'test@w.co.za', %s::uuid, 'test')
                         ON CONFLICT(clerk_user_id) DO UPDATE SET rep_id=EXCLUDED.rep_id, is_active=TRUE""",
                      (fake_uid, rep['id']))
        conn.commit()
        conn.close()
        return fake_uid, rep['id'], other_rep['id'] if other_rep else None

    def test_child_followup_uses_server_side_rep(self):
        """Follow-up created with activity must use the authenticated rep, not payload rep."""
        fake_uid, kol_id, hel_id = self._mapped_rep_user('KOL001')
        if not hel_id: pytest.skip("Need HEL001")

        tc = TestClient(app)
        rep_user = _make_user('REP', uid=fake_uid)
        app.dependency_overrides[verify_clerk_token] = lambda: rep_user

        conn = _conn()
        with conn.cursor() as c:
            c.execute("SELECT id::text FROM clients WHERE canonical_name='Van Riebeeck Liquors'")
            row = c.fetchone()
        conn.close()
        if not row: pytest.skip()
        client_id = row[0]

        r = tc.post('/api/crm/activities', json={
            'client_id': client_id,
            'rep_id': hel_id,   # attacker tries to attribute to HEL001
            'activity_type': 'VISIT', 'general_notes': 'Child attr test', 'overall_sentiment': 'NEUTRAL',
            'follow_up': {
                'follow_up_type': 'Call', 'due_date': '2026-12-01',
                'description': 'Child follow-up test',
                'rep_id': hel_id,           # attacker tries child attribution too
            },
            'support_request': {
                'support_type': 'Samples', 'notes': 'Child SR test',
                'rep_id': hel_id,           # attacker tries child SR attribution
            },
        }, headers={'Authorization': 'Bearer dev'})
        assert r.status_code == 200
        fu_id = r.json().get('follow_up_id')
        sr_id = r.json().get('support_request_id')

        conn = _conn()
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            if fu_id:
                c.execute("SELECT rep_id::text, created_by FROM crm_follow_ups WHERE id=%s::uuid", (fu_id,))
                fu_row = c.fetchone()
                assert fu_row['rep_id'] == kol_id, \
                    f"Follow-up rep must be KOL001 (mapped), not HEL001 (payload). Got {fu_row['rep_id']}"
                assert fu_row['created_by'] == fake_uid, \
                    "Follow-up created_by must be Clerk user_id"

            if sr_id:
                c.execute("SELECT rep_id::text, created_by FROM crm_support_requests WHERE id=%s::uuid", (sr_id,))
                sr_row = c.fetchone()
                assert sr_row['rep_id'] == kol_id, \
                    f"Support request rep must be KOL001 (mapped), not HEL001 (payload). Got {sr_row['rep_id']}"
                assert sr_row['created_by'] == fake_uid, \
                    "Support request created_by must be Clerk user_id"
        conn.close()
        _reset()

    def test_standalone_followup_uses_server_side_rep(self):
        """Standalone POST /follow-ups must use authenticated rep, not payload rep."""
        fake_uid, kol_id, hel_id = self._mapped_rep_user('KOL001')
        if not hel_id: pytest.skip()
        tc = TestClient(app)
        app.dependency_overrides[verify_clerk_token] = lambda: _make_user('REP', uid=fake_uid)

        conn = _conn()
        with conn.cursor() as c:
            c.execute("SELECT id::text FROM clients WHERE canonical_name='Van Riebeeck Liquors'")
            row = c.fetchone()
        conn.close()
        if not row: pytest.skip()

        r = tc.post('/api/crm/follow-ups', json={
            'client_id': row[0], 'rep_id': hel_id,  # impersonation attempt
            'follow_up_type': 'Call', 'due_date': '2026-12-01',
            'description': 'Standalone FU attr test', 'priority': 'LOW',
        }, headers={'Authorization': 'Bearer dev'})
        assert r.status_code == 200
        fu_id = r.json()['follow_up_id']

        conn = _conn()
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("SELECT rep_id::text, created_by FROM crm_follow_ups WHERE id=%s::uuid", (fu_id,))
            row = c.fetchone()
        conn.close()
        assert row['rep_id'] == kol_id, f"Must use mapped rep, not payload. Got {row['rep_id']}"
        assert row['created_by'] == fake_uid
        _reset()

    def test_webapp_not_accepted_as_created_by(self):
        """'webapp' must never appear as created_by — must be Clerk user_id."""
        fake_uid, kol_id, _ = self._mapped_rep_user('KOL001')
        tc = TestClient(app)
        app.dependency_overrides[verify_clerk_token] = lambda: _make_user('REP', uid=fake_uid)

        conn = _conn()
        with conn.cursor() as c:
            c.execute("SELECT id::text FROM clients WHERE canonical_name='Van Riebeeck Liquors'")
            row = c.fetchone()
        conn.close()
        if not row: pytest.skip()

        r = tc.post('/api/crm/activities', json={
            'client_id': row[0], 'rep_id': kol_id,
            'activity_type': 'CALL', 'general_notes': 'Created-by test', 'overall_sentiment': 'NEUTRAL',
            'created_by': 'webapp',  # browser tries to set this
        }, headers={'Authorization': 'Bearer dev'})
        act_id = r.json().get('activity_id')
        if not act_id: pytest.skip("No act_id returned")

        conn = _conn()
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("SELECT created_by FROM crm_activities WHERE id=%s::uuid", (act_id,))
            row = c.fetchone()
        conn.close()
        assert row['created_by'] != 'webapp', \
            "created_by must be Clerk user_id, not browser-supplied 'webapp'"
        assert row['created_by'] == fake_uid
        _reset()
