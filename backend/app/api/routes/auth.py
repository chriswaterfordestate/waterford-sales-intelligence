"""
Sprint 6: Authentication and user/rep mapping endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from app.database import get_db_conn
from app.core.auth import verify_clerk_token, require_admin, CurrentUser

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me")
async def me(current_user: CurrentUser = Depends(verify_clerk_token)):
    """Return current user and their mapped rep record (if any)."""
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("""
                SELECT urm.clerk_user_id,
                       r.id::text rep_id, r.rep_code, r.full_name,
                       r.role, r.employment_status,
                       t.territory_code, t.territory_name
                FROM user_rep_mappings urm
                JOIN reps r ON r.id = urm.rep_id
                LEFT JOIN rep_territory_assignments rta ON rta.rep_id = r.id
                    AND rta.effective_from <= CURRENT_DATE
                    AND (rta.effective_to IS NULL OR rta.effective_to >= CURRENT_DATE)
                LEFT JOIN territories t ON t.id = rta.territory_id
                WHERE urm.clerk_user_id = %s AND urm.is_active = TRUE
                LIMIT 1
            """, (current_user.user_id,))
            mapping = c.fetchone()
        return {
            "user_id": current_user.user_id,
            "email": current_user.email,
            "role": current_user.role,
            "full_name": current_user.full_name,
            "rep": dict(mapping) if mapping else None,
        }
    finally:
        conn.close()


@router.get("/user-mappings")
async def list_mappings(current_user: CurrentUser = Depends(require_admin)):
    """Admin: list all Clerk user → rep mappings."""
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("""
                SELECT urm.id::text, urm.clerk_user_id, urm.clerk_email,
                       r.rep_code, r.full_name, urm.is_active, urm.created_at
                FROM user_rep_mappings urm
                JOIN reps r ON r.id = urm.rep_id
                ORDER BY r.full_name
            """)
            return {"mappings": [dict(r) for r in c.fetchall()]}
    finally:
        conn.close()


@router.post("/user-mappings")
async def create_mapping(body: dict, current_user: CurrentUser = Depends(require_admin)):
    """
    Admin: map a Clerk user ID to a rep record.
    body: { clerk_user_id, clerk_email, rep_id }
    """
    conn = get_db_conn()
    try:
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO user_rep_mappings
                    (clerk_user_id, clerk_email, rep_id, created_by)
                VALUES (%s, %s, %s::uuid, %s)
                ON CONFLICT (clerk_user_id) DO UPDATE
                SET clerk_email = EXCLUDED.clerk_email,
                    rep_id = EXCLUDED.rep_id,
                    is_active = TRUE,
                    updated_at = NOW()
            """, (body['clerk_user_id'], body.get('clerk_email',''),
                  body['rep_id'], current_user.user_id))
        conn.commit()
        return {"status": "ok", "clerk_user_id": body['clerk_user_id']}
    finally:
        conn.close()


@router.delete("/user-mappings/{clerk_user_id}")
async def remove_mapping(clerk_user_id: str,
                         current_user: CurrentUser = Depends(require_admin)):
    conn = get_db_conn()
    try:
        with conn.cursor() as c:
            c.execute("""
                UPDATE user_rep_mappings SET is_active = FALSE
                WHERE clerk_user_id = %s
            """, (clerk_user_id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        conn.close()
