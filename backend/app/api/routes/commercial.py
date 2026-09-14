"""
S4-D: Commercial client queue prioritisation.
S4-E: FY2027 commercial dashboard APIs.
S4-G: Period-aware target achievement.
"""
from fastapi import APIRouter, Query, Depends
from typing import Optional
from psycopg2.extras import RealDictCursor
from app.database import get_db_conn
from app.core.auth import verify_clerk_token, require_manager, require_admin, CurrentUser
from fastapi import Depends
from app.services.import_engine.classify import DTC_GROUPS, EXPORT_DEBTORS

router = APIRouter(dependencies=[Depends(require_manager)],
    prefix="/api/commercial", tags=["commercial"])

# ERP drgrpname prefixes that indicate non-commercial rows
_NON_COMMERCIAL_DRGRP = {
    'Wine Club', 'DTC', 'Private Clients', 'Society', 'Staff', 'Cellar Door',
    'Tasting Room (Cash Accounts)', 'Tasting Room - Tour Operators', 'Online Clients',
    'Legacy Members', 'Internal - Tasting Room', 'Wine Drive',
}
_EXPORT_DRGRP_PREFIX = ('Export',)
_INTERNAL_DRGRP = ('Non Wine Sales', 'Head Office', 'Internal')


@router.get("/queue/debtors")
def commercial_debtor_queue(
    min_rv: float = 0,
    limit: int = 100,
):
    """
    Prioritised commercial unknown-client queue.

    Excludes:
      - DTC / Wine Club / Tasting Room / Private Client groups
      - Export drgrpname groups
      - Internal/non-wine accounts
      - EXPORT_DEBTORS list

    Prioritises by: confirmed ERP revenue DESC, then bottles, then recency.
    Returns probable canonical match (fuzzy MCR lookup) where available.
    """
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Build exclusion list for drgrpname
            exclude_drgrps = _NON_COMMERCIAL_DRGRP | {'Internal - Tasting Room', 'Wine Drive'}
            exclude_drgrp_tuple = tuple(exclude_drgrps) + ('',)

            cur.execute("""
                WITH debtor_agg AS (
                    SELECT
                        irr.raw_data->>'debtor'    as erp_debtor_code,
                        MAX(irr.raw_data->>'drname') as erp_debtor_name,
                        MAX(irr.raw_data->>'drgrpname') as erp_debtor_group,
                        COUNT(*) as row_count,
                        SUM((irr.raw_data->>'bottles')::numeric) as total_bottles,
                        ROUND(SUM((irr.raw_data->>'net')::numeric)) as total_rv_confirmed,
                        MIN((irr.raw_data->>'finmth')||'/'||(irr.raw_data->>'finyear')) as first_period,
                        MAX((irr.raw_data->>'finmth')||'/'||(irr.raw_data->>'finyear')) as last_period,
                        COUNT(DISTINCT (irr.raw_data->>'finmth')||(irr.raw_data->>'finyear')) as period_count
                    FROM import_queue_items iq
                    JOIN import_raw_rows irr ON irr.id = iq.import_raw_row_id
                    WHERE iq.status = 'OPEN'
                      AND iq.issue_type IN ('UNKNOWN_CLIENT', 'PROBABLE_CLIENT')
                      -- Exclude non-commercial ERP groups
                      AND irr.raw_data->>'drgrpname' NOT IN %s
                      -- Exclude export groups (drgrpname starts with 'Export')
                      AND irr.raw_data->>'drgrpname' NOT ILIKE 'Export%%'
                      -- Exclude internal groups
                      AND irr.raw_data->>'drgrpname' NOT ILIKE 'Non Wine Sales%%'
                      AND irr.raw_data->>'drgrpname' NOT ILIKE 'Internal%%'
                    GROUP BY irr.raw_data->>'debtor'
                    HAVING ROUND(SUM((irr.raw_data->>'net')::numeric)) >= %s
                )
                SELECT d.*,
                    -- Best probable canonical match using name prefix similarity
                    (SELECT c.canonical_name FROM clients c
                     WHERE c.is_deleted=FALSE
                       AND LOWER(c.canonical_name) SIMILAR TO
                           '%%' || LOWER(LEFT(d.erp_debtor_name, 8)) || '%%'
                     LIMIT 1) as probable_match
                FROM debtor_agg d
                -- Exclude debtors that already have an active ERP alias (already resolved)
                WHERE NOT EXISTS (
                    SELECT 1 FROM client_source_aliases csa
                    JOIN data_sources ds2 ON ds2.id=csa.source_id
                    WHERE csa.source_code=d.erp_debtor_code
                      AND ds2.source_code='ERP_EXPORT'
                      AND csa.match_status='ACTIVE'
                )
                ORDER BY d.total_rv_confirmed DESC NULLS LAST,
                         d.total_bottles DESC NULLS LAST,
                         d.period_count DESC,
                         d.last_period DESC
                LIMIT %s
            """, (exclude_drgrp_tuple, min_rv, limit))

            debtors = [dict(r) for r in cur.fetchall()]

            return {
                'debtors': debtors,
                'total': len(debtors),
                'note': 'Non-commercial accounts (DTC, export, internal) excluded. Sorted by confirmed ERP revenue.'
            }
    finally:
        conn.close()



@router.post("/queue/resolve-debtor")
def resolve_debtor(body: dict):
    """
    Resolve all pending queue items for an ERP debtor code to a canonical client.

    Workflow:
    1. Find all OPEN queue items for the given erp_debtor_code
    2. Register a source alias (ERP debtor_code → canonical client)
    3. Reprocess each pending row through retroactive resolution
    4. Queue items closed; transactions created

    Body: { "erp_debtor_code": str, "client_id": str, "action": "MAP"|"EXCLUDE" }
    """
    from app.services.import_engine.retroactive_resolve import resolve_raw_row
    from psycopg2.extras import RealDictCursor
    conn = get_db_conn()
    try:
        erp_code  = body.get("erp_debtor_code", "").strip()
        client_id = body.get("client_id", "").strip()
        action    = body.get("action", "MAP")

        if not erp_code:
            return {"error": "erp_debtor_code required"}

        # 1. Register source alias first so retroactive resolution can find it
        if action == "MAP" and client_id:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id FROM data_sources WHERE source_code='ERP_EXPORT'")
                src = cur.fetchone()
                if src:
                    cur.execute("""
                        INSERT INTO client_source_aliases
                            (client_id, source_id, source_code, source_name,
                             match_confidence, match_status, matched_by, confirmed_by)
                        SELECT %s::uuid, %s::uuid, %s,
                               (SELECT canonical_name FROM clients WHERE id=%s::uuid),
                               'CONFIRMED','ACTIVE','queue_resolver','NSM'
                        WHERE NOT EXISTS (
                            SELECT 1 FROM client_source_aliases
                            WHERE source_id=%s::uuid AND source_code=%s AND match_status='ACTIVE'
                        )
                    """, (client_id, src['id'], erp_code, client_id, src['id'], erp_code))
            conn.commit()

        # 2. Find all open queue items for this debtor code
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT irr.id::text as raw_row_id
                FROM import_queue_items iq
                JOIN import_raw_rows irr ON irr.id = iq.import_raw_row_id
                WHERE iq.status = 'OPEN'
                  AND irr.raw_data->>'debtor' = %s
            """, (erp_code,))
            items = cur.fetchall()

        # 3. Retroactively resolve each pending row — resolve_raw_row requires client_id
        resolved = skipped = failed = 0
        for item in items:
            try:
                result = resolve_raw_row(conn, item['raw_row_id'], client_id)
                s = result.get('status', '')
                if s in ('resolved', 'mapped', 'excluded'):
                    resolved += 1
                    # Close the queue item (resolution_type must match CHECK constraint)
                    with conn.cursor() as _c:
                        _c.execute("""
                            UPDATE import_queue_items
                            SET status='RESOLVED', resolved_by='queue_resolver',
                                resolved_at=NOW(), resolution_notes='Debtor alias mapped via commercial queue',
                                resolution_type='ACCEPTED'
                            WHERE import_raw_row_id=%s::uuid AND status='OPEN'
                        """, (item['raw_row_id'],))
                else:
                    skipped += 1
            except Exception:
                failed += 1
        conn.commit()

        return {
            "erp_debtor_code": erp_code,
            "client_id": client_id,
            "action": action,
            "items_found": len(items),
            "resolved": resolved,
            "skipped": skipped,
            "failed": failed,
        }
    finally:
        conn.close()

@router.get("/dashboard")
def commercial_dashboard(
    actual_year: str = "FY2027",
    compare_year: str = "FY2026",
):
    """
    S4-E: FY2027 commercial dashboard.

    Returns:
    - FY2027 YTD commercial performance (periods with data)
    - FY2026 equivalent-period comparison (same calendar months)
    - Territory and product breakdowns
    - Distributor sell-in shown separately (not in commercial totals)
    - Target achievement for periods that have targets
    """
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:

            # ── Determine FY2027 periods with actual data ──────────────────────
            cur.execute("""
                SELECT DISTINCT fp.calendar_year, fp.calendar_month, fp.period_name
                FROM sales_transactions st
                JOIN financial_periods fp ON fp.id=st.financial_period_id
                JOIN financial_years fy ON fy.id=fp.financial_year_id
                WHERE fy.year_label=%s AND st.is_primary_record=TRUE
                ORDER BY fp.calendar_year, fp.calendar_month
            """, (actual_year,))
            fy27_periods = cur.fetchall()

            if not fy27_periods:
                return {"actual_year": actual_year, "compare_year": compare_year,
                        "fy27_periods": [], "note": "No FY2027 data yet"}

            ytd_months = [(p['calendar_year'], p['calendar_month']) for p in fy27_periods]
            ytd_label = f"{fy27_periods[0]['period_name']} – {fy27_periods[-1]['period_name']}"

            def period_filter_cte(year_label, months):
                """Build SQL to select only specific calendar months in a year."""
                pairs = " OR ".join(
                    f"(fp.calendar_year={y} AND fp.calendar_month={m})" for y, m in months
                )
                return f"fy.year_label='{year_label}' AND ({pairs})"

            # ── FY2027 YTD commercial (DIRECT_SALE + DISTRIBUTOR_SELL_THROUGH) ──
            fy27_where = period_filter_cte(actual_year, ytd_months)
            cur.execute(f"""
                SELECT
                    st.transaction_type,
                    ds.source_code,
                    t.territory_code,
                    t.territory_name,
                    COUNT(st.id) as transactions,
                    SUM(stl.bottles_actual) as bottles,
                    SUM(COALESCE(stl.rand_value_confirmed,0)) as rv_confirmed,
                    SUM(COALESCE(stl.rand_value_estimated,0)) as rv_estimated
                FROM sales_transactions st
                JOIN sales_transaction_lines stl ON stl.transaction_id=st.id
                JOIN data_sources ds ON ds.id=st.source_id
                JOIN financial_periods fp ON fp.id=st.financial_period_id
                JOIN financial_years fy ON fy.id=fp.financial_year_id
                LEFT JOIN clients c ON c.id=st.client_id
                LEFT JOIN territories t ON t.id=c.territory_id
                WHERE {fy27_where}
                  AND st.is_primary_record=TRUE
                  AND st.excluded_from_market_view=FALSE
                GROUP BY 1,2,3,4
                ORDER BY bottles DESC
            """)
            fy27_breakdown = [dict(r) for r in cur.fetchall()]

            # ── Distributor sell-in separately ──────────────────────────────────
            cur.execute(f"""
                SELECT COUNT(st.id) txns,
                       SUM(stl.bottles_actual) bottles,
                       SUM(COALESCE(stl.rand_value_confirmed,0)) rv_confirmed
                FROM sales_transactions st
                JOIN sales_transaction_lines stl ON stl.transaction_id=st.id
                JOIN financial_periods fp ON fp.id=st.financial_period_id
                JOIN financial_years fy ON fy.id=fp.financial_year_id
                WHERE {fy27_where}
                  AND st.transaction_type='DISTRIBUTOR_SELL_IN'
                  AND st.is_primary_record=TRUE
            """)
            sell_in = dict(cur.fetchone() or {})

            # ── FY2026 equivalent-period comparison ────────────────────────────
            # Same calendar months in FY2026 (Jul/Aug → Jul 2025/Aug 2025)
            compare_months = [(y - 1, m) for y, m in ytd_months]  # shift back 1 year
            compare_where = period_filter_cte(compare_year, compare_months)
            cur.execute(f"""
                SELECT COUNT(st.id) txns,
                       SUM(stl.bottles_actual) bottles,
                       SUM(COALESCE(stl.rand_value_confirmed,0)) rv_confirmed
                FROM sales_transactions st
                JOIN sales_transaction_lines stl ON stl.transaction_id=st.id
                JOIN financial_periods fp ON fp.id=st.financial_period_id
                JOIN financial_years fy ON fy.id=fp.financial_year_id
                WHERE {compare_where}
                  AND st.excluded_from_market_view=FALSE
                  AND st.is_primary_record=TRUE
            """)
            fy26_compare = dict(cur.fetchone() or {})

            # ── Product mix (FY2027 YTD) ──────────────────────────────────────
            cur.execute(f"""
                SELECT p.product_name, ps.sku_code, ps.bottle_size_ml,
                       SUM(stl.bottles_actual) bottles,
                       SUM(COALESCE(stl.rand_value_confirmed,0)) rv_confirmed
                FROM sales_transactions st
                JOIN sales_transaction_lines stl ON stl.transaction_id=st.id
                JOIN product_skus ps ON ps.id=stl.product_sku_id
                JOIN products p ON p.id=ps.product_id
                JOIN financial_periods fp ON fp.id=st.financial_period_id
                JOIN financial_years fy ON fy.id=fp.financial_year_id
                WHERE {fy27_where}
                  AND st.excluded_from_market_view=FALSE
                  AND st.is_primary_record=TRUE
                GROUP BY 1,2,3
                ORDER BY bottles DESC
            """)
            product_mix = [dict(r) for r in cur.fetchall()]

            # ── Target achievement (period-aware, bottles-based) ────────────────
            # Targets use bottle targets only. Revenue target shown for reference.
            # Jul+Aug 2026: GAU = 3,557 + 3,953 = 7,510 bottles combined target.
            pair_expr = " OR ".join(
                f"(fp.calendar_year={y} AND fp.calendar_month={m})"
                for y, m in ytd_months
            ) or "FALSE"
            cur.execute(f"""
                SELECT t.territory_code, t.territory_name,
                       SUM(tg.target_bottles) target_bottles,
                       SUM(tg.target_rand_value) target_rv
                FROM targets tg
                JOIN territories t ON t.id=tg.territory_id
                JOIN financial_periods fp ON fp.id=tg.financial_period_id
                JOIN financial_years fy ON fy.id=fp.financial_year_id
                WHERE fy.year_label=%s
                  AND tg.territory_id IS NOT NULL
                  AND ({pair_expr})
                GROUP BY 1,2
                ORDER BY 2
            """, (actual_year,))
            targets_raw = [dict(r) for r in cur.fetchall()]

            # Compute actual bottles per territory for achievement
            terr_btls = {}
            for r in fy27_breakdown:
                tc = r.get('territory_code') or 'UNASSIGNED'
                terr_btls[tc] = terr_btls.get(tc, 0) + float(r.get('bottles') or 0)

            targets = []
            for tg in targets_raw:
                tc = tg['territory_code']
                tgt_btls = float(tg['target_bottles'] or 0)
                act_btls = terr_btls.get(tc, 0)
                ach_pct  = round(act_btls / tgt_btls * 100, 1) if tgt_btls > 0 else None
                targets.append({
                    **tg,
                    "actual_bottles": act_btls,
                    "achievement_pct": ach_pct,
                    "note": f"Combined {tc} target — bottle-based. Period: {ytd_label}",
                })

            # ── Pending queue summary for context ────────────────────────────
            cur.execute("""
                SELECT COUNT(*) open_items,
                       COALESCE(SUM((irr.raw_data->>'bottles')::numeric),0) pending_bottles
                FROM import_queue_items iq
                JOIN import_raw_rows irr ON irr.id=iq.import_raw_row_id
                WHERE iq.status='OPEN' AND iq.issue_type='UNKNOWN_CLIENT'
            """)
            queue_info = dict(cur.fetchone() or {})

            # ── Totals ────────────────────────────────────────────────────────
            fy27_btls = float(sum(float(r['bottles'] or 0) for r in fy27_breakdown))
            fy27_rv   = float(sum(float(r['rv_confirmed'] or 0) for r in fy27_breakdown))
            fy26_btls = float(fy26_compare.get('bottles') or 0) if fy26_compare.get('bottles') is not None else 0.0
            yoy_pct   = round((fy27_btls / fy26_btls - 1) * 100, 1) if fy26_btls else None

        return {
            "actual_year":    actual_year,
            "compare_year":   compare_year,
            "ytd_label":      ytd_label,
            "ytd_periods":    [dict(p) for p in fy27_periods],
            "totals": {
                "fy27_bottles":       fy27_btls,
                "fy27_rv_confirmed":  fy27_rv,
                "fy26_bottles":       fy26_btls,
                "fy26_rv_confirmed":  float(fy26_compare.get('rv_confirmed') or 0),
                "yoy_pct":            yoy_pct,
            },
            "distributor_sell_in": {
                "bottles":       float(sell_in.get('bottles') or 0),
                "rv_confirmed":  float(sell_in.get('rv_confirmed') or 0),
                "note":          "Confirmed Waterford revenue from distributor sell-in. Not included in end-client commercial totals.",
            },
            "fy27_breakdown":  fy27_breakdown,
            "fy26_comparison": fy26_compare,
            "product_mix":     product_mix,
            "targets":         targets,
            "queue":           queue_info,
            "data_note":       f"Commercial market view only (DIRECT_SALE + DISTRIBUTOR_SELL_THROUGH). Distributor sell-in shown separately.",
        }
    finally:
        conn.close()


@router.get("/client360/{client_id}")
def client360_fy2027(
    client_id: str,
    actual_year:  str = "FY2027",
    compare_year: str = "FY2026",
):
    """
    S4-F: Client 360 FY2027 commercial view.

    Shows:
    - FY2027 YTD vs FY2026 equivalent period
    - Monthly trend (FY2026 full year + FY2027 months)
    - Product mix
    - Source/channel breakdown
    - Ownership (SCD-2, effective-dated)
    """
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:

            # Client record
            cur.execute("""
                SELECT c.id::text, c.canonical_name, c.trading_name, c.outlet_type,
                       c.tier, c.is_distributor, c.notes,
                       t.territory_code, t.territory_name
                FROM clients c
                LEFT JOIN territories t ON t.id=c.territory_id
                WHERE c.id=%s::uuid AND c.is_deleted=FALSE
            """, (client_id,))
            client_rec = cur.fetchone()
            if not client_rec:
                return {"error": "Client not found"}

            # Current ownership
            cur.execute("""
                SELECT r.full_name, r.rep_code, r.role,
                       t.territory_code, t.territory_name,
                       co.effective_from, co.effective_to
                FROM client_ownership co
                JOIN reps r ON r.id=co.rep_id
                LEFT JOIN territories t ON t.id=co.territory_id
                WHERE co.client_id=%s::uuid
                  AND co.effective_from <= CURRENT_DATE
                  AND (co.effective_to IS NULL OR co.effective_to >= CURRENT_DATE)
                ORDER BY co.effective_from DESC LIMIT 3
            """, (client_id,))
            ownership = cur.fetchall()

            # Source aliases
            cur.execute("""
                SELECT csa.source_code, csa.source_name, ds.source_code as source_type
                FROM client_source_aliases csa
                JOIN data_sources ds ON ds.id=csa.source_id
                WHERE csa.client_id=%s::uuid AND csa.match_status='ACTIVE'
                ORDER BY ds.source_code, csa.source_code
            """, (client_id,))
            aliases = cur.fetchall()

            # ── FY2027 YTD periods (calendar months with data) ──────────────
            cur.execute("""
                SELECT DISTINCT fp.calendar_year, fp.calendar_month
                FROM sales_transactions st
                JOIN financial_periods fp ON fp.id=st.financial_period_id
                JOIN financial_years fy ON fy.id=fp.financial_year_id
                WHERE fy.year_label=%s AND st.is_primary_record=TRUE
                ORDER BY fp.calendar_year, fp.calendar_month
            """, (actual_year,))
            fy27_months = [(r['calendar_year'], r['calendar_month']) for r in cur.fetchall()]

            # Compare: same months in previous year
            compare_months = [(y - 1, m) for y, m in fy27_months]

            def _period_expr(months):
                return " OR ".join(f"(fp.calendar_year={y} AND fp.calendar_month={m})"
                                   for y, m in months) or "FALSE"

            # ── FY2027 client actuals ──────────────────────────────────────
            def client_totals(year_label, months):
                if not months:
                    return {}
                cur.execute(f"""
                    SELECT COUNT(st.id) txns,
                           SUM(stl.bottles_actual) bottles,
                           SUM(COALESCE(stl.rand_value_confirmed,0)) rv_confirmed,
                           SUM(COALESCE(stl.rand_value_estimated,0)) rv_estimated,
                           MAX(st.transaction_date) last_transaction
                    FROM sales_transactions st
                    JOIN sales_transaction_lines stl ON stl.transaction_id=st.id
                    JOIN financial_periods fp ON fp.id=st.financial_period_id
                    JOIN financial_years fy ON fy.id=fp.financial_year_id
                    WHERE st.client_id=%s::uuid
                      AND fy.year_label=%s
                      AND ({_period_expr(months)})
                      AND st.excluded_from_market_view=FALSE
                      AND st.is_primary_record=TRUE
                """, (client_id, year_label))
                return dict(cur.fetchone() or {})

            fy27_totals = client_totals(actual_year, fy27_months)
            fy26_totals = client_totals(compare_year, compare_months)

            fy27_btls = float(fy27_totals.get('bottles') or 0)
            fy26_btls = float(fy26_totals.get('bottles') or 0)
            yoy_pct = round((fy27_btls / fy26_btls - 1) * 100, 1) if fy26_btls else None

            # ── Monthly trend: FY2026 full year + FY2027 YTD ──────────────
            cur.execute("""
                SELECT fy.year_label, fp.calendar_year, fp.calendar_month, fp.period_name,
                       ds.source_code,
                       SUM(stl.bottles_actual) bottles,
                       SUM(COALESCE(stl.rand_value_confirmed,0)) rv_confirmed,
                       SUM(COALESCE(stl.rand_value_estimated,0)) rv_estimated
                FROM sales_transactions st
                JOIN sales_transaction_lines stl ON stl.transaction_id=st.id
                JOIN data_sources ds ON ds.id=st.source_id
                JOIN financial_periods fp ON fp.id=st.financial_period_id
                JOIN financial_years fy ON fy.id=fp.financial_year_id
                WHERE st.client_id=%s::uuid
                  AND fy.year_label IN (%s, %s)
                  AND st.excluded_from_market_view=FALSE
                  AND st.is_primary_record=TRUE
                GROUP BY 1,2,3,4,5
                ORDER BY fp.calendar_year, fp.calendar_month, ds.source_code
            """, (client_id, actual_year, compare_year))
            monthly_trend = [dict(r) for r in cur.fetchall()]

            # ── Product mix (FY2027 YTD + FY2026 full) ─────────────────────
            cur.execute("""
                SELECT fy.year_label, p.product_name, ps.sku_code, ps.bottle_size_ml,
                       SUM(stl.bottles_actual) bottles,
                       SUM(COALESCE(stl.rand_value_confirmed,0)) rv_confirmed
                FROM sales_transactions st
                JOIN sales_transaction_lines stl ON stl.transaction_id=st.id
                JOIN product_skus ps ON ps.id=stl.product_sku_id
                JOIN products p ON p.id=ps.product_id
                JOIN financial_periods fp ON fp.id=st.financial_period_id
                JOIN financial_years fy ON fy.id=fp.financial_year_id
                WHERE st.client_id=%s::uuid
                  AND fy.year_label IN (%s, %s)
                  AND st.excluded_from_market_view=FALSE
                  AND st.is_primary_record=TRUE
                GROUP BY 1,2,3,4
                ORDER BY fy.year_label DESC, bottles DESC
            """, (client_id, actual_year, compare_year))
            product_mix = [dict(r) for r in cur.fetchall()]

            # ── Source/channel breakdown ────────────────────────────────────
            cur.execute("""
                SELECT fy.year_label, ds.source_code, ds.source_name,
                       st.transaction_type,
                       SUM(stl.bottles_actual) bottles,
                       SUM(COALESCE(stl.rand_value_confirmed,0)) rv_confirmed
                FROM sales_transactions st
                JOIN sales_transaction_lines stl ON stl.transaction_id=st.id
                JOIN data_sources ds ON ds.id=st.source_id
                JOIN financial_periods fp ON fp.id=st.financial_period_id
                JOIN financial_years fy ON fy.id=fp.financial_year_id
                WHERE st.client_id=%s::uuid
                  AND fy.year_label IN (%s, %s)
                  AND st.excluded_from_market_view=FALSE
                  AND st.is_primary_record=TRUE
                GROUP BY 1,2,3,4
                ORDER BY fy.year_label DESC, bottles DESC
            """, (client_id, actual_year, compare_year))
            source_breakdown = [dict(r) for r in cur.fetchall()]

        return {
            "client":          dict(client_rec),
            "ownership":       [dict(r) for r in ownership],
            "aliases":         [dict(r) for r in aliases],
            "actual_year":     actual_year,
            "compare_year":    compare_year,
            "ytd_label":       f"Jul–{fy27_months[-1][1] if fy27_months else 'Jun'} {actual_year}" if fy27_months else None,
            "performance": {
                "fy27_bottles":      fy27_btls,
                "fy27_rv_confirmed": float(fy27_totals.get('rv_confirmed') or 0),
                "fy27_rv_estimated": float(fy27_totals.get('rv_estimated') or 0),
                "fy26_bottles":      fy26_btls,
                "fy26_rv_confirmed": float(fy26_totals.get('rv_confirmed') or 0),
                "yoy_pct":           yoy_pct,
                "last_transaction":  str(fy27_totals.get('last_transaction') or ''),
            },
            "monthly_trend":   monthly_trend,
            "product_mix":     product_mix,
            "source_breakdown": source_breakdown,
        }
    finally:
        conn.close()
