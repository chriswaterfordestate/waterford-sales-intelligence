"""
Historical (Discontinued) Product Tests.

Verifies that discontinued products:
  1. Resolve to their canonical SKU (not UNKNOWN_PRODUCT).
  2. Never resolve to an incorrect active product.
  3. Are reportable historically despite is_active=FALSE.
  4. Waterford Estate SB and Elgin SB remain separate canonicals.
"""
import pytest
import psycopg2

DSN = "host=localhost dbname=waterford_si_test user=waterford password=waterford_dev"


@pytest.fixture(scope="session")
def db():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    yield conn
    conn.close()


def q(conn, sql, p=None):
    with conn.cursor() as c:
        c.execute(sql, p)
        return c.fetchall()


def s(conn, sql, p=None):
    rows = q(conn, sql, p)
    return rows[0][0] if rows else None


# ── T-HIST-01: Pinot Noir SKU exists and is discontinued (not deleted) ────────
def test_hist_01_pinot_noir_exists_as_discontinued(db):
    """Waterford Pinot Noir: product exists, is_active=FALSE, not deleted."""
    row = q(db, """
        SELECT p.product_code, p.is_active, ps.sku_code, ps.is_active as sku_active
        FROM products p JOIN product_skus ps ON ps.product_id=p.id
        WHERE p.product_code='PNOIR'
    """)
    assert row, "Waterford Pinot Noir product must exist in product master"
    product_code, prod_active, sku_code, sku_active = row[0]
    assert product_code == 'PNOIR', "Product code must be PNOIR"
    assert prod_active == False, "Discontinued product: is_active must be FALSE"
    assert sku_active == False,  "Discontinued SKU: is_active must be FALSE"
    assert sku_code == 'PNOIR001', "SKU code must be PNOIR001"


# ── T-HIST-02: Pinot Noir alias resolves correctly ────────────────────────────
def test_hist_02_pinot_noir_alias_resolves(db):
    """ERP salgrpname 'Waterford Pinot Noir' must resolve to PNOIR001, not UNKNOWN."""
    sku_id = s(db, """
        SELECT psa.product_sku_id::text
        FROM product_source_aliases psa
        JOIN data_sources ds ON ds.id=psa.source_id
        WHERE ds.source_code='ERP_EXPORT'
          AND psa.source_description='Waterford Pinot Noir'
          AND psa.match_confidence='CONFIRMED'
          AND psa.is_active=TRUE
    """)
    assert sku_id is not None, \
        "'Waterford Pinot Noir' salgrpname must have a CONFIRMED alias (historical product)"

    # Verify it maps to PNOIR001 specifically
    sku_code = s(db, "SELECT sku_code FROM product_skus WHERE id=%s::uuid", (sku_id,))
    assert sku_code == 'PNOIR001', \
        f"Must resolve to PNOIR001, not {sku_code}"


# ── T-HIST-03: Discontinued product alias is active (for historical resolution) ─
def test_hist_03_discontinued_sku_alias_is_active_for_resolution(db):
    """Alias for PNOIR001 must have is_active=TRUE even though the SKU is inactive.
    Discontinued ≠ deleted. Historical rows must still resolve."""
    row = q(db, """
        SELECT psa.is_active, ps.is_active as sku_active
        FROM product_source_aliases psa
        JOIN product_skus ps ON ps.id=psa.product_sku_id
        WHERE ps.sku_code='PNOIR001'
          AND psa.match_confidence='CONFIRMED'
    """)
    assert row, "PNOIR001 must have a confirmed alias"
    alias_active, sku_active = row[0]
    assert alias_active == True,  \
        "Alias is_active must be TRUE — discontinued product still needs alias for historical resolution"
    assert sku_active == False, \
        "SKU is_active must be FALSE — product is discontinued"


# ── T-HIST-04: Estate SB exists as separate canonical from Elgin SB ──────────
def test_hist_04_estate_sb_separate_from_elgin_sb(db):
    """Estate SB and Elgin SB must be separate products with different product_codes."""
    rows = q(db, """
        SELECT p.product_code, p.product_name, p.is_active
        FROM products p WHERE p.product_code IN ('ELG','WSB')
        ORDER BY p.product_code
    """)
    codes = {r[0]: r for r in rows}
    assert 'ELG' in codes, "Elgin SB product (ELG) must exist"
    assert 'WSB' in codes, "Estate SB product (WSB) must exist"
    assert codes['ELG'][2] == True,  "Elgin SB must be active"
    assert codes['WSB'][2] == False, "Estate SB must be discontinued (is_active=FALSE)"
    # Confirm they have DIFFERENT product_names
    assert codes['ELG'][1] != codes['WSB'][1], "Products must have different names"


# ── T-HIST-05: 'Waterford Estate Sauv Blanc' alias resolves to WSB001, not ELG ─
def test_hist_05_estate_sb_alias_resolves_to_wsb_not_elg(db):
    """CRITICAL: 'Waterford Estate Sauv Blanc' must NEVER map to Elgin SB."""
    sku_id = s(db, """
        SELECT psa.product_sku_id::text
        FROM product_source_aliases psa
        JOIN data_sources ds ON ds.id=psa.source_id
        WHERE ds.source_code='ERP_EXPORT'
          AND psa.source_description='Waterford Estate Sauv Blanc'
          AND psa.match_confidence='CONFIRMED'
          AND psa.is_active=TRUE
    """)
    assert sku_id is not None, \
        "'Waterford Estate Sauv Blanc' must have a CONFIRMED alias"

    sku_code = s(db, "SELECT sku_code FROM product_skus WHERE id=%s::uuid", (sku_id,))
    assert sku_code == 'WSB001', \
        f"'Waterford Estate Sauv Blanc' must resolve to WSB001, not {sku_code}"

    # Double-check: no alias for Estate SB maps to any ELG SKU
    bad_mapping = s(db, """
        SELECT COUNT(*) FROM product_source_aliases psa
        JOIN product_skus ps ON ps.id=psa.product_sku_id
        JOIN products p ON p.id=ps.product_id
        JOIN data_sources ds ON ds.id=psa.source_id
        WHERE ds.source_code='ERP_EXPORT'
          AND psa.source_description='Waterford Estate Sauv Blanc'
          AND p.product_code='ELG'
    """)
    assert bad_mapping == 0, \
        "CRITICAL: 'Waterford Estate Sauv Blanc' must NOT be aliased to any Elgin SB SKU"


# ── T-HIST-06: Elgin SB aliases do not include Estate SB descriptions ─────────
def test_hist_06_elgin_sb_not_contaminated_with_estate_sb_aliases(db):
    """Elgin SB (ELG SKUs) must have no alias named 'Estate Sauvignon Blanc'."""
    contamination = q(db, """
        SELECT psa.source_description FROM product_source_aliases psa
        JOIN product_skus ps ON ps.id=psa.product_sku_id
        JOIN products p ON p.id=ps.product_id
        WHERE p.product_code='ELG'
          AND LOWER(psa.source_description) LIKE '%estate%sauv%'
    """)
    assert not contamination, \
        f"Elgin SB must not have 'Estate Sauv' aliases — found: {contamination}"


# ── T-HIST-07: Discontinued products reportable (SBE / btl_size accessible) ──
def test_hist_07_discontinued_products_have_complete_sku_data(db):
    """Discontinued products must have full SKU data for historical reporting."""
    for sku_code, expected_size, expected_sbe in [
        ('PNOIR001', 750, 1.000),
        ('WSB001',   750, 1.000),
    ]:
        row = q(db, """
            SELECT bottle_size_ml, standard_bottle_equivalent
            FROM product_skus WHERE sku_code=%s
        """, (sku_code,))
        assert row, f"{sku_code} must exist in product_skus for historical reporting"
        size_ml, sbe = row[0]
        assert size_ml == expected_size, f"{sku_code}: bottle_size_ml must be {expected_size}"
        assert float(sbe) == expected_sbe, f"{sku_code}: SBE must be {expected_sbe}"


# ── T-HIST-08: Product matcher runtime: Pinot Noir resolves not unknown ───────
def test_hist_08_runtime_pinot_noir_resolves(db):
    """Runtime product matcher must resolve 'Waterford Pinot Noir' to PNOIR001."""
    import sys, os
    sys.path.insert(0, '/home/claude/waterford-si/backend')
    os.environ['DATABASE_URL_SYNC'] = 'host=localhost dbname=waterford_si_test user=waterford password=waterford_dev'

    from app.services.import_engine.product_matcher import match_product

    source_id = s(db, "SELECT id::text FROM data_sources WHERE source_code='ERP_EXPORT'")
    result = match_product(db, source_id, 'Waterford Pinot Noir')

    assert result['confidence'] == 'CONFIRMED', \
        f"Waterford Pinot Noir must be CONFIRMED, not {result['confidence']}"
    assert result['sku_id'] is not None, \
        "Waterford Pinot Noir must resolve to a SKU ID (not UNKNOWN)"
    assert result['requires_review'] == False, \
        "Historical discontinued product must not require review"

    sku_code = s(db, "SELECT sku_code FROM product_skus WHERE id=%s::uuid", (result['sku_id'],))
    assert sku_code == 'PNOIR001', \
        f"Must resolve to PNOIR001, got {sku_code}"


# ── T-HIST-09: Runtime: Estate SB resolves, never to Elgin SB ────────────────
def test_hist_09_runtime_estate_sb_resolves_correctly(db):
    """Runtime: 'Waterford Estate Sauv Blanc' → WSB001, never ELG001."""
    import sys, os
    sys.path.insert(0, '/home/claude/waterford-si/backend')
    os.environ['DATABASE_URL_SYNC'] = 'host=localhost dbname=waterford_si_test user=waterford password=waterford_dev'

    from app.services.import_engine.product_matcher import match_product

    source_id = s(db, "SELECT id::text FROM data_sources WHERE source_code='ERP_EXPORT'")
    result = match_product(db, source_id, 'Waterford Estate Sauv Blanc')

    assert result['confidence'] == 'CONFIRMED', \
        f"Estate SB must be CONFIRMED, not {result['confidence']}"
    assert result['sku_id'] is not None, \
        "Estate SB must resolve to a SKU"
    assert result['requires_review'] == False

    sku_code = s(db, "SELECT sku_code FROM product_skus WHERE id=%s::uuid", (result['sku_id'],))
    assert sku_code == 'WSB001', \
        f"CRITICAL: Estate SB must resolve to WSB001, not {sku_code} (must not be ELG001)"
    assert sku_code != 'ELG001', \
        "Estate SB must NEVER resolve to Elgin SB (ELG001)"


# ── T-HIST-10: Runtime: 1.5L descriptions blocked from 750ml SKUs ────────────
def test_hist_10_large_format_guard_blocks_750ml_fallthrough(db):
    """Descriptions with 1.5L/Magnum indicators must not resolve to 750ml SKUs."""
    import sys, os
    sys.path.insert(0, '/home/claude/waterford-si/backend')
    os.environ['DATABASE_URL_SYNC'] = 'host=localhost dbname=waterford_si_test user=waterford password=waterford_dev'

    from app.services.import_engine.product_matcher import match_product

    source_id = s(db, "SELECT id::text FROM data_sources WHERE source_code='ERP_EXPORT'")

    # These descriptions have no exact alias — must be UNRESOLVED, not 750ml
    unaliased_large_formats = [
        'Some New Product 1.5L',
        'Hypothetical Wine Magnum',
        'Unknown Magnum Wine 1500ml',
    ]

    for desc in unaliased_large_formats:
        result = match_product(db, source_id, desc)
        assert result['sku_id'] is None, \
            f"'{desc}' must return sku_id=None (UNRESOLVED), not match a 750ml SKU"
        assert result['confidence'] == 'UNRESOLVED', \
            f"'{desc}' must be UNRESOLVED, got {result['confidence']}"
