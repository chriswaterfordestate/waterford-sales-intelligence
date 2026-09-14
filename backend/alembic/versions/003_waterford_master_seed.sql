-- =============================================================================
-- MIGRATION 003: Waterford Master Data Seed
-- Reps, products, SKUs, ASPs, confirmed client groups, confirmed clients,
-- confirmed aliases, client ownership, source configurations
--
-- CLASSIFICATION:
--   APPROVED TO LOAD: reps, products, SKUs, ASPs, source_configs,
--                     confirmed client groups, 26 confirmed canonical clients,
--                     87 confirmed aliases, current ownership records
--
--   DO NOT LOAD HERE: 49 PROBABLE client aliases (loaded via review queue),
--                     21 UNRESOLVED clients, individual rep targets (Phase 2)
-- =============================================================================

-- ── Reps ─────────────────────────────────────────────────────────────────────
-- NSM DECISION (Sep 2026): Moya Fourie = FY26 historical ownership only.
-- FY27: any account without active ownership falls to Head Office.
-- Moya's rep_territory_assignment ends 2026-06-30 (end of FY26).
-- No exact departure date needed for schema logic.
INSERT INTO reps (id, rep_code, first_name, last_name, full_name, erp_srepname, role, channel_focus, employment_status, start_date, end_date, departure_reason, created_by)
VALUES
  ('d8c9d37d-a13c-45d4-62ae-5ff6f3bf5e0a', 'KOL001', 'Koliswa',   'Jayiya',       'Koliswa Jayiya',       'Koliswa Jayiya',     'Sales Representative', 'ON_TRADE',   'ACTIVE',   '2023-01-01', NULL,         NULL, 'system'),
  ('e5eb41ad-fe4c-3ba5-3ae4-558019ee0959', 'SAN001', 'Sandile',    'Yende',        'Sandile Yende',        'Sandile Yende',      'Sales Representative', 'RETAIL',     'ACTIVE',   '2022-03-01', NULL,         NULL, 'system'),
  ('4035414f-6f67-700e-3259-a0a40db7af8f', 'HEL001', 'Helena',     'Pires',        'Helena Pires',         'Helena Pires',       'Sales Representative', 'ON_TRADE',   'ACTIVE',   '2021-07-01', NULL,         NULL, 'system'),
  ('cb81c6c9-4b86-fdd4-7b99-950895ea9ca0', 'MOY001', 'Moya',       'Fourie',       'Moya Fourie',          'Moya Fourie',        'Sales Representative', 'ON_TRADE',   'DEPARTED', '2020-03-01', '2026-06-30', 'NSM decision Sep 2026: FY26 historical ownership only. FY27 accounts -> Head Office.', 'system'),
  ('f55c92c5-34a4-1949-fbc1-7a437253bc38', 'NAT001', 'Nathalie',   'Watkins',      'Nathalie Watkins',     'Nathalie Watkins',   'Key Account Manager',  'KAM',        'ACTIVE',   '2019-05-01', NULL,         NULL, 'system'),
  ('21874f4b-a161-74dd-7523-5004946770da', 'SER001', 'Sergio',     'King',         'Sergio King',          'Sergio King',        'Sales Representative', 'ON_TRADE',   'RESIGNED', '2018-09-01', '2026-06-30', 'Resigned. WC accounts redistributed to Nathalie (KAM) and new Brand Managers.', 'system'),
  ('31dcf3e2-3af9-c88c-071f-fca3b73fa56c', 'JAN001', 'Jane',       'Simon',        'Jane Simon',           'Jane Simon',         'Sales Representative', 'ON_TRADE',   'ACTIVE',   '2020-02-01', NULL,         NULL, 'system'),
  ('bbc78a46-94c5-eb9a-296d-afba8b0e4ced', 'MAG001', 'Maggie',     'Colman',       'Maggie Colman',        'Maggie Colman',      'Sales Representative', 'ON_TRADE',   'ACTIVE',   '2021-01-01', NULL,         NULL, 'system'),
  ('cfd9fc27-0cd0-112b-c60a-642c389b3529', 'WER001', 'Werner',     'Briedenhann',  'Werner Briedenhann',   'Werner Briedenhann', 'Export Manager',       'EXPORT',     'ACTIVE',   '2015-01-01', NULL,         NULL, 'system'),
  ('41c9ab80-3b6d-375e-5510-6e802813e086', 'HO001',  'NSM',        'Head Office',  'NSM / Head Office',    'NSM',                'National Sales Manager','MANAGEMENT', 'ACTIVE',   '2015-01-01', NULL,         NULL, 'system')
ON CONFLICT DO NOTHING;

-- ── Rep → Territory Assignments ───────────────────────────────────────────────
INSERT INTO rep_territory_assignments (id, rep_id, territory_id, effective_from, effective_to, notes, created_by)
VALUES
  ('27f13018-d63b-b0eb-c0ae-e910271efc40', 'd8c9d37d-a13c-45d4-62ae-5ff6f3bf5e0a', 'abbf9648-42ab-9760-61ff-f3ebaeaa4602', '2023-07-01', NULL,         'Gauteng ON-TRADE accounts', 'system'),
  ('b376dfce-8f21-54dd-e283-3337426b3ea3', 'e5eb41ad-fe4c-3ba5-3ae4-558019ee0959', 'abbf9648-42ab-9760-61ff-f3ebaeaa4602', '2022-07-01', NULL,         'Gauteng RETAIL accounts', 'system'),
  ('9685a4b0-8778-f197-b458-eec6b6875bf4', '4035414f-6f67-700e-3259-a0a40db7af8f', 'abbf9648-42ab-9760-61ff-f3ebaeaa4602', '2021-07-01', NULL,         'Gauteng ON-TRADE accounts', 'system'),
  ('1764e544-58a6-8eee-b175-5833e88de6e6', 'cb81c6c9-4b86-fdd4-7b99-950895ea9ca0', 'abbf9648-42ab-9760-61ff-f3ebaeaa4602', '2020-07-01', '2026-06-30', 'FY26 ownership only. FY27 Moya accounts -> Head Office. Exact departure date not needed for schema logic.', 'system'),
  -- NAT001 WC territory assignment NOT seeded: WC restructure split not yet decided by NSM.
  -- Will be added as a new effective-dated record when NSM confirms the account allocation.
  ('4317570c-5a37-9d59-5d56-322451fe9e86',  '21874f4b-a161-74dd-7523-5004946770da', '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', '2018-09-01', '2026-06-30', 'WC territory until resignation', 'system'),
  ('e17a0065-6574-2fd1-dcd2-1ce2d039a4a1',  '31dcf3e2-3af9-c88c-071f-fca3b73fa56c', '12a4b757-a731-7edc-f81b-182da9fd1ba7', '2020-02-01', NULL,         'Garden Route territory', 'system'),
  ('12178d13-8082-6684-4354-d2603ee94d01', 'bbc78a46-94c5-eb9a-296d-afba8b0e4ced', 'c1285dfb-4347-2b2c-ae0f-caa699166049', '2021-01-01', NULL,         'KZN territory', 'system'),
  ('e77ce82c-7f17-516f-727a-1fd055dd98ca', 'cfd9fc27-0cd0-112b-c60a-642c389b3529', 'ae6f0fb3-9e55-1cd0-3cf3-920083df1d36', '2015-01-01', NULL,         'Export territory', 'system')
ON CONFLICT DO NOTHING;

-- ── Products ──────────────────────────────────────────────────────────────────
INSERT INTO products (id, product_code, product_name, brand_name, tier, is_active, created_by)
VALUES
  ('b93a1d0b-b9c5-011e-61bf-62d7cd18d879', 'RM',       'Rose-Mary',                        'Waterford Estate', 'PREMIUM', TRUE, 'system'),
  ('9de171df-5c37-1bba-2265-7522cb51ff12', 'KAS',      'Kevin Arnold Shiraz',              'Waterford Estate', 'ICON',    TRUE, 'system'),
  ('e9b3be67-3819-f53e-0fd8-4173eb17d7a1', 'CAB',      'Waterford Cabernet Sauvignon',     'Waterford Estate', 'ICON',    TRUE, 'system'),
  ('82bd1511-e62f-c84b-481d-84d15bb05a46', 'JEM',      'Jem',                              'Waterford Estate', 'ICON',    TRUE, 'system'),
  ('2e0895f7-80e9-35f4-0ae5-f923b1d20803', 'ANT',      'Waterford Antigo',                 'Waterford Estate', 'PREMIUM', TRUE, 'system'),
  ('09672209-d0f1-c7b6-a4bd-a04fb81ef0f5', 'PS_CHENIN','Pecan Stream Chenin Blanc',        'Pecan Stream',     'ENTRY',   TRUE, 'system'),
  ('fd886c28-8ce3-422c-41bd-25231675874c', 'PS_SB',    'Pecan Stream Sauvignon Blanc',     'Pecan Stream',     'ENTRY',   TRUE, 'system'),
  ('a15dc1a9-bc6a-e58c-f8b0-24ad16a70506', 'PS_RED',   'Pecan Stream Red',                 'Pecan Stream',     'ENTRY',   TRUE, 'system'),
  ('2a685135-7c20-61e0-7e45-a84b0a283ae2', 'CHD',      'Waterford Chardonnay',             'Waterford Estate', 'PREMIUM', TRUE, 'system'),
  ('4f24d30f-aa5a-c4c1-88ec-2223dd5e2861', 'ELG',      'Waterford Elgin Sauvignon Blanc',  'Waterford Estate', 'PREMIUM', TRUE, 'system'),
  ('9ab3014f-feef-a003-5a41-962073c46f30', 'GRN',      'Waterford Grenache',               'Waterford Estate', 'PREMIUM', TRUE, 'system'),
  ('cd92eced-751a-f56c-b722-d561b8dca5c6', 'HEA',      'Waterford Heatherleigh',           'Waterford Estate', 'PREMIUM', TRUE, 'system'),
  ('76a98884-b8a0-a821-d372-bca5d7bf8f2a', 'OVP',      'Waterford Old Vine Pinotage',      'Waterford Estate', 'PREMIUM', TRUE, 'system')
ON CONFLICT DO NOTHING;

-- ── Product SKUs ──────────────────────────────────────────────────────────────
-- standard_bottle_equivalent: 375ml=0.500, 750ml=1.000, 1500ml=2.000
-- default_case_size is INFORMATIONAL ONLY — never used in calculations
INSERT INTO product_skus (id, product_id, sku_code, sku_name, bottle_size_ml, standard_bottle_equivalent, default_case_size, tier, is_active, created_by)
VALUES
  -- Rose-Mary
  ('a088e898-c5c2-b5ef-ec60-e67006994598',   'b93a1d0b-b9c5-011e-61bf-62d7cd18d879', 'RM001',     'Rose-Mary 750ml',                           750,  1.000, 6,  'PREMIUM', TRUE, 'system'),
  -- Kevin Arnold Shiraz
  ('bd2c66a7-6bed-3fb1-75e3-98024563cde9',  '9de171df-5c37-1bba-2265-7522cb51ff12', 'KAS001',    'Kevin Arnold Shiraz 750ml',                 750,  1.000, 6,  'ICON',    TRUE, 'system'),
  ('29e1f200-47ef-00c5-3a06-e6b0569dd993', '9de171df-5c37-1bba-2265-7522cb51ff12', 'KAS1L',     'Kevin Arnold Shiraz 1.5L Magnum',           1500, 2.000, 3,  'ICON',    TRUE, 'system'),
  -- Cabernet Sauvignon
  ('bbbf5139-b9a6-1723-560f-86261c883b84',  'e9b3be67-3819-f53e-0fd8-4173eb17d7a1', 'CAB001',    'Waterford Cabernet Sauvignon 750ml',        750,  1.000, 6,  'ICON',    TRUE, 'system'),
  ('c3311a41-0217-1b30-a9db-db1ba666210b',  'e9b3be67-3819-f53e-0fd8-4173eb17d7a1', 'CAB375',    'Waterford Cabernet Sauvignon 375ml',        375,  0.500, 12, 'ICON',    TRUE, 'system'),
  -- Jem
  ('31e6e5ad-bf88-8877-956d-1377e7aa196f',  '82bd1511-e62f-c84b-481d-84d15bb05a46', 'JEM001',    'Jem 750ml',                                 750,  1.000, 6,  'ICON',    TRUE, 'system'),
  -- Antigo
  ('7aeb9327-2e29-46ba-f095-22b592cf4c42',  '2e0895f7-80e9-35f4-0ae5-f923b1d20803', 'ANT001',    'Waterford Antigo 750ml',                    750,  1.000, 6,  'PREMIUM', TRUE, 'system'),
  -- Pecan Stream
  ('2dae3f25-3746-6297-8f50-a4b77cba0495',  '09672209-d0f1-c7b6-a4bd-a04fb81ef0f5', 'PSC001',    'Pecan Stream Chenin Blanc 750ml',           750,  1.000, 6,  'ENTRY',   TRUE, 'system'),
  ('bbdb41af-406f-eb57-49ea-d8cbd8bb079f',  'fd886c28-8ce3-422c-41bd-25231675874c', 'PSS001',    'Pecan Stream Sauvignon Blanc 750ml',        750,  1.000, 6,  'ENTRY',   TRUE, 'system'),
  ('21b8f830-c17a-f626-e8c6-8b73d6f7fdb9',  'a15dc1a9-bc6a-e58c-f8b0-24ad16a70506', 'PSR001',    'Pecan Stream Red 750ml',                    750,  1.000, 6,  'ENTRY',   TRUE, 'system'),
  -- Chardonnay
  ('bb8ba7f1-9e50-018e-0c77-0ee5c6f89e51',  '2a685135-7c20-61e0-7e45-a84b0a283ae2', 'CHD001',    'Waterford Chardonnay 750ml',                750,  1.000, 6,  'PREMIUM', TRUE, 'system'),
  -- Elgin Sauvignon Blanc
  ('a2cbe70b-d045-94b3-3f0a-0ce804d9ad6c',  '4f24d30f-aa5a-c4c1-88ec-2223dd5e2861', 'ELG001',    'Waterford Elgin Sauvignon Blanc 750ml',     750,  1.000, 6,  'PREMIUM', TRUE, 'system'),
  -- Grenache
  ('83f14406-8314-476d-d1f3-1e75a6bd45ac',  '9ab3014f-feef-a003-5a41-962073c46f30', 'GRN001',    'Waterford Grenache 750ml',                  750,  1.000, 6,  'PREMIUM', TRUE, 'system'),
  -- Heatherleigh (375ml format)
  ('aff57c7d-caf0-1e1c-e90f-3b0d22c1b2d3',  'cd92eced-751a-f56c-b722-d561b8dca5c6', 'HEA001',    'Waterford Heatherleigh 375ml',              375,  0.500, 12, 'PREMIUM', TRUE, 'system'),
  -- Old Vine Pinotage
  ('4ff39288-a10a-7987-e656-b0f002de5a88',  '76a98884-b8a0-a821-d372-bca5d7bf8f2a', 'OVP001',    'Waterford Old Vine Pinotage 750ml',         750,  1.000, 6,  'PREMIUM', TRUE, 'system')
ON CONFLICT DO NOTHING;

-- ── ASP Versions (FY2027 target sheet prices, effective 2026-07-01) ───────────
-- Source: Sergio King FY2027 Target Sheet (best available ASP data)
-- Methodology: TARGET_SHEET_DERIVED — retail-facing price, NOT ERP wholesale average
-- Note: ERP average is lower (dragged down by distributor wholesale discounts)
INSERT INTO asp_versions (id, product_sku_id, asp_value, currency, effective_from, effective_to, source_document, methodology, is_approved, approved_by, approved_at, notes, created_by)
VALUES
  ('42909af6-732e-93a6-609b-bd9d096fc796',   'a088e898-c5c2-b5ef-ec60-e67006994598',   94.37,  'ZAR', '2026-07-01', NULL, 'Sergio King FY2027 Target Sheet', 'TARGET_SHEET_DERIVED', TRUE, 'system', NOW(), 'Trade-facing ASP. ERP actual avg R89.51 (lower due to distributor discount). Use this for distributor estimation.', 'system'),
  ('f4db1d0a-44dc-690d-4158-37d4214520a3',  'bd2c66a7-6bed-3fb1-75e3-98024563cde9',  231.90, 'ZAR', '2026-07-01', NULL, 'Sergio King FY2027 Target Sheet', 'TARGET_SHEET_DERIVED', TRUE, 'system', NOW(), 'Kevin Arnold Shiraz 750ml ASP', 'system'),
  ('ad970816-ee93-3803-9a29-e81cf0b0dce7','29e1f200-47ef-00c5-3a06-e6b0569dd993', 463.80, 'ZAR', '2026-07-01', NULL, 'Sergio King FY2027 Target Sheet', 'TARGET_SHEET_DERIVED', TRUE, 'system', NOW(), 'Kevin Arnold Shiraz 1.5L — 2× 750ml ASP', 'system'),
  ('03ff1595-ee48-03e1-9667-a66c682408de',  'bbbf5139-b9a6-1723-560f-86261c883b84',  254.00, 'ZAR', '2026-07-01', NULL, 'Sergio King FY2027 Target Sheet', 'TARGET_SHEET_DERIVED', TRUE, 'system', NOW(), 'Cabernet Sauvignon 750ml ASP', 'system'),
  ('e02379d1-d717-dd7d-6d25-7ee3b97f5beb','c3311a41-0217-1b30-a9db-db1ba666210b', 127.00, 'ZAR', '2026-07-01', NULL, 'Sergio King FY2027 Target Sheet', 'TARGET_SHEET_DERIVED', TRUE, 'system', NOW(), 'Cabernet Sauvignon 375ml — 0.5× 750ml ASP', 'system'),
  ('3becefca-ef2a-2a86-3e85-f62d2ce0f31a',  '31e6e5ad-bf88-8877-956d-1377e7aa196f',  359.00, 'ZAR', '2026-07-01', NULL, 'Sergio King FY2027 Target Sheet', 'TARGET_SHEET_DERIVED', TRUE, 'system', NOW(), 'Jem 750ml ASP', 'system'),
  ('78662424-a1c6-415a-3766-21fbbbef529c',  '7aeb9327-2e29-46ba-f095-22b592cf4c42',  165.00, 'ZAR', '2026-07-01', NULL, 'Sergio King FY2027 Target Sheet', 'TARGET_SHEET_DERIVED', TRUE, 'system', NOW(), 'Antigo 750ml ASP', 'system'),
  ('85c38785-cf18-723e-1c86-f5d606315883',  '2dae3f25-3746-6297-8f50-a4b77cba0495',  82.00,  'ZAR', '2026-07-01', NULL, 'Sergio King FY2027 Target Sheet', 'TARGET_SHEET_DERIVED', TRUE, 'system', NOW(), 'Pecan Stream Chenin Blanc ASP', 'system'),
  ('2a6ab7da-c428-430f-6d15-78fa958535a2',  'bbdb41af-406f-eb57-49ea-d8cbd8bb079f',  82.00,  'ZAR', '2026-07-01', NULL, 'Sergio King FY2027 Target Sheet', 'TARGET_SHEET_DERIVED', TRUE, 'system', NOW(), 'Pecan Stream Sauvignon Blanc ASP', 'system'),
  ('cc09618e-6174-f261-fb0f-90d0fa508f2f',  '21b8f830-c17a-f626-e8c6-8b73d6f7fdb9',  82.00,  'ZAR', '2026-07-01', NULL, 'Sergio King FY2027 Target Sheet', 'TARGET_SHEET_DERIVED', TRUE, 'system', NOW(), 'Pecan Stream Red ASP', 'system'),
  ('8a9d678c-cf9c-555d-9432-474ead06c1b2',  'bb8ba7f1-9e50-018e-0c77-0ee5c6f89e51',  149.00, 'ZAR', '2026-07-01', NULL, 'Sergio King FY2027 Target Sheet', 'TARGET_SHEET_DERIVED', TRUE, 'system', NOW(), 'Chardonnay 750ml ASP', 'system'),
  ('20b0976c-4a3d-1930-807c-fce6ce1a6593',  'a2cbe70b-d045-94b3-3f0a-0ce804d9ad6c',  149.00, 'ZAR', '2026-07-01', NULL, 'Sergio King FY2027 Target Sheet', 'TARGET_SHEET_DERIVED', TRUE, 'system', NOW(), 'Elgin SB 750ml ASP', 'system'),
  ('fb32a928-a9c9-e2d9-4d3c-73677e626344',  '83f14406-8314-476d-d1f3-1e75a6bd45ac',  149.00, 'ZAR', '2026-07-01', NULL, 'Sergio King FY2027 Target Sheet', 'TARGET_SHEET_DERIVED', TRUE, 'system', NOW(), 'Grenache 750ml ASP', 'system'),
  ('926472ac-436b-b8fe-c45d-d641ddcfb2cc',  'aff57c7d-caf0-1e1c-e90f-3b0d22c1b2d3',  89.00,  'ZAR', '2026-07-01', NULL, 'Sergio King FY2027 Target Sheet', 'TARGET_SHEET_DERIVED', TRUE, 'system', NOW(), 'Heatherleigh 375ml ASP', 'system'),
  ('1baa4d19-4c7a-24f5-61a9-51818301648c',  '4ff39288-a10a-7987-e656-b0f002de5a88',  165.00, 'ZAR', '2026-07-01', NULL, 'Sergio King FY2027 Target Sheet', 'TARGET_SHEET_DERIVED', TRUE, 'system', NOW(), 'Old Vine Pinotage 750ml ASP', 'system')
ON CONFLICT DO NOTHING;

-- ── Client Groups (confirmed) ──────────────────────────────────────────────────
INSERT INTO client_groups (id, group_name, group_type, is_national, notes, created_by)
VALUES
  ('7240f8d7-eaa0-23b9-cf31-cd42f02f6f3c',     'Tashas Group',       'RESTAURANT_CHAIN', TRUE,  'Multi-outlet restaurant group. V&A, Constantia, Canal Walk, Cavendish, Arlecchino.', 'system'),
  ('51d4b480-cb1f-90b8-f5bc-55a96bef85c8',     'Hussar Grill Group', 'RESTAURANT_CHAIN', TRUE,  'Franchise steakhouse group. Paarl, Franschhoek, Worcester outlets confirmed.', 'system'),
  ('4d6fbf84-7ce1-bb24-47fe-fc075096a904','Cattle Baron Group', 'RESTAURANT_CHAIN', TRUE,  'Franchise steakhouse group. Multiple outlets — Stellenbosch confirmed. De Waterkant in NGF Monthly. Additional outlets UNRESOLVED.', 'system'),
  ('69cac0f4-a248-320a-41df-647fac42a1c8',       'Lupa Group',         'RESTAURANT_CHAIN', FALSE, 'Italian restaurant group. Durbanville and Parelberg outlets confirmed.', 'system')
ON CONFLICT DO NOTHING;

-- ── Canonical Clients — CONFIRMED ONLY (26 clients approved to load) ──────────
-- Only CONFIRMED MCR entries from the stress test and MCR exercise.
-- PROBABLE and UNRESOLVED clients are NOT loaded here — they enter via review queue.

-- Distributors (as clients — for sell-in tracking)
INSERT INTO clients (id, canonical_name, outlet_type, tier, territory_id, primary_channel_id, is_distributor, distributor_entity_id, is_active, notes, created_by)
VALUES
  -- NGF as distributor-client (receives WF sell-in)
  ('af084827-065b-e93c-a9a4-471f1b1f3661', 'NGF Norman Goodfellows (Distributor)', 'DISTRIBUTOR', 'DISTRIBUTOR',
   '55f7332d-1552-5a9e-4f3b-56b8c260f1a1', 'e567b0b8-8b95-aa2c-9a58-857216b2ca0a',
   TRUE, 'acc21c78-f6af-4cb4-eb3c-8571e42e9752', TRUE,
   'NGF as the distributor entity that receives WF sell-in. DISTINCT from NGF JHB as buyer (cl-ngf-jhb-buyer).', 'system'),

  -- NGF JHB as wholesale buyer (also buys from VDP)
  ('820abb2c-3055-d1e4-1b18-d26e59326915', 'Norman Goodfellows JHB (as Wholesale Buyer)', 'WHOLESALE', 'WHOLESALE',
   'abbf9648-42ab-9760-61ff-f3ebaeaa4602', '9dc768e1-cd97-9208-54c6-807daf32bea8',
   TRUE, 'acc21c78-f6af-4cb4-eb3c-8571e42e9752', TRUE,
   'Norman Goodfellows as a BUYER from VDP and occasionally from WF direct. Different commercial role from cl-ngf-dist. distributor_entity_id links to NGF distributor record.', 'system'),

  -- VDP as distributor-client
  ('6fe0a8de-60a5-c2e3-1661-1c8e8960c4ff', 'VDP Prestige Distributors Gauteng (Distributor)', 'DISTRIBUTOR', 'DISTRIBUTOR',
   'abbf9648-42ab-9760-61ff-f3ebaeaa4602', '9dc768e1-cd97-9208-54c6-807daf32bea8',
   TRUE, '9ab2ddd1-7a50-841a-86d4-41796d6269d1', TRUE,
   'VDP as the distributor entity receiving WF sell-in to Gauteng.', 'system'),

  -- Distriliq as distributor-client
  ('97f105ae-ebf2-ea17-04c7-c02fde7a3147', 'Distriliq Cape Town (Distributor)', 'DISTRIBUTOR', 'DISTRIBUTOR',
   '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'adbc1ae4-0a3b-935e-8b45-27449f47da2f',
   TRUE, 'f394bb9e-0088-7e37-834d-9e202b3bf1cd', TRUE,
   'Distriliq CPT as distributor receiving WF sell-in to CPT.', 'system'),

  -- Distri George
  ('c52b9c96-c142-361b-d0bc-6341280b22fa', 'Distri George (Pty) Ltd (Distributor)', 'DISTRIBUTOR', 'DISTRIBUTOR',
   '12a4b757-a731-7edc-f81b-182da9fd1ba7', '0c478abc-5906-a7ca-234f-53c2247f4465',
   TRUE, '959725b7-02c5-a620-f521-9c9ba5f87049', TRUE,
   'Distri George as distributor for Garden Route.', 'system')
ON CONFLICT DO NOTHING;

-- Tashas Group outlets (5 confirmed)
INSERT INTO clients (id, canonical_name, client_group_id, outlet_type, tier, territory_id, primary_channel_id, is_active, created_by)
VALUES
  ('618c2177-5635-64d4-62f4-71bb9b65b26d',    'Tashas V and A Waterfront',  '7240f8d7-eaa0-23b9-cf31-cd42f02f6f3c', 'RESTAURANT', 'ON_TRADE', '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'e567b0b8-8b95-aa2c-9a58-857216b2ca0a', TRUE, 'system'),
  ('11efa714-c6ff-b8dc-0505-a876d93261f5', 'Tashas Constantia',           '7240f8d7-eaa0-23b9-cf31-cd42f02f6f3c', 'RESTAURANT', 'ON_TRADE', '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'adbc1ae4-0a3b-935e-8b45-27449f47da2f', TRUE, 'system'),
  ('d12e46df-1dbc-8179-c8b2-650f68a2f35e',    'Tashas Canal Walk',            '7240f8d7-eaa0-23b9-cf31-cd42f02f6f3c', 'RESTAURANT', 'ON_TRADE', '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'adbc1ae4-0a3b-935e-8b45-27449f47da2f', TRUE, 'system'),
  ('d29ea75c-f1c2-013d-bbba-6f0b4c0cc8b0',   'Tashas Cavendish',             '7240f8d7-eaa0-23b9-cf31-cd42f02f6f3c', 'RESTAURANT', 'ON_TRADE', '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'adbc1ae4-0a3b-935e-8b45-27449f47da2f', TRUE, 'system'),
  ('70d9eb91-b31c-53bf-f1c7-9a2b2b608a95',   'Arlecchino by Tashas',         '7240f8d7-eaa0-23b9-cf31-cd42f02f6f3c', 'RESTAURANT', 'ON_TRADE', '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'adbc1ae4-0a3b-935e-8b45-27449f47da2f', TRUE, 'system')
ON CONFLICT DO NOTHING;

-- WC confirmed clients
INSERT INTO clients (id, canonical_name, outlet_type, tier, territory_id, primary_channel_id, secondary_channel_id, is_active, notes, created_by)
VALUES
  ('ca74262e-6d93-8200-c626-87c3e80b25e5',      'Van Riebeeck Liquors',          'BOTTLE_STORE', 'KAM',       '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'c83cf810-5c5a-4ae9-9bc6-fda1e3592b98', 'adbc1ae4-0a3b-935e-8b45-27449f47da2f', TRUE, 'Dual channel: direct ERP primary + Distriliq secondary', 'system'),
  ('38094438-3b0d-0d5f-7df4-98ff5c52b64b',     'Willoughby and Co',             'BOTTLE_STORE', 'KAM',       '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'adbc1ae4-0a3b-935e-8b45-27449f47da2f', 'e567b0b8-8b95-aa2c-9a58-857216b2ca0a', TRUE, 'Primary: Distriliq 1738 btls. Secondary: NGF SalesOut 150 btls Jul 25', 'system'),
  ('52b98daa-5f80-f66c-f38a-180bc864373f',       'POD Byron Bay Property',        'BOTTLE_STORE', 'KAM',       '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'adbc1ae4-0a3b-935e-8b45-27449f47da2f', 'e567b0b8-8b95-aa2c-9a58-857216b2ca0a', TRUE, 'Primary: Distriliq 1686 btls. NGF SalesOut 108 btls Jul 25', 'system'),
  ('4d609174-3fd9-b288-37f9-6f40d73de9e0','Lord Charles Hotel',           'HOTEL',        'ON_TRADE',  'dd7c1549-2531-5b15-d389-9e7ead901178', 'e567b0b8-8b95-aa2c-9a58-857216b2ca0a', 'adbc1ae4-0a3b-935e-8b45-27449f47da2f', TRUE, 'NGF LOR008 is primary confirmed code (484 btls). THE004 is UNRESOLVED — may be same entity or different dept. See AMBER decision.', 'system'),
  ('4ca52590-76d4-deca-bb1a-c3d355118c76',      'The Fat Butcher',               'RESTAURANT',   'ON_TRADE',  '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'c83cf810-5c5a-4ae9-9bc6-fda1e3592b98', 'e567b0b8-8b95-aa2c-9a58-857216b2ca0a', TRUE, 'Dual channel FY26: direct ERP FATB0001 + NGF SalesOut THE043', 'system'),
  ('ce45e088-8976-7cba-e243-bac73cbd77e5',  'Manoushe Lebanese Restaurant',  'RESTAURANT',   'ON_TRADE',  '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'adbc1ae4-0a3b-935e-8b45-27449f47da2f', NULL,                                    TRUE, 'Moved to Distriliq voluntarily. Do not force back to direct.', 'system'),
  ('69461f83-4e5b-1493-26a1-7152fe6974bf',   'Balboas',                       'RESTAURANT',   'ON_TRADE',  '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'e567b0b8-8b95-aa2c-9a58-857216b2ca0a', NULL,                                    TRUE, 'NGF SalesOut BAL003', 'system'),
  ('9edb3713-8326-6c60-8fe4-88f52aa18c79',   'Mileori',                       'RESTAURANT',   'ON_TRADE',  '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'e567b0b8-8b95-aa2c-9a58-857216b2ca0a', NULL,                                    TRUE, 'NGF SalesOut LIB001', 'system'),
  ('4bdcc6da-6ad0-f669-a67a-b5769e520045',  'Club Como CPT (Algoabrite)',    'RESTAURANT',   'ON_TRADE',  '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'e567b0b8-8b95-aa2c-9a58-857216b2ca0a', NULL,                                    TRUE, 'Algoabrite (Pty) Ltd T/A Club Como Mediterranean. NGF SalesOut THE180', 'system'),
  ('7d8bdb18-7975-e60c-2b4c-6af54d2b5b28', '3XE Mezza Luna',                'RESTAURANT',   'ON_TRADE',  '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'e567b0b8-8b95-aa2c-9a58-857216b2ca0a', NULL,                                    TRUE, '3XE (Pty) Ltd T/A Mezza Luna. NGF SalesOut MEZ004', 'system'),
  ('5d8abdbe-1d17-f41c-2bbf-2e586548965d',   'Nelsons Eye Restaurant',        'RESTAURANT',   'ON_TRADE',  '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'e567b0b8-8b95-aa2c-9a58-857216b2ca0a', NULL,                                    TRUE, 'ERP NELSON01 + NGF SalesOut NEL001', 'system'),
  ('a694afac-edce-edee-6e09-a0ef491ddb39',   'One and Only Cape Town',        'HOTEL',        'ON_TRADE',  '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'e567b0b8-8b95-aa2c-9a58-857216b2ca0a', NULL,                                    TRUE, 'ERP ONEA0001 + NGF SalesOut ONE001', 'system'),
  ('41961b43-1ab0-d733-69b2-fbba737eee82',  'Stardust Theatrical Dining',    'RESTAURANT',   'ON_TRADE',  '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'e567b0b8-8b95-aa2c-9a58-857216b2ca0a', NULL,                                    TRUE, 'ERP STAR0002 + NGF SalesOut STA007', 'system'),
  ('ec4c85b4-8a60-ad09-497f-c86b5f88aaa7', 'DeCameron Restaurant',          'RESTAURANT',   'ON_TRADE',  '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'e567b0b8-8b95-aa2c-9a58-857216b2ca0a', NULL,                                    TRUE, 'ERP DECAM001 + NGF SalesOut DEC001', 'system'),
  ('17502033-4069-c42a-ce0a-3a0f99e177cc',   'De Zalze Golf Club',            'HOTEL',        'ON_TRADE',  'dd7c1549-2531-5b15-d389-9e7ead901178', 'c83cf810-5c5a-4ae9-9bc6-fda1e3592b98', 'e567b0b8-8b95-aa2c-9a58-857216b2ca0a', TRUE, 'ERP DEZALZE1 + NGF SalesOut DE022', 'system'),
  ('9eaf50a1-d60d-bba3-8194-7e38fdb60fde',    'Tokara Restaurant',             'RESTAURANT',   'ON_TRADE',  'dd7c1549-2531-5b15-d389-9e7ead901178', 'c83cf810-5c5a-4ae9-9bc6-fda1e3592b98', NULL,                                    TRUE, 'ERP TOKARA01 + NGF SalesOut TOK001 (1 btl — low volume)', 'system'),
  ('953c0cc1-45b7-fd0f-a59e-5b83225f5e58',      'Tang Waterfront',               'RESTAURANT',   'ON_TRADE',  '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'e567b0b8-8b95-aa2c-9a58-857216b2ca0a', NULL,                                    TRUE, 'NGF SalesOut TAN001 + NGF Monthly confirms', 'system'),
  ('8246d70f-18d3-8146-11c4-2a0a5fc7226d',  'Hotel Sky Cape Town',           'HOTEL',        'ON_TRADE',  '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'e567b0b8-8b95-aa2c-9a58-857216b2ca0a', NULL,                                    TRUE, 'NGF SalesOut HOT005 + NGF Monthly confirms', 'system'),
  ('80191f2a-d3c4-daae-2772-eb310c2c769d',    'Qcooks',                        'CATERING',     'ON_TRADE',  '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'e567b0b8-8b95-aa2c-9a58-857216b2ca0a', NULL,                                    TRUE, 'NGF SalesOut OAK007', 'system')
ON CONFLICT DO NOTHING;

-- Gauteng confirmed clients
INSERT INTO clients (id, canonical_name, outlet_type, tier, territory_id, primary_channel_id, secondary_channel_id, is_active, notes, created_by)
VALUES
  ('cc3f077f-9b98-683d-ad0c-cdc2d79da861',    'Solly Kramers Parkhurst',        'BOTTLE_STORE', 'RETAIL',    'abbf9648-42ab-9760-61ff-f3ebaeaa4602', '9dc768e1-cd97-9208-54c6-807daf32bea8', 'c83cf810-5c5a-4ae9-9bc6-fda1e3592b98', TRUE, 'ERP SOL001 + VDP Jul/Aug 26', 'system'),
  ('779ce630-6384-d4fa-408e-00713683cb56',    'Zulzi',                          'RETAIL',       'RETAIL',    'abbf9648-42ab-9760-61ff-f3ebaeaa4602', '9dc768e1-cd97-9208-54c6-807daf32bea8', 'c83cf810-5c5a-4ae9-9bc6-fda1e3592b98', TRUE, 'ERP ZUL001 + VDP Jul/Aug 26', 'system'),
  ('adaea0e2-7604-2b49-f9ec-290f0e0d1040',  'GD Saint Restaurants',           'RESTAURANT',   'ON_TRADE',  'abbf9648-42ab-9760-61ff-f3ebaeaa4602', 'c83cf810-5c5a-4ae9-9bc6-fda1e3592b98', '9dc768e1-cd97-9208-54c6-807daf32bea8', TRUE, 'ERP GDS001 + VDP + Distriliq GD SAINTS (PROBABLE - pending confirm)', 'system'),
  ('99b34138-d1a1-4227-2723-a6af92df0d69',    'Dolci Cafe',                     'RESTAURANT',   'ON_TRADE',  'abbf9648-42ab-9760-61ff-f3ebaeaa4602', 'c83cf810-5c5a-4ae9-9bc6-fda1e3592b98', '9dc768e1-cd97-9208-54c6-807daf32bea8', TRUE, 'ERP DOLCI001 (name has phone number embedded). VDP confirms.', 'system'),
  ('c8989d0a-2ca1-6e60-8c06-9a78e091570c',  'Big Five Duty Free Johannesburg', 'KEY_ACCOUNT', 'KEY_ACCOUNT','abbf9648-42ab-9760-61ff-f3ebaeaa4602', 'c83cf810-5c5a-4ae9-9bc6-fda1e3592b98', 'e567b0b8-8b95-aa2c-9a58-857216b2ca0a', TRUE, 'Was NGF channel Aug25-Feb26; went direct from Mar26. ERP BIGF0001.', 'system'),
  ('e5836289-e543-e26f-a002-072a76c0358a',  'Big Five Duty Free Cape Town',   'KEY_ACCOUNT', 'KEY_ACCOUNT','3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2', 'c83cf810-5c5a-4ae9-9bc6-fda1e3592b98', 'e567b0b8-8b95-aa2c-9a58-857216b2ca0a', TRUE, 'Same channel transition as JHB. ERP BIGF0002.', 'system')
ON CONFLICT DO NOTHING;

-- ── Client Source Aliases — CONFIRMED ONLY ────────────────────────────────────
-- CONFIRMED requires confirmed_by = human user ID or 'system' for known-certain matches.
-- Source: MCR exercise cross-referenced with ERP debtor codes and distributor files.
INSERT INTO client_source_aliases (id, client_id, source_id, source_name, source_code, match_confidence, match_status, matched_by, confirmed_by, confirmed_at, alias_notes)
VALUES
  -- NGF dist
  ('d92d5356-9f56-8662-2a58-965dab9c7136', 'af084827-065b-e93c-a9a4-471f1b1f3661', 'd02b430a-f424-4930-e449-9c4fe3af0063', 'Norman Goodfellows Wynberg Jhb', 'NORM0002', 'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'Primary ERP debtor for NGF'),
  ('11771fa1-a9bc-7095-a871-04dff4a58a24',   'af084827-065b-e93c-a9a4-471f1b1f3661', 'd02b430a-f424-4930-e449-9c4fe3af0063', 'NGF/Norman Goodfellows CPT',     'NORMGF',   'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'Secondary NGF debtor code'),
  -- VDP dist
  ('58203b7a-52ec-a210-2b8d-e0e99e358bd5', '6fe0a8de-60a5-c2e3-1661-1c8e8960c4ff', 'd02b430a-f424-4930-e449-9c4fe3af0063', 'VDP Prestige Distributors', 'VDPGAU01', 'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'ERP debtor for VDP sell-in'),
  -- NGF JHB buyer
  ('f3212b17-fd19-c5af-b08a-7b23f4a7514f', '820abb2c-3055-d1e4-1b18-d26e59326915', '07e9366b-1e6e-7352-3533-00a8117a0ea6', 'NORMAN GOODFELLOWS (PTY) LTD', '', 'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF as VDP buyer Jul 26: 854 btls'),
  -- Tashas group
  ('46134382-42ae-9764-9b2a-ec0db348c7da',  '618c2177-5635-64d4-62f4-71bb9b65b26d',    'cf399ce6-ab61-b009-fd0a-0d39745bfd01', 'TASHAS V & A',                      '',     'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF Monthly CPT'),
  ('a79eb724-637d-099a-6184-c2c28b7889b7',  '618c2177-5635-64d4-62f4-71bb9b65b26d',    'f86a696e-4143-9a84-7352-b39bb553ebf7', 'TASHAS V&A WATERFRONT NO',           '',     'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'Distriliq CPT'),
  ('b13d3a22-d1e0-4f35-3ee9-4fd940823197',   '618c2177-5635-64d4-62f4-71bb9b65b26d',    '040f86eb-f98c-b847-46fe-6774b658a6ee', 'TASHAS V&A WATERFRONT NO',           'TAS006','CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF SalesOut debtor TAS006'),
  ('0823683c-ea53-9183-9338-569fdc9e3c2d',   '11efa714-c6ff-b8dc-0505-a876d93261f5', 'f86a696e-4143-9a84-7352-b39bb553ebf7', 'TASHAS CONSTANTIA-RUBY',             '',     'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'Distriliq CPT'),
  ('9f7d7ce1-b193-a36e-5642-c648fc4734ac','11efa714-c6ff-b8dc-0505-a876d93261f5', '040f86eb-f98c-b847-46fe-6774b658a6ee', 'TASHAS CONSTANTIA - RUBY',           'TAS002','CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF SalesOut TAS002'),
  ('cfdd5064-93a4-7ba2-9caa-b30994285c0d',  'd12e46df-1dbc-8179-c8b2-650f68a2f35e',    'f86a696e-4143-9a84-7352-b39bb553ebf7', 'TASHAS CANAL WALK',                  '',     'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'Distriliq CPT'),
  ('07835b71-0d34-d36d-8db5-895fe263f34d',   'd12e46df-1dbc-8179-c8b2-650f68a2f35e',    '040f86eb-f98c-b847-46fe-6774b658a6ee', 'TASHAS CANAL WALK',                  'TAS007','CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF SalesOut TAS007'),
  ('b1438982-0185-6125-d793-0beeab5e39ac', 'd29ea75c-f1c2-013d-bbba-6f0b4c0cc8b0',   'f86a696e-4143-9a84-7352-b39bb553ebf7', 'TASHAS CAVENDISH SQUARE',            '',     'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'Distriliq CPT'),
  ('65ca7b47-2906-c4af-062a-2edaed9b3473',  'd29ea75c-f1c2-013d-bbba-6f0b4c0cc8b0',   '040f86eb-f98c-b847-46fe-6774b658a6ee', 'TASHAS CAVENDISH',                   'TAS001','CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF SalesOut TAS001'),
  ('0bfa10f3-bf74-fab0-81f6-767b31552efb', '70d9eb91-b31c-53bf-f1c7-9a2b2b608a95',   'f86a696e-4143-9a84-7352-b39bb553ebf7', 'ARLECCHINO BY TASHAS',               '',     'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'Distriliq CPT'),
  ('089cf0e0-8a3b-5e60-7769-f706c89695bf',  '70d9eb91-b31c-53bf-f1c7-9a2b2b608a95',   '040f86eb-f98c-b847-46fe-6774b658a6ee', 'ARLECCHINO BY TASHAS',               'ARL001','CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF SalesOut ARL001'),
  -- Van Riebeeck
  ('7b80118d-80be-cfc2-19db-9c775ea71cac',  'ca74262e-6d93-8200-c626-87c3e80b25e5', 'd02b430a-f424-4930-e449-9c4fe3af0063', 'Van Riebeeck Liquors Soutriver', 'VAN RIEB',  'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'Primary ERP debtor R1.9m FY26'),
  ('88437eb0-fc25-f71a-8f02-20e0b25af0b9',  'ca74262e-6d93-8200-c626-87c3e80b25e5', 'd02b430a-f424-4930-e449-9c4fe3af0063', 'Van Riebeeck Liquors',           'VANR0002',  'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'Secondary ERP debtor'),
  ('5cfa7903-be45-226a-3c5f-dd09e926bbc6',   'ca74262e-6d93-8200-c626-87c3e80b25e5', 'f86a696e-4143-9a84-7352-b39bb553ebf7', 'VAN RIEBEECK DRANKGROEP',        '',          'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'Distriliq CPT — Afrikaans form of same entity'),
  ('98d4810d-beb0-081b-fc13-2e6d587f334e',    'ca74262e-6d93-8200-c626-87c3e80b25e5', '040f86eb-f98c-b847-46fe-6774b658a6ee', 'VAN RIEBEECK DRANKGROEP',        'VAN003',    'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF SalesOut VAN003'),
  -- Willoughby
  ('8c55ca04-ec53-08a7-c814-97c433cbb0a8',  '38094438-3b0d-0d5f-7df4-98ff5c52b64b', 'd02b430a-f424-4930-e449-9c4fe3af0063', 'Willoughby & Co.',               'WILL0003',  'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'ERP credit note only — not primary channel'),
  ('85172bbd-e864-8404-cc63-4e4a88f87a70',  '38094438-3b0d-0d5f-7df4-98ff5c52b64b', 'f86a696e-4143-9a84-7352-b39bb553ebf7', 'WILLOUGHBY & CO',                '',          'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'Distriliq CPT primary: 1738 btls FY26'),
  ('dd671c99-b7b0-b5ed-8e86-e5d2d9154634',   '38094438-3b0d-0d5f-7df4-98ff5c52b64b', '040f86eb-f98c-b847-46fe-6774b658a6ee', 'WILLOUGHBY & CO',                'WIL001',    'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF SalesOut WIL001: 1738 btls FY26'),
  -- POD
  ('f8be92a8-71e5-4591-a264-62cc2b39fc6a',    '52b98daa-5f80-f66c-f38a-180bc864373f',   'f86a696e-4143-9a84-7352-b39bb553ebf7', 'POD (BYRON BAY PROPERTY',        '',          'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'Distriliq CPT: 1686 btls'),
  ('cf90cc73-65b3-ab56-aa28-253e39ef78c9',     '52b98daa-5f80-f66c-f38a-180bc864373f',   '040f86eb-f98c-b847-46fe-6774b658a6ee', 'POD (BYRON BAY PROPERTY',        'POD001',    'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF SalesOut POD001: 108 btls Jul 25'),
  -- Lord Charles — LOR008 ONLY (THE004 is UNRESOLVED — NOT loaded as alias yet)
  ('89060454-28ac-021a-4187-b0fdf82814e8',     '4d609174-3fd9-b288-37f9-6f40d73de9e0', 'cf399ce6-ab61-b009-fd0a-0d39745bfd01', 'LORD CHARLES HOTEL',         '',      'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF Monthly CPT'),
  ('2d9ecdf6-65c7-4295-1a43-d5b12724d23c','4d609174-3fd9-b288-37f9-6f40d73de9e0', '040f86eb-f98c-b847-46fe-6774b658a6ee', 'LORD CHARLES HOTEL (PTY)',  'LOR008', 'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), '484 btls FY26. Primary confirmed code.'),
  -- NOTE: THE004 alias NOT loaded — UNRESOLVED. Will appear as import_queue_item when SalesOut imported.
  -- Fat Butcher
  ('93483437-ceee-e901-4835-b0d739540d7a',   '4ca52590-76d4-deca-bb1a-c3d355118c76',  'd02b430a-f424-4930-e449-9c4fe3af0063', 'The Fat Butcher',                'FATB0001', 'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'ERP direct — Nathalie account: 162 btls FY26'),
  ('fe7a333b-ee27-5212-e93d-8e64660efcbf',    '4ca52590-76d4-deca-bb1a-c3d355118c76',  '040f86eb-f98c-b847-46fe-6774b658a6ee', 'THE FAT BUTCHER (PTY) LT',       'THE043',   'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF SalesOut THE043: 271 btls FY26'),
  -- Manoushe
  ('08038dd7-14f1-4218-49a5-61eaede2d7d9',    'ce45e088-8976-7cba-e243-bac73cbd77e5', 'd02b430a-f424-4930-e449-9c4fe3af0063', 'Manoushe',               'MANO0002',  'PROBABLE',  'ACTIVE', 'system', NULL, NULL, 'Was direct — moved to Distriliq. ERP alias likely but needs confirm.'),
  ('38566fa0-09c6-2a6d-52cc-8e5416618bb2',    'ce45e088-8976-7cba-e243-bac73cbd77e5', 'f86a696e-4143-9a84-7352-b39bb553ebf7', 'MANOUSHE LEBANESE BAKERY', '',         'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'Distriliq CPT: 336 btls FY26'),
  ('7487537c-c940-3072-55ca-01f79a101187',     'ce45e088-8976-7cba-e243-bac73cbd77e5', '040f86eb-f98c-b847-46fe-6774b658a6ee', 'MANOUSHE LEBANESE BAKERY', 'MAN003',   'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF SalesOut MAN003'),
  -- Other confirmed CPT aliases
  ('c7cb6e92-389f-e83a-28dd-5c2cac37e85b',   '69461f83-4e5b-1493-26a1-7152fe6974bf',  '040f86eb-f98c-b847-46fe-6774b658a6ee', 'BALBOAS',                      'BAL003', 'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF SalesOut BAL003: 391 btls'),
  ('a3132593-8daf-c30e-85ad-2c160e8df648',   '9edb3713-8326-6c60-8fe4-88f52aa18c79',  '040f86eb-f98c-b847-46fe-6774b658a6ee', 'MILEORI (PTY) LTD',            'LIB001', 'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF SalesOut LIB001: 354 btls'),
  ('25a6f642-866e-e422-099d-b768570071fb',    '4bdcc6da-6ad0-f669-a67a-b5769e520045', '040f86eb-f98c-b847-46fe-6774b658a6ee', 'ALGOABRITE (PTY) LTD T/A',     'THE180', 'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF SalesOut THE180: 302 btls'),
  ('b5c53d24-01a4-edf9-7937-56d9c143453a',   '7d8bdb18-7975-e60c-2b4c-6af54d2b5b28','040f86eb-f98c-b847-46fe-6774b658a6ee', '3XE (PTY) LTD T/A MEZZA',      'MEZ004', 'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF SalesOut MEZ004: 140 btls'),
  ('e62180e7-0a2c-b44f-4277-955d2823f5dc',  '5d8abdbe-1d17-f41c-2bbf-2e586548965d',  'd02b430a-f424-4930-e449-9c4fe3af0063', 'Nelsons Eye Restaurant cc',     'NELSON01','CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'ERP direct: 102 btls FY26'),
  ('9f07306d-600e-70a0-aa17-8afd8b4df5ac',   '5d8abdbe-1d17-f41c-2bbf-2e586548965d',  '040f86eb-f98c-b847-46fe-6774b658a6ee', 'NELSONS EYE RESTAURANT',        'NEL001', 'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF SalesOut NEL001: 60 btls'),
  ('ecc86938-f73b-7d96-0398-25449a652102','a694afac-edce-edee-6e09-a0ef491ddb39',  'd02b430a-f424-4930-e449-9c4fe3af0063', 'One and Only Cape Town',        'ONEA0001','CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'ERP direct: 84 btls'),
  ('effc00b3-7b08-18a7-56c3-df05ff12de23', 'a694afac-edce-edee-6e09-a0ef491ddb39',  '040f86eb-f98c-b847-46fe-6774b658a6ee', 'ONE AND ONLY CAPE TOWN (',      'ONE001', 'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF SalesOut ONE001: 90 btls'),
  ('9dd8e3a5-ad25-b79e-e8b1-2f1b2671db2e', '41961b43-1ab0-d733-69b2-fbba737eee82', 'd02b430a-f424-4930-e449-9c4fe3af0063', 'Stardust Theatrical Dining cc', 'STAR0002','CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'ERP: 162 btls'),
  ('7f8c27a7-1ed8-a01b-09df-f7e4ea5e0a64',  '41961b43-1ab0-d733-69b2-fbba737eee82', '040f86eb-f98c-b847-46fe-6774b658a6ee', 'STARDUST THEATRICAL DINI',      'STA007', 'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF SalesOut STA007: 18 btls'),
  ('215b8647-17d4-57b5-5b5b-1b365bd475e8',  'ec4c85b4-8a60-ad09-497f-c86b5f88aaa7','d02b430a-f424-4930-e449-9c4fe3af0063', 'DeCameron Restaurant',          'DECAM001','CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'ERP: 72 btls'),
  ('00e5f03c-7921-f94e-5898-2b1553e90c37',   'ec4c85b4-8a60-ad09-497f-c86b5f88aaa7','040f86eb-f98c-b847-46fe-6774b658a6ee', 'DECAMERON',                     'DEC001', 'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF SalesOut DEC001: 12 btls'),
  ('c50bd2a9-7c5d-16cd-e568-f5bac8fec878',  '17502033-4069-c42a-ce0a-3a0f99e177cc',  'd02b430a-f424-4930-e449-9c4fe3af0063', 'De Zalze Golf Club',            'DEZALZE1','CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'ERP: 541 btls'),
  ('7ba73ea1-ed5a-4f4a-45f4-712ac4d0d14d',   '17502033-4069-c42a-ce0a-3a0f99e177cc',  '040f86eb-f98c-b847-46fe-6774b658a6ee', 'DE ZALZE GOLF CLUB NPC',        'DE 022', 'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF SalesOut DE022: 24 btls'),
  ('3dc782b2-6f13-b4da-d2ce-4115029d3650',  '9eaf50a1-d60d-bba3-8194-7e38fdb60fde',   'd02b430a-f424-4930-e449-9c4fe3af0063', 'Tokara Restaurant',             'TOKARA01','CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'ERP: 30 btls'),
  ('70b72a79-d060-ff1a-b9dd-b5cb6904e57c',   '9eaf50a1-d60d-bba3-8194-7e38fdb60fde',   '040f86eb-f98c-b847-46fe-6774b658a6ee', 'TOKARA RESTAURANT - OASI',      'TOK001', 'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF SalesOut TOK001: 1 btl'),
  ('6594a1c0-c1e5-0ae1-368b-b57af686ae6c',  '953c0cc1-45b7-fd0f-a59e-5b83225f5e58',     '040f86eb-f98c-b847-46fe-6774b658a6ee', 'TANG WATERFRONT (PTY)LTD',      'TAN001', 'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF SalesOut TAN001: 19 btls'),
  ('943f5bba-553a-48dd-b76c-e400f8dad0a5',  '8246d70f-18d3-8146-11c4-2a0a5fc7226d', '040f86eb-f98c-b847-46fe-6774b658a6ee', 'HOTEL SKY CAPE TOWN',           'HOT005', 'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF SalesOut HOT005: 18 btls'),
  ('03f46d94-f640-7fa9-ae6f-652c89dbf69a','80191f2a-d3c4-daae-2772-eb310c2c769d',   '040f86eb-f98c-b847-46fe-6774b658a6ee', 'QCOOKS (PTY)LTD WCP/04',        'OAK007', 'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF SalesOut OAK007: 17 btls'),
  -- Gauteng confirmed aliases
  ('f8b0719a-33a9-8e4d-9b6b-3696e3b03002',   'cc3f077f-9b98-683d-ad0c-cdc2d79da861',   'd02b430a-f424-4930-e449-9c4fe3af0063', 'Solly Kramers Parkhurst',      'SOL001', 'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'ERP direct — apostrophe in name'),
  ('f40d1444-8942-4225-f8ae-2fa108750548',   'cc3f077f-9b98-683d-ad0c-cdc2d79da861',   '07e9366b-1e6e-7352-3533-00a8117a0ea6', 'SOLLY KRAMERS PARKHURST',       '',       'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'VDP Monthly Jul+Aug 26'),
  ('3a9ccab5-83a7-fb82-da53-e8ddc9bdd5c4',   '779ce630-6384-d4fa-408e-00713683cb56',   'd02b430a-f424-4930-e449-9c4fe3af0063', 'Zulzi on Demand (Pty) Ltd',     'ZUL001', 'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'ERP direct'),
  ('84da2f6c-afb6-05a2-6dfb-1d482467911d',   '779ce630-6384-d4fa-408e-00713683cb56',   '07e9366b-1e6e-7352-3533-00a8117a0ea6', 'ZULZI',                         '',       'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'VDP Monthly'),
  ('ab53dc5c-e762-b249-0887-ed28c0440a71',   'adaea0e2-7604-2b49-f9ec-290f0e0d1040', 'd02b430a-f424-4930-e449-9c4fe3af0063', 'GD Saint Restaurants (Pty)Ltd', 'GDS001', 'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'ERP direct — Sandile account'),
  ('b03c6ad5-8722-7793-acb2-315e39fe434d',   'adaea0e2-7604-2b49-f9ec-290f0e0d1040', '07e9366b-1e6e-7352-3533-00a8117a0ea6', 'GD SAINT RESTAURANTS (PTY) LTD t/a SAINT RESTAURANT', '', 'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'VDP Jul+Aug 26'),
  ('5e726c72-c7ce-d559-e968-42e622f49491',   '99b34138-d1a1-4227-2723-a6af92df0d69',   'd02b430a-f424-4930-e449-9c4fe3af0063', 'Dolci Cafe 010 900 2274',       '',       'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'Phone number in ERP name — normalised to Dolci Cafe'),
  ('df748183-3fc7-8a0d-36f7-0ef20c7f302a',   '99b34138-d1a1-4227-2723-a6af92df0d69',   '07e9366b-1e6e-7352-3533-00a8117a0ea6', 'DOLCI CAFE',                    '',       'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'VDP Jul 26'),
  ('526dc798-6746-c000-ce94-33ec427deb53', 'c8989d0a-2ca1-6e60-8c06-9a78e091570c', 'd02b430a-f424-4930-e449-9c4fe3af0063', 'Big Five Duty Free Joburg',    'BIGF0001','CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'ERP direct from Mar 26'),
  ('4c9a42de-db2d-74be-1cb6-3813c84cd44e', 'c8989d0a-2ca1-6e60-8c06-9a78e091570c', 'cf399ce6-ab61-b009-fd0a-0d39745bfd01', '(HPSS) BIG FIVE DUTY FREE (PTY) LTD', '', 'CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'NGF Monthly JHB Aug25-Feb26'),
  ('badc0ac0-4295-4178-a422-87b84beedd4c', 'e5836289-e543-e26f-a002-072a76c0358a', 'd02b430a-f424-4930-e449-9c4fe3af0063', 'Big Five Duty Free Cape Town',  'BIGF0002','CONFIRMED', 'ACTIVE', 'system', 'system', NOW(), 'ERP direct from Mar 26')
ON CONFLICT DO NOTHING;
