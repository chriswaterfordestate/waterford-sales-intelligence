"""
Product matcher — Waterford Sales Intelligence system.

ERP RESOLUTION ARCHITECTURE (ERP rows with stockunit field):
  salgrpname  → canonical Waterford product (alias lookup OR pattern matching)
  stockunit   → canonical bottle format (B375/B500/B750/B1.5/B3.0/B5L/B18L)
  product × size → canonical SKU

  No vintage-specific stockitem alias is required. A new vintage year (L25→L26)
  resolves automatically through salgrpname + stockunit.

CONFIDENCE LEVELS:
  CONFIRMED      — product and format both positively identified
  PROBABLE       — fuzzy match only, needs review
  UNKNOWN_FORMAT — product is known; exact format not in master (not UNKNOWN_PRODUCT)
  UNRESOLVED     — product identity itself cannot be determined

LARGE-FORMAT GUARD (text sources without stockunit):
  If a description contains a 1.5L/Magnum indicator but no alias matched,
  return UNRESOLVED rather than allowing fallthrough to a 750ml SKU.
"""

from __future__ import annotations
import re
from typing import Optional
from .db_ops import s

# ── stockunit → bottle size in ml ────────────────────────────────────────────
STOCKUNIT_TO_ML: dict[str, int] = {
    'B375': 375, 'B500': 500, 'B750': 750,
    'B1.5': 1500, 'B3.0': 3000, 'B5L': 5000, 'B12L': 12000, 'B18L': 18000,
}
LARGE_FORMAT_STOCKUNITS: set[str] = {'B1.5', 'B3.0', 'B5L', 'B12L', 'B18L'}

# ── Large-format guard for text-based sources ────────────────────────────────
# \b = genuine regex word-boundary (not backspace \x08)
LARGE_FORMAT_PATTERNS = re.compile(
    r'\b(?:1[.,]5\s*[Ll]?|1500\s*[Mm][Ll]?|[Mm]agnum|[Mm][Aa][Gg])\b',
    re.IGNORECASE
)

# ── Pattern → SKU code (fallback product identification) ─────────────────────
# Ordered most-specific first. These identify the PRODUCT only; the final SKU
# is determined by combining with bottle_size_ml from stockunit.
WATERFORD_SKU_PATTERNS: dict[str, str] = {
    # Rose-Mary
    r'ROSE.?MARY.*750':            'RM001',
    r'ROSE.?MARY.*1\.5':           'RM1500',
    r'ROSE.?MARY':                 'RM001',
    # Kevin Arnold Shiraz
    r'KEVIN.*ARNOLD.*1\.5':        'KAS1L',
    r'KEVIN.*ARNOLD.*SHIRAZ':      'KAS001',
    r'K.*ARNOLD.*SHIR':            'KAS001',
    r'KASHI.*1\.5':                'KAS1L',
    r'KASHI':                      'KAS001',
    # Cabernet Sauvignon
    r'CAB.*SAUV.*375':             'CAB375',
    r'CAB.*1\.5':                  'CABMAG',
    r'CAB.*SAUVIGNON':             'CAB001',
    r'CAB.*SAUV':                  'CAB001',
    # Jem
    r'JEM.*1\.5':                  'JEM1500',
    r'JEM.*750':                   'JEM001',
    r'\bJEM\b':                    'JEM001',
    # Antigo
    r'ANTIGO.*1\.5':               'ANT1500',
    r'ANTIGO':                     'ANT001',
    # Chardonnay
    r'CHARDON.*1\.5':              'CHD1500',
    r'CHARDON':                    'CHD001',
    # Elgin Sauvignon Blanc (500ml aliases before 750ml)
    r'ELGIN.*SB.*500':             'ELG500',
    r'ELGIN.*SAUV.*500':           'ELG500',
    r'ELGIN.*B1.*500':             'ELG500',
    r'ELGIN.*SAUV':                'ELG001',
    r'ELGIN.*SB':                  'ELG001',
    # Grenache
    r'GRENACHE':                   'GRN001',
    # Heatherleigh
    r'HEATHERLEIGH':               'HEA001',
    # Pecan Stream
    r'PECAN.*CHENIN|PS.*CHENIN':   'PSC001',
    r'PECAN.*SAUV|PS.*SAUV':       'PSS001',
    r'PECAN.*RED|PS.*RED':         'PSR001',
    # Old Vine Pinotage
    r'OLD.*VINE.*PINOT':           'OVP001',
    # Historical/discontinued
    r'PINOT.*NOIR':                'PNOIR001',
    r'ESTATE.*SAUV':               'WSB001',
    # Cap Classique
    r'CAP.*CLASSIQUE':             'MCC001',
    r'\bMCC\b':                    'MCC001',
    r'BUBBLY':                     'MCC001',
    # Chenin Blanc (WCB / OVP Chenin)
    r'CHENIN.*BLANC':              'WCB001',
    r'OVP.*CHENIN':                'WCB001',
}


# ── DB helpers ────────────────────────────────────────────────────────────────

def find_product_alias_by_description(conn, source_id: str, description: str) -> Optional[str]:
    """Exact alias match → product_sku_id."""
    return s(conn, """
        SELECT product_sku_id::text FROM product_source_aliases
        WHERE source_id=%s::uuid
          AND LOWER(source_description)=LOWER(%s)
          AND match_confidence='CONFIRMED'
          AND is_active=TRUE
        LIMIT 1
    """, (source_id, description))


def _get_sku_uuid(conn, sku_code: str) -> Optional[str]:
    return s(conn, "SELECT id::text FROM product_skus WHERE sku_code=%s", (sku_code,))


def _get_sku_size(conn, sku_id: str) -> Optional[int]:
    return s(conn, "SELECT bottle_size_ml FROM product_skus WHERE id=%s::uuid", (sku_id,))


def _get_product_from_sku(conn, sku_id: str) -> Optional[str]:
    return s(conn, "SELECT product_id::text FROM product_skus WHERE id=%s::uuid", (sku_id,))


def _find_sku_by_product_and_size(conn, product_id: str, size_ml: int) -> Optional[str]:
    """Find the canonical SKU for a product at a specific size. Includes discontinued."""
    return s(conn, """
        SELECT id::text FROM product_skus
        WHERE product_id=%s::uuid AND bottle_size_ml=%s
        LIMIT 1
    """, (product_id, size_ml))


def _get_product_name(conn, product_id: str) -> Optional[str]:
    return s(conn, "SELECT product_name FROM products WHERE id=%s::uuid", (product_id,))


def _product_id_via_pattern(conn, description: str) -> Optional[str]:
    """
    Identify product via pattern matching on description, then return the product_id.
    This is the fallback when no exact alias exists for the salgrpname.
    """
    norm = re.sub(r"['\-.,/\\()]", ' ', str(description or '').upper())
    norm = re.sub(r'\s+', ' ', norm).strip()
    for pattern, sku_code in WATERFORD_SKU_PATTERNS.items():
        if re.search(pattern, norm):
            sku_id = _get_sku_uuid(conn, sku_code)
            if sku_id:
                return _get_product_from_sku(conn, sku_id)
    return None


def extract_vintage(description: str) -> Optional[int]:
    m = re.search(r'\b(19\d{2}|20[012]\d)\b', str(description or ''))
    return int(m.group(1)) if m else None


def normalise_product(description: str) -> str:
    desc = re.sub(r"['\-.,/\\()]", ' ', str(description or '').upper())
    return re.sub(r'\s+', ' ', desc).strip()


# ── Structural ERP resolution ─────────────────────────────────────────────────

def _resolve_erp_structural(conn, source_id: str, salgrpname: str, stockunit: str):
    """
    Primary resolution for ERP rows using salgrpname + stockunit.

    Step A: stockunit → size_ml (structural, definitive)
    Step B: salgrpname → product_id
              first via exact alias lookup (catches source naming variations),
              then via pattern matching (catches salgrpname without an alias).
    Step C: product_id + size_ml → SKU

    Returns: (sku_id_or_None, confidence, context_dict)
    """
    # A: size from stockunit
    size_ml = STOCKUNIT_TO_ML.get(stockunit.upper() if stockunit else '')
    if not size_ml:
        return None, 'UNRESOLVED', {'reason': f'unrecognised stockunit: {stockunit}'}

    # B1: product via exact alias
    product_id = s(conn, """
        SELECT DISTINCT ps.product_id::text
        FROM product_source_aliases psa
        JOIN product_skus ps ON ps.id = psa.product_sku_id
        WHERE psa.source_id = %s::uuid
          AND LOWER(psa.source_description) = LOWER(%s)
          AND psa.match_confidence = 'CONFIRMED'
          AND psa.is_active = TRUE
        LIMIT 1
    """, (source_id, salgrpname))

    # B2: product via pattern matching (fallback when no alias exists yet)
    if not product_id:
        product_id = _product_id_via_pattern(conn, salgrpname)

    if not product_id:
        return None, 'UNRESOLVED', {'reason': f'product not identified for: {salgrpname}'}

    # C: find SKU at this product + size
    sku_id = _find_sku_by_product_and_size(conn, product_id, size_ml)
    if sku_id:
        return sku_id, 'CONFIRMED', {
            'path': 'structural: salgrpname→product + stockunit→size',
            'product_id': product_id, 'size_ml': size_ml
        }
    else:
        # Product known, format not yet in master — UNKNOWN_FORMAT, not UNKNOWN_PRODUCT
        product_name = _get_product_name(conn, product_id)
        return None, 'UNKNOWN_FORMAT', {
            'reason': f'product known ({product_name}) but {size_ml}ml format not in master',
            'product_id': product_id, 'size_ml': size_ml
        }


# ── Main entry point ──────────────────────────────────────────────────────────

def match_product(
    conn,
    source_id: str,
    description: str,
    _alias_cache=None,
    stockunit: Optional[str] = None,
) -> dict:
    """
    Resolve a source product description to a canonical product_sku.

    For ERP rows (stockunit provided):
      → Structural path: salgrpname → product, stockunit → size, product+size → SKU
      → No vintage-specific alias required; L25WFRM1.5 and L26WFRM1.5 auto-resolve.

    For other sources (no stockunit):
      → Legacy path: exact alias → pattern → UNRESOLVED (with large-format guard).
    """
    vintage   = extract_vintage(description)
    base = {
        'sku_id': None, 'vintage': vintage, 'confidence': 'UNRESOLVED',
        'matched_on': '', 'requires_review': True,
        'suggested_sku_id': None, 'product_id': None, 'size_ml': None,
    }

    # ── STRUCTURAL PATH (ERP rows — any stockunit present) ──────────────────────
    # Principle: if ERP provides a stockunit field, ALWAYS use the structured ERP path.
    # Never fall through to legacy text/regex matching when structured format data exists.
    # Known product + unrecognised format = UNKNOWN_FORMAT, not a guessed SKU.
    if stockunit:
        su_upper = stockunit.upper()

        if su_upper not in STOCKUNIT_TO_ML:
            # stockunit present but not in our mapping (e.g. B600, B2L, EACH).
            # Identify the product if possible, then return UNKNOWN_FORMAT.
            # Do NOT allow legacy regex to guess a SKU from an unknown format.
            product_id = s(conn, """
                SELECT DISTINCT ps.product_id::text
                FROM product_source_aliases psa
                JOIN product_skus ps ON ps.id = psa.product_sku_id
                WHERE psa.source_id = %s::uuid
                  AND LOWER(psa.source_description) = LOWER(%s)
                  AND psa.match_confidence = 'CONFIRMED' AND psa.is_active = TRUE
                LIMIT 1
            """, (source_id, description)) or _product_id_via_pattern(conn, description)
            return {**base,
                    'confidence': 'UNKNOWN_FORMAT',
                    'matched_on': f'unrecognised ERP stockunit: {stockunit} — not in STOCKUNIT_TO_ML',
                    'product_id': product_id,
                    'size_ml': None}

        # stockunit recognised → full structural resolution
        sku_id, conf, ctx = _resolve_erp_structural(conn, source_id, description, stockunit)

        if conf == 'CONFIRMED':
            return {**base, 'sku_id': sku_id, 'confidence': 'CONFIRMED',
                    'matched_on': ctx.get('path', 'structural'), 'requires_review': False}

        if conf == 'UNKNOWN_FORMAT':
            return {**base, 'confidence': 'UNKNOWN_FORMAT',
                    'matched_on': ctx.get('reason', ''),
                    'product_id': ctx.get('product_id'), 'size_ml': ctx.get('size_ml')}

        # UNRESOLVED: salgrpname genuinely not identified even via patterns
        return {**base, 'confidence': 'UNRESOLVED',
                'matched_on': ctx.get('reason', 'product not identified'),
                'requires_review': True}
    # ── LEGACY PATH (no stockunit — NGF SalesOut, etc.) ──────────────────────
    is_large_format = bool(LARGE_FORMAT_PATTERNS.search(str(description)))

    # Stage 1: Exact alias
    sku_id = find_product_alias_by_description(conn, source_id, description)
    if sku_id:
        return {**base, 'sku_id': sku_id, 'confidence': 'CONFIRMED',
                'matched_on': f'exact alias: {description}', 'requires_review': False}

    # Large-format guard: block fallthrough to 750ml patterns
    if is_large_format:
        return {**base, 'confidence': 'UNRESOLVED',
                'matched_on': 'large format (no stockunit), no alias — held for review'}

    # Stage 2: Pattern matching
    norm_upper = normalise_product(description).upper()
    for pattern, sku_code in WATERFORD_SKU_PATTERNS.items():
        if re.search(pattern, norm_upper):
            sku_id = _get_sku_uuid(conn, sku_code)
            if sku_id:
                return {**base, 'sku_id': sku_id, 'confidence': 'CONFIRMED',
                        'matched_on': f'pattern: {pattern} → {sku_code}',
                        'requires_review': False}

    return base
