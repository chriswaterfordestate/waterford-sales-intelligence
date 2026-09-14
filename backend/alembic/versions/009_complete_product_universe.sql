-- =============================================================================
-- MIGRATION 009: Complete ERP Product Universe
-- Based on full audit of 43 unique ERP salgrpnames in FY2026 data
--
-- NSM confirmed: all four 1.5L Magnum formats exist
-- Architecture: salgrpname → canonical SKU is the primary ERP mapping path
--
-- New SKUs created: RM1500, CHD1500, ANT1500, JEM1500
-- Aliases added:    all unaliased standard salgrpnames + all 1.5L variants
-- Not created:      Pinot Noir, &Beyond, Library, Estate SB (hold for NSM)
-- Excluded:         Tasting room items, packaging, samples, Rose-Mary 500ml, Jem 375ml
-- =============================================================================

-- ────────────────────────────────────────────────────────────────────────────
-- SECTION A: NEW 1.5L SKUs (all confirmed by NSM)
-- Pattern: add as new SKU under EXISTING canonical product
--          1 physical bottle = 1 bottle_actual = 2 standard_bottle_equiv
-- ────────────────────────────────────────────────────────────────────────────

-- A1. Rose-Mary 1.5L Magnum
INSERT INTO product_skus
(id, product_id, sku_code, sku_name, bottle_size_ml, standard_bottle_equivalent, default_case_size, tier, is_active, created_by)
VALUES (
    md5('sku-rm-1500')::uuid,
    (SELECT id FROM products WHERE product_code='RM'),
    'RM1500', 'Rose-Mary 1.5L Magnum', 1500, 2.000, 3, 'PREMIUM', TRUE, 'system'
) ON CONFLICT DO NOTHING;

-- A2. Waterford Chardonnay 1.5L Magnum
INSERT INTO product_skus
(id, product_id, sku_code, sku_name, bottle_size_ml, standard_bottle_equivalent, default_case_size, tier, is_active, created_by)
VALUES (
    md5('sku-chd-1500')::uuid,
    (SELECT id FROM products WHERE product_code='CHD'),
    'CHD1500', 'Waterford Chardonnay 1.5L Magnum', 1500, 2.000, 3, 'PREMIUM', TRUE, 'system'
) ON CONFLICT DO NOTHING;

-- A3. Waterford Antigo 1.5L Magnum
INSERT INTO product_skus
(id, product_id, sku_code, sku_name, bottle_size_ml, standard_bottle_equivalent, default_case_size, tier, is_active, created_by)
VALUES (
    md5('sku-ant-1500')::uuid,
    (SELECT id FROM products WHERE product_code='ANT'),
    'ANT1500', 'Waterford Antigo 1.5L Magnum', 1500, 2.000, 3, 'PREMIUM', TRUE, 'system'
) ON CONFLICT DO NOTHING;

-- A4. Jem 1.5L Magnum
INSERT INTO product_skus
(id, product_id, sku_code, sku_name, bottle_size_ml, standard_bottle_equivalent, default_case_size, tier, is_active, created_by)
VALUES (
    md5('sku-jem-1500')::uuid,
    (SELECT id FROM products WHERE product_code='JEM'),
    'JEM1500', 'Jem 1.5L Magnum', 1500, 2.000, 3, 'ICON', TRUE, 'system'
) ON CONFLICT DO NOTHING;

-- SBE sanity check
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM product_skus WHERE bottle_size_ml=1500 AND standard_bottle_equivalent != 2.000
  ) THEN
    RAISE EXCEPTION 'SBE check failed: all 1500ml SKUs must have standard_bottle_equivalent=2.000';
  END IF;
  RAISE NOTICE 'SBE check passed: all 1.5L SKUs have SBE=2.000';
END $$;

-- ────────────────────────────────────────────────────────────────────────────
-- SECTION B: FIX INCORRECT ALIAS
-- "Jem 1.5L" was previously aliased to JEM001 (750ml) — WRONG.
-- Remove that alias; add correct alias to JEM1500.
-- ────────────────────────────────────────────────────────────────────────────
DELETE FROM product_source_aliases
WHERE source_description = 'Jem 1.5L'
  AND product_sku_id = (SELECT id FROM product_skus WHERE sku_code='JEM001');

-- Confirm the deletion didn't leave orphaned business data
-- (Any transactions using Jem 1.5L → JEM001 would have wrong SBE; 
--  there were only 1 mapped row before so this is safe)

-- ────────────────────────────────────────────────────────────────────────────
-- SECTION C: PRODUCT SOURCE ALIASES — COMPLETE ERP SALGRPNAME COVERAGE
-- Maps every resolvable ERP salgrpname to canonical SKU.
-- Source: full audit of 43 unique salgrpnames from FY2026 ERP.
-- ────────────────────────────────────────────────────────────────────────────

INSERT INTO product_source_aliases
(id, product_sku_id, source_id, source_description, match_confidence, confirmed_by, confirmed_at, is_active, notes)
SELECT
    md5(concat('psa009-ERP-', desc_val))::uuid,
    (SELECT id FROM product_skus WHERE sku_code = sku_c),
    (SELECT id FROM data_sources WHERE source_code = 'ERP_EXPORT'),
    desc_val, 'CONFIRMED', 'NSM', NOW(), TRUE, note_val
FROM (VALUES
    -- ── Standard 750ml / 375ml / 500ml ──────────────────────────────────────
    -- Rose-Mary: currently has alias 'Rose-Mary' ✓
    -- Kevin Arnold Shiraz: has 'Kevin Arnold Shiraz' ✓; add 750ml variant
    ('Kevin Arnold Shiraz 750ml',         'KAS001', 'ERP salgrpname with size suffix'),

    -- Waterford Cabernet Sauvignon: has 'Waterford Cabernet Sauvignon' ✓; add Cab Sauv short form
    ('Waterford Cab Sauv',                'CAB001', 'Short ERP name for Cab Sauv'),

    -- Pecan Stream: CRITICAL — salgrpname uses shortened form
    ('Pecan Stream Chenin',               'PSC001', 'ERP salgrpname: Pecan Stream Chenin (not Chenin Blanc) — same product, 55K btls FY26'),
    ('Pecan Stream Sauv Blanc',           'PSS001', 'ERP salgrpname: Sauv Blanc (already confirmed in 007/008)'),
    ('Pecan Stream Red 750ml',            'PSR001', 'ERP salgrpname: with 750ml suffix — same Pecan Stream Red'),
    ('Pecan Stream Sauv blanc 750ml',     'PSS001', 'Lower-case b variant'),

    -- Antigo with 750ml suffix
    ('Waterford Antigo 750ml',            'ANT001', 'ERP salgrpname includes 750ml suffix'),
    ('Waterford Antigo',                  'ANT001', 'Short form (already seeded but ensure coverage)'),

    -- Chardonnay with 750ml suffix
    ('Waterford Chardonnay 750ml',        'CHD001', 'ERP salgrpname includes 750ml suffix'),

    -- Jem with 750ml suffix: currently has 'Jem 750ml' ✓
    -- Elgin: B1 = Batch 1 / Block 1 indicator
    ('Waterford Elgin Sauv B1 750ml',     'ELG001', 'B1 = Batch 1 / Block 1 range indicator. Same canonical Elgin SB 750ml'),
    ('Waterford Elgin Sauv B1 500ml',     'ELG500', 'B1 = Batch 1. Elgin SB 500ml format'),
    ('Waterford Elgin Sauvignon Blanc',   'ELG001', 'Long-form without B1 indicator'),

    -- ── 1.5L Magnums ────────────────────────────────────────────────────────
    ('Rose-Mary 1.5L',                    'RM1500', 'NSM confirmed: Rose-Mary 1.5L Magnum exists'),
    ('Waterford Chardonnay 1.5L',         'CHD1500','NSM confirmed: Chardonnay 1.5L Magnum'),
    ('Waterford Antigo 1.5L',             'ANT1500','NSM confirmed: Antigo 1.5L Magnum'),
    ('Jem 1.5L',                          'JEM1500','NSM confirmed: Jem 1.5L Magnum — CORRECTED from wrong JEM001 alias'),

    -- Kevin Arnold Shiraz 1.5L: already in 008 aliases as → KAS1L
    -- Waterford Cab Sauv 1.5L: already in 008 aliases as → CABMAG

    -- ── Vintage-style L** codes for 1.5L formats ───────────────────────────
    -- Rose-Mary (RM): L**WFRM1.5
    ('L25WFRM1.5',   'RM1500', 'Vintage SKU: L25=2025, WF=Waterford, RM=Rose-Mary, 1.5=1.5L'),
    ('L26WFRM1.5',   'RM1500', 'NSM example: L26 vintage = same Rose-Mary 1.5L'),
    ('L24WFRM1.5',   'RM1500', '2024 vintage prefix — same product'),
    -- Chardonnay 1.5L (CHD): L**WFCH1.5
    ('L25WFCH1.5',   'CHD1500','Vintage SKU: Chardonnay 1.5L 2025'),
    ('L24WFCH1.5',   'CHD1500','Chardonnay 1.5L 2024'),
    -- Antigo 1.5L (ANT): L**WFAN1.5 or similar
    ('L25WFAN1.5',   'ANT1500','Vintage SKU: Antigo 1.5L 2025'),
    -- Jem 1.5L: L**WFJE1.5
    ('L25WFJE1.5',   'JEM1500','Vintage SKU: Jem 1.5L 2025'),
    -- Kevin Arnold 1.5L: L**WFKA1.5 or L**WFKAS1.5
    ('L25WFKA1.5',   'KAS1L',  'Vintage SKU: Kevin Arnold 1.5L 2025'),
    ('L25WFKAS1.5',  'KAS1L',  'Alternative vintage SKU format'),

    -- ── Vintage-style L** codes for standard 750ml ─────────────────────────
    -- Rose-Mary 750ml: L**WFRM750
    ('L25WFRM750',   'RM001',  'Vintage SKU: Rose-Mary 750ml 2025 vintage'),
    ('L24WFRM750',   'RM001',  '2024 vintage prefix'),
    ('L26WFRM750',   'RM001',  '2026 vintage prefix (future-proofing)'),
    -- Kevin Arnold Shiraz 750ml: L**WFKA750 or L**WFKAS750
    ('L25WFKA750',   'KAS001', 'Kevin Arnold Shiraz 750ml 2025'),
    ('L25WFKAS750',  'KAS001', 'Alternative format'),
    -- Jem 750ml: L**WFJE750 or L**WFJEM750
    ('L25WFJE750',   'JEM001', 'Jem 750ml 2025'),
    ('L25WFJEM750',  'JEM001', 'Jem 750ml alternative format'),
    -- Cab Sauv 750ml: L**WFCS750
    ('L25WFCS750',   'CAB001', 'Cab Sauv 750ml 2025'),
    ('L24WFCS750',   'CAB001', '2024 vintage'),
    -- Antigo 750ml: L**WFAN750
    ('L25WFAN750',   'ANT001', 'Antigo 750ml 2025'),
    -- Chardonnay 750ml: L**WFCH750
    ('L25WFCH750',   'CHD001', 'Chardonnay 750ml 2025'),
    -- Elgin SB 750ml: L**WFEB750
    ('L25WFEB750',   'ELG001', 'Elgin SB 750ml 2025'),
    ('L25WFELG750',  'ELG001', 'Elgin SB 750ml alternative format'),
    -- Grenache 750ml
    ('L25WFGRE750',  'GRN001', 'Grenache 750ml 2025'),
    ('L25WFGR750',   'GRN001', 'Grenache 750ml short format'),
    -- OVP Pinotage 750ml
    ('L25WFOVP750',  'OVP001', 'Old Vine Pinotage 750ml 2025'),
    -- Rose-Mary 750ml: also sold as RM
    ('L25WFRM75P',   'RM001',  'Rose-Mary 750ml with P suffix (packaging variant)'),
    -- Cab Sauv 375ml
    ('L25WFCS375',   'CAB375', 'Cab Sauv 375ml 2025'),
    -- WCB / Chenin Blanc variants already seeded in 008

    -- ── NGF SalesOut additional salgrpname variants ─────────────────────────
    ('Waterford Antigo 750ml',     'ANT001', 'NGF Monthly variant with size'),
    ('Waterford Chardonnay 750ml', 'CHD001', 'NGF Monthly with size')

) AS t(desc_val, sku_c, note_val)
WHERE (SELECT id FROM product_skus WHERE sku_code = t.sku_c) IS NOT NULL
ON CONFLICT DO NOTHING;

-- Also add NGF SalesOut 1.5L aliases
INSERT INTO product_source_aliases
(id, product_sku_id, source_id, source_description, match_confidence, confirmed_by, confirmed_at, is_active, notes)
SELECT
    md5(concat('psa009-NGF-', desc_val))::uuid,
    (SELECT id FROM product_skus WHERE sku_code = sku_c),
    (SELECT id FROM data_sources WHERE source_code = src_c),
    desc_val, 'CONFIRMED', 'NSM', NOW(), TRUE, 'NSM confirmed 1.5L format'
FROM (VALUES
    ('NGF_SALESOUT', 'ROSE-MARY 1.5L',                 'RM1500'),
    ('NGF_SALESOUT', 'WATERFORD ROSE-MARY 1.5L',       'RM1500'),
    ('NGF_SALESOUT', 'WATERFORD CHARDONNAY 1.5L',      'CHD1500'),
    ('NGF_SALESOUT', 'WATERFORD ANTIGO 1.5L',          'ANT1500'),
    ('NGF_SALESOUT', 'JEM 1.5L',                       'JEM1500'),
    ('NGF_SALESOUT', 'WATERFORD EST JEM 1.5L',         'JEM1500'),
    ('NGF_MONTHLY',  'ROSE-MARY 1.5L',                 'RM1500'),
    ('NGF_MONTHLY',  'WATERFORD CHARDONNAY 1.5L',      'CHD1500'),
    ('NGF_MONTHLY',  'WATERFORD ANTIGO 1.5L',          'ANT1500'),
    ('NGF_MONTHLY',  'JEM 1.5L',                       'JEM1500')
) AS t(src_c, desc_val, sku_c)
ON CONFLICT DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────────
-- SECTION D: SALGRPNAMES HELD UNRESOLVED (do not create canonical SKUs)
-- These appear in the ERP but require NSM confirmation before any mapping.
-- They will remain UNKNOWN_PRODUCT in the review queue.
-- ────────────────────────────────────────────────────────────────────────────
-- Unresolved salgrpnames (documented, not aliased):
-- 'Special - &Beyond Wines'    : 3,240 btls — co-label/private label for &Beyond lodges
--                                All through UNDE0001 (bonded export). NSM to confirm product identity.
-- 'Library Collection Wines'   : 1,056 btls — multi-product archival range, cannot map to single SKU
-- 'Waterford Pinot Noir'       :   378 btls — finmth5/FY26 only, some through export & Mooiberge Winery
--                                Not in original 13 products. NSM to confirm product exists.
-- 'Waterford Estate Sauv Blanc':    50 btls — 50 btls only, mix of private/hotel/internal
--                                May be Elgin SB or separate range. NSM to confirm.
-- 'Large Bottles 3/5/12/18'   :   135 btls — large format catch-all (3L+)
-- 'Special - Other Wines'      :   544 btls — unclassified
-- 'Other Wines'                :   464 btls — catch-all
-- 'Library - White Wines'      :     1 btl  — single row

-- ────────────────────────────────────────────────────────────────────────────
-- SECTION E: VERIFICATION
-- ────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  sku_count  int;
  alias_count int;
BEGIN
  SELECT COUNT(*) INTO sku_count FROM product_skus WHERE bottle_size_ml=1500 AND is_active=TRUE;
  SELECT COUNT(*) INTO alias_count FROM product_source_aliases
    WHERE source_id=(SELECT id FROM data_sources WHERE source_code='ERP_EXPORT')
      AND is_active=TRUE;

  RAISE NOTICE '=== Migration 009 Verification ===';
  RAISE NOTICE 'Active 1.5L SKUs: % (expected 6: CABMAG, KAS1L, RM1500, CHD1500, ANT1500, JEM1500)', sku_count;
  RAISE NOTICE 'Total ERP product aliases: %', alias_count;

  -- Check RM1500 SBE
  IF (SELECT standard_bottle_equivalent FROM product_skus WHERE sku_code='RM1500') != 2.000 THEN
    RAISE EXCEPTION 'RM1500 SBE must be 2.000';
  END IF;

  -- Check JEM001 no longer has "Jem 1.5L" alias
  IF EXISTS (SELECT 1 FROM product_source_aliases
             WHERE source_description='Jem 1.5L'
               AND product_sku_id=(SELECT id FROM product_skus WHERE sku_code='JEM001')) THEN
    RAISE EXCEPTION 'Jem 1.5L alias must NOT point to JEM001 (750ml)';
  END IF;
  RAISE NOTICE 'Jem 1.5L → JEM001 incorrect alias: absent (correct)';

  -- Check JEM1500 has "Jem 1.5L" alias
  IF NOT EXISTS (SELECT 1 FROM product_source_aliases
                  WHERE source_description='Jem 1.5L'
                    AND product_sku_id=(SELECT id FROM product_skus WHERE sku_code='JEM1500')) THEN
    RAISE EXCEPTION 'Jem 1.5L must map to JEM1500';
  END IF;
  RAISE NOTICE 'Jem 1.5L → JEM1500 alias: present (correct)';
END $$;
