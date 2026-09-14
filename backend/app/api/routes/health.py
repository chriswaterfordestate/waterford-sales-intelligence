"""
Health check endpoints.

/api/health          — basic liveness check (no DB)
/api/health/db       — database connectivity
/api/health/coverage — data coverage status summary (authenticated)

These are used by:
- Render.com health checks
- Import Centre UI to show system status
- Monitoring
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime
import logging

from app.database import get_db
from app.core.auth import verify_clerk_token, CurrentUser

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Liveness probe — no database required. Returns 200 if process is running."""
    return {
        "status": "ok",
        "service": "waterford-si-api",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/health/db")
async def db_health(db: AsyncSession = Depends(get_db)):
    """
    Database connectivity check.
    Returns 200 if PostgreSQL is reachable and schema exists.
    Returns 503 if database is unreachable.
    """
    try:
        result = await db.execute(
            text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'")
        )
        table_count = result.scalar()
        return {
            "status": "ok",
            "database": "connected",
            "tables": table_count,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unavailable: {str(e)}",
        )


@router.get("/health/coverage")
async def coverage_status(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(verify_clerk_token),
):
    """
    Data coverage summary — requires authentication.
    Shows how many periods are COVERED/MISSING/PARTIAL across all sources.
    Used by Import Centre UI to surface missing data.
    """
    try:
        result = await db.execute(
            text("""
                SELECT
                    coverage_status,
                    COUNT(*) as period_count
                FROM data_coverage
                GROUP BY coverage_status
                ORDER BY coverage_status
            """)
        )
        rows = result.fetchall()
        coverage_summary = {row[0]: row[1] for row in rows}

        # Also surface HIGH priority missing periods
        missing_result = await db.execute(
            text("""
                SELECT
                    ds.source_code,
                    dc.region,
                    fp.period_name,
                    dc.notes
                FROM data_coverage dc
                JOIN data_sources ds ON ds.id = dc.source_id
                JOIN financial_periods fp ON fp.id = dc.financial_period_id
                WHERE dc.coverage_status = 'MISSING'
                  AND fp.financial_year_id IN (
                    SELECT id FROM financial_years WHERE is_current = TRUE OR is_history = TRUE
                  )
                ORDER BY ds.source_code, dc.region, fp.start_date
                LIMIT 20
            """)
        )
        missing_periods = [
            {"source": row[0], "region": row[1], "period": row[2], "notes": row[3]}
            for row in missing_result.fetchall()
        ]

        return {
            "status": "ok",
            "coverage_summary": coverage_summary,
            "missing_periods": missing_periods,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Coverage health check failed: {e}")
        return {
            "status": "degraded",
            "error": str(e),
            "coverage_summary": {},
            "missing_periods": [],
        }
