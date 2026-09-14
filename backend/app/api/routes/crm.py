from __future__ import annotations
"""
Sprint 5: CRM API — activities, follow-ups, opportunities, support requests,
account health, range gap, ICS calendar events.
"""
import uuid
from datetime import date, datetime, timezone
from typing import Optional
from fastapi import APIRouter, Query, Depends
from fastapi.responses import Response
from psycopg2.extras import RealDictCursor

from app.database import get_db_conn
from app.core.auth import verify_clerk_token, require_manager, require_admin, CurrentUser
from fastapi import Depends

router = APIRouter(dependencies=[Depends(verify_clerk_token)],
    prefix="/api/crm", tags=["crm"])

# ── Constants ─────────────────────────────────────────────────────────────────
ACTIVITY_TYPES = ["VISIT","CALL","TASTING","EMAIL","EVENT","SAMPLE_DROP","TRAINING","LISTING_REVIEW","OTHER"]
FOLLOW_UP_TYPES = ["Call","Visit","Tasting","Training","Send Samples","Send Pricing",
                   "Follow-up","Event Support","Stock / Allocation","Management Follow-up","Other"]
SUPPORT_TYPES = ["Wine Training","Tasting","Samples","POS / Marketing Material","Event Support",
                 "Pricing / Deal","Stock / Allocation","Winemaker Visit","Management Support","Other"]
OPPORTUNITY_TYPES = ["New Listing","By The Glass","Additional Product","Increased Volume",
                     "Event","Training / Activation","New Outlet / Group Expansion","Other"]

def _health_config(conn) -> dict:
    with conn.cursor() as c:
        c.execute("SELECT key, value FROM crm_health_config")
        return {r[0]: float(r[1]) for r in c.fetchall()}

def _q1(conn, sql, params=()):
    with conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute(sql, params)
        return c.fetchone()

def _qn(conn, sql, params=()):
    with conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute(sql, params)
        return c.fetchall()

# ═══════════════════════════════════════════════════════════════════════════════
# ACTIVITIES (visits, calls, tastings, etc.)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/activities")
def create_activity(body: dict, current_user: "CurrentUser" = Depends(verify_clerk_token)):
    """Log a visit/call/tasting. Fields: client_id, rep_id, activity_date, activity_type,
    contact_person?, outcome?, general_notes?, overall_sentiment?, follow_up? """
    conn = get_db_conn()
    try:
        act_id = str(uuid.uuid4())

        # Resolve performing rep: for REP users, derive from user_rep_mappings
        # to prevent impersonation. MANAGER/ADMIN may assign to others.
        performing_rep_id = body.get('rep_id')
        created_by = current_user.user_id

        if not current_user.is_manager:
            # REP: override rep_id from server-side mapping
            with conn.cursor(cursor_factory=RealDictCursor) as c:
                c.execute("""SELECT rep_id::text FROM user_rep_mappings
                             WHERE clerk_user_id=%s AND is_active=TRUE LIMIT 1""",
                          (current_user.user_id,))
                row = c.fetchone()
                if row:
                    performing_rep_id = row['rep_id']
                elif not performing_rep_id:
                    return {"error": "No rep mapping found — ask admin to set up your account"}

        with conn.cursor() as c:
            c.execute("""
                INSERT INTO crm_activities
                    (id, client_id, rep_id, activity_date, activity_type,
                     contact_person, outcome, general_notes, overall_sentiment,
                     status, created_by)
                VALUES
                    (%s, %s::uuid, %s::uuid, %s, %s,
                     %s, %s, %s, %s,
                     'COMPLETED', %s)
            """, (
                act_id,
                body['client_id'], performing_rep_id,
                body.get('activity_date', date.today().isoformat()),
                body.get('activity_type', 'VISIT'),
                body.get('contact_person'), body.get('outcome'),
                body.get('general_notes', ''), body.get('overall_sentiment'),
                created_by,
            ))

            # Optional follow-up — uses server-resolved performing_rep_id and Clerk created_by
            fu = body.get('follow_up')
            fu_id = None
            if fu and fu.get('description'):
                fu_id = str(uuid.uuid4())
                # assigned_to may differ from creator (e.g. manager assigns to another rep)
                # but originating rep must be the authenticated user's rep
                assigned_rep = fu.get('assigned_to_rep_id') or performing_rep_id
                c.execute("""
                    INSERT INTO crm_follow_ups
                        (id, client_id, rep_id, activity_id, follow_up_type,
                         due_date, description, priority, status, assigned_to_rep_id,
                         calendar_event_uid, created_by)
                    VALUES
                        (%s, %s::uuid, %s::uuid, %s::uuid, %s,
                         %s, %s, %s, 'OPEN', %s,
                         %s, %s)
                """, (
                    fu_id,
                    body['client_id'], performing_rep_id, act_id,
                    fu.get('follow_up_type', 'Follow-up'),
                    fu.get('due_date'), fu.get('description', ''),
                    fu.get('priority', 'MEDIUM'),
                    assigned_rep,
                    fu.get('calendar_event_uid'),
                    created_by,   # always the authenticated Clerk user_id
                ))

            # Optional support request — originating rep is authenticated user's rep
            sr = body.get('support_request')
            sr_id = None
            if sr and sr.get('support_type'):
                sr_id = str(uuid.uuid4())
                c.execute("""
                    INSERT INTO crm_support_requests
                        (id, client_id, rep_id, activity_id, support_type,
                         assigned_to_rep_id, required_by, notes, status, created_by)
                    VALUES
                        (%s, %s::uuid, %s::uuid, %s::uuid, %s,
                         %s, %s, %s, 'REQUESTED', %s)
                """, (
                    sr_id,
                    body['client_id'], performing_rep_id, act_id,
                    sr['support_type'],
                    sr.get('assigned_to_rep_id'),
                    sr.get('required_by'),
                    sr.get('notes', ''),
                    created_by,   # always the authenticated Clerk user_id
                ))

        conn.commit()
        return {"activity_id": act_id, "follow_up_id": fu_id, "support_request_id": sr_id}
    finally:
        conn.close()


@router.get("/activities/client/{client_id}")
def get_client_activities(client_id: str, limit: int = 30):
    """Client activity timeline — activities, follow-ups, support requests, opportunities."""
    conn = get_db_conn()
    try:
        activities = _qn(conn, """
            SELECT ca.id::text, ca.activity_date, ca.activity_type,
                   ca.contact_person, ca.outcome, ca.general_notes,
                   ca.overall_sentiment, ca.status,
                   r.full_name as rep_name, r.rep_code,
                   ca.created_at
            FROM crm_activities ca
            JOIN reps r ON r.id=ca.rep_id
            WHERE ca.client_id=%s::uuid AND ca.is_deleted=FALSE
            ORDER BY ca.activity_date DESC, ca.created_at DESC
            LIMIT %s
        """, (client_id, limit))

        follow_ups = _qn(conn, """
            SELECT cf.id::text, cf.follow_up_type, cf.due_date, cf.description,
                   cf.priority, cf.status, cf.completed_at,
                   cf.activity_id::text,
                   r.full_name as rep_name,
                   ar.full_name as assigned_name
            FROM crm_follow_ups cf
            JOIN reps r ON r.id=cf.rep_id
            LEFT JOIN reps ar ON ar.id=cf.assigned_to_rep_id
            WHERE cf.client_id=%s::uuid AND cf.is_deleted=FALSE
            ORDER BY
                CASE cf.status WHEN 'OPEN' THEN 0 WHEN 'OVERDUE' THEN 0 ELSE 1 END,
                cf.due_date
        """, (client_id,))

        support_reqs = _qn(conn, """
            SELECT sr.id::text, sr.support_type, sr.required_by, sr.notes,
                   sr.status, sr.completed_at, sr.activity_id::text,
                   r.full_name as requested_by,
                   ar.full_name as assigned_to
            FROM crm_support_requests sr
            JOIN reps r ON r.id=sr.rep_id
            LEFT JOIN reps ar ON ar.id=sr.assigned_to_rep_id
            WHERE sr.client_id=%s::uuid AND sr.is_deleted=FALSE
            ORDER BY sr.created_at DESC
        """, (client_id,))

        opps = _qn(conn, """
            SELECT co.id::text, co.title, co.opportunity_type, co.potential,
                   co.estimated_bottles_annual, co.status, co.target_close_date,
                   co.notes, co.created_at,
                   r.full_name as rep_name
            FROM crm_opportunities co
            JOIN reps r ON r.id=co.rep_id
            WHERE co.client_id=%s::uuid AND co.is_deleted=FALSE
              AND co.status NOT IN ('LOST')
            ORDER BY co.created_at DESC
        """, (client_id,))

        # Last visit summary
        last = _q1(conn, """
            SELECT ca.activity_date, ca.overall_sentiment, ca.general_notes,
                   r.full_name as rep_name
            FROM crm_activities ca JOIN reps r ON r.id=ca.rep_id
            WHERE ca.client_id=%s::uuid AND ca.activity_type='VISIT'
              AND ca.is_deleted=FALSE
            ORDER BY ca.activity_date DESC LIMIT 1
        """, (client_id,))

        return {
            "last_visit": dict(last) if last else None,
            "activities": [dict(a) for a in activities],
            "follow_ups": [dict(f) for f in follow_ups],
            "support_requests": [dict(s) for s in support_reqs],
            "opportunities": [dict(o) for o in opps],
        }
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# FOLLOW-UPS / ACTIONS
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/follow-ups")
def create_follow_up(body: dict, current_user: CurrentUser = Depends(verify_clerk_token)):
    conn = get_db_conn()
    try:
        fu_id = str(uuid.uuid4())
        # Derive rep_id server-side for REP users
        performing_rep_id = body.get('rep_id')
        if not current_user.is_manager:
            with conn.cursor(cursor_factory=RealDictCursor) as c:
                c.execute("SELECT rep_id::text FROM user_rep_mappings WHERE clerk_user_id=%s AND is_active=TRUE LIMIT 1", (current_user.user_id,))
                row = c.fetchone()
                if row: performing_rep_id = row['rep_id']
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO crm_follow_ups
                    (id, client_id, rep_id, activity_id, opportunity_id,
                     follow_up_type, due_date, description, priority, status,
                     assigned_to_rep_id, calendar_event_uid, created_by)
                VALUES
                    (%s, %s::uuid, %s::uuid, %s, %s,
                     %s, %s, %s, %s, 'OPEN',
                     %s, %s, %s)
            """, (
                fu_id,
                body['client_id'], performing_rep_id,
                body.get('activity_id'), body.get('opportunity_id'),
                body.get('follow_up_type','Follow-up'), body.get('due_date'),
                body.get('description',''), body.get('priority','MEDIUM'),
                body.get('assigned_to_rep_id') or performing_rep_id,
                body.get('calendar_event_uid'),
                current_user.user_id,   # always Clerk user, never browser-supplied
            ))
        conn.commit()
        return {"follow_up_id": fu_id}
    finally:
        conn.close()


@router.patch("/follow-ups/{fu_id}")
def update_follow_up(fu_id: str, body: dict):
    """Complete, cancel, or update a follow-up."""
    conn = get_db_conn()
    try:
        sets, vals = [], []
        for col in ['status','description','due_date','priority','completed_notes','calendar_event_uid']:
            if col in body:
                sets.append(f"{col}=%s")
                vals.append(body[col])
        if body.get('status') in ('COMPLETED','CANCELLED'):
            sets.append("completed_at=%s")
            vals.append(datetime.now(timezone.utc))
        if sets:
            vals.append(fu_id)
            with conn.cursor() as c:
                c.execute(f"UPDATE crm_follow_ups SET {','.join(sets)} WHERE id=%s::uuid", vals)
            conn.commit()
        return {"follow_up_id": fu_id, "updated": len(sets) > 0}
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# SUPPORT REQUESTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/support-requests")
def create_support_request(body: dict, current_user: CurrentUser = Depends(verify_clerk_token)):
    conn = get_db_conn()
    try:
        sr_id = str(uuid.uuid4())
        performing_rep_id = body.get('rep_id')
        if not current_user.is_manager:
            with conn.cursor(cursor_factory=RealDictCursor) as c:
                c.execute("SELECT rep_id::text FROM user_rep_mappings WHERE clerk_user_id=%s AND is_active=TRUE LIMIT 1", (current_user.user_id,))
                row = c.fetchone()
                if row: performing_rep_id = row['rep_id']
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO crm_support_requests
                    (id, client_id, rep_id, activity_id, support_type,
                     assigned_to_rep_id, required_by, notes, status, created_by)
                VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, 'REQUESTED', %s)
            """, (
                sr_id, body['client_id'], performing_rep_id,
                body.get('activity_id'),
                body['support_type'],
                body.get('assigned_to_rep_id'),
                body.get('required_by'), body.get('notes',''),
                current_user.user_id,
            ))
        conn.commit()
        return {"support_request_id": sr_id}
    finally:
        conn.close()


@router.patch("/support-requests/{sr_id}")
def update_support_request(sr_id: str, body: dict):
    conn = get_db_conn()
    try:
        sets, vals = [], []
        for col in ['status','notes','assigned_to_rep_id','required_by','completed_notes']:
            if col in body:
                sets.append(f"{col}=%s"); vals.append(body[col])
        if body.get('status') == 'COMPLETED':
            sets.append("completed_at=%s"); vals.append(datetime.now(timezone.utc))
        if sets:
            vals.append(sr_id)
            with conn.cursor() as c:
                c.execute(f"UPDATE crm_support_requests SET {','.join(sets)} WHERE id=%s::uuid", vals)
            conn.commit()
        return {"support_request_id": sr_id}
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# OPPORTUNITIES
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/opportunities")
def create_opportunity(body: dict, current_user: CurrentUser = Depends(verify_clerk_token)):
    conn = get_db_conn()
    try:
        opp_id = str(uuid.uuid4())
        performing_rep_id = body.get('rep_id')
        if not current_user.is_manager:
            with conn.cursor(cursor_factory=RealDictCursor) as c:
                c.execute("SELECT rep_id::text FROM user_rep_mappings WHERE clerk_user_id=%s AND is_active=TRUE LIMIT 1", (current_user.user_id,))
                row = c.fetchone()
                if row: performing_rep_id = row['rep_id']
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO crm_opportunities
                    (id, client_id, rep_id, activity_id, opportunity_type,
                     title, description, potential, estimated_bottles_annual,
                     status, target_close_date, notes, created_by)
                VALUES (%s, %s::uuid, %s::uuid, %s, %s,
                        %s, %s, %s, %s,
                        'OPEN', %s, %s, %s)
            """, (
                opp_id, body['client_id'], performing_rep_id,
                body.get('activity_id'),
                body.get('opportunity_type','Other'),
                body['title'], body.get('description'),
                body.get('potential'), body.get('estimated_bottles_annual'),
                body.get('target_close_date'), body.get('notes',''),
                current_user.user_id,
            ))
        conn.commit()
        return {"opportunity_id": opp_id}
    finally:
        conn.close()


@router.patch("/opportunities/{opp_id}")
def update_opportunity(opp_id: str, body: dict):
    conn = get_db_conn()
    try:
        sets, vals = [], []
        for col in ['status','title','description','potential','estimated_bottles_annual',
                    'target_close_date','notes','lost_reason']:
            if col in body:
                sets.append(f"{col}=%s"); vals.append(body[col])
        if body.get('status') in ('WON','LOST'):
            sets.append("actual_close_date=%s"); vals.append(date.today().isoformat())
        if sets:
            vals.append(opp_id)
            with conn.cursor() as c:
                c.execute(f"UPDATE crm_opportunities SET {','.join(sets)} WHERE id=%s::uuid", vals)
            conn.commit()
        return {"opportunity_id": opp_id}
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ACCOUNT HEALTH & RANGE GAP
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/account-health/{client_id}")
def account_health(client_id: str):
    """
    Account health flags for a single client.
    Uses thresholds from crm_health_config.
    Transparent rules only — no black-box scoring.
    """
    conn = get_db_conn()
    try:
        cfg = _health_config(conn)
        today = date.today()

        # Last visit
        last_visit = _q1(conn, """
            SELECT activity_date, r.full_name rep_name
            FROM crm_activities ca JOIN reps r ON r.id=ca.rep_id
            WHERE ca.client_id=%s::uuid AND ca.activity_type='VISIT' AND ca.is_deleted=FALSE
            ORDER BY activity_date DESC LIMIT 1
        """, (client_id,))

        # Last order (FY2027 + FY2026)
        last_order = _q1(conn, """
            SELECT MAX(st.transaction_date) last_date
            FROM sales_transactions st
            WHERE st.client_id=%s::uuid AND st.excluded_from_market_view=FALSE
              AND st.is_primary_record=TRUE
        """, (client_id,))

        # FY2027 YTD vs FY2026 equivalent
        perf = _q1(conn, """
            SELECT
              SUM(CASE WHEN fy.year_label='FY2027' THEN stl.bottles_actual ELSE 0 END) fy27,
              SUM(CASE WHEN fy.year_label='FY2026' THEN stl.bottles_actual ELSE 0 END) fy26
            FROM sales_transactions st
            JOIN sales_transaction_lines stl ON stl.transaction_id=st.id
            JOIN financial_periods fp ON fp.id=st.financial_period_id
            JOIN financial_years fy ON fy.id=fp.financial_year_id
            WHERE st.client_id=%s::uuid AND st.excluded_from_market_view=FALSE
              AND st.is_primary_record=TRUE
              AND (
                (fy.year_label='FY2027')
                OR (fy.year_label='FY2026' AND fp.calendar_month IN (
                    SELECT fp2.calendar_month FROM financial_periods fp2
                    JOIN financial_years fy2 ON fy2.id=fp2.financial_year_id
                    WHERE fy2.year_label='FY2027'
                    AND fp2.id IN (
                        SELECT DISTINCT financial_period_id FROM sales_transactions
                        WHERE excluded_from_market_view=FALSE AND is_primary_record=TRUE
                    )
                ))
              )
        """, (client_id,))

        # Open overdue follow-up
        overdue = _q1(conn, """
            SELECT COUNT(*) cnt FROM crm_follow_ups
            WHERE client_id=%s::uuid AND status='OPEN' AND due_date < %s AND is_deleted=FALSE
        """, (client_id, today))

        flags = []

        # Visit overdue flag
        if last_visit:
            days_since = (today - last_visit['activity_date']).days
            if days_since > cfg.get('visit_overdue_days', 60):
                flags.append({
                    "flag": "VISIT_OVERDUE",
                    "label": "Visit overdue",
                    "detail": f"Last visit {days_since} days ago (by {last_visit['rep_name']})",
                })
        else:
            flags.append({
                "flag": "NO_VISIT",
                "label": "No recorded visit",
                "detail": "No visits logged for this client",
            })

        # Last order flag
        if last_order and last_order['last_date']:
            days_order = (today - last_order['last_date']).days
            if days_order > cfg.get('no_order_alert_days', 120):
                flags.append({
                    "flag": "NO_RECENT_ORDER",
                    "label": "No recent order",
                    "detail": f"Last order {days_order} days ago",
                })
        else:
            flags.append({
                "flag": "DORMANT",
                "label": "Dormant account",
                "detail": "No commercial order on record",
            })

        # YoY flag
        fy27 = float(perf['fy27'] or 0)
        fy26 = float(perf['fy26'] or 0)
        if fy26 > 0 and fy27 > 0:
            yoy = (fy27 / fy26 - 1) * 100
            threshold = cfg.get('decline_threshold_pct', 20)
            if yoy < -threshold:
                flags.append({
                    "flag": "DECLINING",
                    "label": "Declining",
                    "detail": f"↓ {abs(yoy):.0f}% vs FY2026 equivalent period",
                })
            elif yoy > cfg.get('growth_threshold_pct', 20):
                flags.append({
                    "flag": "GROWING",
                    "label": "Growing",
                    "detail": f"↑ {yoy:.0f}% vs FY2026 equivalent period",
                })

        # Overdue action flag
        if overdue and int(overdue['cnt']) > 0:
            flags.append({
                "flag": "ACTION_OVERDUE",
                "label": "Action overdue",
                "detail": f"{overdue['cnt']} action(s) past due date",
            })

        return {
            "client_id": client_id,
            "last_visit": dict(last_visit) if last_visit else None,
            "last_order_date": str(last_order['last_date']) if last_order and last_order['last_date'] else None,
            "fy27_ytd_bottles": fy27,
            "fy26_equiv_bottles": fy26,
            "yoy_pct": round((fy27/fy26 - 1)*100, 1) if fy26 > 0 else None,
            "open_overdue_actions": int(overdue['cnt']) if overdue else 0,
            "flags": flags,
        }
    finally:
        conn.close()


@router.get("/range-gap/{client_id}")
def range_gap(client_id: str):
    """
    Products in active Waterford portfolio vs what client currently buys.
    Shows what client IS buying and what they are NOT buying.
    Does not auto-create opportunities — rep records context manually.
    """
    conn = get_db_conn()
    try:
        # Active portfolio (products with at least one active SKU in FY2027 sales)
        active_products = _qn(conn, """
            SELECT DISTINCT p.id::text, p.product_name,
                   ps.sku_code, ps.bottle_size_ml
            FROM products p
            JOIN product_skus ps ON ps.product_id=p.id
            WHERE EXISTS (
                SELECT 1 FROM sales_transaction_lines stl
                JOIN sales_transactions st ON st.id=stl.transaction_id
                JOIN financial_periods fp ON fp.id=st.financial_period_id
                JOIN financial_years fy ON fy.id=fp.financial_year_id
                WHERE stl.product_sku_id=ps.id
                  AND fy.year_label IN ('FY2027','FY2026')
                  AND st.excluded_from_market_view=FALSE
            )
            ORDER BY p.product_name, ps.bottle_size_ml
        """)

        # What client buys (FY2027 YTD + last 2 FY2026)
        client_buying = _qn(conn, """
            SELECT DISTINCT p.id::text as product_id, p.product_name,
                   ps.sku_code, ps.bottle_size_ml,
                   SUM(stl.bottles_actual) total_bottles,
                   MAX(fp.calendar_year||'-'||fp.calendar_month) last_period
            FROM sales_transaction_lines stl
            JOIN sales_transactions st ON st.id=stl.transaction_id
            JOIN product_skus ps ON ps.id=stl.product_sku_id
            JOIN products p ON p.id=ps.product_id
            JOIN financial_periods fp ON fp.id=st.financial_period_id
            JOIN financial_years fy ON fy.id=fp.financial_year_id
            WHERE st.client_id=%s::uuid
              AND fy.year_label IN ('FY2027','FY2026')
              AND st.excluded_from_market_view=FALSE
              AND st.is_primary_record=TRUE
            GROUP BY 1,2,3,4
            ORDER BY total_bottles DESC
        """, (client_id,))

        buying_ids = {r['product_id'] for r in client_buying}
        not_buying = [p for p in active_products if p['id'] not in buying_ids]

        return {
            "currently_buying": [dict(r) for r in client_buying],
            "not_currently_buying": [dict(p) for p in not_buying],
            "gap_count": len(not_buying),
        }
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ICS CALENDAR EVENT
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/calendar-event.ics")
def calendar_event_ics(
    client_name: str,
    action_type: str,
    due_date: str,
    notes: str = "",
    follow_up_id: str = "",
):
    """
    Generate a downloadable .ics file for a follow-up action.
    Compatible with Outlook, Apple Calendar, Google Calendar.
    The web app remains system of record — this is a one-way export.
    Future path: replace with Microsoft Graph calendar event creation
    (POST /me/events) without changing the CRM data model.
    """
    uid = follow_up_id or str(uuid.uuid4())
    dt_str = due_date.replace("-", "")  # YYYYMMDD
    now_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    summary = f"{action_type} — {client_name}"
    description = notes.replace("\n", "\\n").replace(",", "\\,") if notes else ""
    # Web app reference
    description += f"\\n\\nWaterford Sales Intelligence reference: {uid}"

    ics = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Waterford Estate Sales Intelligence//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH
BEGIN:VEVENT
UID:{uid}@waterford.sales
DTSTAMP:{now_str}
DTSTART;VALUE=DATE:{dt_str}
DTEND;VALUE=DATE:{dt_str}
SUMMARY:{summary}
DESCRIPTION:{description}
STATUS:CONFIRMED
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR"""

    return Response(
        content=ics.strip(),
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="action_{uid[:8]}.ics"',
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MY DAY (rep home view)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/my-day")
def my_day_self(current_user: "CurrentUser" = Depends(verify_clerk_token)):
    """My Day for the currently logged-in user (rep derived server-side)."""
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("""
                SELECT rep_id::text FROM user_rep_mappings
                WHERE clerk_user_id=%s AND is_active=TRUE LIMIT 1
            """, (current_user.user_id,))
            row = c.fetchone()
    finally:
        conn.close()
    if not row:
        return {"error": "No rep mapping found for your account. Ask an admin to map your Clerk user to a rep.", "rep_id": None, "due_today": [], "overdue": [], "upcoming": [], "recent_activity": [], "opportunities": [], "support_requests": [], "accounts_needing_attention": []}
    rep_id = row['rep_id']
    return _my_day_for_rep(rep_id)


@router.get("/my-day/{rep_id}")
def my_day_for_rep(rep_id: str, _auth: "CurrentUser" = Depends(require_manager)):
    """My Day for a specific rep — managers only."""
    return _my_day_for_rep(rep_id)


def _my_day_for_rep(rep_id: str):
    """Internal implementation shared by /my-day and /my-day/{rep_id}."""
    """
    Rep-focused working view. Prioritises action over charts.
    Shows what needs attention today, what's overdue, and what's upcoming.
    """
    conn = get_db_conn()
    try:
        today = date.today()

        # Due today
        due_today = _qn(conn, """
            SELECT cf.id::text, cf.follow_up_type, cf.due_date, cf.description,
                   cf.priority, cf.status, c.canonical_name client_name, c.id::text client_id
            FROM crm_follow_ups cf JOIN clients c ON c.id=cf.client_id
            WHERE (cf.rep_id=%s::uuid OR cf.assigned_to_rep_id=%s::uuid)
              AND cf.due_date = %s AND cf.status='OPEN' AND cf.is_deleted=FALSE
            ORDER BY cf.priority, c.canonical_name
        """, (rep_id, rep_id, today))

        # Overdue
        overdue = _qn(conn, """
            SELECT cf.id::text, cf.follow_up_type, cf.due_date, cf.description,
                   cf.priority, cf.status, c.canonical_name client_name, c.id::text client_id,
                   (%s - cf.due_date) days_overdue
            FROM crm_follow_ups cf JOIN clients c ON c.id=cf.client_id
            WHERE (cf.rep_id=%s::uuid OR cf.assigned_to_rep_id=%s::uuid)
              AND cf.due_date < %s AND cf.status='OPEN' AND cf.is_deleted=FALSE
            ORDER BY cf.due_date, cf.priority
            LIMIT 20
        """, (today, rep_id, rep_id, today))

        # Upcoming 7 days
        upcoming = _qn(conn, """
            SELECT cf.id::text, cf.follow_up_type, cf.due_date, cf.description,
                   cf.priority, c.canonical_name client_name, c.id::text client_id
            FROM crm_follow_ups cf JOIN clients c ON c.id=cf.client_id
            WHERE (cf.rep_id=%s::uuid OR cf.assigned_to_rep_id=%s::uuid)
              AND cf.due_date BETWEEN %s AND (%s + INTERVAL '7 days')
              AND cf.status='OPEN' AND cf.is_deleted=FALSE
            ORDER BY cf.due_date, cf.priority
            LIMIT 15
        """, (rep_id, rep_id, today, today))

        # Recent activity (last 14 days)
        recent = _qn(conn, """
            SELECT ca.id::text, ca.activity_date, ca.activity_type,
                   ca.overall_sentiment, ca.general_notes,
                   c.canonical_name client_name, c.id::text client_id
            FROM crm_activities ca JOIN clients c ON c.id=ca.client_id
            WHERE ca.rep_id=%s::uuid AND ca.is_deleted=FALSE
              AND ca.activity_date >= (%s - INTERVAL '14 days')
            ORDER BY ca.activity_date DESC LIMIT 10
        """, (rep_id, today))

        # Open opportunities
        opps = _qn(conn, """
            SELECT co.id::text, co.title, co.opportunity_type, co.potential,
                   co.target_close_date, co.estimated_bottles_annual,
                   c.canonical_name client_name, c.id::text client_id
            FROM crm_opportunities co JOIN clients c ON c.id=co.client_id
            WHERE co.rep_id=%s::uuid AND co.status='OPEN' AND co.is_deleted=FALSE
            ORDER BY CASE co.potential WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END,
                     co.target_close_date NULLS LAST
            LIMIT 10
        """, (rep_id,))

        # Outstanding support requests created by this rep
        support = _qn(conn, """
            SELECT sr.id::text, sr.support_type, sr.required_by, sr.status,
                   sr.notes, c.canonical_name client_name, c.id::text client_id,
                   ar.full_name assigned_to
            FROM crm_support_requests sr
            JOIN clients c ON c.id=sr.client_id
            LEFT JOIN reps ar ON ar.id=sr.assigned_to_rep_id
            WHERE sr.rep_id=%s::uuid AND sr.status IN ('REQUESTED','IN_PROGRESS')
              AND sr.is_deleted=FALSE
            ORDER BY sr.required_by NULLS LAST, sr.created_at DESC
            LIMIT 10
        """, (rep_id,))

        # Accounts needing attention — owned clients with health issues
        attention = _qn(conn, """
            WITH rep_clients AS (
                SELECT DISTINCT co.client_id
                FROM client_ownership co
                WHERE co.rep_id=%s::uuid
                  AND co.effective_from <= %s
                  AND (co.effective_to IS NULL OR co.effective_to >= %s)
            ),
            last_orders AS (
                SELECT st.client_id, MAX(st.transaction_date) last_order
                FROM sales_transactions st
                WHERE st.excluded_from_market_view=FALSE AND st.is_primary_record=TRUE
                GROUP BY 1
            ),
            last_visits AS (
                SELECT ca.client_id, MAX(ca.activity_date) last_visit
                FROM crm_activities ca WHERE ca.activity_type='VISIT' AND ca.is_deleted=FALSE
                GROUP BY 1
            )
            SELECT c.id::text client_id, c.canonical_name,
                   lo.last_order, lv.last_visit,
                   EXTRACT(DAY FROM NOW()-lo.last_order)::int days_since_order,
                   EXTRACT(DAY FROM NOW()-lv.last_visit)::int days_since_visit
            FROM rep_clients rc
            JOIN clients c ON c.id=rc.client_id
            LEFT JOIN last_orders lo ON lo.client_id=rc.client_id
            LEFT JOIN last_visits lv ON lv.client_id=rc.client_id
            WHERE (lo.last_order IS NULL OR lo.last_order < %s - INTERVAL '90 days')
               OR (lv.last_visit IS NULL OR lv.last_visit < %s - INTERVAL '60 days')
            ORDER BY lo.last_order NULLS FIRST, lv.last_visit NULLS FIRST
            LIMIT 10
        """, (rep_id, today, today, today, today))

        return {
            "rep_id": rep_id,
            "as_of": str(today),
            "due_today":  [dict(r) for r in due_today],
            "overdue":    [dict(r) for r in overdue],
            "upcoming":   [dict(r) for r in upcoming],
            "recent_activity": [dict(r) for r in recent],
            "opportunities": [dict(r) for r in opps],
            "support_requests": [dict(r) for r in support],
            "accounts_needing_attention": [dict(r) for r in attention],
        }
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# MANAGER VIEW
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/manager-view")
def manager_view(days: int = 7, _auth: "CurrentUser" = Depends(require_manager)):
    """
    Management team activity view — cross-rep visibility.
    Shows activity, overdue actions, support requests, opportunities.
    """
    conn = get_db_conn()
    try:
        today = date.today()

        # Team activity this period
        team_activity = _qn(conn, """
            SELECT r.full_name, r.rep_code,
                   COUNT(CASE WHEN ca.activity_date >= %s - (%s * INTERVAL '1 day') THEN 1 END) recent,
                   COUNT(CASE WHEN ca.activity_date >= date_trunc('month', %s::date) THEN 1 END) this_month
            FROM crm_activities ca JOIN reps r ON r.id=ca.rep_id
            WHERE ca.is_deleted=FALSE AND r.employment_status='ACTIVE'
            GROUP BY 1,2 ORDER BY recent DESC
        """, (today, days, today))

        # All overdue actions
        all_overdue = _qn(conn, """
            SELECT cf.id::text, cf.follow_up_type, cf.due_date,
                   cf.description, cf.priority,
                   r.full_name rep_name, c.canonical_name client_name, c.id::text client_id,
                   (current_date - cf.due_date) days_overdue
            FROM crm_follow_ups cf
            JOIN clients c ON c.id=cf.client_id
            JOIN reps r ON r.id=COALESCE(cf.assigned_to_rep_id, cf.rep_id)
            WHERE cf.status='OPEN' AND cf.due_date < %s AND cf.is_deleted=FALSE
            ORDER BY cf.due_date, cf.priority
            LIMIT 30
        """, (today,))

        # Support requests outstanding
        support = _qn(conn, """
            SELECT sr.id::text, sr.support_type, sr.required_by, sr.status, sr.notes,
                   r.full_name requested_by, ar.full_name assigned_to,
                   c.canonical_name client_name, c.id::text client_id,
                   sr.created_at
            FROM crm_support_requests sr
            JOIN clients c ON c.id=sr.client_id
            JOIN reps r ON r.id=sr.rep_id
            LEFT JOIN reps ar ON ar.id=sr.assigned_to_rep_id
            WHERE sr.status IN ('REQUESTED','IN_PROGRESS') AND sr.is_deleted=FALSE
            ORDER BY sr.required_by NULLS LAST, sr.created_at
            LIMIT 30
        """)

        # Opportunities by rep
        opps = _qn(conn, """
            SELECT r.full_name rep_name, co.status,
                   COUNT(*) count,
                   COALESCE(SUM(co.estimated_bottles_annual),0) total_bottles
            FROM crm_opportunities co JOIN reps r ON r.id=co.rep_id
            WHERE co.is_deleted=FALSE
            GROUP BY 1,2 ORDER BY 1,2
        """)

        # Clients with declining sales + no recent visit or open action
        concern = _qn(conn, """
            WITH fy27 AS (
                SELECT st.client_id, SUM(stl.bottles_actual) btls
                FROM sales_transactions st JOIN sales_transaction_lines stl ON stl.transaction_id=st.id
                JOIN financial_years fy ON fy.id=(
                    SELECT fy2.id FROM financial_periods fp2
                    JOIN financial_years fy2 ON fy2.id=fp2.financial_year_id
                    WHERE fp2.id=st.financial_period_id)
                WHERE fy.year_label='FY2027' AND st.excluded_from_market_view=FALSE AND st.is_primary_record=TRUE
                GROUP BY 1
            ),
            fy26 AS (
                SELECT st.client_id, SUM(stl.bottles_actual) btls
                FROM sales_transactions st JOIN sales_transaction_lines stl ON stl.transaction_id=st.id
                JOIN financial_years fy ON fy.id=(
                    SELECT fy2.id FROM financial_periods fp2
                    JOIN financial_years fy2 ON fy2.id=fp2.financial_year_id
                    WHERE fp2.id=st.financial_period_id)
                WHERE fy.year_label='FY2026' AND st.excluded_from_market_view=FALSE AND st.is_primary_record=TRUE
                GROUP BY 1
            )
            SELECT c.id::text client_id, c.canonical_name,
                   ROUND(f27.btls) fy27_btls, ROUND(f26.btls) fy26_btls,
                   ROUND((f27.btls/NULLIF(f26.btls,0)-1)*100,1) yoy_pct,
                   r.full_name rep_name
            FROM fy27 f27
            JOIN fy26 f26 ON f26.client_id=f27.client_id
            LEFT JOIN client_ownership co ON co.client_id=f27.client_id
              AND co.effective_from <= %s AND (co.effective_to IS NULL OR co.effective_to >= %s)
            LEFT JOIN reps r ON r.id=co.rep_id
            JOIN clients c ON c.id=f27.client_id
            WHERE (f27.btls / NULLIF(f26.btls,0) - 1) * 100 < -20
            ORDER BY yoy_pct LIMIT 15
        """, (today, today))

        return {
            "as_of": str(today),
            "period_days": days,
            "team_activity": [dict(r) for r in team_activity],
            "all_overdue": [dict(r) for r in all_overdue],
            "support_requests": [dict(r) for r in support],
            "opportunities_by_rep": [dict(r) for r in opps],
            "accounts_of_concern": [dict(r) for r in concern],
        }
    finally:
        conn.close()


@router.get("/reps")
def list_reps():
    conn = get_db_conn()
    try:
        reps = _qn(conn, """
            SELECT id::text, rep_code, full_name, role, employment_status
            FROM reps WHERE employment_status='ACTIVE' ORDER BY full_name
        """)
        return {"reps": [dict(r) for r in reps]}
    finally:
        conn.close()
