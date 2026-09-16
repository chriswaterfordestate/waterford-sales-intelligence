-- Migration 013: Master data corrections
-- 1. Sergio King (SER001): correct employment_status from RESIGNED to ACTIVE.
--    The Sergio/Nathalie WC restructure was never approved. This reverts the
--    incorrect seed. His history, ASP data and ERP transactions are untouched.
-- 2. Register 18 additional Makro ERP store codes as aliases to the existing
--    "Makro" canonical client. All are Massmart trading as Makro at specific
--    store locations. The canonical client already exists; these are provenance aliases.
--
-- Safe forward migration:
--   - UPDATE uses WHERE clause scoped to SER001 only.
--   - INSERT aliases use ON CONFLICT DO NOTHING (idempotent).
--   - No deletes, no cascade effects.

-- ── 1. Correct Sergio King ──────────────────────────────────────────────────
UPDATE reps
SET    employment_status = 'ACTIVE',
       end_date          = NULL,
       departure_reason  = NULL,
       updated_at        = NOW()
WHERE  rep_code = 'SER001';

-- ── 2. Additional Makro store aliases ───────────────────────────────────────
-- Canonical client ID for "Makro" (seeded in 003/mcr_bootstrap)
DO $$
DECLARE
  v_client   UUID;
  v_source   UUID;
BEGIN
  SELECT id INTO v_client FROM clients WHERE canonical_name = 'Makro' AND is_deleted = FALSE;
  SELECT id INTO v_source FROM data_sources WHERE source_code = 'ERP_EXPORT';

  IF v_client IS NULL THEN
    RAISE NOTICE 'Makro canonical client not found — aliases skipped (run mcr_bootstrap first)';
    RETURN;
  END IF;

  INSERT INTO client_source_aliases
    (client_id, source_id, source_code, source_name,
     match_confidence, match_status, matched_by, confirmed_by, confirmed_at)
  VALUES
    -- Source: ERP debtor codes confirmed as Makro store locations
    (v_client, v_source, 'MAKROGER',  'Makro Germiston',              'CONFIRMED', 'ACTIVE', 'migration_013', 'NSM', NOW()),
    (v_client, v_source, 'MAKROMI1',  'Makro Montague Gardens',       'CONFIRMED', 'ACTIVE', 'migration_013', 'NSM', NOW()),
    (v_client, v_source, 'MAKROCE1',  'Makro Centurion',              'CONFIRMED', 'ACTIVE', 'migration_013', 'NSM', NOW()),
    (v_client, v_source, 'MAKRO002',  'Makro Nelspruit/Mbombela',     'CONFIRMED', 'ACTIVE', 'migration_013', 'NSM', NOW()),
    (v_client, v_source, 'MAKROSP1',  'Makro Springfield',            'CONFIRMED', 'ACTIVE', 'migration_013', 'NSM', NOW()),
    (v_client, v_source, 'MAKROP01',  'Makro Pietermaritzburg',       'CONFIRMED', 'ACTIVE', 'migration_013', 'NSM', NOW()),
    (v_client, v_source, 'MAKROSI1',  'Makro Silver Lakes',           'CONFIRMED', 'ACTIVE', 'migration_013', 'NSM', NOW()),
    (v_client, v_source, 'MAKROCAR',  'Makro Carnival City',          'CONFIRMED', 'ACTIVE', 'migration_013', 'NSM', NOW()),
    (v_client, v_source, 'MAKROST1',  'Makro Strubens Valley',        'CONFIRMED', 'ACTIVE', 'migration_013', 'NSM', NOW()),
    (v_client, v_source, 'MAKRORIV',  'Makro Riversands',             'CONFIRMED', 'ACTIVE', 'migration_013', 'NSM', NOW()),
    (v_client, v_source, 'MAKROOT1',  'Makro Ottery',                 'CONFIRMED', 'ACTIVE', 'migration_013', 'NSM', NOW()),
    (v_client, v_source, 'MAKRO AM',  'Makro Amanzimtoti',            'CONFIRMED', 'ACTIVE', 'migration_013', 'NSM', NOW()),
    (v_client, v_source, 'MAKROALB',  'Makro Alberton',               'CONFIRMED', 'ACTIVE', 'migration_013', 'NSM', NOW()),
    (v_client, v_source, 'MAKROPOL',  'Makro Polokwane',              'CONFIRMED', 'ACTIVE', 'migration_013', 'NSM', NOW()),
    (v_client, v_source, 'MAKROWO1',  'Makro Wonderboom',             'CONFIRMED', 'ACTIVE', 'migration_013', 'NSM', NOW()),
    (v_client, v_source, 'MAKCAPGA',  'Makro Cape Gate',              'CONFIRMED', 'ACTIVE', 'migration_013', 'NSM', NOW()),
    (v_client, v_source, 'MAKROCR1',  'Makro Crown Mines',            'CONFIRMED', 'ACTIVE', 'migration_013', 'NSM', NOW()),
    (v_client, v_source, 'MAKROGO1',  'Makro Gonubie',                'CONFIRMED', 'ACTIVE', 'migration_013', 'NSM', NOW()),
    (v_client, v_source, 'MAKROPE2',  'Makro Gqeberha (PE)',          'CONFIRMED', 'ACTIVE', 'migration_013', 'NSM', NOW())
  ON CONFLICT DO NOTHING;

  RAISE NOTICE 'Migration 013: Sergio King corrected to ACTIVE; Makro store aliases registered.';
END;
$$;

-- ── 3. Add missing updated_at column to client_ownership ────────────────────
-- The set_updated_at trigger was registered for this table in migration 001 but
-- the column was not included in the original CREATE TABLE. Without it, any
-- UPDATE on client_ownership raises "record 'new' has no field 'updated_at'".
ALTER TABLE client_ownership
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
