-- Migration 016: Session hotfixes applied during final MCR / UAT pass
-- 
-- DATA CHANGES ALREADY APPLIED directly to DB in previous session:
-- 1. MAKBL001 repointed to Makro canonical (MAKBL001 correction)
-- 2. BONDED Under the Influence removed from EXPORT_DEBTORS classification
--    → 44 transactions reclassified from EXPORT_SALE to DIRECT_SALE
-- 3. asp_version_id bug fixed in retroactive_resolve.py (asp['id'] → asp['asp_version_id'])
-- 4. classify.py extended: Internal groups, EXPORT_DRGROUPS, Non-wine groups added to DTC_GROUPS
-- 5. product_source_alias added: "Library Collection Wines" → DLIB (750ml, CONFIRMED)
-- 6. Non-commercial category anchor clients created (mcr_noncommercial)
-- 7. Commercial Category C clients resolved (mcr_commercial_c)
-- 8. client_ownership populated from ERP srepname attribution (ERP_DERIVED)
-- 9. Human-review flags set on MANO0004, TOPSM002, UNITED01, UNITED02
--
-- This migration is a documentation/idempotency record.
-- Running it on a freshly bootstrapped DB has no effect (all changes are via scripts/MCR).
-- Running it on the production DB after bootstrap+import will confirm state.

-- Confirm MAKBL001 points to Makro (idempotent check)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM client_source_aliases csa
    JOIN data_sources ds ON ds.id = csa.source_id
    JOIN clients c ON c.id = csa.client_id
    WHERE ds.source_code = 'ERP_EXPORT' AND csa.source_code = 'MAKBL001'
      AND c.canonical_name = 'Makro'
  ) THEN
    RAISE NOTICE 'MAKBL001 not yet pointed to Makro — apply MCR scripts before this migration';
  ELSE
    RAISE NOTICE '016 check: MAKBL001 → Makro OK';
  END IF;
END $$;

-- Ensure product_source_alias for Library Collection Wines exists
-- (safe to run; ON CONFLICT DO NOTHING)
INSERT INTO product_source_aliases (
    product_sku_id, source_id, source_sku_code, source_description,
    match_confidence, confirmed_by, confirmed_at, is_active, notes
)
SELECT 
    ps.id,
    ds.id,
    NULL,
    'Library Collection Wines',
    'CONFIRMED',
    'mcr_dlib_mapping',
    NOW(),
    TRUE,
    '016 hotfix: DLIB aggregate SKU for ERP salgrpname Library Collection Wines (B750 only).'
FROM product_skus ps
JOIN products p ON p.id = ps.product_id
JOIN data_sources ds ON ds.source_code = 'ERP_EXPORT'
WHERE p.product_code = 'DLIB' AND ps.sku_code = 'DLIB'
ON CONFLICT DO NOTHING;
