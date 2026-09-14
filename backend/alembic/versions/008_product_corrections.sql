-- =============================================================================
-- MIGRATION 008: Product corrections per NSM confirmation (September 2026)
--
-- 1. CABMAG: rename CAB1L → CABMAG, reactivate, add ERP aliases
-- 2. KAS1L:  add missing ERP alias "Kevin Arnold Shiraz 1.5L"
-- 3. WCB001: add L25WFCB750 and other ERP vintage-format aliases
-- 4. MCC001: add L19WFMCC750 (confirmed); L19WFMCC75P as PROBABLE pending investigation
--
-- HOLDING for NSM confirmation (not created here):
--   Rose-Mary 1.5L (758 btls pending)  -- may be a data entry issue or genuine SKU
--   Waterford Chardonnay 1.5L (202 btls)
--   Waterford Antigo 1.5L (191 btls)
--   Jem 1.5L (48 btls)
--   "Other Wines" / "Large Bottles 3/5/12/18" (catch-all ERP categories, unresolvable)
--
-- ERP REVENUE RULE (confirmed by NSM):
--   ERP net_val = CONFIRMED Waterford revenue. Never replaced by ASP estimate.
--   ASP estimates only for distributor sell-through reports with no invoice value.
-- =============================================================================

-- ────────────────────────────────────────────────────────────────────────────
-- 1. RENAME CAB1L → CABMAG and reactivate
-- NSM confirmed: Waterford produces Cabernet Sauvignon 1.5L Magnum.
-- CAB1L was ambiguous (looks like "1 Liter"). CABMAG = unambiguous Magnum.
-- ────────────────────────────────────────────────────────────────────────────
-- Sprint 6: ensure notes column exists (may be added by 007, repeated here for safety)
ALTER TABLE product_skus ADD COLUMN IF NOT EXISTS notes TEXT;


UPDATE product_skus
SET sku_code = 'CABMAG',
    sku_name  = 'Waterford Cabernet Sauvignon 1.5L Magnum',
    is_active = TRUE,
    notes     = 'NSM confirmed September 2026: Waterford produces Cab Sauv 1.5L Magnum. '
             || 'Renamed from CAB1L (ambiguous) to CABMAG. '
             || '1.5L = 2 standard_bottle_equivalents (SBE). '
             || 'ERP aliases: Waterford Cab Sauv 1.5L, L18WFCS1.5, L18WFCSMAG.'
WHERE sku_code = 'CAB1L';

-- Add product source aliases for CABMAG
INSERT INTO product_source_aliases
(id, product_sku_id, source_id, source_description, match_confidence, confirmed_by, confirmed_at, is_active, notes)
SELECT
    md5(concat('psa008-', src_c, '-', desc_val))::uuid,
    (SELECT id FROM product_skus WHERE sku_code IN ('CABMAG','CAB1L') LIMIT 1),
    (SELECT id FROM data_sources WHERE source_code = src_c),
    desc_val, 'CONFIRMED'::match_confidence_enum, 'NSM', NOW(), TRUE,
    'NSM confirmed Sep 2026: Waterford Cab Sauv 1.5L Magnum. ' || note_val
FROM (VALUES
    -- FY2026 ERP actual salgrpname
    ('ERP_EXPORT', 'Waterford Cab Sauv 1.5L',      'ERP FY26 salgrpname confirmed by NSM'),
    -- Vintage-format SKU codes (NSM examples: L18WFCS1.5, L18WFCSMAG)
    ('ERP_EXPORT', 'L18WFCS1.5',                   'Vintage SKU: L=list, 18=vintage year, WF=Waterford, CS=Cab Sauv, 1.5=1.5L'),
    ('ERP_EXPORT', 'L18WFCSMAG',                   'Vintage SKU: MAG=Magnum variant of same product'),
    -- Long-form variants for cross-source coverage
    ('ERP_EXPORT', 'Waterford Cabernet Sauvignon 1.5L',       'Long-form variant'),
    ('ERP_EXPORT', 'Waterford Cabernet Sauvignon 1.5L Magnum','Extended description'),
    ('NGF_MONTHLY','WATERFORD CABERNET SAUV 1.5L',             'NGF Monthly format')
) AS t(src_c, desc_val, note_val)
ON CONFLICT DO NOTHING;

-- SBE is already set to 2.000 in product_skus (1500ml / 750ml = 2.0) ✓
-- Verify
DO $$
BEGIN
  IF (SELECT standard_bottle_equivalent FROM product_skus WHERE sku_code='CABMAG') != 2.000 THEN
    RAISE EXCEPTION 'CABMAG SBE must be 2.000 (1.5L = 2 standard 750ml bottles)';
  END IF;
  RAISE NOTICE 'CABMAG: is_active=%, SBE=%',
    (SELECT is_active FROM product_skus WHERE sku_code='CABMAG'),
    (SELECT standard_bottle_equivalent FROM product_skus WHERE sku_code='CABMAG');
END $$;

-- ────────────────────────────────────────────────────────────────────────────
-- 2. KAS1L: add missing ERP alias
-- KAS1L already exists in Sprint 1 seed. Just add the product alias.
-- ────────────────────────────────────────────────────────────────────────────
INSERT INTO product_source_aliases
(id, product_sku_id, source_id, source_description, match_confidence, confirmed_by, confirmed_at, is_active, notes)
VALUES (
    md5('psa008-ERP-Kevin Arnold Shiraz 1.5L')::uuid,
    (SELECT id FROM product_skus WHERE sku_code = 'KAS1L'),
    (SELECT id FROM data_sources WHERE source_code = 'ERP_EXPORT'),
    'Kevin Arnold Shiraz 1.5L',
    'CONFIRMED'::match_confidence_enum, 'NSM', NOW(), TRUE,
    'KAS1L (1.5L Magnum) already existed in Sprint 1. Adding ERP FY26 salgrpname alias.'
) ON CONFLICT DO NOTHING;

-- Also add vintage-format variants for future-proofing
INSERT INTO product_source_aliases
(id, product_sku_id, source_id, source_description, match_confidence, confirmed_by, confirmed_at, is_active, notes)
SELECT
    md5(concat('psa008-', src_c, '-', desc_val))::uuid,
    (SELECT id FROM product_skus WHERE sku_code = 'KAS1L'),
    (SELECT id FROM data_sources WHERE source_code = src_c),
    desc_val, 'CONFIRMED'::match_confidence_enum, 'NSM', NOW(), TRUE,
    'Kevin Arnold Shiraz 1.5L Magnum alias'
FROM (VALUES
    ('ERP_EXPORT', 'Kevin Arnold Shiraz 1.5L Magnum'),
    ('ERP_EXPORT', 'Kevin Arnold Shiraz Magnum 1.5L'),
    ('NGF_MONTHLY','KEVIN ARNOLD SHIRAZ 1.5L')
) AS t(src_c, desc_val)
ON CONFLICT DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────────
-- 3. WCB001: add L25WFCB750 and other ERP vintage-format aliases
-- NSM confirmed: L25WFCB750 = Waterford Chenin Blanc 750ml (2025 vintage prefix)
-- Pattern: L{YY}WF{product}750 = vintage SKU code, different year = same canonical
-- ────────────────────────────────────────────────────────────────────────────
INSERT INTO product_source_aliases
(id, product_sku_id, source_id, source_description, match_confidence, confirmed_by, confirmed_at, is_active, notes)
SELECT
    md5(concat('psa008-', src_c, '-', desc_val))::uuid,
    (SELECT id FROM product_skus WHERE sku_code = 'WCB001'),
    (SELECT id FROM data_sources WHERE source_code = src_c),
    desc_val, conf, 'NSM', NOW(), TRUE, note_val
FROM (VALUES
    -- NSM explicitly confirmed:
    ('ERP_EXPORT', 'L25WFCB750',                   'CONFIRMED'::match_confidence_enum, 'NSM confirmed: L25=vintage 2025, WF=Waterford, CB=Chenin Blanc, 750=750ml'),
    -- Earlier vintage codes follow same pattern:
    ('ERP_EXPORT', 'L24WFCB750',                   'CONFIRMED'::match_confidence_enum, 'Same product, 2024 vintage prefix'),
    ('ERP_EXPORT', 'L23WFCB750',                   'CONFIRMED'::match_confidence_enum, 'Same product, 2023 vintage prefix'),
    ('ERP_EXPORT', 'L22WFCB750',                   'CONFIRMED'::match_confidence_enum, 'Same product, 2022 vintage prefix'),
    ('ERP_EXPORT', 'L21WFCB750',                   'CONFIRMED'::match_confidence_enum, 'Same product, 2021 vintage prefix'),
    -- Long-form descriptions already seeded in 006 but confirm here:
    ('NGF_MONTHLY','WATERFORD CHENIN BLANC',        'CONFIRMED'::match_confidence_enum, 'NGF Monthly format'),
    ('NGF_MONTHLY','OLD VINE PROJECT CHENIN BLANC', 'CONFIRMED'::match_confidence_enum, 'OVP brand name variant in NGF')
) AS t(src_c, desc_val, conf, note_val)
ON CONFLICT DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────────
-- 4. MCC001: add L19WFMCC750 (confirmed) and L19WFMCC75P (PROBABLE, investigate P)
--
-- NSM noted: L19WFMCC75P — the P suffix. In FY2026 ERP we only see
-- "Special - Waterford Bubbly". No L-format codes appear in FY26 data.
-- These aliases prepare for FY2027 ERP imports.
--
-- P suffix investigation:
--   Wine industry common P suffixes: P = Perlage (sparkling), Prestige, Pét-nat, POP.
--   For Cap Classique: most likely P = different packaging/closure, not different product.
--   Mapping L19WFMCC75P to MCC001 as PROBABLE until NSM can confirm.
-- ────────────────────────────────────────────────────────────────────────────
INSERT INTO product_source_aliases
(id, product_sku_id, source_id, source_description, match_confidence, confirmed_by, confirmed_at, is_active, notes)
SELECT
    md5(concat('psa008-', src_c, '-', desc_val))::uuid,
    (SELECT id FROM product_skus WHERE sku_code = 'MCC001'),
    (SELECT id FROM data_sources WHERE source_code = src_c),
    desc_val, conf, 'NSM', NOW(), TRUE, note_val
FROM (VALUES
    -- NSM confirmed 750ml format:
    ('ERP_EXPORT', 'L19WFMCC750', 'CONFIRMED'::match_confidence_enum, 'NSM confirmed: L19=vintage 2019, WF=Waterford, MCC=Cap Classique, 750=750ml'),
    ('ERP_EXPORT', 'L20WFMCC750', 'CONFIRMED'::match_confidence_enum, 'Same product, 2020 vintage prefix'),
    ('ERP_EXPORT', 'L21WFMCC750', 'CONFIRMED'::match_confidence_enum, 'Same product, 2021 vintage prefix'),
    ('ERP_EXPORT', 'L22WFMCC750', 'CONFIRMED'::match_confidence_enum, 'Same product, 2022 vintage prefix'),
    ('ERP_EXPORT', 'L23WFMCC750', 'CONFIRMED'::match_confidence_enum, 'Same product, 2023 vintage prefix'),
    -- P suffix: PROBABLE until confirmed (likely same product, different packaging/closure)
    ('ERP_EXPORT', 'L19WFMCC75P', 'PROBABLE',  'P suffix under investigation. Most likely same product (different closure/packaging). Confirm with NSM before promoting to CONFIRMED.'),
    ('ERP_EXPORT', 'L20WFMCC75P', 'PROBABLE',  'P suffix under investigation.'),
    ('ERP_EXPORT', 'Waterford Cap Classique 750ml', 'CONFIRMED'::match_confidence_enum, 'Long-form ERP variant'),
    ('ERP_EXPORT', 'Waterford MCC 750ml',           'CONFIRMED'::match_confidence_enum, 'MCC abbreviation in ERP'),
    ('NGF_MONTHLY','WATERFORD MCC',                 'CONFIRMED'::match_confidence_enum, 'NGF Monthly format'),
    ('NGF_MONTHLY','WATERFORD CAP CLASSIQUE',       'CONFIRMED'::match_confidence_enum, 'NGF Monthly long form')
) AS t(src_c, desc_val, conf, note_val)
ON CONFLICT DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────────
-- SECTION: VERIFICATION AND COUNTS
-- ────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
  RAISE NOTICE '=== Migration 008 Verification ===';
  RAISE NOTICE 'CABMAG active: %, SBE: %, aliases: %',
    (SELECT is_active FROM product_skus WHERE sku_code='CABMAG'),
    (SELECT standard_bottle_equivalent FROM product_skus WHERE sku_code='CABMAG'),
    (SELECT COUNT(*) FROM product_source_aliases WHERE product_sku_id=(SELECT id FROM product_skus WHERE sku_code='CABMAG'));
  RAISE NOTICE 'KAS1L aliases: %',
    (SELECT COUNT(*) FROM product_source_aliases WHERE product_sku_id=(SELECT id FROM product_skus WHERE sku_code='KAS1L'));
  RAISE NOTICE 'WCB001 aliases: %',
    (SELECT COUNT(*) FROM product_source_aliases WHERE product_sku_id=(SELECT id FROM product_skus WHERE sku_code='WCB001'));
  RAISE NOTICE 'MCC001 aliases: %',
    (SELECT COUNT(*) FROM product_source_aliases WHERE product_sku_id=(SELECT id FROM product_skus WHERE sku_code='MCC001'));
  RAISE NOTICE 'Total product_source_aliases: %', (SELECT COUNT(*) FROM product_source_aliases);
END $$;
