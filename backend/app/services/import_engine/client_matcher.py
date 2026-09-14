"""
Client Matching Engine — 5-stage algorithm.

Stage 1: Exact source_code match in client_source_aliases (100% confidence)
Stage 2: Exact source_name match for this source_id, case-insensitive (100%)
Stage 3: Normalised name match (strip PTY/LTD/apostrophes/phone numbers) (95%)
Stage 4: Fuzzy match using RapidFuzz token_sort_ratio >= 85 (PROBABLE — human confirm)
Stage 5: No match → PENDING_MAPPING

Rules:
- Only CONFIRMED aliases auto-resolve.
- PROBABLE matches create a review queue item and hold the row.
- The system NEVER silently creates a canonical client.
- A confirmed mapping is permanent — future imports auto-resolve via Stage 1 or 2.
"""
import re
from typing import Optional
from rapidfuzz import fuzz

from app.services.import_engine.db_ops import (
    find_alias_by_code, find_alias_by_name, find_aliases_all
)

# Exclude these words from name normalisation
STRIP_WORDS = {
    'PTY', 'LTD', 'CC', 'NPC', 'THE', 'AND', 'OF', 'AT', 'BY', 'SA',
    'DE', 'T/A', 'TA', 'CO', 'INC', 'CORP', 'GROUP', 'HOLDINGS', 'TRADING',
    'ENTERPRISES', 'PROPERTIES', 'INVESTMENTS', 'MANAGEMENT'
}

PHONE_PATTERN = re.compile(r'\b0\d{2}[\s-]?\d{3}[\s-]?\d{4}\b')


def normalise(name: str) -> str:
    """Normalise a client name for comparison."""
    n = str(name).upper().strip()
    # Remove phone numbers
    n = PHONE_PATTERN.sub('', n)
    # Remove special chars
    n = re.sub(r"['\-&\(\)\.,/\\]", ' ', n)
    # Remove stop words
    words = n.split()
    words = [w for w in words if w not in STRIP_WORDS and len(w) > 1]
    return ' '.join(words).strip()


def match_client(
    conn,
    source_id: str,
    source_name: str,
    source_code: Optional[str],
    _alias_cache: Optional[list] = None,  # Pass pre-loaded aliases for performance
) -> dict:
    """
    Attempt to match a source client name to a canonical MCR client.

    Returns:
        {
            "client_id": str or None,
            "stage": int (1-5),
            "confidence": "CONFIRMED" | "PROBABLE" | "UNRESOLVED",
            "score": float (0-100),
            "matched_on": str (what was matched),
            "requires_review": bool,
            "attempts": list (log of stages tried)
        }
    """
    attempts = []

    # Stage 1: Exact source_code match
    if source_code and str(source_code).strip() not in ('', 'None', 'nan'):
        clean_code = str(source_code).strip().upper()
        client_id = find_alias_by_code(conn, source_id, clean_code)
        attempts.append({"stage": 1, "input": clean_code, "result": client_id})
        if client_id:
            return {
                "client_id": client_id, "stage": 1, "confidence": "CONFIRMED",
                "score": 100.0, "matched_on": f"source_code={clean_code}",
                "requires_review": False, "attempts": attempts
            }

    # Stage 2: Exact source_name match (case-insensitive)
    clean_name = str(source_name).strip()
    client_id = find_alias_by_name(conn, source_id, clean_name)
    attempts.append({"stage": 2, "input": clean_name, "result": client_id})
    if client_id:
        return {
            "client_id": client_id, "stage": 2, "confidence": "CONFIRMED",
            "score": 100.0, "matched_on": f"source_name={clean_name}",
            "requires_review": False, "attempts": attempts
        }

    # Stage 3: Normalised name match
    norm_input = normalise(clean_name)
    if norm_input:
        aliases = _alias_cache or find_aliases_all(conn, source_id)
        for cid, alias_name, alias_code in aliases:
            if normalise(alias_name) == norm_input:
                attempts.append({"stage": 3, "input": norm_input,
                                  "matched_alias": alias_name, "result": cid})
                return {
                    "client_id": cid, "stage": 3, "confidence": "CONFIRMED",
                    "score": 100.0,
                    "matched_on": f"normalised name match: {alias_name}",
                    "requires_review": False, "attempts": attempts
                }
        attempts.append({"stage": 3, "input": norm_input, "result": None})

    # Stage 4: Fuzzy match (RapidFuzz token_sort_ratio)
    # Only suggest — requires human confirmation
    aliases = _alias_cache or find_aliases_all(conn, source_id)
    if aliases:
        best_score = 0
        best_cid = None
        best_alias = None
        for cid, alias_name, alias_code in aliases:
            score = fuzz.token_sort_ratio(norm_input, normalise(alias_name))
            if score > best_score:
                best_score = score
                best_cid = cid
                best_alias = alias_name

        attempts.append({
            "stage": 4, "input": norm_input,
            "best_match": best_alias,
            "best_score": best_score,
            "result": best_cid if best_score >= 85 else None
        })

        if best_score >= 85 and best_cid:
            return {
                "client_id": None,  # Not auto-confirmed — needs human
                "stage": 4,
                "confidence": "PROBABLE",
                "score": float(best_score),
                "matched_on": f"fuzzy: {best_alias} ({best_score:.0f}%)",
                "requires_review": True,
                "suggested_client_id": best_cid,
                "suggested_name": best_alias,
                "attempts": attempts
            }

    # Stage 5: No match
    attempts.append({"stage": 5, "input": norm_input, "result": "UNRESOLVED"})
    return {
        "client_id": None, "stage": 5, "confidence": "UNRESOLVED",
        "score": 0.0, "matched_on": "no match",
        "requires_review": True, "attempts": attempts
    }
