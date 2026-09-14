"""
Authentication via Clerk JWT tokens.

Flow:
1. Frontend authenticates via Clerk SDK
2. Frontend attaches Clerk session JWT to every API request (Authorization: Bearer <token>)
3. Backend verifies JWT against Clerk's JWKS endpoint
4. Backend extracts user_id and roles from JWT claims

Roles are set in Clerk dashboard → Users → Public Metadata: {"role": "ADMIN"}
  The JWT session-token must include: { "role": "{{user.public_metadata.role}}" }
  (Clerk dashboard → Configure → Sessions → Customize session token)
  Backend reads the top-level 'role' claim from the decoded JWT.

  Values: ADMIN, MANAGER, REP, ANALYST
"""
import httpx
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from functools import lru_cache
from typing import Optional
import logging

from app.config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer()


# ── JWKS cache (refresh hourly in production) ──────────────────────────────────
_jwks_cache: Optional[dict] = None


async def get_jwks() -> dict:
    """Fetch Clerk's public keys for JWT verification. Cached in memory."""
    global _jwks_cache
    if _jwks_cache is None:
        if not settings.clerk_jwks_url:
            # Development mode — skip JWKS fetch
            return {}
        async with httpx.AsyncClient() as client:
            resp = await client.get(settings.clerk_jwks_url)
            resp.raise_for_status()
            _jwks_cache = resp.json()
    return _jwks_cache


# ── Token models ───────────────────────────────────────────────────────────────
class CurrentUser:
    def __init__(self, user_id: str, email: str, role: str, full_name: str = ""):
        self.user_id = user_id
        self.email = email
        self.role = role  # ADMIN, MANAGER, REP, ANALYST
        self.full_name = full_name

    @property
    def is_admin(self) -> bool:
        return self.role == "ADMIN"

    @property
    def is_manager(self) -> bool:
        return self.role in ("ADMIN", "MANAGER")

    @property
    def is_rep(self) -> bool:
        return self.role == "REP"

    @property
    def is_analyst(self) -> bool:
        return self.role in ("ADMIN", "MANAGER", "ANALYST")


# ── JWT verification ───────────────────────────────────────────────────────────
async def verify_clerk_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> CurrentUser:
    """
    Verify a Clerk JWT and return the current user.
    Raises 401 if token is invalid or expired.
    """
    token = credentials.credentials

    # Development bypass — accept any token in local env if no Clerk keys set
    if settings.app_env == "development" and not settings.clerk_jwks_url:
        logger.warning("AUTH BYPASS ACTIVE — development mode only")
        return CurrentUser(
            user_id="dev-user-001",
            email="dev@waterford.co.za",
            role="ADMIN",
            full_name="Dev User",
        )

    try:
        jwks = await get_jwks()
        # Clerk uses RS256 — verify against JWKS
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            options={"verify_aud": False},  # Clerk doesn't use aud claim
        )

        user_id: str = payload.get("sub", "")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: no subject claim",
            )

        # Role from custom Clerk session-token claim.
        # Configure in Clerk dashboard → Sessions → Customize session token:
        #   { "role": "{{user.public_metadata.role}}" }
        # This ensures the role is always present in the JWT payload at the
        # top level, regardless of Clerk plan or JWT template settings.
        role = payload.get("role", "REP")  # Default to REP if claim is absent
        email = payload.get("email", "")
        full_name = payload.get("name", "")

        return CurrentUser(user_id=user_id, email=email, role=role, full_name=full_name)

    except JWTError as e:
        logger.error(f"JWT verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


# ── Role-based dependencies ────────────────────────────────────────────────────
async def require_admin(current_user: CurrentUser = Depends(verify_clerk_token)) -> CurrentUser:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


async def require_manager(current_user: CurrentUser = Depends(verify_clerk_token)) -> CurrentUser:
    if not current_user.is_manager:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager access required")
    return current_user


async def require_analyst(current_user: CurrentUser = Depends(verify_clerk_token)) -> CurrentUser:
    if not current_user.is_analyst:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Analyst access required")
    return current_user


# ── Rep Attribution Helper ─────────────────────────────────────────────────────
# Single authoritative function for deriving rep from client_ownership SCD-2
# Implements Moya Fourie business rule: FY26 = Moya, FY27 = Head Office fallback

HEAD_OFFICE_REP_ID = "41c9ab80-3b6d-375e-5510-6e802813e086"  # rep-ho001

async def get_rep_at_date(
    client_id: str,
    transaction_date: str,  # ISO date string
    db,
) -> tuple[str, str]:
    """
    Returns (rep_id, rep_code) for a client at a given transaction date.

    Logic:
    1. Query client_ownership for active record at transaction_date
    2. If found: return that rep
    3. If NOT found (e.g. Moya accounts in FY27 where her ownership ended 2026-06-30):
       return Head Office rep (business rule: NSM decision Sep 2026)

    This is the SINGLE authoritative source for rep attribution.
    Never read rep from sales_transactions — rep_id was removed (AMBER item 2).
    """
    from sqlalchemy import text

    result = await db.execute(text("""
        SELECT co.rep_id, r.rep_code, r.full_name
        FROM client_ownership co
        JOIN reps r ON r.id = co.rep_id
        WHERE co.client_id = :client_id
          AND co.effective_from <= :tx_date::date
          AND (co.effective_to IS NULL OR co.effective_to >= :tx_date::date)
        ORDER BY co.effective_from DESC
        LIMIT 1
    """), {"client_id": client_id, "tx_date": transaction_date})

    row = result.fetchone()
    if row:
        return str(row[0]), str(row[1])

    # No active ownership record found (e.g. Moya accounts in FY27)
    # Business rule: fall back to Head Office
    return HEAD_OFFICE_REP_ID, "HO001"
