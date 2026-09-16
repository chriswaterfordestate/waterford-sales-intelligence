"""
S3-C: Client search and Client 360.
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from app.database import get_db_conn
from app.core.auth import verify_clerk_token, require_manager, require_admin, CurrentUser
from rapidfuzz import fuzz
import re

router = APIRouter(dependencies=[Depends(verify_clerk_token)],
    prefix="/api/clients", tags=["clients"])


def _norm(name: str) -> str:
    n = re.sub(r"['\-&\(\)\.,/\\]", ' ', (name or '').upper())
    return re.sub(r'\s+', ' ', n).strip()


@router.get("/search")
def search_clients(q: str = Query(..., min_length=1), limit: int = 10):
    """
    Fuzzy search across canonical names, trading names, and all source aliases.
    Returns top matches with score and basic client context.
    """
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Pull all active clients with their aliases
            cur.execute("""
                SELECT
                    c.id::text,
                    c.canonical_name,
                    c.trading_name,
                    c.outlet_type,
                    c.tier,
                    c.is_distributor,
                    t.territory_code,
                    t.territory_name,
                    ARRAY_AGG(DISTINCT csa.source_code) FILTER (
                        WHERE csa.source_code IS NOT NULL AND csa.match_status='ACTIVE'
                    ) as erp_codes,
                    ARRAY_AGG(DISTINCT csa.source_name) FILTER (
                        WHERE csa.source_name IS NOT NULL AND csa.match_status='ACTIVE'
                    ) as alias_names
                FROM clients c
                LEFT JOIN territories t ON t.id = c.territory_id
                LEFT JOIN client_source_aliases csa ON csa.client_id = c.id
                WHERE c.is_deleted = FALSE
                GROUP BY c.id, c.canonical_name, c.trading_name, c.outlet_type,
                         c.tier, c.is_distributor, t.territory_code, t.territory_name
            """)
            all_clients = cur.fetchall()

        q_norm = _norm(q)
        results = []
        for client in all_clients:
            # Score against canonical name, trading name, and all alias names
            candidates = [client['canonical_name'], client['trading_name'] or '']
            if client['alias_names']:
                candidates.extend(client['alias_names'])
            if client['erp_codes']:
                candidates.extend(client['erp_codes'])

            best_score = max(fuzz.token_sort_ratio(q_norm, _norm(c)) for c in candidates if c)
            if best_score >= 40:
                results.append({'score': best_score, **dict(client)})

        results.sort(key=lambda x: -x['score'])
        return {'results': results[:limit], 'total_searched': len(all_clients)}
    finally:
        conn.close()


@router.get("/{client_id}")
def get_client_360(client_id: str):
    """
    Client 360: canonical record, territory, rep, aliases, transaction summary by period.
    """
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Core client record
            cur.execute("""
                SELECT c.id::text, c.canonical_name, c.trading_name, c.outlet_type,
                       c.tier, c.is_distributor, c.notes,
                       t.territory_code, t.territory_name
                FROM clients c
                LEFT JOIN territories t ON t.id=c.territory_id
                WHERE c.id=%s::uuid AND c.is_deleted=FALSE
            """, (client_id,))
            client = cur.fetchone()
            if not client:
                return {'error': 'Client not found'}

            # Source aliases
            cur.execute("""
                SELECT csa.source_code, csa.source_name, csa.match_confidence,
                       ds.source_code as data_source
                FROM client_source_aliases csa
                JOIN data_sources ds ON ds.id=csa.source_id
                WHERE csa.client_id=%s::uuid AND csa.match_status='ACTIVE'
                ORDER BY ds.source_code, csa.source_code
            """, (client_id,))
            aliases = cur.fetchall()

            # Current rep (from SCD-2 ownership)
            cur.execute("""
                SELECT r.full_name, r.rep_code, r.role,
                       t.territory_code, t.territory_name,
                       cto.effective_from, cto.effective_to
                FROM client_ownership cto
                JOIN reps r ON r.id = cto.rep_id
                LEFT JOIN territories t ON t.id = cto.territory_id
                WHERE cto.client_id=%s::uuid
                  AND cto.effective_from <= CURRENT_DATE
                  AND (cto.effective_to IS NULL OR cto.effective_to >= CURRENT_DATE)
                ORDER BY cto.effective_from DESC
                LIMIT 3
            """, (client_id,))
            reps = cur.fetchall()

            # Transaction summary by period
            cur.execute("""
                SELECT
                    fy.year_label,
                    fp.period_name,
                    fp.calendar_month,
                    fp.calendar_year,
                    ds.source_code,
                    st.transaction_type,
                    st.excluded_from_market_view,
                    COUNT(st.id) as transactions,
                    ROUND(SUM(stl.bottles_actual))::int as bottles,
                    ROUND(SUM(COALESCE(stl.rand_value_confirmed,0)))::int as rv_confirmed,
                    ROUND(SUM(COALESCE(stl.rand_value_estimated,0)))::int as rv_estimated
                FROM sales_transactions st
                JOIN sales_transaction_lines stl ON stl.transaction_id=st.id
                JOIN data_sources ds ON ds.id=st.source_id
                JOIN financial_periods fp ON fp.id=st.financial_period_id
                JOIN financial_years fy ON fy.id=fp.financial_year_id
                WHERE st.client_id=%s::uuid
                GROUP BY 1,2,3,4,5,6,7
                ORDER BY fp.calendar_year, fp.calendar_month
            """, (client_id,))
            periods = cur.fetchall()

        return {
            'client': dict(client),
            'aliases': [dict(a) for a in aliases],
            'current_reps': [dict(r) for r in reps],
            'period_summary': [dict(p) for p in periods],
            'totals': {
                'bottles': sum(p['bottles'] for p in periods if not p['excluded_from_market_view']),
                'rv_confirmed': sum(p['rv_confirmed'] for p in periods if not p['excluded_from_market_view']),
            }
        }
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Ownership management
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{client_id}/ownership")
def get_ownership_history(client_id: str):
    """
    Full effective-dated ownership history for a client.
    Returns current owner first, then historical records.
    """
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    co.id::text,
                    r.full_name, r.rep_code, r.role,
                    t.territory_name,
                    co.effective_from, co.effective_to,
                    co.change_reason,
                    co.notes,
                    co.created_by,
                    co.created_at,
                    CASE
                        WHEN co.effective_from <= CURRENT_DATE
                         AND (co.effective_to IS NULL OR co.effective_to >= CURRENT_DATE)
                        THEN TRUE ELSE FALSE
                    END AS is_current
                FROM client_ownership co
                JOIN reps r ON r.id = co.rep_id
                LEFT JOIN territories t ON t.id = co.territory_id
                WHERE co.client_id = %s::uuid
                ORDER BY co.effective_from DESC
            """, (client_id,))
            history = cur.fetchall()
        return {"history": [dict(h) for h in history]}
    finally:
        conn.close()


@router.post("/{client_id}/ownership")
def change_ownership(client_id: str, body: dict,
                     _auth=Depends(require_manager)):
    """
    Assign a new owner to a client (manager/admin only).
    Closes any currently-open ownership records (ERP_DERIVED or otherwise)
    the day before the new effective_from, then creates a MANUAL_ASSIGNMENT record.

    body: { rep_id, effective_from, notes? }
    """
    conn = get_db_conn()
    try:
        rep_id = body.get("rep_id")
        effective_from_str = body.get("effective_from")
        notes = body.get("notes", "")

        if not rep_id or not effective_from_str:
            return {"error": "rep_id and effective_from are required"}

        from datetime import date as date_type, timedelta
        effective_from = date_type.fromisoformat(effective_from_str)
        close_date = effective_from - timedelta(days=1)

        with conn.cursor() as cur:
            # Close any currently-open ownership that starts before effective_from
            cur.execute("""
                UPDATE client_ownership
                SET effective_to = %s
                WHERE client_id = %s::uuid
                  AND (effective_to IS NULL OR effective_to >= %s)
                  AND effective_from < %s
            """, (close_date, client_id, effective_from, effective_from))

            # Create the new MANUAL_ASSIGNMENT record
            cur.execute("""
                INSERT INTO client_ownership
                    (client_id, rep_id, effective_from, effective_to,
                     change_reason, notes, created_by)
                VALUES
                    (%s::uuid, %s::uuid, %s, NULL,
                     'MANUAL_ASSIGNMENT', %s, 'web_app')
                RETURNING id::text
            """, (client_id, rep_id, effective_from, notes))
            new_id = cur.fetchone()[0]

        conn.commit()
        return {"id": new_id, "status": "ok"}
    finally:
        conn.close()


@router.post("/transfers/bulk")
def bulk_transfer_ownership(body: dict, _auth=Depends(require_manager)):
    """
    Transfer selected clients from one rep to another.
    Only transfers clients that are CURRENTLY owned by from_rep_id.

    body: {
      from_rep_id: str,
      to_rep_id:   str,
      effective_from: str (YYYY-MM-DD),
      client_ids:  list[str] | "all"   -- "all" means all currently-owned clients
      notes?: str
    }
    """
    conn = get_db_conn()
    try:
        from_rep_id  = body.get("from_rep_id")
        to_rep_id    = body.get("to_rep_id")
        eff_from_str = body.get("effective_from")
        client_ids   = body.get("client_ids", "all")
        notes        = body.get("notes", f"Bulk transfer")

        if not from_rep_id or not to_rep_id or not eff_from_str:
            return {"error": "from_rep_id, to_rep_id and effective_from are required"}
        if from_rep_id == to_rep_id:
            return {"error": "from_rep_id and to_rep_id must be different"}

        from datetime import date as date_type, timedelta
        effective_from = date_type.fromisoformat(eff_from_str)
        close_date     = effective_from - timedelta(days=1)

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Find clients currently owned by from_rep
            if client_ids == "all":
                cur.execute("""
                    SELECT DISTINCT client_id::text
                    FROM client_ownership
                    WHERE rep_id = %s::uuid
                      AND effective_from <= CURRENT_DATE
                      AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
                """, (from_rep_id,))
                target_ids = [r["client_id"] for r in cur.fetchall()]
            else:
                # Filter supplied list to those currently owned by from_rep
                cur.execute("""
                    SELECT DISTINCT client_id::text
                    FROM client_ownership
                    WHERE rep_id = %s::uuid
                      AND client_id = ANY(%s::uuid[])
                      AND effective_from <= CURRENT_DATE
                      AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
                """, (from_rep_id, client_ids))
                target_ids = [r["client_id"] for r in cur.fetchall()]

        transferred = 0
        with conn.cursor() as cur:
            for cid in target_ids:
                # Close current ownership
                cur.execute("""
                    UPDATE client_ownership
                    SET effective_to = %s
                    WHERE client_id = %s::uuid
                      AND rep_id = %s::uuid
                      AND (effective_to IS NULL OR effective_to >= %s)
                      AND effective_from < %s
                """, (close_date, cid, from_rep_id, effective_from, effective_from))

                # Open new MANUAL_ASSIGNMENT
                cur.execute("""
                    INSERT INTO client_ownership
                        (client_id, rep_id, effective_from, effective_to,
                         change_reason, notes, created_by)
                    VALUES
                        (%s::uuid, %s::uuid, %s, NULL,
                         'MANUAL_ASSIGNMENT', %s, 'web_app')
                """, (cid, to_rep_id, effective_from, notes))
                transferred += 1

        conn.commit()
        return {"transferred": transferred, "effective_from": eff_from_str, "status": "ok"}
    finally:
        conn.close()
