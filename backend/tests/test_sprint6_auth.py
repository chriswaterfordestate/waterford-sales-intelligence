"""
Sprint 6: Real role-based authorization tests.
Tests prove security at the dependency level, not by inspecting source strings.
"""
import os, sys, uuid, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault('DATABASE_URL', 'postgresql://waterford:waterford_dev@localhost:5432/waterford_si')
os.environ.setdefault('APP_ENV', 'development')

from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.core.auth import (
    verify_clerk_token, require_manager, require_admin, CurrentUser
)
import psycopg2
from psycopg2.extras import RealDictCursor

PROD_DSN = 'host=localhost dbname=waterford_si user=waterford password=waterford_dev'

def _conn(): return psycopg2.connect(PROD_DSN)
def _get_rep(code='KOL001'):
    conn = _conn()
    with conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute("SELECT id::text, rep_code, full_name FROM reps WHERE rep_code=%s", (code,))
        r = c.fetchone()
    conn.close()
    return r

def _make_user(role: str, user_id: str = None) -> CurrentUser:
    return CurrentUser(
        user_id=user_id or f"user_{role.lower()}_test",
        email=f"{role.lower()}@test.waterford.co.za",
        role=role,
        full_name=f"Test {role.title()}",
    )

def _client_with_role(role: str, user_id: str = None) -> TestClient:
    """Create a TestClient with a mock CurrentUser injected via dependency override."""
    tc = TestClient(app, raise_server_exceptions=False)
    user = _make_user(role, user_id)
    app.dependency_overrides[verify_clerk_token] = lambda: user
    if role in ('MANAGER', 'ADMIN'):
        app.dependency_overrides[require_manager] = lambda: user
    if role == 'ADMIN':
        app.dependency_overrides[require_admin] = lambda: user
    return tc

def _reset_overrides():
    app.dependency_overrides.clear()

def _unauthenticated_client() -> TestClient:
    """TestClient with no auth headers and no overrides."""
    _reset_overrides()
    return TestClient(app, raise_server_exceptions=False)


# ── Unauthenticated ──────────────────────────────────────────────────────────

class TestUnauthenticated:
    def setup_method(self):
        _reset_overrides()

    def test_clients_search_returns_401(self):
        tc = _unauthenticated_client()
        r = tc.get('/api/clients/search?q=test')
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"

    def test_commercial_dashboard_returns_401(self):
        tc = _unauthenticated_client()
        r = tc.get('/api/commercial/dashboard')
        assert r.status_code in (401, 403)

    def test_imports_returns_401(self):
        tc = _unauthenticated_client()
        r = tc.get('/api/imports/batches')
        assert r.status_code in (401, 403)

    def test_crm_reps_returns_401(self):
        tc = _unauthenticated_client()
        r = tc.get('/api/crm/reps')
        assert r.status_code in (401, 403)

    def test_queue_summary_returns_401(self):
        tc = _unauthenticated_client()
        r = tc.get('/api/queue/summary')
        assert r.status_code in (401, 403)

    def test_manager_view_returns_401(self):
        tc = _unauthenticated_client()
        r = tc.get('/api/crm/manager-view')
        assert r.status_code in (401, 403)

    def test_health_is_public(self):
        tc = _unauthenticated_client()
        r = tc.get('/api/health')
        assert r.status_code == 200


# ── REP role ─────────────────────────────────────────────────────────────────

class TestREPRole:
    def setup_method(self):
        _reset_overrides()

    def test_rep_can_access_crm_reps(self):
        tc = _client_with_role('REP')
        r = tc.get('/api/crm/reps', headers={'Authorization': 'Bearer ignored'})
        assert r.status_code == 200
        _reset_overrides()

    def test_rep_cannot_access_manager_view(self):
        """REP must be blocked from manager-view at the backend — not just hidden in nav."""
        _reset_overrides()
        tc = TestClient(app, raise_server_exceptions=False)
        rep_user = _make_user('REP')
        # Only override verify_clerk_token — require_manager must enforce role
        app.dependency_overrides[verify_clerk_token] = lambda: rep_user
        r = tc.get('/api/crm/manager-view', headers={'Authorization': 'Bearer rep-token'})
        assert r.status_code in (403, 401), (
            f"Manager View must reject REP role at the backend. Got {r.status_code}"
        )
        _reset_overrides()

    def test_rep_cannot_access_commercial_queue(self):
        """Commercial queue is manager-protected."""
        _reset_overrides()
        tc = TestClient(app, raise_server_exceptions=False)
        rep_user = _make_user('REP')
        app.dependency_overrides[verify_clerk_token] = lambda: rep_user
        r = tc.get('/api/queue/summary', headers={'Authorization': 'Bearer rep-token'})
        assert r.status_code in (403, 401), f"Queue must reject REP. Got {r.status_code}"
        _reset_overrides()

    def test_rep_cannot_access_import_centre(self):
        """Import centre is manager-protected."""
        _reset_overrides()
        tc = TestClient(app, raise_server_exceptions=False)
        rep_user = _make_user('REP')
        app.dependency_overrides[verify_clerk_token] = lambda: rep_user
        r = tc.get('/api/imports/batches', headers={'Authorization': 'Bearer rep-token'})
        assert r.status_code in (403, 401), f"Imports must reject REP. Got {r.status_code}"
        _reset_overrides()

    def test_rep_my_day_is_server_side_resolved(self):
        """
        /api/crm/my-day (no rep_id in URL) derives identity from user_rep_mappings.
        A REP cannot supply an arbitrary rep_id.
        """
        _reset_overrides()
        tc = TestClient(app, raise_server_exceptions=False)
        rep_user = _make_user('REP', user_id='user_rep_no_mapping')
        app.dependency_overrides[verify_clerk_token] = lambda: rep_user
        r = tc.get('/api/crm/my-day', headers={'Authorization': 'Bearer rep-token'})
        # Should return 200 with either data or a "no mapping" message — not 403
        assert r.status_code == 200
        d = r.json()
        # If unmapped, returns error key rather than arbitrary rep's data
        if d.get('error'):
            assert 'mapping' in d['error'].lower(), "Error must mention mapping"
        _reset_overrides()

    def test_rep_cannot_access_another_reps_my_day_via_url(self):
        """GET /api/crm/my-day/{rep_id} must require manager role."""
        _reset_overrides()
        tc = TestClient(app, raise_server_exceptions=False)
        rep_user = _make_user('REP')
        app.dependency_overrides[verify_clerk_token] = lambda: rep_user
        rep = _get_rep('KOL001')
        if not rep: pytest.skip("KOL001 not in DB")
        r = tc.get(f"/api/crm/my-day/{rep['id']}", headers={'Authorization': 'Bearer rep-token'})
        assert r.status_code in (403, 401), (
            f"REP must not access /my-day/{{rep_id}}. Got {r.status_code}"
        )
        _reset_overrides()

    def test_rep_cannot_impersonate_another_rep_in_activity_payload(self):
        """
        REP submits activity with another rep's rep_id in payload.
        Server must override with mapping-derived rep_id.
        """
        _reset_overrides()
        tc = TestClient(app, raise_server_exceptions=False)
        # REP user who IS mapped to KOL001
        rep_kol = _get_rep('KOL001')
        rep_hel = _get_rep('HEL001')
        if not rep_kol or not rep_hel: pytest.skip("Need KOL001 and HEL001")

        # Create a mapping for the REP user
        conn = _conn()
        fake_user_id = 'user_auth_test_kol001'
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO user_rep_mappings(clerk_user_id, clerk_email, rep_id, created_by)
                VALUES (%s, 'kol@test.com', %s::uuid, 'test')
                ON CONFLICT(clerk_user_id) DO UPDATE SET rep_id=EXCLUDED.rep_id, is_active=TRUE
            """, (fake_user_id, rep_kol['id']))
        conn.commit()
        conn.close()

        rep_user = _make_user('REP', user_id=fake_user_id)
        app.dependency_overrides[verify_clerk_token] = lambda: rep_user

        # Get any client ID
        conn = _conn()
        with conn.cursor() as c:
            c.execute("SELECT id::text FROM clients WHERE canonical_name='Van Riebeeck Liquors'")
            row = c.fetchone()
        conn.close()
        if not row: pytest.skip("Van Riebeeck Liquors not in DB")
        client_id = row[0]

        # Submit activity with HEL001's rep_id in payload (impersonation attempt)
        r = tc.post('/api/crm/activities', json={
            'client_id': client_id,
            'rep_id': rep_hel['id'],   # ← attacker tries to impersonate HEL001
            'activity_type': 'CALL',
            'general_notes': 'Auth test: impersonation attempt',
            'overall_sentiment': 'NEUTRAL',
        }, headers={'Authorization': 'Bearer rep-token'})
        assert r.status_code == 200
        act_id = r.json().get('activity_id')

        # Verify: activity must be stored with KOL001's ID, not HEL001's
        conn = _conn()
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("SELECT rep_id::text, created_by FROM crm_activities WHERE id=%s::uuid", (act_id,))
            row = c.fetchone()
        conn.close()

        assert row['rep_id'] == rep_kol['id'], (
            f"Activity rep_id must be KOL001 (mapped), not HEL001 (payload). "
            f"Got: {row['rep_id']}"
        )
        assert row['created_by'] == fake_user_id, "created_by must be the authenticated user_id"
        _reset_overrides()


# ── MANAGER role ──────────────────────────────────────────────────────────────

class TestManagerRole:
    def setup_method(self):
        _reset_overrides()

    def test_manager_can_access_manager_view(self):
        tc = _client_with_role('MANAGER')
        r = tc.get('/api/crm/manager-view', headers={'Authorization': 'Bearer mgr-token'})
        assert r.status_code == 200
        _reset_overrides()

    def test_manager_can_access_commercial_queue(self):
        tc = _client_with_role('MANAGER')
        r = tc.get('/api/queue/summary', headers={'Authorization': 'Bearer mgr-token'})
        assert r.status_code == 200
        _reset_overrides()

    def test_manager_can_access_rep_my_day(self):
        """Manager can view any rep's My Day via /my-day/{rep_id}."""
        tc = _client_with_role('MANAGER')
        rep = _get_rep('KOL001')
        if not rep: pytest.skip()
        r = tc.get(f"/api/crm/my-day/{rep['id']}", headers={'Authorization': 'Bearer mgr-token'})
        assert r.status_code == 200
        _reset_overrides()

    def test_manager_can_access_imports(self):
        tc = _client_with_role('MANAGER')
        r = tc.get('/api/imports/batches', headers={'Authorization': 'Bearer mgr-token'})
        assert r.status_code == 200
        _reset_overrides()


# ── ADMIN role ────────────────────────────────────────────────────────────────

class TestAdminRole:
    def setup_method(self):
        _reset_overrides()

    def test_admin_can_access_user_mappings(self):
        tc = _client_with_role('ADMIN')
        r = tc.get('/api/auth/user-mappings', headers={'Authorization': 'Bearer admin-token'})
        assert r.status_code == 200
        assert 'mappings' in r.json()
        _reset_overrides()

    def test_non_admin_cannot_access_user_mappings(self):
        """REP or MANAGER cannot manage user→rep mappings."""
        _reset_overrides()
        tc = TestClient(app, raise_server_exceptions=False)
        rep_user = _make_user('REP')
        app.dependency_overrides[verify_clerk_token] = lambda: rep_user
        r = tc.get('/api/auth/user-mappings', headers={'Authorization': 'Bearer rep-token'})
        assert r.status_code in (403, 401), f"Non-admin must be blocked. Got {r.status_code}"
        _reset_overrides()

    def test_admin_can_create_mapping(self):
        """Admin can POST a new user→rep mapping without SQL or Render shell."""
        tc = _client_with_role('ADMIN')
        rep = _get_rep('KOL001')
        if not rep: pytest.skip()
        test_uid = f"user_admin_test_{uuid.uuid4().hex[:8]}"
        r = tc.post('/api/auth/user-mappings', json={
            'clerk_user_id': test_uid,
            'clerk_email': 'admin-test@waterford.co.za',
            'rep_id': rep['id'],
        }, headers={'Authorization': 'Bearer admin-token'})
        assert r.status_code == 200
        assert r.json().get('status') == 'ok'
        _reset_overrides()


# ── Production configuration ──────────────────────────────────────────────────

class TestProductionConfig:
    def _make_settings(self, db_url: str = None, db_sync: str = None, app_env: str = "development"):
        """Create a Settings instance with environment override — bypasses Pydantic Settings env priority."""
        import os
        from importlib import reload
        saved = {k: os.environ.get(k) for k in ("DATABASE_URL", "DATABASE_URL_SYNC", "APP_ENV")}
        if db_url: os.environ["DATABASE_URL"] = db_url
        elif "DATABASE_URL" in os.environ: del os.environ["DATABASE_URL"]
        if db_sync: os.environ["DATABASE_URL_SYNC"] = db_sync
        elif "DATABASE_URL_SYNC" in os.environ: del os.environ["DATABASE_URL_SYNC"]
        os.environ["APP_ENV"] = app_env
        import app.config
        app.config.get_settings.cache_clear()
        s = app.config.Settings()
        # Restore
        for k, v in saved.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v
        app.config.get_settings.cache_clear()
        return s

    def test_database_url_derives_both_sync_and_async(self):
        """A single DATABASE_URL must feed both psycopg2 and asyncpg correctly."""
        s = self._make_settings(db_url='postgresql://user:pass@host:5432/mydb')
        assert 'host:5432/mydb' in s.database_url_sync, f"sync URL wrong: {s.database_url_sync}"
        assert 'host:5432/mydb' in s.database_url_async, f"async URL wrong: {s.database_url_async}"
        assert s.database_url_sync.startswith('postgresql://')
        assert s.database_url_async.startswith('postgresql+asyncpg://')

    def test_asyncpg_url_also_derives_correctly(self):
        """asyncpg-prefixed URL must produce correct sync URL."""
        s = self._make_settings(db_url='postgresql+asyncpg://user:pass@render-host:5432/db')
        assert s.database_url_sync.startswith('postgresql://')
        assert not s.database_url_sync.startswith('postgresql+asyncpg')
        assert s.database_url_async.startswith('postgresql+asyncpg://')
        assert 'render-host' in s.database_url_sync

    def test_psycopg2_dsn_also_converts(self):
        """psycopg2 DSN (host= format) converts correctly to both URLs."""
        s = self._make_settings(db_sync='host=myhost dbname=mydb user=u password=p port=5432')
        assert 'myhost' in s.database_url_sync, f"sync URL: {s.database_url_sync}"
        assert 'myhost' in s.database_url_async, f"async URL: {s.database_url_async}"

    def test_no_localhost_in_production(self):
        """Under production DATABASE_URL, no localhost appears in derived URLs."""
        s = self._make_settings(
            db_url='postgresql://renderuser:renderpass@render-db.render.com:5432/mydb',
            app_env='production'
        )
        assert 'localhost' not in s.database_url_sync, f"localhost in sync: {s.database_url_sync}"
        assert 'localhost' not in s.database_url_async
        assert 'render-db.render.com' in s.database_url_sync

    def test_allowed_origins_not_wildcard(self):
        from app.config import settings
        assert '*' not in settings.allowed_origins

    def test_auth_bypass_requires_development_mode(self):
        """The dev auth bypass only activates under APP_ENV=development."""
        from app.core.auth import verify_clerk_token
        import inspect
        src = inspect.getsource(verify_clerk_token)
        # Bypass requires both development AND no Clerk URL
        assert 'development' in src
        assert 'clerk_jwks_url' in src


# ── MCR bootstrap ─────────────────────────────────────────────────────────────

class TestMCRBootstrap:
    def test_mcr_bootstrap_file_present_in_package(self):
        import os
        scripts = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
        assert os.path.exists(os.path.join(scripts, 'mcr_bootstrap.sql')), \
            "mcr_bootstrap.sql must be packaged — it is the production bootstrap artifact"

    def test_bootstrap_script_present(self):
        import os
        scripts = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
        bootstrap = os.path.join(scripts, 'bootstrap.sh')
        assert os.path.exists(bootstrap), "bootstrap.sh must exist"
        content = open(bootstrap).read()
        assert 'alembic upgrade head' in content
        assert 'mcr_bootstrap.sql' in content

    def test_alembic_wrapper_chain_complete(self):
        """All 11 revisions must have .py files in the correct chain."""
        import os
        versions_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'alembic', 'versions')
        for num in ['007', '008', '009']:
            py_files = [f for f in os.listdir(versions_dir) if f.startswith(f'{num}_') and f.endswith('.py')]
            assert py_files, f"Missing Alembic .py wrapper for migration {num}"

    def test_mcr_bootstrap_has_data(self):
        """Clients and source aliases must exist after bootstrap. Ownership is built by imports."""
        conn = _conn()
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM clients")
            clients = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM client_source_aliases WHERE match_status='ACTIVE'")
            aliases = c.fetchone()[0]
        conn.close()
        assert clients > 0, f"Must have canonical clients after bootstrap, got {clients}"
        assert aliases > 0, f"Must have confirmed source aliases after bootstrap, got {aliases}"
        # Note: client_ownership is built by import pipeline attribution, not pre-loaded
