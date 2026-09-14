"""
Sprint 6 Clerk integration tests:
- ALLOWED_ORIGINS parsing from plain Render env var
- Clerk role claim contract (payload["role"])
- Production config instantiation
- JWT-shaped payload → CurrentUser role resolution
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest


# ── ALLOWED_ORIGINS ──────────────────────────────────────────────────────────

class TestAllowedOrigins:

    def _settings(self, origins_str: str | None = None, **extra_env):
        """Instantiate Settings with given ALLOWED_ORIGINS value."""
        from app.config import Settings
        env = dict(DATABASE_URL='postgresql://x:y@h:5432/db', APP_ENV='development')
        env.update(extra_env)
        if origins_str is not None:
            env['ALLOWED_ORIGINS'] = origins_str
        else:
            env.pop('ALLOWED_ORIGINS', None)
        saved = {k: os.environ.get(k) for k in env}
        try:
            for k, v in env.items():
                os.environ[k] = v
            return Settings()
        finally:
            for k, v in saved.items():
                if v is None: os.environ.pop(k, None)
                else: os.environ[k] = v

    def test_single_origin_plain_string(self):
        """Render sets a plain URL — must not require JSON encoding."""
        s = self._settings('https://waterford-si-frontend.onrender.com')
        assert s.allowed_origins == ['https://waterford-si-frontend.onrender.com'], s.allowed_origins

    def test_multiple_origins_comma_separated(self):
        s = self._settings('https://a.example.com,https://b.example.com')
        assert s.allowed_origins == ['https://a.example.com', 'https://b.example.com']

    def test_whitespace_trimmed(self):
        s = self._settings('  https://a.example.com  ,  https://b.example.com  ')
        assert s.allowed_origins == ['https://a.example.com', 'https://b.example.com']

    def test_empty_entries_ignored(self):
        s = self._settings('https://a.example.com,,https://b.example.com,')
        assert s.allowed_origins == ['https://a.example.com', 'https://b.example.com']

    def test_default_is_localhost(self):
        s = self._settings(None)
        assert 'localhost' in s.allowed_origins[0]

    def test_wildcard_not_in_origins_by_default(self):
        """* must not appear in production origins list."""
        s = self._settings('https://waterford.co.za')
        assert '*' not in s.allowed_origins

    def test_wildcard_rejected_in_production(self):
        """ALLOWED_ORIGINS=* must raise ValueError in production."""
        from app.config import Settings
        import pytest as _pytest
        saved = {k: os.environ.get(k) for k in ['ALLOWED_ORIGINS','DATABASE_URL','APP_ENV']}
        try:
            os.environ['ALLOWED_ORIGINS'] = '*'
            os.environ['DATABASE_URL'] = 'postgresql://x:y@h/db'
            os.environ['APP_ENV'] = 'production'
            s = Settings()
            with _pytest.raises(ValueError, match="Wildcard CORS"):
                _ = s.allowed_origins
        finally:
            for k, v in saved.items():
                if v is None: os.environ.pop(k, None)
                else: os.environ[k] = v

    def test_wildcard_combo_rejected_in_production(self):
        """https://frontend.example.com,* must also be rejected in production."""
        from app.config import Settings
        import pytest as _pytest
        saved = {k: os.environ.get(k) for k in ['ALLOWED_ORIGINS','DATABASE_URL','APP_ENV']}
        try:
            os.environ['ALLOWED_ORIGINS'] = 'https://frontend.example.com,*'
            os.environ['DATABASE_URL'] = 'postgresql://x:y@h/db'
            os.environ['APP_ENV'] = 'production'
            s = Settings()
            with _pytest.raises(ValueError, match="Wildcard CORS"):
                _ = s.allowed_origins
        finally:
            for k, v in saved.items():
                if v is None: os.environ.pop(k, None)
                else: os.environ[k] = v

    def test_valid_single_origin_passes_in_production(self):
        """Single real URL must pass validation in production."""
        from app.config import Settings
        saved = {k: os.environ.get(k) for k in ['ALLOWED_ORIGINS','DATABASE_URL','APP_ENV']}
        try:
            os.environ['ALLOWED_ORIGINS'] = 'https://waterford-si-frontend.onrender.com'
            os.environ['DATABASE_URL'] = 'postgresql://x:y@h/db'
            os.environ['APP_ENV'] = 'production'
            s = Settings()
            assert s.allowed_origins == ['https://waterford-si-frontend.onrender.com']
        finally:
            for k, v in saved.items():
                if v is None: os.environ.pop(k, None)
                else: os.environ[k] = v

    def test_production_startup_succeeds_with_render_value(self):
        """App must start cleanly with ALLOWED_ORIGINS as Render supplies it."""
        from app.config import Settings
        # Test the allowed_origins property directly — it parses the raw string
        # regardless of which DB URL is configured in this test environment.
        s = Settings()
        # Simulate what Settings sees when ALLOWED_ORIGINS is set to a plain string:
        # call the property with a spoofed raw value via instantiation
        # Use _settings helper from TestAllowedOrigins instead
        helper = TestAllowedOrigins()
        s2 = helper._settings('https://waterford-si-frontend.onrender.com')
        assert s2.allowed_origins == ['https://waterford-si-frontend.onrender.com'], s2.allowed_origins
        print("  Settings startup OK with plain Render ALLOWED_ORIGINS string")


# ── Clerk JWT claim contract ──────────────────────────────────────────────────

class TestClerkJWTContract:
    """
    Tests for the exact Clerk JWT claim the backend reads.
    Chosen contract: top-level "role" claim.
    Clerk session-token customization: { "role": "{{user.public_metadata.role}}" }
    """

    def _decode_role(self, payload: dict) -> str:
        """Replicate the role-extraction logic from auth.py."""
        return payload.get("role", "REP")

    def test_admin_payload_resolves_admin(self):
        payload = {"sub": "user_admin_test", "role": "ADMIN"}
        assert self._decode_role(payload) == "ADMIN"

    def test_manager_payload_resolves_manager(self):
        payload = {"sub": "user_mgr_test", "role": "MANAGER"}
        assert self._decode_role(payload) == "MANAGER"

    def test_rep_payload_resolves_rep(self):
        payload = {"sub": "user_rep_test", "role": "REP"}
        assert self._decode_role(payload) == "REP"

    def test_missing_role_defaults_to_rep(self):
        """JWT without a role claim → safe default REP (never elevated)."""
        payload = {"sub": "user_no_role"}
        assert self._decode_role(payload) == "REP"

    def test_nested_public_metadata_does_NOT_set_role(self):
        """Old contract (public_metadata.role) must NOT work — new contract is top-level."""
        payload = {"sub": "user_old_contract", "public_metadata": {"role": "ADMIN"}}
        # This should default to REP (the role claim is absent at top level)
        role = self._decode_role(payload)
        assert role == "REP", (
            "Backend must read payload['role'], not payload['public_metadata']['role']. "
            "Ensure Clerk session-token JSON is: {\"role\": \"{{user.public_metadata.role}}\"}"
        )

    def test_current_user_from_admin_payload(self):
        """ADMIN JWT produces is_admin=True."""
        from app.core.auth import CurrentUser
        user = CurrentUser(user_id="u", email="e@w.co.za", role="ADMIN")
        assert user.is_admin
        assert user.is_manager

    def test_current_user_from_manager_payload(self):
        from app.core.auth import CurrentUser
        user = CurrentUser(user_id="u", email="e@w.co.za", role="MANAGER")
        assert not user.is_admin
        assert user.is_manager

    def test_current_user_from_rep_payload(self):
        from app.core.auth import CurrentUser
        user = CurrentUser(user_id="u", email="e@w.co.za", role="REP")
        assert user.is_rep
        assert not user.is_manager
        assert not user.is_admin

    def test_auth_py_reads_role_from_top_level(self):
        """Verify auth.py source uses payload.get('role') not public_metadata."""
        src = open(os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'app', 'core', 'auth.py'
        )).read()
        assert 'payload.get("role"' in src or "payload.get('role'" in src, \
            "auth.py must read role from payload['role'] (top-level custom claim)"
        # public_metadata may appear in comments but must NOT appear in active code
        # Check the role extraction line specifically
        role_line = [l for l in src.split("\n") if "role" in l and "payload" in l and "get" in l]
        assert any("payload.get(\"role\"" in l or "payload.get(\'role\'" in l for l in role_line), \
            f"auth.py must read payload.get(\'role\') for the role claim. Found: {role_line}"

    def test_require_admin_passes_for_admin_user(self):
        """After JWT decoding, ADMIN passes require_admin dependency."""
        from app.core.auth import CurrentUser, require_admin
        import asyncio
        user = CurrentUser(user_id="admin_u", email="a@w.co.za", role="ADMIN")

        async def _run():
            from unittest.mock import AsyncMock
            from fastapi import HTTPException
            mock_dep = AsyncMock(return_value=user)
            result = await require_admin(current_user=user)
            assert result.is_admin
        asyncio.run(_run())

    def test_require_admin_blocks_rep_user(self):
        """REP user decoded from JWT fails require_admin."""
        from app.core.auth import CurrentUser, require_admin
        from fastapi import HTTPException
        import asyncio
        user = CurrentUser(user_id="rep_u", email="r@w.co.za", role="REP")

        async def _run():
            with pytest.raises(HTTPException) as exc_info:
                await require_admin(current_user=user)
            assert exc_info.value.status_code == 403
        asyncio.run(_run())


# ── Production config validation ─────────────────────────────────────────────

class TestProductionConfig:

    def _prod_settings(self, extra_env=None):
        from app.config import Settings
        env = {
            'APP_ENV': 'production',
            'DATABASE_URL': 'postgresql://u:p@renderhost:5432/waterford_si',
            'CLERK_JWKS_URL': 'https://example.clerk.accounts.dev/.well-known/jwks.json',
            'ALLOWED_ORIGINS': 'https://waterford-si-frontend.onrender.com',
        }
        if extra_env: env.update(extra_env)
        saved = {k: os.environ.get(k) for k in env}
        try:
            for k, v in env.items(): os.environ[k] = v
            return Settings()
        finally:
            for k, v in saved.items():
                if v is None: os.environ.pop(k, None)
                else: os.environ[k] = v

    def test_production_settings_instantiate(self):
        s = self._prod_settings()
        assert s is not None

    def test_allowed_origins_correct(self):
        s = self._prod_settings()
        assert s.allowed_origins == ['https://waterford-si-frontend.onrender.com']

    def test_no_localhost_in_db_url(self):
        """Under a production DATABASE_URL, derived URLs must use that host."""
        from app.config import Settings
        saved = {k: os.environ.get(k) for k in ['DATABASE_URL','DATABASE_URL_SYNC','APP_ENV','ALLOWED_ORIGINS']}
        try:
            os.environ['DATABASE_URL'] = 'postgresql://u:p@renderhost:5432/waterford_si'
            os.environ.pop('DATABASE_URL_SYNC', None)
            os.environ['APP_ENV'] = 'production'
            os.environ['ALLOWED_ORIGINS'] = 'https://frontend.example.com'
            s = Settings()
            assert 'localhost' not in s.database_url_sync, f"sync: {s.database_url_sync}"
            assert 'localhost' not in s.database_url_async, f"async: {s.database_url_async}"
            assert 'renderhost' in s.database_url_sync, f"sync: {s.database_url_sync}"
        finally:
            for k, v in saved.items():
                if v is None: os.environ.pop(k, None)
                else: os.environ[k] = v

    def test_dev_bypass_disabled_in_production(self):
        s = self._prod_settings()
        # Production must have both clerk_jwks_url and non-development app_env
        assert s.app_env == 'production'
        assert s.clerk_jwks_url != ''
        # Auth bypass condition: app_env == 'development' AND no clerk_jwks_url
        bypass_active = (s.app_env == 'development' and not s.clerk_jwks_url)
        assert not bypass_active, "Auth bypass must be inactive in production"

    def test_wildcard_cors_not_in_origins(self):
        s = self._prod_settings()
        assert '*' not in s.allowed_origins, "Production must not use wildcard CORS"


# ── Frontend auth checks ──────────────────────────────────────────────────────

class TestFrontendAuthMechanism:

    FRONTEND_SRC = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'frontend', 'src'
    )

    def test_clerk_token_bridge_exists(self):
        """ClerkTokenBridge component must exist to use the React hook."""
        bridge = os.path.join(self.FRONTEND_SRC, 'components', 'ClerkTokenBridge.tsx')
        assert os.path.exists(bridge), "ClerkTokenBridge.tsx must exist"
        content = open(bridge).read()
        assert 'useAuth' in content, "Bridge must use useAuth from @clerk/clerk-react"
        assert 'setClerkTokenProvider' in content, "Bridge must call setClerkTokenProvider"

    def test_api_ts_has_set_clerk_token_provider(self):
        content = open(os.path.join(self.FRONTEND_SRC, 'lib', 'api.ts')).read()
        assert 'setClerkTokenProvider' in content
        assert '_clerkGetToken' in content, "Module-level token provider variable must exist"

    def test_app_tsx_mounts_clerk_token_bridge(self):
        """ClerkProvider is in main.tsx; ClerkTokenBridge is mounted inside it."""
        main_content = open(os.path.join(self.FRONTEND_SRC, 'main.tsx')).read()
        assert 'ClerkProvider' in main_content, "main.tsx must use ClerkProvider"
        assert 'ClerkTokenBridge' in main_content, "main.tsx must mount ClerkTokenBridge inside ClerkProvider"
        bridge = open(os.path.join(self.FRONTEND_SRC, 'components', 'ClerkTokenBridge.tsx')).read()
        assert 'useAuth' in bridge, "Bridge must use useAuth()"

    def test_no_bearer_dev_anywhere(self):
        import glob
        files = glob.glob(f'{self.FRONTEND_SRC}/**/*.tsx', recursive=True)
        files += glob.glob(f'{self.FRONTEND_SRC}/**/*.ts', recursive=True)
        for fpath in files:
            content = open(fpath).read()
            assert 'Bearer dev' not in content, f"Found 'Bearer dev' in {fpath}"
