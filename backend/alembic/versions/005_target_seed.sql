-- =============================================================================
-- MIGRATION 005: FY2027 Initial Targets (Gauteng Combined — MVP)
--
-- WHAT THESE FIGURES REPRESENT:
--   3,557 btls (July 2026)  = Combined target for Koliswa + Sandile + Helena
--   3,953 btls (August 2026) = Combined target for all three Gauteng reps
--   657,045 ZAR (July 2026)  = Combined rand value target
--   784,286 ZAR (August 2026) = Combined rand value target
--
-- WHAT THESE DO NOT REPRESENT:
--   Individual rep splits — NOT available without Target Entry UI
--   Sep 2026–Jun 2027 — NOT loaded (enter via Target Entry UI in Phase 2)
--   Per-SKU targets — NOT loaded at this stage
--
-- LOADED AS: territory_id = GAU, rep_id = NULL, product_sku_id = NULL
-- target_level = TERRITORY (MVP)
-- =============================================================================

DO $$
DECLARE
  ts_id UUID;
BEGIN
  -- Create the target set
  INSERT INTO target_sets (id, financial_year_id, set_name, is_active, target_level, source_document, approved_by, approved_at, notes, created_by)
  VALUES (
    'b8dc1af2-88b4-f7ae-4799-72898968471b',
    '711c05f1-fb11-13d3-71e6-5c7c926e5dfe',
    'FY2027 Initial — Gauteng Combined',
    TRUE,
    'TERRITORY',
    'Sergio King FY2027 Target Sheet (K+S+H combined)',
    'system',
    NOW(),
    'MVP territory-level targets only. Individual rep splits to be entered via Target Entry UI in Phase 2. Only July and August loaded — Sep-Jun targets must be entered via UI.',
    'system'
  ) RETURNING id INTO ts_id;

  -- July 2026 target — Gauteng territory combined
  INSERT INTO targets (id, target_set_id, rep_id, territory_id, product_sku_id, financial_period_id, target_bottles, target_rand_value, source_document, notes, created_by)
  VALUES (
    'b8187d1b-0d8b-a31c-1ec8-c2baa909e9cc',
    'b8dc1af2-88b4-f7ae-4799-72898968471b',
    NULL,                                             -- rep_id NULL = territory-level target
    'abbf9648-42ab-9760-61ff-f3ebaeaa4602',           -- GAU territory
    NULL,                                             -- product_sku_id NULL = all SKUs combined
    'b62e09e7-1dcf-871d-f751-61d3211ff48a',                                     -- July 2026
    3557,
    657045,
    'Sergio King FY2027 Target Sheet',
    'Combined K+S+H Gauteng July 2026. Source: target PDF total row.',
    'system'
  );

  -- August 2026 target — Gauteng territory combined
  INSERT INTO targets (id, target_set_id, rep_id, territory_id, product_sku_id, financial_period_id, target_bottles, target_rand_value, source_document, notes, created_by)
  VALUES (
    '9c9d09f1-ccb0-2a3f-50b3-72d82c102bc0',
    'b8dc1af2-88b4-f7ae-4799-72898968471b',
    NULL,
    'abbf9648-42ab-9760-61ff-f3ebaeaa4602',
    NULL,
    'ff33766f-1d50-e169-67e3-316053193007',                                     -- August 2026
    3953,
    784286,
    'Sergio King FY2027 Target Sheet',
    'Combined K+S+H Gauteng August 2026. Source: target PDF total row.',
    'system'
  );

  RAISE NOTICE 'FY2027 Gauteng targets seeded: Jul=3557 btls R657045, Aug=3953 btls R784286';
END $$;
