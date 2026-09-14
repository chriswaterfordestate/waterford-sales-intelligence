"""
S3-B: Sales reporting APIs.
"""
from fastapi import APIRouter, Query, Depends
from typing import Optional
from psycopg2.extras import RealDictCursor
from app.database import get_db_conn
from app.core.auth import verify_clerk_token, require_manager, require_admin, CurrentUser
from fastapi import Depends

router = APIRouter(dependencies=[Depends(verify_clerk_token)],
    prefix="/api/reports", tags=["reports"])


@router.get("/market-view")
def market_view(
    year_label: Optional[str] = None,
    sku_code: Optional[str] = None,
    territory_code: Optional[str] = None,
):
    """
    Deduplicated market view — DC rules already applied at write-time.
    Supported filters: year_label, sku_code, territory_code.
    Revenue: CONFIRMED from ERP invoice; ESTIMATED from ASP × bottles.

    Unsupported parameters (rep_code, channel_code) are not accepted
    to avoid silently filtering nothing.
    """
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            where = [
                "st.excluded_from_market_view = FALSE",
                "st.is_primary_record = TRUE",
            ]
            params: list = []

            if year_label:
                where.append("fy.year_label = %s")
                params.append(year_label)
            if sku_code:
                where.append("ps.sku_code = %s")
                params.append(sku_code)
            if territory_code:
                # Clients must be joined to filter by territory
                where.append("t.territory_code = %s")
                params.append(territory_code)

            # Always join clients + territories so territory_code filter works
            cur.execute(f"""
                SELECT
                    fy.year_label,
                    fp.period_name,
                    fp.calendar_year,
                    fp.calendar_month,
                    ds.source_code,
                    st.transaction_type,
                    stl.r_value_status,
                    p.product_code,
                    p.product_name,
                    ps.sku_code,
                    ps.sku_name,
                    ps.bottle_size_ml,
                    t.territory_code,
                    t.territory_name,
                    COUNT(st.id)                                     AS transactions,
                    SUM(stl.bottles_actual)                          AS bottles,
                    SUM(stl.standard_bottle_equiv)                   AS standard_btl_equiv,
                    SUM(COALESCE(stl.rand_value_confirmed, 0))       AS rv_confirmed,
                    SUM(COALESCE(stl.rand_value_estimated, 0))       AS rv_estimated
                FROM sales_transactions st
                JOIN sales_transaction_lines stl ON stl.transaction_id = st.id
                JOIN data_sources ds              ON ds.id   = st.source_id
                JOIN financial_periods fp         ON fp.id   = st.financial_period_id
                JOIN financial_years fy           ON fy.id   = fp.financial_year_id
                JOIN product_skus ps              ON ps.id   = stl.product_sku_id
                JOIN products p                   ON p.id    = ps.product_id
                LEFT JOIN clients c               ON c.id    = st.client_id
                LEFT JOIN territories t           ON t.id    = c.territory_id
                WHERE {" AND ".join(where)}
                GROUP BY 1,2,3,4,5,6,7,8,9,10,11,12,13,14
                ORDER BY fp.calendar_year, fp.calendar_month, p.product_code
            """, params)

            rows = cur.fetchall()
            totals = {
                'bottles':       sum(r['bottles'] or 0 for r in rows),
                'rv_confirmed':  sum(r['rv_confirmed'] or 0 for r in rows),
                'rv_estimated':  sum(r['rv_estimated'] or 0 for r in rows),
            }
            return {'rows': [dict(r) for r in rows], 'totals': totals,
                    'filters_applied': {
                        'year_label': year_label, 'sku_code': sku_code,
                        'territory_code': territory_code,
                    }}
    finally:
        conn.close()


@router.get("/rep-performance")
def rep_performance(
    actual_year:  str = Query('FY2026', description="Financial year of actuals (e.g. FY2026)"),
    target_year:  str = Query('FY2027', description="Financial year of targets (e.g. FY2027)"),
):
    """
    Rep performance: actuals vs targets with gap and achievement %.

    Parameters:
        actual_year: which year's actual sales to use (FY2026 = Jul 2025 – Jun 2026)
        target_year: which year's target set to compare against (FY2027 = Jul 2026 – Jun 2027)

    Response clearly labels actual year, target year, and per-period breakdown.
    """
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Actuals via SCD-2 rep attribution
            cur.execute("""
                SELECT
                    r.full_name as rep_name,
                    r.rep_code,
                    t.territory_code,
                    t.territory_name,
                    fp.period_name,
                    fp.calendar_month,
                    fp.calendar_year,
                    SUM(stl.bottles_actual)                    as bottles_actual,
                    SUM(COALESCE(stl.rand_value_confirmed, 0)) as rv_confirmed
                FROM sales_transactions st
                JOIN sales_transaction_lines stl ON stl.transaction_id = st.id
                JOIN financial_periods fp ON fp.id = st.financial_period_id
                JOIN financial_years fy   ON fy.id = fp.financial_year_id
                JOIN client_ownership co
                    ON co.client_id = st.client_id
                    AND co.effective_from <= st.transaction_date::date
                    AND (co.effective_to IS NULL OR co.effective_to >= st.transaction_date::date)
                JOIN reps r        ON r.id  = co.rep_id
                JOIN territories t ON t.id  = co.territory_id
                WHERE fy.year_label = %s
                  AND st.excluded_from_market_view = FALSE
                GROUP BY r.full_name, r.rep_code, t.territory_code,
                         t.territory_name, fp.period_name, fp.calendar_month, fp.calendar_year
                ORDER BY t.territory_code, fp.calendar_year, fp.calendar_month
            """, (actual_year,))
            actuals = cur.fetchall()

            # Territory-level targets for target_year
            cur.execute("""
                SELECT t.territory_code, t.territory_name,
                       fp.period_name, fp.calendar_month, fp.calendar_year,
                       SUM(tg.target_bottles)    as target_bottles,
                       SUM(tg.target_rand_value) as target_rv
                FROM targets tg
                JOIN territories t   ON t.id = tg.territory_id
                JOIN financial_periods fp ON fp.id = tg.financial_period_id
                JOIN financial_years fy   ON fy.id = fp.financial_year_id
                WHERE fy.year_label = %s
                  AND tg.territory_id IS NOT NULL
                GROUP BY t.territory_code, t.territory_name,
                         fp.period_name, fp.calendar_month, fp.calendar_year
                ORDER BY t.territory_code, fp.calendar_month
            """, (target_year,))
            targets = cur.fetchall()

        # Build combined response with gap and achievement %
        target_map: dict = {}
        for tg in targets:
            key = (tg['territory_code'], tg['calendar_month'])
            target_map[key] = {
                'target_bottles': float(tg['target_bottles'] or 0),
                'target_rv':      float(tg['target_rv'] or 0),
            }

        actuals_with_gap = []
        for a in actuals:
            key  = (a['territory_code'], a['calendar_month'])
            tg   = target_map.get(key, {'target_bottles': None, 'target_rv': None})
            row  = dict(a)
            row['target_bottles'] = tg['target_bottles']
            row['target_rv']      = tg['target_rv']
            if tg['target_bottles']:
                row['bottles_gap']  = float(a['bottles_actual'] or 0) - tg['target_bottles']
                row['achievement_pct'] = round(
                    float(a['bottles_actual'] or 0) / tg['target_bottles'] * 100, 1)
            else:
                row['bottles_gap'] = None
                row['achievement_pct'] = None
            actuals_with_gap.append(row)

        return {
            'actual_year':  actual_year,
            'target_year':  target_year,
            'actuals':      actuals_with_gap,
            'targets':      [dict(t) for t in targets],
            'note': (f"Actuals from {actual_year} (Jul–Jun). "
                     f"Targets from {target_year}. "
                     f"Financial year runs July–June.")
        }
    finally:
        conn.close()


@router.get("/product-mix")
def product_mix(year_label: Optional[str] = None):
    """Bottles and revenue by SKU/product/format."""
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            where = ["st.excluded_from_market_view=FALSE", "st.is_primary_record=TRUE"]
            params: list = []
            if year_label:
                where.append("fy.year_label=%s"); params.append(year_label)
            cur.execute(f"""
                SELECT p.product_code, p.product_name, p.brand_name, p.tier,
                       ps.sku_code, ps.sku_name, ps.bottle_size_ml,
                       SUM(stl.bottles_actual)                    as bottles,
                       SUM(stl.standard_bottle_equiv)             as standard_btl_equiv,
                       SUM(COALESCE(stl.rand_value_confirmed, 0)) as rv_confirmed,
                       SUM(COALESCE(stl.rand_value_estimated, 0)) as rv_estimated
                FROM sales_transactions st
                JOIN sales_transaction_lines stl ON stl.transaction_id=st.id
                JOIN product_skus ps ON ps.id=stl.product_sku_id
                JOIN products p      ON p.id=ps.product_id
                JOIN financial_periods fp ON fp.id=st.financial_period_id
                JOIN financial_years fy   ON fy.id=fp.financial_year_id
                WHERE {" AND ".join(where)}
                GROUP BY 1,2,3,4,5,6,7
                ORDER BY bottles DESC NULLS LAST
            """, params)
            rows = cur.fetchall()
            return {
                'rows': [dict(r) for r in rows],
                'total_bottles':      sum(r['bottles'] or 0 for r in rows),
                'total_rv_confirmed': sum(r['rv_confirmed'] or 0 for r in rows),
            }
    finally:
        conn.close()


@router.get("/client-leaderboard")
def client_leaderboard(
    year_label: Optional[str] = None,
    territory_code: Optional[str] = None,
    limit: int = 25,
):
    """Top clients by bottles, including R-value and territory."""
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            where = ["st.excluded_from_market_view=FALSE", "st.is_primary_record=TRUE",
                     "c.is_deleted=FALSE"]
            params: list = []
            if year_label:
                where.append("fy.year_label=%s"); params.append(year_label)
            if territory_code:
                where.append("t.territory_code=%s"); params.append(territory_code)
            cur.execute(f"""
                SELECT c.id::text as client_id, c.canonical_name, c.outlet_type,
                       t.territory_code, t.territory_name,
                       SUM(stl.bottles_actual) as bottles,
                       SUM(COALESCE(stl.rand_value_confirmed,0)) as rv_confirmed,
                       COUNT(DISTINCT st.financial_period_id) as periods_active
                FROM sales_transactions st
                JOIN sales_transaction_lines stl ON stl.transaction_id=st.id
                JOIN clients c    ON c.id=st.client_id
                LEFT JOIN territories t ON t.id=c.territory_id
                JOIN financial_periods fp ON fp.id=st.financial_period_id
                JOIN financial_years fy   ON fy.id=fp.financial_year_id
                WHERE {" AND ".join(where)}
                GROUP BY c.id, c.canonical_name, c.outlet_type, t.territory_code, t.territory_name
                ORDER BY bottles DESC NULLS LAST
                LIMIT %s
            """, params + [limit])
            return {'leaderboard': [dict(r) for r in cur.fetchall()]}
    finally:
        conn.close()
