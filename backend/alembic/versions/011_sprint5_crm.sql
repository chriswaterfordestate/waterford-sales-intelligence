-- Migration 011 — Sprint 5 CRM Layer
-- Upgrades approved Sprint 4 schema to Sprint 5 operational CRM.
--
-- Changes:
--   1. crm_support_requests  (new table)
--   2. crm_activities.contact_person  (new column)
--   3. crm_opportunities.potential    (new column)
--   4. crm_follow_ups.calendar_event_uid  (new column, future Outlook Graph hook)
--   5. crm_follow_ups.assigned_to_rep_id  (new column, separate from creator rep_id)
--   6. crm_health_config  (new table, centralised account-health thresholds)
--
-- All changes are IF NOT EXISTS / ADD COLUMN IF NOT EXISTS — safe to re-run.

-- ── 1. crm_support_requests ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS crm_support_requests (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id          UUID NOT NULL REFERENCES clients(id),
    rep_id             UUID NOT NULL REFERENCES reps(id),
    activity_id        UUID REFERENCES crm_activities(id),
    support_type       VARCHAR(50) NOT NULL,
    assigned_to_rep_id UUID REFERENCES reps(id),
    required_by        DATE,
    notes              TEXT NOT NULL DEFAULT '',
    status             VARCHAR(20) NOT NULL DEFAULT 'REQUESTED'
                       CHECK (status IN ('REQUESTED','IN_PROGRESS','COMPLETED','DECLINED')),
    completed_at       TIMESTAMPTZ,
    completed_notes    TEXT,
    is_deleted         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by         VARCHAR(100) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_supp_client
    ON crm_support_requests(client_id, status);
CREATE INDEX IF NOT EXISTS idx_supp_rep
    ON crm_support_requests(rep_id, status);

-- Trigger: auto-update updated_at
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_supp_updated_at'
    ) THEN
        CREATE TRIGGER trg_supp_updated_at
            BEFORE UPDATE ON crm_support_requests
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END;
$$;

-- ── 2. crm_activities.contact_person ─────────────────────────────────────────
ALTER TABLE crm_activities
    ADD COLUMN IF NOT EXISTS contact_person VARCHAR(200);

-- ── 3. crm_opportunities.potential ───────────────────────────────────────────
ALTER TABLE crm_opportunities
    ADD COLUMN IF NOT EXISTS potential VARCHAR(10)
        CHECK (potential IN ('LOW','MEDIUM','HIGH'));

-- ── 4. crm_follow_ups.calendar_event_uid ─────────────────────────────────────
-- Stores Outlook/calendar event UID for future Microsoft Graph two-way sync.
-- Web app remains system of record until direct sync is implemented.
ALTER TABLE crm_follow_ups
    ADD COLUMN IF NOT EXISTS calendar_event_uid VARCHAR(200);

-- ── 5. crm_follow_ups.assigned_to_rep_id ─────────────────────────────────────
-- Separates the rep who creates the task from the rep who owns it.
ALTER TABLE crm_follow_ups
    ADD COLUMN IF NOT EXISTS assigned_to_rep_id UUID REFERENCES reps(id);

-- ── 6. crm_health_config ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS crm_health_config (
    key   VARCHAR(60) PRIMARY KEY,
    value NUMERIC NOT NULL,
    label VARCHAR(100) NOT NULL
);

INSERT INTO crm_health_config (key, value, label) VALUES
    ('visit_overdue_days',   60,  'Days since last visit before flagged as overdue'),
    ('no_order_warning_days', 90, 'Days since last order before warning'),
    ('no_order_alert_days',  120, 'Days since last order before alert'),
    ('decline_threshold_pct', 20, 'YoY % decline threshold for DECLINING flag'),
    ('growth_threshold_pct',  20, 'YoY % growth threshold for GROWING flag'),
    ('new_account_days',      90, 'Days since first order to be considered new'),
    ('dormant_days',         365, 'Days of inactivity before DORMANT flag')
ON CONFLICT (key) DO NOTHING;

-- ── 7. user_rep_mappings ──────────────────────────────────────────────────────
-- Maps Clerk authenticated user IDs to Waterford rep records.
-- Admin creates these mappings in the web UI.
-- Enables: Koliswa logs in → My Day automatically shows Koliswa's data.
CREATE TABLE IF NOT EXISTS user_rep_mappings (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clerk_user_id VARCHAR(200) NOT NULL,
    clerk_email   VARCHAR(200) NOT NULL DEFAULT '',
    rep_id        UUID NOT NULL REFERENCES reps(id),
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by    VARCHAR(200) NOT NULL DEFAULT 'system',
    UNIQUE (clerk_user_id)
);
CREATE INDEX IF NOT EXISTS idx_urm_clerk ON user_rep_mappings(clerk_user_id) WHERE is_active=TRUE;
CREATE TRIGGER trg_urm_updated_at BEFORE UPDATE ON user_rep_mappings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
