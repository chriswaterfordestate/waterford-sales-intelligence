-- =============================================================================
-- MIGRATION 002: Reference Data Seed
-- Financial years, periods, channels, territories, distributors, data sources
-- These are structural reference records — they never change after initial load.
-- =============================================================================

-- ── Financial Years ───────────────────────────────────────────────────────────
INSERT INTO financial_years (id, year_label, year_number, start_date, end_date, is_current, is_history, created_by)
VALUES
  ('9ac5dd4b-aa24-7e13-2d06-3c410b6a70e7', 'FY2026', 2026, '2025-07-01', '2026-06-30', FALSE, TRUE, 'system'),
  ('711c05f1-fb11-13d3-71e6-5c7c926e5dfe', 'FY2027', 2027, '2026-07-01', '2027-06-30', TRUE,  FALSE, 'system')
ON CONFLICT DO NOTHING;

-- ── Financial Periods (24 rows — 12 per FY) ───────────────────────────────────
-- FY2026: July 2025 (M1) through June 2026 (M12)
INSERT INTO financial_periods (id, financial_year_id, period_number, period_name, calendar_month, calendar_year, start_date, end_date, is_closed)
VALUES
  ('6fd451ab-2242-bdcc-2c3a-07fc88a5e1bf', '9ac5dd4b-aa24-7e13-2d06-3c410b6a70e7', 1,  'July 2025',      7,  2025, '2025-07-01', '2025-07-31', TRUE),
  ('9819e124-409c-3159-7925-57de6c08c325', '9ac5dd4b-aa24-7e13-2d06-3c410b6a70e7', 2,  'August 2025',    8,  2025, '2025-08-01', '2025-08-31', TRUE),
  ('69442b08-d3fa-38ec-8bc6-a4bcd6076017', '9ac5dd4b-aa24-7e13-2d06-3c410b6a70e7', 3,  'September 2025', 9,  2025, '2025-09-01', '2025-09-30', TRUE),
  ('db79bba1-27bb-40af-b21b-1c1d1d3ac1c9', '9ac5dd4b-aa24-7e13-2d06-3c410b6a70e7', 4,  'October 2025',   10, 2025, '2025-10-01', '2025-10-31', TRUE),
  ('33a79f38-6c52-d0d3-d4d6-e01ed1208fd8', '9ac5dd4b-aa24-7e13-2d06-3c410b6a70e7', 5,  'November 2025',  11, 2025, '2025-11-01', '2025-11-30', TRUE),
  ('1bbdd150-da8f-8faf-6769-fba03b5ddab2', '9ac5dd4b-aa24-7e13-2d06-3c410b6a70e7', 6,  'December 2025',  12, 2025, '2025-12-01', '2025-12-31', TRUE),
  ('83d842e5-7d78-118a-c3bf-60ab99b87231', '9ac5dd4b-aa24-7e13-2d06-3c410b6a70e7', 7,  'January 2026',   1,  2026, '2026-01-01', '2026-01-31', TRUE),
  ('314ed498-fdce-f539-c8b5-a1b17c2e415f', '9ac5dd4b-aa24-7e13-2d06-3c410b6a70e7', 8,  'February 2026',  2,  2026, '2026-02-01', '2026-02-28', TRUE),
  ('6989e460-5d1c-1125-2fe2-466f1de05a27', '9ac5dd4b-aa24-7e13-2d06-3c410b6a70e7', 9,  'March 2026',     3,  2026, '2026-03-01', '2026-03-31', TRUE),
  ('651f95b3-73ae-bad6-0f3c-e20a0cbb7908', '9ac5dd4b-aa24-7e13-2d06-3c410b6a70e7', 10, 'April 2026',     4,  2026, '2026-04-01', '2026-04-30', TRUE),
  ('71218f3b-42b5-449b-90fa-ede3f9773054', '9ac5dd4b-aa24-7e13-2d06-3c410b6a70e7', 11, 'May 2026',       5,  2026, '2026-05-01', '2026-05-31', TRUE),
  ('8f790c84-41ab-93c4-019b-cc78c223481c', '9ac5dd4b-aa24-7e13-2d06-3c410b6a70e7', 12, 'June 2026',      6,  2026, '2026-06-01', '2026-06-30', TRUE)
ON CONFLICT DO NOTHING;

-- FY2027: July 2026 (M1) through June 2027 (M12)
INSERT INTO financial_periods (id, financial_year_id, period_number, period_name, calendar_month, calendar_year, start_date, end_date, is_closed)
VALUES
  ('b62e09e7-1dcf-871d-f751-61d3211ff48a', '711c05f1-fb11-13d3-71e6-5c7c926e5dfe', 1,  'July 2026',      7,  2026, '2026-07-01', '2026-07-31', TRUE),
  ('ff33766f-1d50-e169-67e3-316053193007', '711c05f1-fb11-13d3-71e6-5c7c926e5dfe', 2,  'August 2026',    8,  2026, '2026-08-01', '2026-08-31', TRUE),
  ('16ddf8df-0c89-ff6e-bb30-b286b3f44cb4', '711c05f1-fb11-13d3-71e6-5c7c926e5dfe', 3,  'September 2026', 9,  2026, '2026-09-01', '2026-09-30', FALSE),
  ('3ac5bc1e-ded9-2ba3-35a3-bf7444e982f0', '711c05f1-fb11-13d3-71e6-5c7c926e5dfe', 4,  'October 2026',   10, 2026, '2026-10-01', '2026-10-31', FALSE),
  ('4077ecc8-43c2-d165-4c88-d08a65e056a7', '711c05f1-fb11-13d3-71e6-5c7c926e5dfe', 5,  'November 2026',  11, 2026, '2026-11-01', '2026-11-30', FALSE),
  ('9a5e2591-8580-bd74-2f56-fe28c9ba889d', '711c05f1-fb11-13d3-71e6-5c7c926e5dfe', 6,  'December 2026',  12, 2026, '2026-12-01', '2026-12-31', FALSE),
  ('c8765c74-e9ee-bfaa-2cd2-7e9c485f7dd7', '711c05f1-fb11-13d3-71e6-5c7c926e5dfe', 7,  'January 2027',   1,  2027, '2027-01-01', '2027-01-31', FALSE),
  ('cadeb2a8-1dde-932f-9383-0c5166c815b6', '711c05f1-fb11-13d3-71e6-5c7c926e5dfe', 8,  'February 2027',  2,  2027, '2027-02-01', '2027-02-28', FALSE),
  ('d155a98a-f56e-08e2-2983-822d10158755', '711c05f1-fb11-13d3-71e6-5c7c926e5dfe', 9,  'March 2027',     3,  2027, '2027-03-01', '2027-03-31', FALSE),
  ('c11f5c0b-ab05-212d-c161-48e7dca2a35c', '711c05f1-fb11-13d3-71e6-5c7c926e5dfe', 10, 'April 2027',     4,  2027, '2027-04-01', '2027-04-30', FALSE),
  ('95a34638-785e-68d6-bf0c-e76f26d86b02', '711c05f1-fb11-13d3-71e6-5c7c926e5dfe', 11, 'May 2027',       5,  2027, '2027-05-01', '2027-05-31', FALSE),
  ('4b2a6adc-eb6f-02b5-5a65-4d41494c018b', '711c05f1-fb11-13d3-71e6-5c7c926e5dfe', 12, 'June 2027',      6,  2027, '2027-06-01', '2027-06-30', FALSE)
ON CONFLICT DO NOTHING;

-- ── Channels ──────────────────────────────────────────────────────────────────
INSERT INTO channels (id, channel_code, channel_name, is_domestic, is_active)
VALUES
  ('c83cf810-5c5a-4ae9-9bc6-fda1e3592b98', 'DIRECT_ERP',    'Direct ERP (Waterford direct)',    TRUE,  TRUE),
  ('e567b0b8-8b95-aa2c-9a58-857216b2ca0a', 'NGF',           'Norman Goodfellows / NGF',         TRUE,  TRUE),
  ('9dc768e1-cd97-9208-54c6-807daf32bea8', 'VDP_GAU',       'VDP Prestige Gauteng',             TRUE,  TRUE),
  ('adbc1ae4-0a3b-935e-8b45-27449f47da2f', 'DISTRILIQ_CPT', 'Distriliq Cape Town',              TRUE,  TRUE),
  ('0c478abc-5906-a7ca-234f-53c2247f4465', 'DISTRI_GEORGE', 'Distri George (Garden Route)',     TRUE,  TRUE),
  ('37cb578d-f168-0526-0cb7-e36f68dc479f', 'DTC',           'Direct-to-Consumer (Cellar Door)', TRUE,  TRUE),
  ('edf7c2dc-5c21-06a0-6b47-cc0caafc3194', 'EXPORT',        'Export (foreign buyers)',          FALSE, TRUE),
  ('177e096c-06ba-9a91-d0b0-30615c0390b2', 'NATIONAL',      'National / Multi-territory',       TRUE,  TRUE)
ON CONFLICT DO NOTHING;

-- ── Territories ───────────────────────────────────────────────────────────────
INSERT INTO territories (id, territory_code, territory_name, is_domestic, is_active)
VALUES
  ('abbf9648-42ab-9760-61ff-f3ebaeaa4602', 'GAU',          'Gauteng',                    TRUE,  TRUE),
  ('3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'WC_CPT',       'Western Cape — Cape Town',   TRUE,  TRUE),
  ('dd7c1549-2531-5b15-d389-9e7ead901178', 'WC_STELB',     'Western Cape — Stellenbosch',TRUE,  TRUE),
  ('12a4b757-a731-7edc-f81b-182da9fd1ba7', 'GARDEN_ROUTE', 'Garden Route',               TRUE,  TRUE),
  ('c1285dfb-4347-2b2c-ae0f-caa699166049', 'KZN',          'KwaZulu-Natal',              TRUE,  TRUE),
  ('55f7332d-1552-5a9e-4f3b-56b8c260f1a1', 'NATIONAL',     'National / Multi-territory', TRUE,  TRUE),
  ('ae6f0fb3-9e55-1cd0-3cf3-920083df1d36', 'EXPORT',       'Export',                     FALSE, TRUE)
ON CONFLICT DO NOTHING;

-- ── Distributors ──────────────────────────────────────────────────────────────
INSERT INTO distributors (id, distributor_code, distributor_name, erp_debtor_codes, erp_primary_debtor, territory_id, regions_covered, is_active)
VALUES
  ('acc21c78-f6af-4cb4-eb3c-8571e42e9752', 'NGF',
   'Norman Goodfellows & Franchisees',
   ARRAY['NORM0002','NORMGF'], 'NORM0002',
   '55f7332d-1552-5a9e-4f3b-56b8c260f1a1',
   ARRAY['CPT','JHB','KZN'], TRUE),

  ('9ab2ddd1-7a50-841a-86d4-41796d6269d1', 'VDP_GAU',
   'VDP Prestige Distributors Gauteng',
   ARRAY['VDPGAU01'], 'VDPGAU01',
   'abbf9648-42ab-9760-61ff-f3ebaeaa4602',
   ARRAY['GAU'], TRUE),

  ('f394bb9e-0088-7e37-834d-9e202b3bf1cd', 'DISTRILIQ_CPT',
   'Distriliq Cape Town',
   ARRAY['DISTRILIQ01'], 'DISTRILIQ01',
   '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2',
   ARRAY['CPT'], TRUE),

  ('959725b7-02c5-a620-f521-9c9ba5f87049', 'DISTRI_GEORGE',
   'Distri George (Pty) Ltd',
   ARRAY['DISTRIGEO01'], 'DISTRIGEO01',
   '12a4b757-a731-7edc-f81b-182da9fd1ba7',
   ARRAY['GEORGE','GR'], TRUE)
ON CONFLICT DO NOTHING;

-- ── Data Sources ──────────────────────────────────────────────────────────────
INSERT INTO data_sources (id, source_code, source_name, distributor_id, source_type, transaction_types_produced, default_region, file_format, expected_frequency, is_active)
VALUES
  ('d02b430a-f424-4930-e449-9c4fe3af0063', 'ERP_EXPORT',
   'EzyWine ERP Direct Export (CSV)',
   NULL, 'ERP',
   ARRAY['DIRECT_SALE','DISTRIBUTOR_SELL_IN','DTC_SALE','EXPORT_SALE']::transaction_type_enum[],
   'ALL', 'CSV', 'MONTHLY', TRUE),

  ('cf399ce6-ab61-b009-fd0a-0d39745bfd01', 'NGF_MONTHLY',
   'NGF Monthly Sell-Through Report (Excel)',
   'acc21c78-f6af-4cb4-eb3c-8571e42e9752', 'DISTRIBUTOR_REPORT',
   ARRAY['DISTRIBUTOR_SELL_THROUGH']::transaction_type_enum[],
   NULL, 'EXCEL', 'MONTHLY', TRUE),

  ('040f86eb-f98c-b847-46fe-6774b658a6ee', 'NGF_SALESOUT',
   'NGF SalesOut Transaction File (Excel 4REP tab)',
   'acc21c78-f6af-4cb4-eb3c-8571e42e9752', 'DISTRIBUTOR_REPORT',
   ARRAY['DISTRIBUTOR_SELL_THROUGH']::transaction_type_enum[],
   'CPT', 'EXCEL', 'ANNUAL', TRUE),

  ('7cfe80f8-cdc3-c569-869a-fbe52d10cd5c', 'VDP_WEEKLY_PDF',
   'VDP Prestige Gauteng Weekly PDF (cumulative)',
   '9ab2ddd1-7a50-841a-86d4-41796d6269d1', 'DISTRIBUTOR_REPORT',
   ARRAY['DISTRIBUTOR_SELL_THROUGH']::transaction_type_enum[],
   'GAU', 'PDF', 'WEEKLY', TRUE),

  ('07e9366b-1e6e-7352-3533-00a8117a0ea6', 'VDP_MONTHLY_EXCEL',
   'VDP Prestige Gauteng Monthly Excel (Sales Per Customer Per SKU)',
   '9ab2ddd1-7a50-841a-86d4-41796d6269d1', 'DISTRIBUTOR_REPORT',
   ARRAY['DISTRIBUTOR_SELL_THROUGH']::transaction_type_enum[],
   'GAU', 'EXCEL', 'MONTHLY', TRUE),

  ('f86a696e-4143-9a84-7352-b39bb553ebf7', 'DISTRILIQ_CPT',
   'Distriliq CPT Client Report (Excel — Client History tab)',
   'f394bb9e-0088-7e37-834d-9e202b3bf1cd', 'DISTRIBUTOR_REPORT',
   ARRAY['DISTRIBUTOR_SELL_THROUGH']::transaction_type_enum[],
   'CPT', 'EXCEL', 'ANNUAL', TRUE),

  ('ea71ca0c-a8d9-26ce-c202-854c0e4927c5', 'DISTRI_GEORGE',
   'Distri George Monthly Excel',
   '959725b7-02c5-a620-f521-9c9ba5f87049', 'DISTRIBUTOR_REPORT',
   ARRAY['DISTRIBUTOR_SELL_THROUGH']::transaction_type_enum[],
   'GEORGE', 'EXCEL', 'MONTHLY', TRUE),

  ('40951c31-1dbc-7506-a1a7-60af2da0e5f1', 'NGF_COMBINED_FY27',
   'NGF Combined FY27 System File (Jul-Aug 26)',
   'acc21c78-f6af-4cb4-eb3c-8571e42e9752', 'DISTRIBUTOR_REPORT',
   ARRAY['DISTRIBUTOR_SELL_THROUGH']::transaction_type_enum[],
   NULL, 'EXCEL', 'AD_HOC', TRUE)
ON CONFLICT DO NOTHING;
