"""
ERP-derived ownership derivation.

Called after a successful ERP batch import to establish historical client/rep
ownership records from the ERP srepname field.

Design rules
────────────
1. Only ERP_EXPORT rows are processed — NGF and Distriliq are not authoritative
   for Waterford rep ownership.
2. Per client, we collect all (rep, date) points from the batch raw_data, then
   derive contiguous periods, splitting whenever the rep changes.
3. Only rows already resolved to a canonical client_id are considered.
4. Repeated imports are idempotent: we update the period end-date of an existing
   ERP_DERIVED record rather than creating a duplicate.
5. MANUAL_ASSIGNMENT records take absolute precedence — ERP_DERIVED records are
   never created that overlap a MANUAL_ASSIGNMENT, and existing MANUAL_ASSIGNMENT
   records are never modified by this function.
6. Unknown/blank srepname values are skipped.

Historical rep-change detection
────────────────────────────────
Within the import batch we sort all resolved rows for a client by calendar date.
We then walk the timeline: when the srepname changes from one non-null value to
another, we close the previous period and open a new one.

This means:
  Jul 2025 Nathalie → Dec 2025 Nathalie → (period 1: Jul 2025 – Dec 2025)
  Jan 2026 Sergio   → Jun 2026 Sergio   → (period 2: Jan 2026 – Jun 2026)

We produce two non-overlapping ownership records.
"""
from __future__ import annotations

import uuid
import logging
from collections import defaultdict
from datetime import date
from typing import Optional

from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def derive_erp_ownership(conn, batch_id: str) -> dict:
    """
    Derive client_ownership records from ERP srepname data in a completed batch.
    Returns summary counts for logging.
    """
    summary = {"created": 0, "extended": 0, "skipped_manual": 0,
               "skipped_unknown_rep": 0, "skipped_no_srepname": 0}

    # Only process ERP_EXPORT batches
    with conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute("""
            SELECT ds.source_code
            FROM import_batches ib
            JOIN data_sources ds ON ds.id = ib.source_id
            WHERE ib.id = %s::uuid
        """, (batch_id,))
        row = c.fetchone()

    if not row or row["source_code"] != "ERP_EXPORT":
        return summary  # Nothing to do for non-ERP sources

    # ── Collect resolved rows with srepname from this batch ─────────────────
    with conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute("""
            SELECT
                st.client_id::text,
                fp.calendar_year,
                fp.calendar_month,
                irr.raw_data->>'srepname'   AS srepname,
                -- Earliest calendar date for sorting
                DATE(fp.calendar_year || '-' ||
                     LPAD(fp.calendar_month::text, 2, '0') || '-01') AS period_start
            FROM import_raw_rows irr
            JOIN import_batches ib ON ib.id = irr.batch_id
            -- Join to resolved sales transaction (PRIMARY record only)
            JOIN sales_transactions st ON st.import_raw_row_id = irr.id
            JOIN financial_periods fp ON fp.id = st.financial_period_id
            WHERE irr.batch_id = %s::uuid
              AND irr.raw_data->>'srepname' IS NOT NULL
              AND irr.raw_data->>'srepname' != ''
              AND st.is_primary_record = TRUE
              AND st.excluded_from_market_view = FALSE
            ORDER BY st.client_id, fp.calendar_year, fp.calendar_month
        """, (batch_id,))
        rows = c.fetchall()

    if not rows:
        return summary

    # ── Resolve rep names → rep UUIDs ────────────────────────────────────────
    rep_cache: dict[str, Optional[str]] = {}

    def _resolve_rep(srepname: str) -> Optional[str]:
        if srepname in rep_cache:
            return rep_cache[srepname]
        with conn.cursor() as c2:
            c2.execute(
                "SELECT id::text FROM reps WHERE LOWER(erp_srepname)=LOWER(%s) AND is_deleted=FALSE",
                (srepname,)
            )
            r = c2.fetchone()
            rep_id = r[0] if r else None
        rep_cache[srepname] = rep_id
        if rep_id is None:
            logger.warning("ownership_deriver: unknown srepname=%r — skipping", srepname)
        return rep_id

    # ── Group by client → list of (period_start, srepname) sorted by date ────
    client_timeline: dict[str, list[tuple[date, str]]] = defaultdict(list)
    for row in rows:
        client_timeline[row["client_id"]].append(
            (row["period_start"], row["srepname"])
        )

    # ── For each client derive contiguous rep periods ─────────────────────────
    for client_id, timeline in client_timeline.items():
        # Sort by date; deduplicate (same date/srepname multiple products → one entry)
        timeline.sort(key=lambda x: x[0])
        seen: set[tuple] = set()
        deduped = []
        for item in timeline:
            if item not in seen:
                seen.add(item)
                deduped.append(item)

        # Build contiguous rep blocks
        # A block ends when the srepname changes to a different non-null value
        blocks: list[dict] = []
        current_rep_name: Optional[str] = None
        block_start: Optional[date] = None
        block_end: Optional[date] = None

        for period_start, srepname in deduped:
            if srepname != current_rep_name:
                # Close the previous block
                if current_rep_name is not None and block_start is not None:
                    blocks.append({
                        "srepname": current_rep_name,
                        "start": block_start,
                        "end": block_end,
                    })
                # Open a new block
                current_rep_name = srepname
                block_start = period_start
                block_end = period_start
            else:
                # Same rep — extend the current block end
                block_end = period_start

        # Close the last block
        if current_rep_name is not None and block_start is not None:
            blocks.append({
                "srepname": current_rep_name,
                "start": block_start,
                "end": None,  # Still active / most recent
            })

        # ── Write ownership records ───────────────────────────────────────────
        for i, block in enumerate(blocks):
            srepname = block["srepname"]

            if not srepname:
                summary["skipped_no_srepname"] += 1
                continue

            rep_id = _resolve_rep(srepname)
            if not rep_id:
                summary["skipped_unknown_rep"] += 1
                continue

            proposed_start = block["start"]
            # Close at day before next block starts; last block stays open (None)
            if i < len(blocks) - 1:
                proposed_end = blocks[i + 1]["start"]  # next block's start = this one ends
            else:
                proposed_end = None

            # ── MANUAL_ASSIGNMENT precedence check ───────────────────────────
            # If any MANUAL_ASSIGNMENT overlaps this proposed period, skip it entirely.
            # We never touch manual decisions.
            conflict = _has_manual_conflict(conn, client_id, proposed_start, proposed_end)
            if conflict:
                summary["skipped_manual"] += 1
                logger.info(
                    "ownership_deriver: MANUAL_ASSIGNMENT exists for client=%s rep=%s "
                    "period=%s..%s — skipping ERP_DERIVED",
                    client_id, srepname, proposed_start, proposed_end
                )
                continue

            # ── Upsert the ERP_DERIVED record ────────────────────────────────
            _upsert_erp_derived(conn, client_id, rep_id, proposed_start,
                                proposed_end, srepname, summary)

    conn.commit()
    logger.info("ownership_deriver: batch=%s %s", batch_id, summary)
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _has_manual_conflict(conn, client_id: str, start: date,
                         end: Optional[date]) -> bool:
    """
    Return True if any MANUAL_ASSIGNMENT (or other human-initiated reason)
    overlaps the proposed period for this client.

    Human-initiated reasons take absolute precedence over ERP_DERIVED.
    They include: MANUAL_ASSIGNMENT, TERRITORY_RESTRUCTURE, ACCOUNT_TRANSFER,
    REP_DEPARTURE, NEW_ACCOUNT, CHANNEL_SHIFT — i.e. anything except ERP_DERIVED.
    """
    with conn.cursor() as c:
        if end is None:
            c.execute("""
                SELECT 1 FROM client_ownership
                WHERE client_id = %s::uuid
                  AND change_reason != 'ERP_DERIVED'
                  AND effective_from <= CURRENT_DATE
                  AND (effective_to IS NULL OR effective_to >= %s)
                LIMIT 1
            """, (client_id, start))
        else:
            c.execute("""
                SELECT 1 FROM client_ownership
                WHERE client_id = %s::uuid
                  AND change_reason != 'ERP_DERIVED'
                  AND effective_from <= %s
                  AND (effective_to IS NULL OR effective_to >= %s)
                LIMIT 1
            """, (client_id, end, start))
        return c.fetchone() is not None


def _upsert_erp_derived(conn, client_id: str, rep_id: str,
                        start: date, end: Optional[date],
                        srepname: str, summary: dict) -> None:
    """
    Insert or update an ERP_DERIVED ownership record.
    Idempotent: if an identical (client, rep, start) record already exists,
    we update the end date only if it changed.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute("""
            SELECT id::text, effective_to
            FROM client_ownership
            WHERE client_id = %s::uuid
              AND rep_id = %s::uuid
              AND effective_from = %s
              AND change_reason = 'ERP_DERIVED'
        """, (client_id, rep_id, start))
        existing = c.fetchone()

    if existing:
        # Already exists — update end date if it changed
        if existing["effective_to"] != end:
            with conn.cursor() as c:
                c.execute("""
                    UPDATE client_ownership
                    SET effective_to = %s
                    WHERE id = %s::uuid
                """, (end, existing["id"]))
            summary["extended"] += 1
    else:
        # Create new ERP_DERIVED record
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO client_ownership
                    (id, client_id, rep_id, effective_from, effective_to,
                     change_reason, notes, created_by)
                VALUES
                    (gen_random_uuid(), %s::uuid, %s::uuid, %s, %s,
                     'ERP_DERIVED',
                     %s,
                     'erp_import')
            """, (
                client_id, rep_id, start, end,
                f"ERP-derived from srepname='{srepname}'"
            ))
        summary["created"] += 1
