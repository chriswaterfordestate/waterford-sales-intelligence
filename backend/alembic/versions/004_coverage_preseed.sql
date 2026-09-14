-- =============================================================================
-- MIGRATION 004: Data Coverage Pre-Seed
-- Pre-populate data_coverage with known status BEFORE any data imports.
-- This ensures YoY calculations return N/A correctly from day one.
-- =============================================================================

DO $$
DECLARE
  src_ngf_monthly   UUID := 'cf399ce6-ab61-b009-fd0a-0d39745bfd01';
  src_ngf_salesout  UUID := '040f86eb-f98c-b847-46fe-6774b658a6ee';
  src_vdp_weekly    UUID := '7cfe80f8-cdc3-c569-869a-fbe52d10cd5c';
  src_vdp_monthly   UUID := '07e9366b-1e6e-7352-3533-00a8117a0ea6';
  src_distriliq_cpt UUID := 'f86a696e-4143-9a84-7352-b39bb553ebf7';
  src_distri_george UUID := 'ea71ca0c-a8d9-26ce-c202-854c0e4927c5';
  src_erp           UUID := 'd02b430a-f424-4930-e449-9c4fe3af0063';
  fp                RECORD;
BEGIN

  -- ── NGF MONTHLY FY26 ───────────────────────────────────────────────────────
  -- July 2025 (fp-fy26-01) = MISSING for all regions (WaterfordMonthlyReport starts Aug 25)
  -- August 2025 through June 2026 = MISSING initially (becomes COVERED when imported)
  FOR fp IN SELECT id FROM financial_periods WHERE financial_year_id = '9ac5dd4b-aa24-7e13-2d06-3c410b6a70e7' LOOP
    INSERT INTO data_coverage (source_id, region, financial_period_id, coverage_status, notes)
    VALUES
      (src_ngf_monthly, 'CPT', fp.id,
       CASE WHEN fp.id = '6fd451ab-2242-bdcc-2c3a-07fc88a5e1bf' THEN 'MISSING'::coverage_status_enum
            ELSE 'MISSING'::coverage_status_enum END,
       CASE WHEN fp.id = '6fd451ab-2242-bdcc-2c3a-07fc88a5e1bf' THEN 'WaterfordMonthlyReport starts Aug 25. Jul 25 CPT in NGF_SALESOUT instead.'
            ELSE 'Not yet imported' END),
      (src_ngf_monthly, 'JHB', fp.id,
       CASE WHEN fp.id = '6fd451ab-2242-bdcc-2c3a-07fc88a5e1bf' THEN 'MISSING'::coverage_status_enum
            ELSE 'MISSING'::coverage_status_enum END,
       CASE WHEN fp.id = '6fd451ab-2242-bdcc-2c3a-07fc88a5e1bf' THEN 'July 2025 JHB NGF sell-through data does not exist in any file. Baseline unavailable.'
            ELSE 'Not yet imported' END),
      (src_ngf_monthly, 'KZN', fp.id,
       CASE WHEN fp.id = '6fd451ab-2242-bdcc-2c3a-07fc88a5e1bf' THEN 'MISSING'::coverage_status_enum
            ELSE 'MISSING'::coverage_status_enum END,
       CASE WHEN fp.id = '6fd451ab-2242-bdcc-2c3a-07fc88a5e1bf' THEN 'July 2025 KZN NGF sell-through data does not exist in any file. Baseline unavailable.'
            ELSE 'Not yet imported' END);
  END LOOP;

  -- ── NGF SALESOUT FY26 ──────────────────────────────────────────────────────
  -- CPT coverage: Jul 25 is MISSING initially (will become COVERED when SalesOut H1 imported)
  -- Only CPT region — JHB and KZN not covered by SalesOut files
  FOR fp IN SELECT id FROM financial_periods WHERE financial_year_id = '9ac5dd4b-aa24-7e13-2d06-3c410b6a70e7' LOOP
    INSERT INTO data_coverage (source_id, region, financial_period_id, coverage_status, notes)
    VALUES
      (src_ngf_salesout, 'CPT', fp.id, 'MISSING'::coverage_status_enum, 'Not yet imported. Will become COVERED when SalesOut files loaded.');
  END LOOP;

  -- ── VDP GAUTENG FY26 ───────────────────────────────────────────────────────
  -- VDP was NOT active as a Waterford channel in FY2026 = NOT_APPLICABLE for all 12 periods
  FOR fp IN SELECT id FROM financial_periods WHERE financial_year_id = '9ac5dd4b-aa24-7e13-2d06-3c410b6a70e7' LOOP
    INSERT INTO data_coverage (source_id, region, financial_period_id, coverage_status, notes)
    VALUES
      (src_vdp_weekly,  'GAU', fp.id, 'NOT_APPLICABLE'::coverage_status_enum, 'VDP Prestige Gauteng was not active as a Waterford channel in FY2026.'),
      (src_vdp_monthly, 'GAU', fp.id, 'NOT_APPLICABLE'::coverage_status_enum, 'VDP Prestige Gauteng was not active as a Waterford channel in FY2026.');
  END LOOP;

  -- ── ERP FY26 and FY27 ──────────────────────────────────────────────────────
  -- All periods initially MISSING — becomes COVERED when ERP CSV imported
  FOR fp IN SELECT id FROM financial_periods WHERE financial_year_id IN (
    '9ac5dd4b-aa24-7e13-2d06-3c410b6a70e7',
    '711c05f1-fb11-13d3-71e6-5c7c926e5dfe'
  ) LOOP
    INSERT INTO data_coverage (source_id, region, financial_period_id, coverage_status, notes)
    VALUES
      (src_erp, 'ALL', fp.id, 'MISSING'::coverage_status_enum, 'Not yet imported');
  END LOOP;

  -- ── VDP FY27 ───────────────────────────────────────────────────────────────
  FOR fp IN SELECT id FROM financial_periods WHERE financial_year_id = '711c05f1-fb11-13d3-71e6-5c7c926e5dfe' LOOP
    INSERT INTO data_coverage (source_id, region, financial_period_id, coverage_status, notes)
    VALUES
      (src_vdp_weekly,  'GAU', fp.id, 'MISSING'::coverage_status_enum, 'Not yet imported'),
      (src_vdp_monthly, 'GAU', fp.id, 'MISSING'::coverage_status_enum, 'Not yet imported');
  END LOOP;

  -- ── NGF FY27 ───────────────────────────────────────────────────────────────
  FOR fp IN SELECT id FROM financial_periods WHERE financial_year_id = '711c05f1-fb11-13d3-71e6-5c7c926e5dfe' LOOP
    INSERT INTO data_coverage (source_id, region, financial_period_id, coverage_status, notes)
    VALUES
      (src_ngf_monthly, 'CPT', fp.id, 'MISSING'::coverage_status_enum, 'Not yet imported'),
      (src_ngf_monthly, 'JHB', fp.id, 'MISSING'::coverage_status_enum, 'Not yet imported'),
      (src_ngf_monthly, 'KZN', fp.id, 'MISSING'::coverage_status_enum, 'Not yet imported');
  END LOOP;

  RAISE NOTICE 'Coverage pre-seed complete. All periods initialised as MISSING or NOT_APPLICABLE.';
END $$;
