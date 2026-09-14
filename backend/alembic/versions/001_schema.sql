-- =============================================================================
-- WATERFORD ESTATE SALES INTELLIGENCE SYSTEM
-- Complete Database Schema v1.0 — September 2026
-- PostgreSQL 15+
-- ALL AMBER ITEMS FROM STRESS TEST INCORPORATED
-- =============================================================================

-- =============================================================================
-- SECTION 0: EXTENSIONS AND AUDIT TRIGGER
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- for fuzzy text search on client names

-- Standard audit trigger applied to every table
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- SECTION 1: ENUMERATIONS (enforced at DB level, not application layer)
-- =============================================================================

-- Core commercial transaction type — CHECK constraint on sales_transactions
CREATE TYPE transaction_type_enum AS ENUM (
  'DIRECT_SALE',            -- Waterford → End Client (direct)
  'DISTRIBUTOR_SELL_IN',    -- Waterford → Distributor (wholesale)
  'DISTRIBUTOR_SELL_THROUGH', -- Distributor → End Client (sell-through)
  'DTC_SALE',               -- Waterford → Consumer (cellar door, wine club)
  'EXPORT_SALE'             -- Waterford → Foreign buyer (excluded from domestic)
);

-- R-value classification — enforced on sales_transaction_lines
CREATE TYPE r_value_status_enum AS ENUM (
  'CONFIRMED',   -- Actual R-value from ERP invoice
  'ESTIMATED',   -- Calculated from ASP × bottles
  'MISSING'      -- No R-value available
);

-- Data coverage per source/region/period
CREATE TYPE coverage_status_enum AS ENUM (
  'COVERED',          -- Data received and processed
  'PARTIAL',          -- Partial period only (e.g. VDP W1, not W4)
  'MISSING',          -- No data available — never shown as zero
  'NOT_APPLICABLE'    -- Source not active for this period/region
);

-- Client/product alias mapping confidence
CREATE TYPE match_confidence_enum AS ENUM (
  'CONFIRMED',      -- Human-confirmed match. Permanent.
  'PROBABLE',       -- System suggestion ≥75%. Needs human sign-off.
  'UNRESOLVED',     -- Cannot determine — held in review queue
  'DO_NOT_MATCH'    -- Confirmed different entities
);

-- Alias record lifecycle status
CREATE TYPE match_status_enum AS ENUM (
  'ACTIVE',       -- Currently used for matching
  'SUPERSEDED',   -- Replaced by a newer alias
  'REJECTED'      -- Human rejected this mapping
);

-- Double-count exclusion rules — exactly DC-001 through DC-006 + TX-TYPE
CREATE TYPE exclusion_rule_enum AS ENUM (
  'DC-001',   -- Sell-in and sell-through same SKU/distributor/period
  'DC-002',   -- Dual-channel: direct sale exists, sell-through excluded
  'DC-003',   -- Market view deduplication at client level
  'DC-004',   -- Big Five transition month
  'DC-005',   -- Norman Goodfellows dual-role separation
  'DC-006',   -- Query-level enforcement (belt and suspenders)
  'TX-TYPE'   -- Transaction type excluded from this view by design
);

-- Import pipeline states
CREATE TYPE import_status_enum AS ENUM (
  'UPLOADED', 'DUPLICATE_DETECTED', 'IDENTIFYING', 'IDENTIFICATION_REQUIRED',
  'IDENTIFIED', 'PERIOD_REQUIRED', 'VALIDATING', 'VALIDATION_FAILED',
  'VALIDATED', 'INGESTING_RAW', 'RAW_COMPLETE', 'MATCHING',
  'REVIEW_REQUIRED', 'NORMALISING', 'APPLYING_DC_RULES', 'UPDATING_COVERAGE',
  'COMPLETE', 'PARTIAL_COMPLETE', 'FAILED', 'SUPERSEDED'
);

-- Raw row status within a batch
CREATE TYPE row_status_enum AS ENUM (
  'PENDING', 'MAPPED', 'FAILED', 'EXCLUDED', 'PENDING_MAPPING', 'SUPERSEDED'
);

-- Import review queue issue types
CREATE TYPE queue_issue_enum AS ENUM (
  'UNKNOWN_CLIENT', 'PROBABLE_CLIENT', 'UNKNOWN_PRODUCT', 'MISSING_CASE_SIZE',
  'AMBIGUOUS_PERIOD', 'POTENTIAL_DUPLICATE', 'CORRECTED_REPORT',
  'UNRESOLVED_DEBTOR', 'VOLUME_ANOMALY', 'TRANSACTION_TYPE_AMBIGUITY',
  'DOWNGRADE_DETECTED'
);

-- Client classification
CREATE TYPE client_tier_enum AS ENUM (
  'KAM', 'ON_TRADE', 'RETAIL', 'WHOLESALE', 'DISTRIBUTOR', 'DTC',
  'PRIVATE', 'KEY_ACCOUNT'
);

-- Rep employment status
CREATE TYPE rep_status_enum AS ENUM (
  'ACTIVE', 'RESIGNED', 'DEPARTED', 'VACANT'
);

-- Opportunity lifecycle
CREATE TYPE opportunity_status_enum AS ENUM (
  'OPEN', 'WON', 'LOST', 'STALE', 'ON_HOLD'
);

-- CRM activity types
CREATE TYPE crm_activity_type_enum AS ENUM (
  'VISIT', 'CALL', 'TASTING', 'EMAIL', 'EVENT',
  'SAMPLE_DROP', 'TRAINING', 'LISTING_REVIEW', 'OTHER'
);

-- Follow-up status
CREATE TYPE follow_up_status_enum AS ENUM (
  'OPEN', 'COMPLETED', 'OVERDUE', 'CANCELLED'
);

-- Rep ownership change reason
CREATE TYPE ownership_change_reason_enum AS ENUM (
  'NEW_ACCOUNT', 'TERRITORY_RESTRUCTURE', 'REP_DEPARTURE',
  'ACCOUNT_TRANSFER', 'CHANNEL_SHIFT'
);

-- =============================================================================
-- SECTION 2: FINANCIAL PERIODS
-- =============================================================================

CREATE TABLE financial_years (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  year_label        VARCHAR(10) NOT NULL UNIQUE,   -- 'FY2026', 'FY2027'
  year_number       INTEGER     NOT NULL UNIQUE,   -- 2026, 2027
  start_date        DATE        NOT NULL,           -- 2025-07-01
  end_date          DATE        NOT NULL,           -- 2026-06-30
  is_current        BOOLEAN     NOT NULL DEFAULT FALSE,
  is_history        BOOLEAN     NOT NULL DEFAULT FALSE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by        VARCHAR(100) NOT NULL DEFAULT 'system',
  CONSTRAINT fy_dates_valid CHECK (end_date > start_date),
  CONSTRAINT fy_only_one_current EXCLUDE USING btree (is_current WITH =) WHERE (is_current = TRUE)
  -- NOTE: Postgres EXCLUDE constraint prevents two rows both having is_current=TRUE
  -- If your Postgres version doesn't support this syntax, enforce via unique partial index:
  -- CREATE UNIQUE INDEX one_current_fy ON financial_years (is_current) WHERE is_current = TRUE;
);

CREATE TABLE financial_periods (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  financial_year_id UUID        NOT NULL REFERENCES financial_years(id),
  period_number     INTEGER     NOT NULL CHECK (period_number BETWEEN 1 AND 12),
  -- 1=July, 2=August, ..., 12=June (maps to ERP finmth)
  period_name       VARCHAR(20) NOT NULL,   -- 'July 2026'
  calendar_month    INTEGER     NOT NULL CHECK (calendar_month BETWEEN 1 AND 12),
  calendar_year     INTEGER     NOT NULL CHECK (calendar_year BETWEEN 2020 AND 2040),
  start_date        DATE        NOT NULL,
  end_date          DATE        NOT NULL,
  is_closed         BOOLEAN     NOT NULL DEFAULT FALSE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (financial_year_id, period_number),
  CONSTRAINT period_dates_valid CHECK (end_date > start_date)
);

CREATE INDEX idx_fp_year ON financial_periods (financial_year_id);
CREATE INDEX idx_fp_dates ON financial_periods (start_date, end_date);

-- =============================================================================
-- SECTION 3: SOURCES, DISTRIBUTORS, CHANNELS
-- =============================================================================

CREATE TABLE channels (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  channel_code  VARCHAR(30) NOT NULL UNIQUE,
  -- DIRECT_ERP, NGF, VDP_GAU, DISTRILIQ_CPT, DISTRI_GEORGE, DTC, EXPORT
  channel_name  VARCHAR(100) NOT NULL,
  is_domestic   BOOLEAN     NOT NULL DEFAULT TRUE,
  is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE territories (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  territory_code    VARCHAR(20) NOT NULL UNIQUE,
  -- GAU, WC_CPT, WC_STELB, GARDEN_ROUTE, KZN, NATIONAL, EXPORT
  territory_name    VARCHAR(100) NOT NULL,
  is_domestic       BOOLEAN     NOT NULL DEFAULT TRUE,
  is_active         BOOLEAN     NOT NULL DEFAULT TRUE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE distributors (
  id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  distributor_code      VARCHAR(20) NOT NULL UNIQUE,
  -- NGF, VDP_GAU, DISTRILIQ_CPT, DISTRI_GEORGE
  distributor_name      VARCHAR(200) NOT NULL,
  erp_debtor_codes      VARCHAR[]   NOT NULL DEFAULT '{}',
  -- Array: ['NORM0002','NORMGF'] for NGF
  erp_primary_debtor    VARCHAR(20),  -- Main ERP code for sell-in invoice matching
  territory_id          UUID        REFERENCES territories(id),
  regions_covered       VARCHAR[]   NOT NULL DEFAULT '{}',
  -- e.g. '{CPT, JHB, KZN}' for NGF
  is_active             BOOLEAN     NOT NULL DEFAULT TRUE,
  notes                 TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE data_sources (
  id                            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  source_code                   VARCHAR(30) NOT NULL UNIQUE,
  -- ERP_EXPORT, NGF_MONTHLY, NGF_SALESOUT, VDP_WEEKLY_PDF, VDP_MONTHLY_EXCEL,
  -- DISTRILIQ_CPT, DISTRI_GEORGE, NGF_COMBINED_FY27
  source_name                   VARCHAR(100) NOT NULL,
  distributor_id                UUID        REFERENCES distributors(id),
  source_type                   VARCHAR(20) NOT NULL CHECK (source_type IN ('ERP','DISTRIBUTOR_REPORT','MANUAL')),
  transaction_types_produced    transaction_type_enum[] NOT NULL,
  default_region                VARCHAR(10),
  file_format                   VARCHAR(10) NOT NULL CHECK (file_format IN ('EXCEL','CSV','PDF','API')),
  expected_frequency            VARCHAR(20),
  -- WEEKLY, MONTHLY, ANNUAL, AD_HOC
  is_active                     BOOLEAN     NOT NULL DEFAULT TRUE,
  notes                         TEXT,
  created_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Source connector configurations (versioned — data-driven import engine)
CREATE TABLE source_configs (
  id                        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id                 UUID        NOT NULL REFERENCES data_sources(id),
  config_version            INTEGER     NOT NULL DEFAULT 1,
  is_active                 BOOLEAN     NOT NULL DEFAULT TRUE,
  file_format               VARCHAR(10) NOT NULL,
  expected_worksheets       JSONB,      -- Array of expected worksheet name patterns
  column_map                JSONB       NOT NULL,
  -- {"client_field":"CustomerName","product_field":"StockDescription",...}
  client_field              VARCHAR(100),
  client_code_field         VARCHAR(100),
  product_field             VARCHAR(100),
  product_code_field        VARCHAR(100),
  quantity_field            VARCHAR(100),
  unit_field                VARCHAR(100),
  default_unit              VARCHAR(20) NOT NULL DEFAULT 'BOTTLES',
  case_size_field           VARCHAR(100),
  r_value_field             VARCHAR(100),  -- NULL if no R-value in source
  date_field                VARCHAR(100),
  period_detection_strategy VARCHAR(50) NOT NULL,
  -- FROM_DATE_COLUMN, FROM_FILENAME, FROM_HEADER, FROM_WORKSHEET_NAME, MANUAL
  region_field              VARCHAR(100),
  default_region            VARCHAR(10),
  rep_field                 VARCHAR(100),
  transaction_type          transaction_type_enum NOT NULL,
  is_cumulative             BOOLEAN     NOT NULL DEFAULT FALSE,
  cumulative_key            VARCHAR(50),
  supersession_strategy     VARCHAR(50) NOT NULL DEFAULT 'NEVER',
  -- REPLACE_SAME_PERIOD, REPLACE_CUMULATIVE_SERIES, NEVER
  dedup_key_fields          JSONB,      -- Fields used to build transaction dedup key
  validation_rules          JSONB,      -- Required columns, numeric checks, etc.
  identification_signatures JSONB,      -- Patterns for auto-identification
  filename_patterns         JSONB,      -- Regex patterns for filename matching
  notes                     TEXT,
  created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by                VARCHAR(100) NOT NULL,
  UNIQUE (source_id, config_version)
);

-- =============================================================================
-- SECTION 4: REPS AND TERRITORY ASSIGNMENTS
-- =============================================================================

CREATE TABLE reps (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  rep_code          VARCHAR(20) NOT NULL UNIQUE,
  -- KOL001, SAN001, HEL001, MOY001, NAT001, SER001, JAN001, MAG001, WER001, HO001
  first_name        VARCHAR(100) NOT NULL,
  last_name         VARCHAR(100) NOT NULL,
  full_name         VARCHAR(200) NOT NULL,
  erp_srepname      VARCHAR(200) NOT NULL UNIQUE,  -- Exact match to ERP srepname field
  email             VARCHAR(200),
  phone             VARCHAR(50),
  role              VARCHAR(100) NOT NULL,
  channel_focus     VARCHAR(50),
  employment_status rep_status_enum NOT NULL DEFAULT 'ACTIVE',
  start_date        DATE,
  end_date          DATE,         -- NULL if still active
  departure_reason  TEXT,
  is_deleted        BOOLEAN     NOT NULL DEFAULT FALSE,
  deleted_at        TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by        VARCHAR(100) NOT NULL DEFAULT 'system',
  CONSTRAINT rep_end_after_start CHECK (end_date IS NULL OR end_date > start_date)
);

-- Effective-dated rep → territory assignments (SCD-2)
CREATE TABLE rep_territory_assignments (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  rep_id          UUID        NOT NULL REFERENCES reps(id),
  territory_id    UUID        NOT NULL REFERENCES territories(id),
  effective_from  DATE        NOT NULL,
  effective_to    DATE,       -- NULL = currently active
  notes           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by      VARCHAR(100) NOT NULL,
  CONSTRAINT rta_dates_valid CHECK (effective_to IS NULL OR effective_to > effective_from)
);

CREATE INDEX idx_rta_rep ON rep_territory_assignments (rep_id, effective_from);
CREATE INDEX idx_rta_territory ON rep_territory_assignments (territory_id);

-- =============================================================================
-- SECTION 5: MASTER CLIENT REGISTRY (MCR)
-- =============================================================================

CREATE TABLE client_groups (
  id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  group_name            VARCHAR(200) NOT NULL,
  group_type            VARCHAR(50) NOT NULL,
  -- RESTAURANT_CHAIN, HOTEL_GROUP, RETAIL_CHAIN, FRANCHISE, CORPORATE, OTHER
  is_national           BOOLEAN     NOT NULL DEFAULT FALSE,
  primary_contact_name  VARCHAR(200),
  primary_contact_email VARCHAR(200),
  notes                 TEXT,
  is_deleted            BOOLEAN     NOT NULL DEFAULT FALSE,
  deleted_at            TIMESTAMPTZ,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by            VARCHAR(100) NOT NULL DEFAULT 'system'
);

CREATE TABLE client_entities (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  client_group_id   UUID        REFERENCES client_groups(id),
  legal_name        VARCHAR(200) NOT NULL,
  registration_number VARCHAR(50),
  vat_number        VARCHAR(50),
  notes             TEXT,
  is_deleted        BOOLEAN     NOT NULL DEFAULT FALSE,
  deleted_at        TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by        VARCHAR(100) NOT NULL DEFAULT 'system'
);

-- THE CANONICAL CLIENT RECORD — MCR
CREATE TABLE clients (
  id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  client_entity_id      UUID        REFERENCES client_entities(id),
  client_group_id       UUID        REFERENCES client_groups(id),
  -- Denormalised from entity for query performance
  canonical_name        VARCHAR(200) NOT NULL,
  trading_name          VARCHAR(200),
  outlet_type           VARCHAR(50) NOT NULL,
  tier                  client_tier_enum NOT NULL,
  territory_id          UUID        NOT NULL REFERENCES territories(id),
  primary_channel_id    UUID        REFERENCES channels(id),
  secondary_channel_id  UUID        REFERENCES channels(id),
  is_distributor        BOOLEAN     NOT NULL DEFAULT FALSE,
  -- TRUE for entities that also distribute (e.g. Norman Goodfellows as buyer)
  distributor_entity_id UUID        REFERENCES distributors(id),
  -- AMBER ITEM 4: Links client record to its distributor role where dual-role exists
  -- e.g. cl-ngf-jhb-buyer.distributor_entity_id = dist-ngf-001
  is_group_buying       BOOLEAN     NOT NULL DEFAULT FALSE,
  is_active             BOOLEAN     NOT NULL DEFAULT TRUE,
  is_new_fy27           BOOLEAN     NOT NULL DEFAULT FALSE,
  physical_address      TEXT,
  city                  VARCHAR(100),
  province              VARCHAR(50),
  primary_contact_name  VARCHAR(200),
  primary_contact_email VARCHAR(200),
  primary_contact_role  VARCHAR(100),
  -- Denormalised for performance — updated by trigger
  last_order_date       DATE,
  last_visit_date       DATE,
  notes                 TEXT,
  is_deleted            BOOLEAN     NOT NULL DEFAULT FALSE,
  deleted_at            TIMESTAMPTZ,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by            VARCHAR(100) NOT NULL DEFAULT 'system'
);

CREATE INDEX idx_clients_territory ON clients (territory_id);
CREATE INDEX idx_clients_canonical ON clients USING gin (to_tsvector('english', canonical_name));
-- GIN index for full-text search on client name
CREATE INDEX idx_clients_group ON clients (client_group_id) WHERE client_group_id IS NOT NULL;
CREATE INDEX idx_clients_active ON clients (is_active, territory_id);

-- Client source alias mapping — THE KEY ENTITY RESOLUTION TABLE
CREATE TABLE client_source_aliases (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id         UUID        NOT NULL REFERENCES clients(id),
  source_id         UUID        NOT NULL REFERENCES data_sources(id),
  source_name       VARCHAR(500) NOT NULL,  -- Original name from source, preserved exactly
  source_code       VARCHAR(100),           -- Source system debtor/customer code (e.g. THE043)
  match_confidence  match_confidence_enum NOT NULL,
  match_status      match_status_enum NOT NULL DEFAULT 'ACTIVE',
  matched_by        VARCHAR(100) NOT NULL,
  -- 'FUZZY_AUTO' for system suggestions; user ID for human confirmations
  confirmed_by      VARCHAR(100),
  -- MUST be a human user ID. NULL until human confirms.
  -- CHECK: match_confidence='CONFIRMED' requires confirmed_by IS NOT NULL
  confirmed_at      TIMESTAMPTZ,
  effective_from    DATE        NOT NULL DEFAULT CURRENT_DATE,
  effective_to      DATE,       -- NULL = currently active
  alias_notes       TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT alias_confirmed_requires_human
    CHECK (match_confidence != 'CONFIRMED' OR confirmed_by IS NOT NULL),
  -- A CONFIRMED alias must have a human sign-off
  CONSTRAINT alias_effective_dates
    CHECK (effective_to IS NULL OR effective_to > effective_from)
);

CREATE UNIQUE INDEX idx_csa_source_code
  ON client_source_aliases (source_id, source_code)
  WHERE source_code IS NOT NULL AND match_status = 'ACTIVE';
-- Unique code per source (when code exists and active)

CREATE INDEX idx_csa_source_name ON client_source_aliases (source_id, match_status);
CREATE INDEX idx_csa_client ON client_source_aliases (client_id);
CREATE INDEX idx_csa_name_trgm ON client_source_aliases
  USING gin (source_name gin_trgm_ops);
-- Trigram index for fast fuzzy matching queries

-- Effective-dated client → rep ownership (SCD-2) — SINGLE SOURCE OF TRUTH
-- AMBER ITEM 2: rep_id REMOVED from sales_transactions. This table is the ONLY
-- source of rep attribution. Queries derive rep via JOIN on client_id + date.
CREATE TABLE client_ownership (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id       UUID        NOT NULL REFERENCES clients(id),
  rep_id          UUID        NOT NULL REFERENCES reps(id),
  territory_id    UUID        REFERENCES territories(id),
  channel_id      UUID        REFERENCES channels(id),
  distributor_id  UUID        REFERENCES distributors(id),
  effective_from  DATE        NOT NULL,
  effective_to    DATE,       -- NULL = currently active
  change_reason   ownership_change_reason_enum NOT NULL,
  approved_by     VARCHAR(100),
  notes           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by      VARCHAR(100) NOT NULL
);

CREATE INDEX idx_ownership_client_date
  ON client_ownership (client_id, effective_from, effective_to);
-- Critical index for the "rep at time of sale" lookup

-- =============================================================================
-- SECTION 6: PRODUCTS AND SKUs
-- =============================================================================

CREATE TABLE products (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  product_code    VARCHAR(20) NOT NULL UNIQUE,
  -- RM, KAS, CAB, JEM, ANT, PS_CHENIN, PS_SB, PS_RED, CHD, ELG, GRN, HEA, OVP
  product_name    VARCHAR(200) NOT NULL,
  brand_name      VARCHAR(100) NOT NULL DEFAULT 'Waterford Estate',
  tier            VARCHAR(20) NOT NULL CHECK (tier IN ('ICON','PREMIUM','ENTRY')),
  is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
  launch_vintage  INTEGER,
  notes           TEXT,
  is_deleted      BOOLEAN     NOT NULL DEFAULT FALSE,
  deleted_at      TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by      VARCHAR(100) NOT NULL DEFAULT 'system'
);

CREATE TABLE product_skus (
  id                        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id                UUID        NOT NULL REFERENCES products(id),
  sku_code                  VARCHAR(20) NOT NULL UNIQUE,
  -- RM001, KAS001, KAS1L, CAB001, CAB375, CAB1L, JEM001, etc.
  sku_name                  VARCHAR(200) NOT NULL,
  bottle_size_ml            INTEGER     NOT NULL CHECK (bottle_size_ml IN (187,375,500,750,1500,3000)),
  standard_bottle_equivalent DECIMAL(4,3) NOT NULL,
  -- 375ml=0.500, 500ml=0.667, 750ml=1.000, 1500ml=2.000
  default_case_size         INTEGER,
  -- INFORMATIONAL ONLY — never used in transaction calculations
  tier                      VARCHAR(20) NOT NULL CHECK (tier IN ('ICON','PREMIUM','ENTRY')),
  is_active                 BOOLEAN     NOT NULL DEFAULT TRUE,
  is_deleted                BOOLEAN     NOT NULL DEFAULT FALSE,
  deleted_at                TIMESTAMPTZ,
  created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by                VARCHAR(100) NOT NULL DEFAULT 'system',
  CONSTRAINT sbe_matches_size CHECK (
    (bottle_size_ml = 375  AND standard_bottle_equivalent = 0.500) OR
    (bottle_size_ml = 500  AND standard_bottle_equivalent = 0.667) OR
    (bottle_size_ml = 750  AND standard_bottle_equivalent = 1.000) OR
    (bottle_size_ml = 1500 AND standard_bottle_equivalent = 2.000) OR
    (bottle_size_ml NOT IN (375,500,750,1500))
    -- Allow non-standard sizes with manual SBE
  )
);

CREATE TABLE product_source_aliases (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  product_sku_id    UUID        NOT NULL REFERENCES product_skus(id),
  source_id         UUID        NOT NULL REFERENCES data_sources(id),
  source_description VARCHAR(500) NOT NULL,  -- Original description from source
  source_sku_code   VARCHAR(100),            -- Source product code if available
  match_confidence  match_confidence_enum NOT NULL,
  confirmed_by      VARCHAR(100),
  confirmed_at      TIMESTAMPTZ,
  is_active         BOOLEAN     NOT NULL DEFAULT TRUE,
  notes             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT product_alias_confirmed_requires_human
    CHECK (match_confidence != 'CONFIRMED' OR confirmed_by IS NOT NULL)
);

CREATE INDEX idx_psa_source ON product_source_aliases (source_id, is_active);
CREATE INDEX idx_psa_desc_trgm ON product_source_aliases
  USING gin (source_description gin_trgm_ops);

-- =============================================================================
-- SECTION 7: ASP VERSIONS (versioned pricing for distributor revenue estimation)
-- =============================================================================

CREATE TABLE asp_versions (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  product_sku_id  UUID        NOT NULL REFERENCES product_skus(id),
  asp_value       DECIMAL(10,2) NOT NULL CHECK (asp_value > 0),
  currency        VARCHAR(3)  NOT NULL DEFAULT 'ZAR',
  effective_from  DATE        NOT NULL,
  effective_to    DATE,       -- NULL = currently active
  source_document VARCHAR(200) NOT NULL,  -- e.g. 'Sergio King FY2027 Target Sheet'
  methodology     VARCHAR(50) NOT NULL,
  -- TARGET_SHEET_DERIVED, ERP_WEIGHTED_AVERAGE, MANUAL_OVERRIDE, BLENDED_CATEGORY
  is_approved     BOOLEAN     NOT NULL DEFAULT FALSE,
  approved_by     VARCHAR(100),
  approved_at     TIMESTAMPTZ,
  notes           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by      VARCHAR(100) NOT NULL,
  CONSTRAINT asp_dates_valid CHECK (effective_to IS NULL OR effective_to > effective_from),
  CONSTRAINT asp_approved_requires_approver CHECK (NOT is_approved OR approved_by IS NOT NULL)
);

CREATE INDEX idx_asp_sku_dates ON asp_versions (product_sku_id, effective_from, effective_to);
-- Critical index for "find ASP in effect on date X" lookup

-- =============================================================================
-- SECTION 8: IMPORT / INGESTION LAYER
-- =============================================================================

CREATE TABLE import_batches (
  id                          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id                   UUID        NOT NULL REFERENCES data_sources(id),
  source_config_id            UUID        REFERENCES source_configs(id),
  file_name                   VARCHAR(500) NOT NULL,
  file_path                   VARCHAR(1000) NOT NULL,  -- S3/storage path — permanent
  file_hash                   VARCHAR(64) NOT NULL,    -- SHA-256
  file_size_bytes             BIGINT      NOT NULL,
  received_date               DATE        NOT NULL,
  imported_at                 TIMESTAMPTZ,
  imported_by                 VARCHAR(100) NOT NULL,
  period_from                 DATE,
  period_to                   DATE,
  report_type                 VARCHAR(50),  -- NGF_MONTHLY, VDP_WEEKLY, ERP_EXPORT, etc.
  report_version              VARCHAR(10),  -- W1, W2, W3, W4, W5 for VDP cumulative
  is_cumulative               BOOLEAN     NOT NULL DEFAULT FALSE,
  identified_automatically    BOOLEAN     NOT NULL DEFAULT FALSE,
  identification_confidence   DECIMAL(5,2),  -- 0.00-100.00
  parser_version              VARCHAR(20),
  status                      import_status_enum NOT NULL DEFAULT 'UPLOADED',
  validation_errors           JSONB,
  rows_total                  INTEGER,
  rows_valid                  INTEGER,
  rows_failed                 INTEGER,
  rows_pending_mapping        INTEGER,
  rows_imported               INTEGER,
  stated_total                DECIMAL(10,2),  -- Grand total from source (for validation)
  supersedes_batch_id         UUID        REFERENCES import_batches(id),
  superseded_by_batch_id      UUID        REFERENCES import_batches(id),
  notes                       TEXT,
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by                  VARCHAR(100) NOT NULL DEFAULT 'system',
  CONSTRAINT hash_unique_per_status
    UNIQUE (file_hash)  -- Prevents exact duplicate files
    -- Actual dedup logic: if hash exists and status=COMPLETE, reject. Allow re-hash on FAILED.
);

CREATE INDEX idx_ib_source ON import_batches (source_id, status);
CREATE INDEX idx_ib_period ON import_batches (period_from, period_to);
CREATE INDEX idx_ib_hash ON import_batches (file_hash);

-- Immutable raw rows — NEVER modified after creation
CREATE TABLE import_raw_rows (
  id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id            UUID        NOT NULL REFERENCES import_batches(id),
  row_number          INTEGER     NOT NULL,
  raw_data            JSONB       NOT NULL,
  -- Complete original row as key-value. IMMUTABLE after insert.
  row_status          row_status_enum NOT NULL DEFAULT 'PENDING',
  transaction_id      UUID,
  -- FK to sales_transactions added after that table created (circular ref avoided via deferred)
  client_alias_id     UUID        REFERENCES client_source_aliases(id),
  product_alias_id    UUID        REFERENCES product_source_aliases(id),
  case_size_required  BOOLEAN     NOT NULL DEFAULT FALSE,
  -- AMBER ITEM 3: TRUE when unit=CASES but no case size in source document
  mapping_error       VARCHAR(500),
  exclusion_reason    VARCHAR(200),
  matching_attempts   JSONB,      -- Log of all 5 matching stages tried for this row
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
  -- NOTE: No updated_at — raw rows are immutable
);

CREATE INDEX idx_irr_batch ON import_raw_rows (batch_id, row_status);
CREATE INDEX idx_irr_transaction ON import_raw_rows (transaction_id)
  WHERE transaction_id IS NOT NULL;

-- Import review queue items
CREATE TABLE import_queue_items (
  id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  import_batch_id       UUID        NOT NULL REFERENCES import_batches(id),
  import_raw_row_id     UUID        NOT NULL REFERENCES import_raw_rows(id),
  issue_type            queue_issue_enum NOT NULL,
  severity              VARCHAR(10) NOT NULL CHECK (severity IN ('HIGH','MEDIUM','LOW')),
  status                VARCHAR(20) NOT NULL DEFAULT 'OPEN'
                        CHECK (status IN ('OPEN','RESOLVED','REJECTED','BULK_APPROVED','IGNORED')),
  source_value          VARCHAR(500) NOT NULL,  -- The problematic value
  suggested_resolution  JSONB,
  can_bulk_approve      BOOLEAN     NOT NULL DEFAULT FALSE,
  resolution_type       VARCHAR(20) CHECK (resolution_type IN ('ACCEPTED','REJECTED','NEW_CANONICAL','EDITED')),
  resolved_by           VARCHAR(100),
  resolved_at           TIMESTAMPTZ,
  resolution_notes      TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_queue_batch ON import_queue_items (import_batch_id, status);
CREATE INDEX idx_queue_status ON import_queue_items (status, severity);

-- =============================================================================
-- SECTION 9: SALES TRANSACTIONS
-- =============================================================================

CREATE TABLE sales_transactions (
  id                        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  import_raw_row_id         UUID        NOT NULL REFERENCES import_raw_rows(id),
  source_id                 UUID        NOT NULL REFERENCES data_sources(id),
  transaction_type          transaction_type_enum NOT NULL,
  transaction_date          DATE        NOT NULL,
  financial_year_id         UUID        NOT NULL REFERENCES financial_years(id),
  financial_period_id       UUID        NOT NULL REFERENCES financial_periods(id),
  distributor_id            UUID        REFERENCES distributors(id),
  client_id                 UUID        NOT NULL REFERENCES clients(id),
  -- AMBER ITEM 2: rep_id REMOVED. Rep is derived at query time via:
  -- SELECT rep_id FROM client_ownership
  -- WHERE client_id = st.client_id
  -- AND effective_from <= st.transaction_date
  -- AND (effective_to IS NULL OR effective_to >= st.transaction_date)
  territory_id              UUID        REFERENCES territories(id),
  source_invoice_no         VARCHAR(100),
  source_order_no           VARCHAR(100),
  source_ref                VARCHAR(200),
  dedup_key                 VARCHAR(500),
  -- Hash of transaction_type+financial_period_id+client_id+source_id for dedup
  is_primary_record         BOOLEAN     NOT NULL DEFAULT TRUE,
  -- FALSE when superseded by newer version (e.g. W4 supersedes W3)
  superseded_by_id          UUID        REFERENCES sales_transactions(id),
  excluded_from_market_view BOOLEAN     NOT NULL DEFAULT FALSE,
  -- AMBER ITEM 1: Three supporting fields for full exclusion auditability:
  exclusion_rule            exclusion_rule_enum,
  -- DC-001 through DC-006 or TX-TYPE. NULL when not excluded.
  exclusion_context         JSONB,
  -- {"competing_transaction_id":"uuid","reason":"DIRECT_SALE_EXISTS_FOR_PERIOD",
  --  "direct_sale_period":"fp-fy26-02"}
  exclusion_evaluated_at    TIMESTAMPTZ,
  -- When the DC rule was applied. Updates if rules are re-evaluated.
  created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by                VARCHAR(100) NOT NULL DEFAULT 'system',
  -- Referential integrity: distributor required for distributor transaction types
  CONSTRAINT distributor_required_for_sell_in
    CHECK (transaction_type NOT IN ('DISTRIBUTOR_SELL_IN','DISTRIBUTOR_SELL_THROUGH')
           OR distributor_id IS NOT NULL),
  -- Exclusion context required when excluded
  CONSTRAINT exclusion_context_when_excluded
    CHECK (NOT excluded_from_market_view
           OR (exclusion_rule IS NOT NULL AND exclusion_evaluated_at IS NOT NULL))
);

CREATE INDEX idx_st_client_period ON sales_transactions (client_id, financial_period_id, is_primary_record);
CREATE INDEX idx_st_period ON sales_transactions (financial_period_id, transaction_type, is_primary_record);
CREATE INDEX idx_st_source ON sales_transactions (source_id, financial_period_id);
CREATE INDEX idx_st_distributor ON sales_transactions (distributor_id, financial_period_id)
  WHERE distributor_id IS NOT NULL;
CREATE INDEX idx_st_market_view ON sales_transactions (excluded_from_market_view, is_primary_record, transaction_type);
-- Critical index for v_end_client_market filter
CREATE UNIQUE INDEX idx_st_dedup ON sales_transactions (dedup_key) WHERE dedup_key IS NOT NULL AND is_primary_record = TRUE;

-- Add FK from import_raw_rows to sales_transactions (deferred to avoid circular dependency)
ALTER TABLE import_raw_rows
  ADD CONSTRAINT fk_irr_transaction
  FOREIGN KEY (transaction_id) REFERENCES sales_transactions(id)
  DEFERRABLE INITIALLY DEFERRED;

-- Transaction line items
CREATE TABLE sales_transaction_lines (
  id                          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  transaction_id              UUID        NOT NULL REFERENCES sales_transactions(id),
  product_sku_id              UUID        NOT NULL REFERENCES product_skus(id),
  vintage                     INTEGER     CHECK (vintage BETWEEN 1990 AND 2040),
  source_product_description  VARCHAR(500) NOT NULL,  -- Original from source — never modified
  source_product_code         VARCHAR(100),
  -- Quantities — original from source
  quantity_original           DECIMAL(10,3) NOT NULL,
  unit_original               VARCHAR(30) NOT NULL,
  -- BOTTLES, CASES, X1, UNITS, EACH, EACH
  case_size_actual            INTEGER,
  -- From source document ONLY. Never assumed from product defaults.
  -- Bottles — derived
  bottles_actual              DECIMAL(10,3) NOT NULL CHECK (bottles_actual != 0),
  -- For credits: negative. For sales: positive.
  standard_bottle_equiv       DECIMAL(10,3) NOT NULL,
  litres                      DECIMAL(10,3) NOT NULL,
  -- R-values
  rand_value_confirmed        DECIMAL(12,2),  -- From ERP invoice (grossval - discval)
  rand_value_estimated        DECIMAL(12,2),  -- Calculated: bottles_actual × ASP
  r_value_status              r_value_status_enum NOT NULL,
  asp_version_id              UUID        REFERENCES asp_versions(id),
  -- Required when r_value_status = ESTIMATED — locks historical price permanently
  discount_amount             DECIMAL(12,2),
  discount_pct                DECIMAL(5,2),
  currency                    VARCHAR(3)  NOT NULL DEFAULT 'ZAR',
  raw_data                    JSONB,      -- Subset of original row for this line
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  -- R-value integrity constraints
  CONSTRAINT confirmed_rvalue_not_null
    CHECK (r_value_status != 'CONFIRMED' OR rand_value_confirmed IS NOT NULL),
  CONSTRAINT estimated_rvalue_not_null
    CHECK (r_value_status != 'ESTIMATED' OR (rand_value_estimated IS NOT NULL AND asp_version_id IS NOT NULL)),
  CONSTRAINT estimated_asp_required
    CHECK (r_value_status != 'ESTIMATED' OR asp_version_id IS NOT NULL)
);

CREATE INDEX idx_stl_transaction ON sales_transaction_lines (transaction_id);
CREATE INDEX idx_stl_sku_period ON sales_transaction_lines (product_sku_id);
-- Note: join to sales_transactions for period filtering

-- =============================================================================
-- SECTION 10: DATA COVERAGE
-- =============================================================================

CREATE TABLE data_coverage (
  id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id           UUID        NOT NULL REFERENCES data_sources(id),
  region              VARCHAR(20) NOT NULL,  -- CPT, JHB, KZN, GAU, ALL
  financial_period_id UUID        NOT NULL REFERENCES financial_periods(id),
  coverage_status     coverage_status_enum NOT NULL,
  import_batch_id     UUID        REFERENCES import_batches(id),
  notes               VARCHAR(500),
  last_evaluated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (source_id, region, financial_period_id)
  -- One coverage record per source+region+period combination
);

CREATE INDEX idx_coverage_period ON data_coverage (financial_period_id, coverage_status);
CREATE INDEX idx_coverage_source ON data_coverage (source_id, financial_period_id);

-- =============================================================================
-- SECTION 11: TARGETS
-- =============================================================================

-- AMBER ITEM 5: MVP uses combined Gauteng territory targets.
-- V2 will add individual rep targets via Target Entry UI.
-- Both are supported by this schema.
CREATE TABLE target_sets (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  financial_year_id UUID        NOT NULL REFERENCES financial_years(id),
  set_name          VARCHAR(200) NOT NULL,
  -- 'FY2027 Initial — Gauteng Combined'
  -- 'FY2027 Individual Reps Phase 2'
  is_active         BOOLEAN     NOT NULL DEFAULT TRUE,
  target_level      VARCHAR(20) NOT NULL DEFAULT 'TERRITORY',
  -- TERRITORY (MVP) or REP (Phase 2)
  source_document   VARCHAR(200),
  approved_by       VARCHAR(100),
  approved_at       TIMESTAMPTZ,
  notes             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by        VARCHAR(100) NOT NULL
);

CREATE TABLE targets (
  id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  target_set_id         UUID        NOT NULL REFERENCES target_sets(id),
  rep_id                UUID        REFERENCES reps(id),
  -- NULL for territory-level targets (MVP)
  territory_id          UUID        REFERENCES territories(id),
  -- Set for territory-level targets (MVP: GAU territory)
  product_sku_id        UUID        REFERENCES product_skus(id),
  -- NULL = total target across all SKUs for this rep/territory/period
  financial_period_id   UUID        NOT NULL REFERENCES financial_periods(id),
  target_bottles        DECIMAL(10,2) NOT NULL CHECK (target_bottles >= 0),
  target_rand_value     DECIMAL(12,2) NOT NULL CHECK (target_rand_value >= 0),
  source_document       VARCHAR(200),
  notes                 TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by            VARCHAR(100) NOT NULL,
  CONSTRAINT target_has_owner
    CHECK (rep_id IS NOT NULL OR territory_id IS NOT NULL)
  -- Either rep_id or territory_id must be set
);

CREATE INDEX idx_targets_period ON targets (financial_period_id, target_set_id);
CREATE INDEX idx_targets_rep ON targets (rep_id, financial_period_id)
  WHERE rep_id IS NOT NULL;
CREATE INDEX idx_targets_territory ON targets (territory_id, financial_period_id)
  WHERE territory_id IS NOT NULL;

-- Target version history (full audit trail)
CREATE TABLE target_versions (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  target_id         UUID        NOT NULL REFERENCES targets(id),
  version_number    INTEGER     NOT NULL,
  target_bottles    DECIMAL(10,2) NOT NULL,
  target_rand_value DECIMAL(12,2) NOT NULL,
  changed_reason    TEXT,
  approved_by       VARCHAR(100),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by        VARCHAR(100) NOT NULL,
  UNIQUE (target_id, version_number)
);

-- =============================================================================
-- SECTION 12: CRM LAYER
-- =============================================================================

CREATE TABLE crm_activities (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id         UUID        NOT NULL REFERENCES clients(id),
  rep_id            UUID        NOT NULL REFERENCES reps(id),
  activity_date     DATE        NOT NULL,
  activity_type     crm_activity_type_enum NOT NULL,
  is_planned        BOOLEAN     NOT NULL DEFAULT FALSE,
  duration_minutes  INTEGER     CHECK (duration_minutes > 0),
  objective         TEXT,
  outcome           TEXT,
  competitor_notes  TEXT,
  general_notes     TEXT        NOT NULL DEFAULT '',
  overall_sentiment VARCHAR(20) CHECK (overall_sentiment IN ('POSITIVE','NEUTRAL','NEGATIVE','AT_RISK')),
  status            VARCHAR(20) NOT NULL DEFAULT 'COMPLETED'
                    CHECK (status IN ('COMPLETED','CANCELLED','NO_SHOW')),
  is_deleted        BOOLEAN     NOT NULL DEFAULT FALSE,
  deleted_at        TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by        VARCHAR(100) NOT NULL
);

CREATE INDEX idx_activities_client ON crm_activities (client_id, activity_date);
CREATE INDEX idx_activities_rep ON crm_activities (rep_id, activity_date);

CREATE TABLE crm_activity_products (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  activity_id     UUID        NOT NULL REFERENCES crm_activities(id),
  product_sku_id  UUID        NOT NULL REFERENCES product_skus(id),
  discussion_type VARCHAR(30) NOT NULL
    CHECK (discussion_type IN (
      'LISTED','DELISTED','PRICE_CONCERN','STOCK_ISSUE','PROMOTION',
      'TASTING','ENQUIRY','COMPLAINT','OTHER'
    )),
  notes           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- SECTION 13: OPPORTUNITIES AND FOLLOW-UPS
-- =============================================================================

CREATE TABLE crm_opportunities (
  id                          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id                   UUID        NOT NULL REFERENCES clients(id),
  rep_id                      UUID        NOT NULL REFERENCES reps(id),
  activity_id                 UUID        REFERENCES crm_activities(id),
  opportunity_type            VARCHAR(50) NOT NULL,
  title                       VARCHAR(200) NOT NULL,
  description                 TEXT,
  estimated_bottles_annual    INTEGER,
  estimated_rand_value_annual DECIMAL(12,2),
  status                      opportunity_status_enum NOT NULL DEFAULT 'OPEN',
  probability_pct             INTEGER     CHECK (probability_pct BETWEEN 0 AND 100),
  target_close_date           DATE,
  actual_close_date           DATE,
  lost_reason                 TEXT,
  notes                       TEXT,
  is_deleted                  BOOLEAN     NOT NULL DEFAULT FALSE,
  deleted_at                  TIMESTAMPTZ,
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by                  VARCHAR(100) NOT NULL
);

CREATE INDEX idx_opp_client ON crm_opportunities (client_id, status);
CREATE INDEX idx_opp_rep ON crm_opportunities (rep_id, status);

CREATE TABLE crm_follow_ups (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id         UUID        NOT NULL REFERENCES clients(id),
  rep_id            UUID        NOT NULL REFERENCES reps(id),
  activity_id       UUID        REFERENCES crm_activities(id),
  opportunity_id    UUID        REFERENCES crm_opportunities(id),
  follow_up_type    VARCHAR(50) NOT NULL,
  due_date          DATE        NOT NULL,
  description       TEXT        NOT NULL,
  priority          VARCHAR(10) NOT NULL CHECK (priority IN ('HIGH','MEDIUM','LOW')),
  status            follow_up_status_enum NOT NULL DEFAULT 'OPEN',
  completed_at      TIMESTAMPTZ,
  completed_notes   TEXT,
  is_deleted        BOOLEAN     NOT NULL DEFAULT FALSE,
  deleted_at        TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by        VARCHAR(100) NOT NULL
);

CREATE INDEX idx_followup_rep_due ON crm_follow_ups (rep_id, due_date, status);
CREATE INDEX idx_followup_client ON crm_follow_ups (client_id, status);

CREATE TABLE client_notes (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id   UUID        NOT NULL REFERENCES clients(id),
  rep_id      UUID        NOT NULL REFERENCES reps(id),
  note_text   TEXT        NOT NULL,
  is_deleted  BOOLEAN     NOT NULL DEFAULT FALSE,
  deleted_at  TIMESTAMPTZ,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by  VARCHAR(100) NOT NULL
);

-- =============================================================================
-- SECTION 14: AUDIT AND PROVENANCE
-- =============================================================================

-- Records every MCR confirmation decision
CREATE TABLE mcr_decisions (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  alias_id          UUID        NOT NULL REFERENCES client_source_aliases(id),
  decision_type     VARCHAR(20) NOT NULL
    CHECK (decision_type IN ('CONFIRMED','REJECTED','NEW_CANONICAL','SUPERSEDED')),
  previous_client_id UUID       REFERENCES clients(id),
  new_client_id     UUID        REFERENCES clients(id),
  decided_by        VARCHAR(100) NOT NULL,  -- Always a human user ID
  decided_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  reason            TEXT,
  import_queue_item_id UUID     REFERENCES import_queue_items(id)
);

-- System-wide audit log for sensitive operations
CREATE TABLE audit_log (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  table_name    VARCHAR(100) NOT NULL,
  record_id     UUID        NOT NULL,
  operation     VARCHAR(10) NOT NULL CHECK (operation IN ('INSERT','UPDATE','DELETE','APPROVE','SUPERSEDE')),
  changed_by    VARCHAR(100) NOT NULL,
  changed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  old_values    JSONB,
  new_values    JSONB,
  change_reason TEXT
);

CREATE INDEX idx_audit_table_record ON audit_log (table_name, record_id);
CREATE INDEX idx_audit_user ON audit_log (changed_by, changed_at);

-- =============================================================================
-- SECTION 15: REPORTING VIEWS (defined here, not materialised for now)
-- =============================================================================

-- v_wf_sell_in: What Waterford invoiced to distributors
CREATE OR REPLACE VIEW v_wf_sell_in AS
SELECT
  st.id AS transaction_id,
  st.transaction_date,
  st.financial_year_id,
  st.financial_period_id,
  st.distributor_id,
  st.client_id,
  stl.product_sku_id,
  stl.vintage,
  stl.bottles_actual,
  stl.standard_bottle_equiv,
  stl.litres,
  stl.rand_value_confirmed,
  stl.r_value_status,
  stl.currency
FROM sales_transactions st
JOIN sales_transaction_lines stl ON stl.transaction_id = st.id
WHERE st.transaction_type = 'DISTRIBUTOR_SELL_IN'
  AND st.is_primary_record = TRUE;

-- v_direct_sales: Waterford directly to end clients
CREATE OR REPLACE VIEW v_direct_sales AS
SELECT
  st.id AS transaction_id,
  st.transaction_date,
  st.financial_year_id,
  st.financial_period_id,
  st.client_id,
  stl.product_sku_id,
  stl.vintage,
  stl.bottles_actual,
  stl.standard_bottle_equiv,
  stl.litres,
  stl.rand_value_confirmed,
  stl.r_value_status
FROM sales_transactions st
JOIN sales_transaction_lines stl ON stl.transaction_id = st.id
WHERE st.transaction_type = 'DIRECT_SALE'
  AND st.is_primary_record = TRUE;

-- v_dist_sell_through: What distributors sold to end clients
CREATE OR REPLACE VIEW v_dist_sell_through AS
SELECT
  st.id AS transaction_id,
  st.transaction_date,
  st.financial_year_id,
  st.financial_period_id,
  st.distributor_id,
  st.client_id,
  stl.product_sku_id,
  stl.vintage,
  stl.bottles_actual,
  stl.standard_bottle_equiv,
  stl.litres,
  stl.rand_value_estimated,
  stl.r_value_status,
  stl.asp_version_id
FROM sales_transactions st
JOIN sales_transaction_lines stl ON stl.transaction_id = st.id
WHERE st.transaction_type = 'DISTRIBUTOR_SELL_THROUGH'
  AND st.is_primary_record = TRUE;

-- v_end_client_market: Deduplicated market-facing view
-- DC rules already applied at write time via excluded_from_market_view
CREATE OR REPLACE VIEW v_end_client_market AS
SELECT
  st.id AS transaction_id,
  st.transaction_date,
  st.financial_year_id,
  st.financial_period_id,
  st.transaction_type,
  st.distributor_id,
  st.client_id,
  st.territory_id,
  stl.product_sku_id,
  stl.vintage,
  stl.bottles_actual,
  stl.standard_bottle_equiv,
  stl.litres,
  stl.rand_value_confirmed,
  stl.rand_value_estimated,
  stl.r_value_status,
  stl.asp_version_id,
  -- Convenience: single revenue figure (confirmed where available, estimated otherwise)
  COALESCE(stl.rand_value_confirmed, stl.rand_value_estimated) AS rand_value_best,
  st.excluded_from_market_view,  -- Always FALSE in this view (filtered below)
  st.exclusion_rule,
  st.exclusion_context
FROM sales_transactions st
JOIN sales_transaction_lines stl ON stl.transaction_id = st.id
WHERE st.transaction_type IN ('DIRECT_SALE', 'DISTRIBUTOR_SELL_THROUGH', 'DTC_SALE')
  AND st.excluded_from_market_view = FALSE
  AND st.is_primary_record = TRUE;

-- Rep attribution function: single authoritative source — client_ownership
-- Called from application code, not embedded in views, for performance
-- But shown here for documentation:
COMMENT ON TABLE client_ownership IS
  'AUTHORITATIVE SOURCE FOR REP ATTRIBUTION. Use: SELECT rep_id FROM client_ownership
   WHERE client_id=$1 AND effective_from <= $2 AND (effective_to IS NULL OR effective_to >= $2)
   ORDER BY effective_from DESC LIMIT 1';

-- =============================================================================
-- SECTION 16: UPDATED_AT TRIGGERS (applied to all mutable tables)
-- =============================================================================

-- Apply updated_at trigger to all mutable tables
DO $$
DECLARE
  t TEXT;
BEGIN
  FOR t IN SELECT unnest(ARRAY[
    'financial_years','financial_periods','channels','territories','distributors',
    'data_sources','source_configs','reps','clients','client_groups','client_entities',
    'client_source_aliases','client_ownership','products','product_skus',
    'product_source_aliases','asp_versions','import_batches','import_queue_items',
    'sales_transactions','data_coverage','target_sets','targets','crm_activities',
    'crm_opportunities','crm_follow_ups','client_notes'
  ]) LOOP
    EXECUTE format(
      'CREATE TRIGGER trg_%s_updated_at
       BEFORE UPDATE ON %s
       FOR EACH ROW EXECUTE FUNCTION set_updated_at()',
      t, t
    );
  END LOOP;
END $$;

-- =============================================================================
-- END OF SCHEMA
-- =============================================================================
