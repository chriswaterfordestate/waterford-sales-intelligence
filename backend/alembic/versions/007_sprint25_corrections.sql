-- =============================================================================
-- MIGRATION 007: Sprint 2.5 Corrections
-- Date: September 2026
--
-- Corrects the following issues identified in NSM review:
--
-- C1. NGF ERP debtors — reclassify to single NGF entity / DISTRIBUTOR_SELL_IN
--     NORMANPA is an NGF warehouse location, not a separate commercial client.
--     All NGF ERP debtors must be DISTRIBUTOR_SELL_IN under cl-ngf-dist.
--     Remove cl-ngf-paarden-eiland as standalone commercial entity.
--
-- C2. Remove all unconfirmed/invented ASP values (is_approved=FALSE)
--     WCB001, MCC001, CAB1L ASPs must not be used.
--     Per NSM: "An ASP may only become approved master data when supported
--     by an approved Waterford source or confirmed by me."
--
-- C3. CAB1L — mark as UNRESOLVED/inactive pending NSM confirmation
--     Source: ERP salgrpname='Waterford Cab Sauv 1.5L' (NOT 1 Liter — the SKU
--     code 'CAB1L' was ambiguous. Source says 1.5L Magnum format.)
--     NSM to confirm if Waterford produces Cabernet Sauvignon 1.5L Magnum.
--     Until confirmed: deactivate alias, mark SKU inactive, rows → PENDING.
--
-- C4. WCB001 (Waterford Chenin Blanc) — confirm it is genuinely NEW, not duplicate
--     Pre-Sprint-2.5 database had NO Waterford Chenin Blanc / OVP Chenin Blanc.
--     WCB001 is correctly a new addition. HOWEVER: remove unconfirmed ASPs.
--     NSM to approve the ASP when ready.
--
-- C5. MCC001 (Waterford Cap Classique) — confirm it is genuinely NEW, not duplicate
--     Pre-Sprint-2.5 database had NO Cap Classique / MCC.
--     MCC001 is correctly a new addition. Remove unconfirmed ASPs.
--
-- NOTE ON KOVE/CAMPSBAY, DIST0002, LEGACY01:
--     These three clients remain as created in migration 006.
--     NSM confirmed each in the previous session.
--     Not affected by these corrections.
-- =============================================================================

-- ────────────────────────────────────────────────────────────────────────────
-- C1. NGF ERP CONSOLIDATION
-- NORMANPA must be treated as a NGF warehouse alias (sell-in to NGF),
-- not a standalone commercial client.
-- ────────────────────────────────────────────────────────────────────────────

-- C1a. Add NORMANPA to NGF distributor's ERP debtor codes array
--      This ensures the ERP connector classifies NORMANPA rows as DISTRIBUTOR_SELL_IN
-- Sprint 6: product_skus.notes was missing from 001 schema — add idempotently
ALTER TABLE product_skus ADD COLUMN IF NOT EXISTS notes TEXT;


UPDATE distributors
SET erp_debtor_codes = array_append(erp_debtor_codes, 'NORMANPA')
WHERE distributor_code = 'NGF'
  AND NOT ('NORMANPA' = ANY(erp_debtor_codes));

-- C1b. Remap NORMANPA source alias from cl-ngf-paarden-eiland → cl-ngf-dist
--      Preserves the ERP debtor code and name in provenance (source_code + source_name kept)
UPDATE client_source_aliases
SET client_id = (SELECT id FROM clients WHERE id = md5('cl-ngf-dist')::uuid),
    alias_notes = 'CORRECTED: NORMANPA is an NGF warehouse location. '
               || 'Maps to NGF distributor entity (cl-ngf-dist), not a standalone commercial client. '
               || 'Original debtor code NORMANPA preserved for provenance. '
               || 'Transaction type must be DISTRIBUTOR_SELL_IN.'
WHERE source_code = 'NORMANPA'
  AND source_id = (SELECT id FROM data_sources WHERE source_code = 'ERP_EXPORT');

-- C1c. Soft-delete cl-ngf-paarden-eiland
--      Do NOT hard-delete — preserve the record with is_deleted=TRUE for audit trail.
--      This records that the decision was considered and rejected.
UPDATE clients
SET is_deleted = TRUE,
    deleted_at = NOW(),
    notes = 'DELETED: NORMANPA/NGF Paarden Eiland is an NGF warehouse location, '
          || 'not a separate commercial client. NSM instruction 2026-09-10: '
          || 'consolidate all NGF ERP debtors under cl-ngf-dist. '
          || 'NORMANPA alias remapped to cl-ngf-dist.'
WHERE id = md5('cl-ngf-paarden-eiland')::uuid;

-- C1d. Verify NGF distributor now includes NORMANPA
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM distributors
    WHERE distributor_code = 'NGF'
      AND 'NORMANPA' = ANY(erp_debtor_codes)
  ) THEN
    RAISE EXCEPTION 'C1 failed: NORMANPA not added to NGF distributor erp_debtor_codes';
  END IF;
  RAISE NOTICE 'C1 OK: NGF distributor erp_debtor_codes now includes NORMANPA';
END $$;

-- ────────────────────────────────────────────────────────────────────────────
-- C2. REMOVE ALL UNCONFIRMED/INVENTED ASP VALUES
-- ASPs require approved Waterford source or NSM confirmation.
-- The three ASPs added in migration 006 with is_approved=FALSE are removed.
-- ────────────────────────────────────────────────────────────────────────────

DELETE FROM asp_versions
WHERE is_approved = FALSE
  AND source_document ILIKE '%Estimated%'
  AND created_by = 'system'
  AND id IN (
    md5('asp-wcb-fy27')::uuid, md5('asp-wcb-fy26')::uuid,
    md5('asp-mcc-fy27')::uuid, md5('asp-mcc-fy26')::uuid,
    md5('asp-cab1l-fy27')::uuid, md5('asp-cab1l-fy26')::uuid
  );

DO $$
DECLARE removed int;
BEGIN
  -- Fixed: asp_versions uses product_sku_id not sku_code (Sprint 6 remediation)
  SELECT COUNT(*) INTO removed FROM asp_versions av
  JOIN product_skus ps ON ps.id = av.product_sku_id
  WHERE av.is_approved = FALSE AND ps.sku_code IN ('WCB001','MCC001');
  RAISE NOTICE 'C2: Counted unconfirmed ASPs: %', removed;
END $$;

-- ────────────────────────────────────────────────────────────────────────────
-- C3. CAB1L — DEACTIVATE PENDING NSM CONFIRMATION
-- Source description: 'Waterford Cab Sauv 1.5L' (1.5 Litre Magnum, not 1 Liter)
-- NSM to confirm whether Waterford produces Cabernet Sauvignon 1.5L Magnum.
-- Until confirmed: deactivate SKU + remove product alias → rows become PENDING.
-- ────────────────────────────────────────────────────────────────────────────

-- Deactivate CAB1L SKU
UPDATE product_skus
SET is_active = FALSE,
    notes = 'UNRESOLVED: ERP source description is "Waterford Cab Sauv 1.5L" (1.5L Magnum). '
          || 'SKU code CAB1L was ambiguous (read as "1 Liter" by NSM). '
          || 'NSM to confirm: does Waterford produce Cabernet Sauvignon in 1.5L Magnum format? '
          || 'Evidence: 21 ERP rows, 216 bottles, R108,684 confirmed revenue FY2026. '
          || 'Pricing R516/btl = 2.03× CAB001 750ml, consistent with 1.5L premium. '
          || 'Activate this SKU when NSM confirms.'
WHERE sku_code = 'CAB1L';

-- Remove the ERP product alias for CAB1L so those rows become UNKNOWN_PRODUCT on re-import
DELETE FROM product_source_aliases
WHERE product_sku_id = (SELECT id FROM product_skus WHERE sku_code = 'CAB1L');

-- Alternative safe delete (handles FK properly)
DELETE FROM product_source_aliases
WHERE product_sku_id = (SELECT id FROM product_skus WHERE sku_code = 'CAB1L');

DO $$
BEGIN
  RAISE NOTICE 'C3: CAB1L deactivated. "Waterford Cab Sauv 1.5L" source rows will become UNKNOWN_PRODUCT on re-import. Held for NSM confirmation.';
END $$;

-- ────────────────────────────────────────────────────────────────────────────
-- C4. WCB001 — CONFIRM IT IS NEW (not a duplicate)
-- Add note confirming pre-Sprint-2.5 product list did NOT include Chenin Blanc.
-- Product structure remains; ASPs already removed by C2.
-- ────────────────────────────────────────────────────────────────────────────

UPDATE products
SET notes = 'ADDED Sprint 2.5 (migration 006). '
          || 'Pre-Sprint-2.5 database had NO Waterford Chenin Blanc canonical product. '
          || 'ERP source: salgrpname="Waterford Chenin Blanc", 46 rows, 966 btls FY2026, confirmed revenue. '
          || 'NSM confirmed this is the Old Vine Project Chenin Blanc. '
          || 'This is NOT a duplicate — PSC001 is Pecan Stream Chenin Blanc (different brand/product). '
          || 'ASP to be confirmed by NSM before estimated revenue calculation is enabled.'
WHERE product_code = 'WCB';

-- ────────────────────────────────────────────────────────────────────────────
-- C5. MCC001 — CONFIRM IT IS NEW (not a duplicate)
-- Add note confirming pre-Sprint-2.5 product list did NOT include Cap Classique.
-- Product structure remains; ASPs already removed by C2.
-- ────────────────────────────────────────────────────────────────────────────

UPDATE products
SET notes = 'ADDED Sprint 2.5 (migration 006). '
          || 'Pre-Sprint-2.5 database had NO Waterford Cap Classique canonical product. '
          || 'ERP source: salgrpname="Special - Waterford Bubbly", 11 rows, 72 btls FY2026, confirmed revenue. '
          || 'NSM confirmed: our only bubbly, not discontinued. Also called Waterford MCC or Cap Classique. '
          || 'This is NOT a duplicate of any Sprint 1 product. '
          || 'ASP to be confirmed by NSM before estimated revenue calculation is enabled.'
WHERE product_code = 'MCC';

-- ────────────────────────────────────────────────────────────────────────────
-- VERIFICATION
-- ────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  ngf_codes text[];
  asp_count int;
  cab1l_active bool;
BEGIN
  SELECT erp_debtor_codes INTO ngf_codes FROM distributors WHERE distributor_code='NGF';
  SELECT COUNT(*) INTO asp_count FROM asp_versions
    WHERE product_sku_id IN (
      SELECT id FROM product_skus WHERE sku_code IN ('WCB001','MCC001','CAB1L')
    );
  SELECT is_active INTO cab1l_active FROM product_skus WHERE sku_code='CAB1L';

  RAISE NOTICE '=== Migration 007 Verification ===';
  RAISE NOTICE 'NGF ERP debtor codes: %', ngf_codes;
  RAISE NOTICE 'ASPs remaining for WCB/MCC/CAB1L: % (should be 0)', asp_count;
  RAISE NOTICE 'CAB1L is_active: % (should be FALSE)', cab1l_active;
  RAISE NOTICE 'cl-ngf-paarden-eiland is_deleted: %',
    (SELECT is_deleted FROM clients WHERE id=md5('cl-ngf-paarden-eiland')::uuid);
END $$;
