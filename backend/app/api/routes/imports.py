"""
S4-B: File upload and import management API.
"""
from fastapi import APIRouter, UploadFile, File, Form, Query, Depends
from fastapi.responses import JSONResponse
from typing import Optional
import tempfile, os, shutil, time
from psycopg2.extras import RealDictCursor
from app.database import get_db_conn
from app.core.auth import verify_clerk_token, require_manager, require_admin, CurrentUser
from fastapi import Depends
from app.services.import_engine.pipeline import import_file, _identify_file
from pathlib import Path

router = APIRouter(dependencies=[Depends(require_manager)],
    prefix="/api/imports", tags=["imports"])

UPLOAD_DIR = "/tmp/waterford_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload")
async def upload_and_import(
    file: UploadFile = File(...),
    source_override: Optional[str] = Form(None),
    imported_by: str = Form("webapp"),
):
    """
    Upload a sales data file and run the import pipeline.

    Stages:
    1. Save file temporarily
    2. Identify format (ERP CSV, NGF SalesOut, NGF Monthly, Distriliq CPT)
    3. Duplicate check (returns immediately if already imported)
    4. Import pipeline (classify, DC rules, client/product matching, coverage)
    5. Return plain-language result

    If format cannot be identified, returns identification_required=True
    with a list of known formats for the user to select.
    """
    if not file.filename:
        return JSONResponse({"error": "No filename"}, status_code=400)

    # Save to temp file
    tmp_path = os.path.join(UPLOAD_DIR, f"{int(time.time())}_{file.filename}")
    try:
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        file_size = os.path.getsize(tmp_path)

        # Enforce file size limit (50 MB)
        MAX_BYTES = 50 * 1024 * 1024
        if file_size > MAX_BYTES:
            return JSONResponse(
                {"status": "ERROR", "error": f"File too large ({file_size/(1024*1024):.1f} MB). Maximum 50 MB."},
                status_code=400,
            )

        # When source_override is provided, skip auto-identification entirely
        if source_override:
            connector = {"source_code": source_override, "report_type": source_override}
            meta = {"manual_override": True}
        else:
            connector, meta = _identify_file(tmp_path, file.filename)

        if not connector:
            return {
                "status": "IDENTIFICATION_REQUIRED",
                "filename": file.filename,
                "file_size_bytes": file_size,
                "message": "Cannot identify file format. Please select the source type.",
                "known_formats": [
                    {"code": "ERP_EXPORT",    "name": "ERP / EzyWine CSV export"},
                    {"code": "NGF_SALESOUT",  "name": "NGF SalesOut (Excel, 4REP tab)"},
                    {"code": "NGF_MONTHLY",   "name": "NGF Monthly Waterford Report (Excel, Data tab)"},
                    {"code": "DISTRILIQ_CPT", "name": "Distriliq CPT Client Report (Excel, Client History tab)"},
                ],
            }

        # Run import — pass source_override so pipeline skips re-identification
        try:
            result = import_file(tmp_path, imported_by=imported_by,
                                 source_override=source_override or None)
        except Exception as exc:
            result = {
                "status": "FAILED",
                "error": str(exc),
                "detected_format": connector.get("source_code") if connector else source_override,
            }
        result["filename"]        = file.filename
        result["file_size_bytes"] = file_size
        result["detected_format"] = connector.get("source_code") if connector else source_hint
        result["summary"] = _build_summary(result, file.filename)
        return result

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _build_summary(result: dict, filename: str) -> dict:
    """Build a plain-language summary of the import result."""
    status = result.get("status", "UNKNOWN")
    mapped  = result.get("rows_mapped", 0)
    excl    = result.get("rows_excluded", 0)
    pending = result.get("rows_pending_mapping", 0)
    total   = result.get("rows_total", 0)
    btls    = int(result.get("bottles_reportable", 0) or 0)
    rv      = int(result.get("rv_confirmed", 0) or 0)

    if status == "DUPLICATE_DETECTED":
        return {
            "headline": f"{filename} — already imported",
            "detail": "This file has been imported before. No action taken to prevent double-counting.",
        }

    lines = []
    lines.append(f"{total:,} rows processed")
    lines.append(f"{mapped:,} mapped and loaded")
    if excl:
        lines.append(f"{excl:,} excluded (DTC / private / export / internal / distributor sell-in)")
    if pending:
        lines.append(f"{pending:,} need client review (queued)")
    if btls:
        lines.append(f"{btls:,} commercial bottles loaded into market view")
    if rv:
        lines.append(f"R{rv:,} confirmed revenue loaded")

    return {
        "headline": f"{filename} — {status.replace('_', ' ').lower()}",
        "lines": lines,
    }


@router.get("/batches")
def list_batches(limit: int = 20, source_code: Optional[str] = None):
    """Import history — recent batches with row counts and status."""
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            where = "WHERE 1=1"
            params = []
            if source_code:
                where += " AND ds.source_code=%s"
                params.append(source_code)
            cur.execute(f"""
                SELECT b.id::text, b.file_name, b.status, b.received_date,
                       ds.source_code, ds.source_name,
                       (SELECT COUNT(*) FROM import_raw_rows WHERE batch_id=b.id) as total_rows,
                       (SELECT COUNT(*) FROM import_raw_rows WHERE batch_id=b.id
                                                               AND row_status='MAPPED') as mapped,
                       (SELECT COUNT(*) FROM import_raw_rows WHERE batch_id=b.id
                                                               AND row_status='PENDING_MAPPING') as pending,
                       b.created_at
                FROM import_batches b
                JOIN data_sources ds ON ds.id=b.source_id
                {where}
                ORDER BY b.created_at DESC
                LIMIT %s
            """, params + [limit])
            return {"batches": [dict(r) for r in cur.fetchall()]}
    finally:
        conn.close()


@router.get("/coverage")
def coverage_summary():
    """Data coverage grid — which source/region/period combinations are available."""
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT ds.source_code, dc.region,
                       fy.year_label, fp.period_name, fp.calendar_month, fp.calendar_year,
                       dc.coverage_status,
                       dc.updated_at
                FROM data_coverage dc
                JOIN data_sources ds ON ds.id=dc.source_id
                JOIN financial_periods fp ON fp.id=dc.financial_period_id
                JOIN financial_years fy ON fy.id=fp.financial_year_id
                ORDER BY ds.source_code, dc.region, fp.calendar_year, fp.calendar_month
            """)
            return {"coverage": [dict(r) for r in cur.fetchall()]}
    finally:
        conn.close()
