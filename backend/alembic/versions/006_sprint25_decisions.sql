-- =============================================================================
-- MIGRATION 006: Sprint 2.5 — NSM Confirmed Decisions
-- Date: September 2026
--
-- Decisions implemented:
-- 1. NORMANPA → new client: NGF Paarden Eiland (separate branch)
-- 2. CAMPSBAY → new client: Divine Inspiration Trading / Kove Collection (Nathalie)
-- 3. DIST0002 → new client: Distriliq CPT — Durbanville Brand (separate brand/manager)
-- 4. LEGACY01 → new distributor + client: Legacy Liquors (independent)
-- 5. Waterford Chenin Blanc = Old Vine Project Chenin Blanc → new product WCB + SKU WCB001
-- 6. Special - Waterford Bubbly = Waterford Cap Classique/MCC → new product MCC + SKU MCC001
-- 7. 3 confirmed ERP product aliases added (Pecan Stream Sauv Blanc, Grenache Noir, Cab 375ml)
-- 8. Waterford Cab Sauv 1.5L → new SKU CAB1L (Cabernet Sauvignon 1.5L)
-- =============================================================================

-- ────────────────────────────────────────────────────────────────────────────
-- SECTION A: NEW PRODUCTS AND SKUs
-- ────────────────────────────────────────────────────────────────────────────

-- A1. Old Vine Project Chenin Blanc (new product)
--     Known in source files as: "Waterford Chenin Blanc", "Waterford Estate Chenin Blanc",
--     "OVP Chenin Blanc", "Old Vine Project Chenin Blanc"
--     NSM confirmed: "Should be a consistent SKU"
INSERT INTO products (id, product_code, product_name, brand_name, tier, is_active, created_by)
VALUES (
    md5('prod-WCB')::uuid,
    'WCB',
    'Old Vine Project Chenin Blanc',
    'Old Vine Project',
    'PREMIUM',
    TRUE,
    'system'
) ON CONFLICT DO NOTHING;

INSERT INTO product_skus (id, product_id, sku_code, sku_name, bottle_size_ml,
    standard_bottle_equivalent, default_case_size, tier, is_active, created_by)
VALUES (
    md5('sku-wcb-750')::uuid,
    md5('prod-WCB')::uuid,
    'WCB001',
    'Old Vine Project Chenin Blanc 750ml',
    750, 1.000, 6, 'PREMIUM', TRUE, 'system'
) ON CONFLICT DO NOTHING;

-- ASP for WCB001 — FY2027 and FY2026 approximations
-- Using R149.00 (same tier as Chardonnay/Elgin/Grenache) — adjust when confirmed
INSERT INTO asp_versions (id, product_sku_id, asp_value, currency, effective_from,
    source_document, methodology, is_approved, approved_by, approved_at, notes, created_by)
VALUES (
    md5('asp-wcb-fy27')::uuid,
    md5('sku-wcb-750')::uuid,
    149.00, 'ZAR', '2026-07-01',
    'Estimated: same tier as ELG/CHD/GRN per NSM verbal',
    'BLENDED_CATEGORY', FALSE, NULL, NULL,
    'UNCONFIRMED ASP — NSM to confirm WCB001 pricing before using for R-value estimation',
    'system'
) ON CONFLICT DO NOTHING;

INSERT INTO asp_versions (id, product_sku_id, asp_value, currency, effective_from, effective_to,
    source_document, methodology, is_approved, approved_by, approved_at, notes, created_by)
VALUES (
    md5('asp-wcb-fy26')::uuid,
    md5('sku-wcb-750')::uuid,
    139.32, 'ZAR', '2020-01-01', '2026-06-30',
    'Estimated FY2026: FY2027 estimate × 0.935',
    'BLENDED_CATEGORY', FALSE, NULL, NULL,
    'UNCONFIRMED ASP — FY2026 estimate only. NSM to confirm.',
    'system'
) ON CONFLICT DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- A2. Waterford Cap Classique / MCC (new product)
--     Known in source files as: "Special - Waterford Bubbly", "Waterford Cap Classique",
--     "Waterford MCC", "Waterford Cap Classique MCC"
--     NSM confirmed: "our only bubbly, not discontinued"
INSERT INTO products (id, product_code, product_name, brand_name, tier, is_active, notes, created_by)
VALUES (
    md5('prod-MCC')::uuid,
    'MCC',
    'Waterford Cap Classique',
    'Waterford Estate',
    'PREMIUM',
    TRUE,
    'Single sparkling wine product. Also known as MCC, Cap Classique, or historically Waterford Bubbly in some source files.',
    'system'
) ON CONFLICT DO NOTHING;

INSERT INTO product_skus (id, product_id, sku_code, sku_name, bottle_size_ml,
    standard_bottle_equivalent, default_case_size, tier, is_active, created_by)
VALUES (
    md5('sku-mcc-750')::uuid,
    md5('prod-MCC')::uuid,
    'MCC001',
    'Waterford Cap Classique 750ml',
    750, 1.000, 6, 'PREMIUM', TRUE, 'system'
) ON CONFLICT DO NOTHING;

INSERT INTO asp_versions (id, product_sku_id, asp_value, currency, effective_from,
    source_document, methodology, is_approved, approved_by, approved_at, notes, created_by)
VALUES (
    md5('asp-mcc-fy27')::uuid,
    md5('sku-mcc-750')::uuid,
    245.00, 'ZAR', '2026-07-01',
    'Estimated: Cap Classique pricing tier',
    'BLENDED_CATEGORY', FALSE, NULL, NULL,
    'UNCONFIRMED ASP — NSM to confirm MCC001 pricing',
    'system'
) ON CONFLICT DO NOTHING;

INSERT INTO asp_versions (id, product_sku_id, asp_value, currency, effective_from, effective_to,
    source_document, methodology, is_approved, approved_by, approved_at, notes, created_by)
VALUES (
    md5('asp-mcc-fy26')::uuid,
    md5('sku-mcc-750')::uuid,
    229.08, 'ZAR', '2020-01-01', '2026-06-30',
    'Estimated FY2026 × 0.935',
    'BLENDED_CATEGORY', FALSE, NULL, NULL,
    'UNCONFIRMED FY2026 ASP',
    'system'
) ON CONFLICT DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- A3. Waterford Cabernet Sauvignon 1.5L (new SKU — Cab Magnum)
--     "Waterford Cab Sauv 1.5L" appears in ERP with 12 rows, 156 btls
INSERT INTO product_skus (id, product_id, sku_code, sku_name, bottle_size_ml,
    standard_bottle_equivalent, default_case_size, tier, is_active, created_by)
VALUES (
    md5('sku-cab-1500')::uuid,
    (SELECT id FROM products WHERE product_code = 'CAB'),
    'CAB1L',
    'Waterford Cabernet Sauvignon 1.5L Magnum',
    1500, 2.000, 3, 'ICON', TRUE, 'system'
) ON CONFLICT DO NOTHING;

INSERT INTO asp_versions (id, product_sku_id, asp_value, currency, effective_from,
    source_document, methodology, is_approved, approved_by, approved_at, notes, created_by)
VALUES (
    md5('asp-cab1l-fy27')::uuid,
    md5('sku-cab-1500')::uuid,
    508.00, 'ZAR', '2026-07-01',
    'Estimated: CAB001 750ml × 2',
    'BLENDED_CATEGORY', FALSE, NULL, NULL,
    'UNCONFIRMED — 2 × R254.00 = R508.00 estimate. NSM to confirm.',
    'system'
) ON CONFLICT DO NOTHING;

INSERT INTO asp_versions (id, product_sku_id, asp_value, currency, effective_from, effective_to,
    source_document, methodology, is_approved, approved_by, approved_at, notes, created_by)
VALUES (
    md5('asp-cab1l-fy26')::uuid,
    md5('sku-cab-1500')::uuid,
    474.98, 'ZAR', '2020-01-01', '2026-06-30',
    'Estimated FY2026 × 0.935',
    'BLENDED_CATEGORY', FALSE, NULL, NULL,
    'UNCONFIRMED FY2026 estimate',
    'system'
) ON CONFLICT DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────────
-- SECTION B: PRODUCT SOURCE ALIASES
-- All confirmed name variants for new and existing SKUs
-- ────────────────────────────────────────────────────────────────────────────

-- B1. Confirmed ERP salgrpname aliases (3 that were pending without alias)
INSERT INTO product_source_aliases
(id, product_sku_id, source_id, source_description, match_confidence, confirmed_by, confirmed_at, is_active)
SELECT
    md5(concat('psa-erp-', desc_val))::uuid,
    (SELECT id FROM product_skus WHERE sku_code = sku_c),
    (SELECT id FROM data_sources WHERE source_code = 'ERP_EXPORT'),
    desc_val, 'CONFIRMED', 'NSM', NOW(), TRUE
FROM (VALUES
    ('Pecan Stream Sauv Blanc',   'PSS001'),   -- 38 rows, 5,988 btls — clear match
    ('Grenache Noir',              'GRN001'),   -- 30 rows,   291 btls — Waterford Grenache
    ('Waterford Cab Sauv 375ml',  'CAB375')    --  5 rows,    54 btls — clear abbreviation
) AS t(desc_val, sku_c)
ON CONFLICT DO NOTHING;

-- B2. ERP aliases for new SKUs (from NSM decisions)
INSERT INTO product_source_aliases
(id, product_sku_id, source_id, source_description, match_confidence, confirmed_by, confirmed_at, is_active, notes)
SELECT
    md5(concat('psa-erp-', desc_val))::uuid,
    (SELECT id FROM product_skus WHERE sku_code = sku_c),
    (SELECT id FROM data_sources WHERE source_code = 'ERP_EXPORT'),
    desc_val, 'CONFIRMED', 'NSM', NOW(), TRUE, note_val
FROM (VALUES
    ('Waterford Chenin Blanc',     'WCB001', 'NSM confirmed: Old Vine Project Chenin Blanc. Consistent SKU across all name variants.'),
    ('Special - Waterford Bubbly', 'MCC001', 'NSM confirmed: our only bubbly, not discontinued. Same as Cap Classique.'),
    ('Waterford Cab Sauv 1.5L',   'CAB1L',  'Waterford Cabernet Sauvignon 1.5L Magnum'),
    ('Jem 1.5L',                   'JEM001', 'Jem 1.5L — very low volume (1 btl). Mapped to standard Jem until 1.5L SKU confirmed needed.')
) AS t(desc_val, sku_c, note_val)
ON CONFLICT DO NOTHING;

-- B3. NGF SalesOut aliases for Old Vine Project Chenin Blanc
--     "WATERFORD CHENIN BLANC   750M" (26 chars truncated, trailing spaces)
INSERT INTO product_source_aliases
(id, product_sku_id, source_id, source_description, match_confidence, confirmed_by, confirmed_at, is_active, notes)
VALUES (
    md5('psa-so-WATERFORD CHENIN BLANC   750M')::uuid,
    (SELECT id FROM product_skus WHERE sku_code = 'WCB001'),
    (SELECT id FROM data_sources WHERE source_code = 'NGF_SALESOUT'),
    'WATERFORD CHENIN BLANC   750M',
    'CONFIRMED', 'NSM', NOW(), TRUE,
    'Old Vine Project Chenin Blanc in NGF SalesOut truncated format'
) ON CONFLICT DO NOTHING;

-- B4. Multi-source aliases for Cap Classique (MCC)
INSERT INTO product_source_aliases
(id, product_sku_id, source_id, source_description, match_confidence, confirmed_by, confirmed_at, is_active, notes)
SELECT
    md5(concat('psa-', src_c, '-', desc_val))::uuid,
    (SELECT id FROM product_skus WHERE sku_code = 'MCC001'),
    (SELECT id FROM data_sources WHERE source_code = src_c),
    desc_val, 'CONFIRMED', 'NSM', NOW(), TRUE,
    'Waterford Cap Classique — various names used across sources'
FROM (VALUES
    ('ERP_EXPORT',    'Waterford Cap Classique'),
    ('ERP_EXPORT',    'Waterford MCC'),
    ('ERP_EXPORT',    'Cap Classique'),
    ('ERP_EXPORT',    'Waterford Bubbly'),
    ('NGF_SALESOUT',  'WATERFORD CAP CLASSIQUE 750M'),
    ('NGF_MONTHLY',   'WATERFORD CAP CLASSIQUE')
) AS t(src_c, desc_val)
ON CONFLICT DO NOTHING;

-- B5. Multi-source aliases for OVP Chenin Blanc
INSERT INTO product_source_aliases
(id, product_sku_id, source_id, source_description, match_confidence, confirmed_by, confirmed_at, is_active, notes)
SELECT
    md5(concat('psa-', src_c, '-', desc_val))::uuid,
    (SELECT id FROM product_skus WHERE sku_code = 'WCB001'),
    (SELECT id FROM data_sources WHERE source_code = src_c),
    desc_val, 'CONFIRMED', 'NSM', NOW(), TRUE,
    'Old Vine Project Chenin Blanc — all known name variants'
FROM (VALUES
    ('ERP_EXPORT',    'Old Vine Project Chenin Blanc'),
    ('ERP_EXPORT',    'OVP Chenin Blanc'),
    ('ERP_EXPORT',    'Waterford Estate Chenin Blanc'),
    ('NGF_MONTHLY',   'WATERFORD CHENIN BLANC'),
    ('NGF_MONTHLY',   'OLD VINE PROJECT CHENIN BLANC')
) AS t(src_c, desc_val)
ON CONFLICT DO NOTHING;

-- B6. Cab Sauv 1.5L alias
INSERT INTO product_source_aliases
(id, product_sku_id, source_id, source_description, match_confidence, confirmed_by, confirmed_at, is_active)
VALUES (
    md5('psa-erp-Waterford Cabernet Sauvignon 1.5L')::uuid,
    (SELECT id FROM product_skus WHERE sku_code = 'CAB1L'),
    (SELECT id FROM data_sources WHERE source_code = 'ERP_EXPORT'),
    'Waterford Cabernet Sauvignon 1.5L',
    'CONFIRMED', 'system', NOW(), TRUE
) ON CONFLICT DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────────
-- SECTION C: NEW DISTRIBUTORS (for entities with distributor role)
-- ────────────────────────────────────────────────────────────────────────────

-- C1. Legacy Liquors — confirmed independent distributor
--     NSM: "different distributor, independent"
INSERT INTO distributors (id, distributor_code, distributor_name, erp_debtor_codes,
    erp_primary_debtor, territory_id, regions_covered, is_active, notes)
VALUES (
    md5('dist-LEGACY01')::uuid,
    'LEGACY_LIQ',
    'Legacy Liquors',
    ARRAY['LEGACY01'],
    'LEGACY01',
    (SELECT id FROM territories WHERE territory_code = 'WC_CPT'),
    ARRAY['CPT', 'WC'],
    TRUE,
    'Independent WC distributor. Rep: Sergio King historically. Confirmed by NSM as independent entity.'
) ON CONFLICT DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────────
-- SECTION D: NEW CANONICAL CLIENTS
-- ────────────────────────────────────────────────────────────────────────────

-- D1. NGF Paarden Eiland — separate NGF branch
--     NSM: "different branch so different client"
--     NORMANPA debtorcode, drgrp='Local - Liquor Store', rep=Sergio King
INSERT INTO clients (id, canonical_name, trading_name, outlet_type, tier,
    territory_id, primary_channel_id, is_active, notes, created_by)
VALUES (
    md5('cl-ngf-paarden-eiland')::uuid,
    'Norman Goodfellows Paarden Eiland',
    'NGF Paarden Eiland',
    'BOTTLE_STORE',
    'ON_TRADE',
    (SELECT id FROM territories WHERE territory_code = 'WC_CPT'),
    (SELECT id FROM channels WHERE channel_code = 'DIRECT_ERP'),
    TRUE,
    'NSM confirmed: separate branch from NGF main (NORM0002/NORMGF). Different physical location. ERP code NORMANPA. Rep: Sergio King territory.',
    'system'
) ON CONFLICT DO NOTHING;

-- D2. Kove Collection / Divine Inspiration Trading (CAMPSBAY)
--     NSM: "known as Divine Inspiration Trading or Kove Collection, managed by Nathalie"
INSERT INTO clients (id, canonical_name, trading_name, outlet_type, tier,
    territory_id, primary_channel_id, is_active, notes, created_by)
VALUES (
    md5('cl-kove-collection')::uuid,
    'Divine Inspiration Trading (Kove Collection)',
    'Kove Collection',
    'RESTAURANT',
    'ON_TRADE',
    (SELECT id FROM territories WHERE territory_code = 'WC_CPT'),
    (SELECT id FROM channels WHERE channel_code = 'DIRECT_ERP'),
    TRUE,
    'NSM confirmed: Kove Collection hospitality group. Legal entity: Divine Inspiration Trading 205. ERP debtor: CAMPSBAY. drgrp: Local - Distributors in ERP but confirmed as on-trade/restaurant group by NSM. Managed by Nathalie Watkins.',
    'system'
) ON CONFLICT DO NOTHING;

-- D3. Distriliq CPT — Durbanville/second brand (DIST0002)
--     NSM: "same company but different brand and different manager"
--     This is a SEPARATE MCR entry from cl-distriliq-dist (which is DISTRILIQ01)
INSERT INTO clients (id, canonical_name, trading_name, outlet_type, tier,
    territory_id, primary_channel_id, is_active, notes, created_by)
VALUES (
    md5('cl-distriliq-cpt-dist0002')::uuid,
    'Distriliq Cape Town (DIST0002 brand)',
    'Distriliq CPT',
    'WHOLESALE',
    'WHOLESALE',
    (SELECT id FROM territories WHERE territory_code = 'WC_CPT'),
    (SELECT id FROM channels WHERE channel_code = 'DISTRILIQ_CPT'),
    TRUE,
    'NSM confirmed: same company as cl-distriliq-dist (DISTRILIQ01) but different brand and different manager within Distriliq. ERP debtor code: DIST0002. Treat as SEPARATE canonical client. Do not merge aliases.',
    'system'
) ON CONFLICT DO NOTHING;

-- D4. Legacy Liquors — independent distributor (client record for sell-in tracking)
INSERT INTO clients (id, canonical_name, outlet_type, tier,
    territory_id, primary_channel_id, is_distributor, distributor_entity_id,
    is_active, notes, created_by)
VALUES (
    md5('cl-legacy-liquors')::uuid,
    'Legacy Liquors',
    'WHOLESALE',
    'DISTRIBUTOR',
    (SELECT id FROM territories WHERE territory_code = 'WC_CPT'),
    (SELECT id FROM channels WHERE channel_code = 'DISTRILIQ_CPT'),
    TRUE,
    md5('dist-LEGACY01')::uuid,
    TRUE,
    'NSM confirmed: independent distributor. Separate from Distriliq. ERP code LEGACY01. Rep: Sergio King territory. distributor_entity_id links to Legacy Liquors distributor record.',
    'system'
) ON CONFLICT DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────────
-- SECTION E: ERP SOURCE ALIASES FOR NEW CLIENTS
-- ────────────────────────────────────────────────────────────────────────────

INSERT INTO client_source_aliases
(id, client_id, source_id, source_name, source_code,
 match_confidence, match_status, matched_by, confirmed_by, confirmed_at, alias_notes)
VALUES
  -- NORMANPA → Norman Goodfellows Paarden Eiland
  (md5('csa-erp-NORMANPA')::uuid,
   md5('cl-ngf-paarden-eiland')::uuid,
   (SELECT id FROM data_sources WHERE source_code='ERP_EXPORT'),
   'NGF Paarden Eiland',
   'NORMANPA',
   'CONFIRMED', 'ACTIVE', 'system', 'NSM', NOW(),
   'NSM confirmed separate branch from NORM0002/NORMGF. NORMANPA = Paarden Eiland location.'),

  -- CAMPSBAY → Kove Collection
  (md5('csa-erp-CAMPSBAY')::uuid,
   md5('cl-kove-collection')::uuid,
   (SELECT id FROM data_sources WHERE source_code='ERP_EXPORT'),
   'Divine Inspiration Trading 205',
   'CAMPSBAY',
   'CONFIRMED', 'ACTIVE', 'system', 'NSM', NOW(),
   'NSM confirmed: Kove Collection. Legal entity Divine Inspiration Trading 205. ERP code CAMPSBAY. Nathalie account.'),

  -- DIST0002 → Distriliq CPT second brand
  (md5('csa-erp-DIST0002')::uuid,
   md5('cl-distriliq-cpt-dist0002')::uuid,
   (SELECT id FROM data_sources WHERE source_code='ERP_EXPORT'),
   'Distri Liq Cape Town',
   'DIST0002',
   'CONFIRMED', 'ACTIVE', 'system', 'NSM', NOW(),
   'NSM confirmed: same company as DISTRILIQ01 but different brand and different manager. SEPARATE canonical. Do not merge with cl-distriliq-dist.'),

  -- LEGACY01 → Legacy Liquors
  (md5('csa-erp-LEGACY01')::uuid,
   md5('cl-legacy-liquors')::uuid,
   (SELECT id FROM data_sources WHERE source_code='ERP_EXPORT'),
   'Legacy Liquors',
   'LEGACY01',
   'CONFIRMED', 'ACTIVE', 'system', 'NSM', NOW(),
   'NSM confirmed: independent distributor. Not related to Distriliq.')

ON CONFLICT DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────────
-- SECTION F: VERIFY COUNTS
-- ────────────────────────────────────────────────────────────────────────────

DO $$
BEGIN
  RAISE NOTICE 'Migration 006 complete.';
  RAISE NOTICE 'New products: %, New SKUs: %, New clients: %, New aliases: %',
    (SELECT COUNT(*) FROM products WHERE product_code IN ('WCB','MCC')),
    (SELECT COUNT(*) FROM product_skus WHERE sku_code IN ('WCB001','MCC001','CAB1L')),
    (SELECT COUNT(*) FROM clients WHERE id IN (
        md5('cl-ngf-paarden-eiland')::uuid,
        md5('cl-kove-collection')::uuid,
        md5('cl-distriliq-cpt-dist0002')::uuid,
        md5('cl-legacy-liquors')::uuid)),
    (SELECT COUNT(*) FROM client_source_aliases
     WHERE confirmed_by='NSM');
END $$;
