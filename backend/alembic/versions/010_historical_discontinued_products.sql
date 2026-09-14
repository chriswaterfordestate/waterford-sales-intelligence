-- =============================================================================
-- MIGRATION 010: Historical Discontinued Products
-- Date: September 2026
--
-- Adds two confirmed historical Waterford products that were absent from the
-- original Sprint 1 seed. Both are discontinued (no longer produced) but must
-- remain as canonical products for accurate historical reporting.
--
-- NSM confirmations:
--   "Waterford Pinot Noir is a legitimate historical Waterford product.
--    It has been discontinued. Add/retain as canonical product for historical
--    reporting; mark discontinued/inactive for current selling."
--
--   "Waterford Estate Sauvignon Blanc is also a legitimate historical product
--    and has been discontinued. It is NOT the same wine as Waterford Elgin
--    Sauvignon Blanc. Maintain these as two separate canonical products."
--
-- Design principles:
--   * is_active=FALSE on product/SKU  → not for current selling
--   * Alias is_active=TRUE             → historical rows still resolve correctly
--   * Discontinued ≠ deleted           → historical transactions remain reportable
-- =============================================================================

-- ────────────────────────────────────────────────────────────────────────────
-- 1. Waterford Pinot Noir
-- ────────────────────────────────────────────────────────────────────────────
INSERT INTO products
    (id, product_code, product_name, brand_name, tier, is_active, notes, created_by)
VALUES (
    md5('prod-PNOIR')::uuid,
    'PNOIR',
    'Waterford Pinot Noir',
    'Waterford Estate',
    'PREMIUM',
    FALSE,        -- discontinued; not for current selling
    'DISCONTINUED: Legitimate historical Waterford product. No longer produced. '
    'is_active=FALSE = not current; historical transactions remain reportable. '
    'ERP FY2026: 378 btls in finmth=5, buyers include SAWINE01, MOOI0001, private clients. '
    'NSM confirmed Sep 2026.',
    'system'
) ON CONFLICT DO NOTHING;

INSERT INTO product_skus
    (id, product_id, sku_code, sku_name, bottle_size_ml,
     standard_bottle_equivalent, default_case_size, tier, is_active, created_by)
VALUES (
    md5('sku-pnoir-750')::uuid,
    md5('prod-PNOIR')::uuid,
    'PNOIR001',
    'Waterford Pinot Noir 750ml',
    750, 1.000, 6, 'PREMIUM',
    FALSE,        -- discontinued
    'system'
) ON CONFLICT DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────────
-- 2. Waterford Estate Sauvignon Blanc
--    SEPARATE product from Waterford Elgin Sauvignon Blanc — must never merge
-- ────────────────────────────────────────────────────────────────────────────
INSERT INTO products
    (id, product_code, product_name, brand_name, tier, is_active, notes, created_by)
VALUES (
    md5('prod-WSB')::uuid,
    'WSB',
    'Waterford Estate Sauvignon Blanc',
    'Waterford Estate',
    'PREMIUM',
    FALSE,        -- discontinued
    'DISCONTINUED: Historical Waterford Estate Sauvignon Blanc. '
    'NOT the same wine as Waterford Elgin Sauvignon Blanc (product code ELG). '
    'These are separate canonical products and must never be merged or share aliases. '
    'is_active=FALSE = discontinued; historical transactions remain reportable. '
    'ERP FY2026: 50 btls, buyers include private clients, Chefs Warehouse, Mount Nelson. '
    'NSM confirmed Sep 2026: separate product from Elgin SB.',
    'system'
) ON CONFLICT DO NOTHING;

INSERT INTO product_skus
    (id, product_id, sku_code, sku_name, bottle_size_ml,
     standard_bottle_equivalent, default_case_size, tier, is_active, created_by)
VALUES (
    md5('sku-wsb-750')::uuid,
    md5('prod-WSB')::uuid,
    'WSB001',
    'Waterford Estate Sauvignon Blanc 750ml',
    750, 1.000, 6, 'PREMIUM',
    FALSE,        -- discontinued
    'system'
) ON CONFLICT DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────────
-- 3. ERP Product Aliases
--    is_active=TRUE on aliases: historical rows must still resolve correctly
--    even though the products are discontinued.
-- ────────────────────────────────────────────────────────────────────────────
INSERT INTO product_source_aliases
    (id, product_sku_id, source_id, source_description,
     match_confidence, confirmed_by, confirmed_at, is_active, notes)
VALUES
(
    md5('psa010-ERP-Waterford Pinot Noir')::uuid,
    md5('sku-pnoir-750')::uuid,
    (SELECT id FROM data_sources WHERE source_code='ERP_EXPORT'),
    'Waterford Pinot Noir',
    'CONFIRMED', 'NSM', NOW(), TRUE,
    'NSM confirmed: legitimate historical product, discontinued. '
    'Alias is_active=TRUE so historical ERP rows resolve correctly.'
),
(
    md5('psa010-ERP-Waterford Estate Sauv Blanc')::uuid,
    md5('sku-wsb-750')::uuid,
    (SELECT id FROM data_sources WHERE source_code='ERP_EXPORT'),
    'Waterford Estate Sauv Blanc',
    'CONFIRMED', 'NSM', NOW(), TRUE,
    'NSM confirmed: separate from Elgin SB. Discontinued. '
    'NEVER map this alias to any ELG SKU. '
    'Alias is_active=TRUE for historical resolution.'
)
ON CONFLICT DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────────
-- 4. Verification
-- ────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM product_skus WHERE sku_code='PNOIR001' AND is_active=FALSE) THEN
        RAISE EXCEPTION 'PNOIR001 must exist and be discontinued (is_active=FALSE)';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM product_skus WHERE sku_code='WSB001' AND is_active=FALSE) THEN
        RAISE EXCEPTION 'WSB001 must exist and be discontinued (is_active=FALSE)';
    END IF;
    -- Confirm WSB is NOT aliased to any ELG SKU (no contamination)
    IF EXISTS (
        SELECT 1 FROM product_source_aliases psa
        JOIN product_skus ps ON ps.id=psa.product_sku_id
        JOIN products p ON p.id=ps.product_id
        WHERE psa.source_description='Waterford Estate Sauv Blanc' AND p.product_code='ELG'
    ) THEN
        RAISE EXCEPTION 'CRITICAL: Estate SB alias must NOT point to any Elgin SB SKU';
    END IF;
    RAISE NOTICE 'Migration 010 verification passed: PNOIR001 discontinued, WSB001 discontinued, separation confirmed';
END $$;
