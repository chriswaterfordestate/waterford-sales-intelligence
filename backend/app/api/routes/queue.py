"""
S3-A: Import queue inspection and pending-client resolution.

Resolution uses retroactive_resolve.resolve_debtor_alias(), which applies the
same classification, DC rules, and transaction logic as the initial import pipeline.
The core invariant: resolving a row later produces the same DB state as if the
client had been known during the original import.
"""
from fastapi import APIRouter, Query, Depends
from typing import Optional
from psycopg2.extras import RealDictCursor
from app.database import get_db_conn
from app.core.auth import verify_clerk_token, require_manager, require_admin, CurrentUser
from fastapi import Depends
from app.services.import_engine.retroactive_resolve import resolve_debtor_alias

router = APIRouter(dependencies=[Depends(require_manager)],
    prefix="/api/queue", tags=["queue"])


@router.get("/summary")
def queue_summary():
    """Counts by issue_type for dashboard badges and UI indicators."""
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT iq.issue_type, COUNT(*) as count,
                       COALESCE(SUM((irr.raw_data->>'bottles')::numeric), 0) as total_bottles
                FROM import_queue_items iq
                JOIN import_raw_rows irr ON irr.id = iq.import_raw_row_id
                WHERE iq.status = 'OPEN'
                GROUP BY iq.issue_type ORDER BY count DESC
            """)
            return {'summary': [dict(r) for r in cur.fetchall()]}
    finally:
        conn.close()


@router.get("/")
def list_queue(
    issue_type: Optional[str] = None,
    source_code: Optional[str] = None,
    debtor_code: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
):
    """Paged queue. Filterable by issue_type, source, ERP debtor code."""
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            where = ["iq.status='OPEN'"]
            params: list = []
            if issue_type:
                where.append("iq.issue_type=%s"); params.append(issue_type)
            if source_code:
                where.append("ds.source_code=%s"); params.append(source_code)
            if debtor_code:
                where.append("irr.raw_data->>'debtor'=%s"); params.append(debtor_code)
            w = "WHERE " + " AND ".join(where)

            cur.execute(f"SELECT COUNT(*) FROM import_queue_items iq "
                        f"JOIN import_raw_rows irr ON irr.id=iq.import_raw_row_id "
                        f"JOIN import_batches b ON b.id=iq.import_batch_id "
                        f"JOIN data_sources ds ON ds.id=b.source_id {w}", params)
            total = cur.fetchone()['count']

            cur.execute(f"""
                SELECT iq.id::text as queue_item_id, iq.issue_type, iq.severity,
                       iq.source_value, iq.suggested_resolution,
                       irr.id::text as raw_row_id,
                       irr.raw_data->>'debtor'    as erp_debtor_code,
                       irr.raw_data->>'drname'    as erp_debtor_name,
                       irr.raw_data->>'drgrpname' as erp_debtor_group,
                       irr.raw_data->>'salgrpname' as salgrpname,
                       irr.raw_data->>'stockunit'  as stockunit,
                       irr.raw_data->>'bottles'    as bottles,
                       irr.raw_data->>'net'        as net_rv,
                       irr.raw_data->>'finmth'     as finmth,
                       irr.raw_data->>'finyear'    as finyear,
                       irr.mapping_error,
                       b.file_name, ds.source_code, iq.created_at
                FROM import_queue_items iq
                JOIN import_raw_rows irr ON irr.id=iq.import_raw_row_id
                JOIN import_batches b ON b.id=iq.import_batch_id
                JOIN data_sources ds ON ds.id=b.source_id
                {w}
                ORDER BY (irr.raw_data->>'bottles')::numeric DESC NULLS LAST, iq.created_at
                LIMIT %s OFFSET %s
            """, params + [page_size, (page - 1) * page_size])

            return {'total': total, 'page': page, 'page_size': page_size,
                    'items': [dict(i) for i in cur.fetchall()]}
    finally:
        conn.close()


@router.get("/debtors")
def list_unknown_debtors(min_bottles: float = 0, limit: int = 100):
    """
    Aggregate UNKNOWN_CLIENT rows by ERP debtor code.
    Used to prioritise which debtors to canonicalise first.
    """
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    irr.raw_data->>'debtor'    as erp_debtor_code,
                    irr.raw_data->>'drname'    as erp_debtor_name,
                    irr.raw_data->>'drgrpname' as erp_debtor_group,
                    COUNT(*) as queue_items,
                    SUM((irr.raw_data->>'bottles')::numeric) as total_bottles,
                    ROUND(SUM((irr.raw_data->>'net')::numeric)) as total_rv
                FROM import_queue_items iq
                JOIN import_raw_rows irr ON irr.id = iq.import_raw_row_id
                JOIN import_batches b ON b.id = iq.import_batch_id
                JOIN data_sources ds ON ds.id = b.source_id
                WHERE iq.status = 'OPEN'
                  AND iq.issue_type IN ('UNKNOWN_CLIENT','PROBABLE_CLIENT')
                GROUP BY 1,2,3
                HAVING SUM((irr.raw_data->>'bottles')::numeric) >= %s
                ORDER BY total_bottles DESC NULLS LAST
                LIMIT %s
            """, (min_bottles, limit))
            return {'debtors': [dict(r) for r in cur.fetchall()]}
    finally:
        conn.close()


@router.post("/resolve")
def resolve_debtor(payload: dict):
    """
    Resolve all pending rows for an ERP debtor code to a canonical client.

    Backend derives the rows to resolve from the debtor_code in raw_data —
    never trusts a frontend-supplied list of row IDs. This prevents blind
    alias registration for arbitrary rows.

    Required payload:
        debtor_code    : ERP source debtor code (e.g. 'SOLL0001')
        client_id      : canonical client UUID
        source_code    : data source (default 'ERP_EXPORT')

    The backend:
        1. Verifies the client exists
        2. Registers the debtor→client alias (idempotent)
        3. Finds ALL pending rows where raw_data->>'debtor' = debtor_code
        4. Calls resolve_debtor_alias() which uses the same classification
           and DC logic as the initial import pipeline
    """
    debtor_code = payload.get('debtor_code', '').strip()
    client_id   = payload.get('client_id',   '').strip()
    source_code = payload.get('source_code', 'ERP_EXPORT')

    if not debtor_code or not client_id:
        return {'error': 'debtor_code and client_id are required'}

    conn = get_db_conn()
    conn.autocommit = False
    try:
        result = resolve_debtor_alias(
            conn, debtor_code, client_id,
            source_code=source_code,
            confirmed_by='queue_resolution_api',
        )
        if 'error' in result:
            conn.rollback()
            return result
        conn.commit()
        return result
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()
