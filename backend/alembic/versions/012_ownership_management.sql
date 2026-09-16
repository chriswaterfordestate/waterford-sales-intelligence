-- Migration 012 — Ownership Management
-- Adds two new reasons to ownership_change_reason_enum:
--   ERP_DERIVED     : ownership inferred from ERP srepname field (historical baseline)
--   MANUAL_ASSIGNMENT : explicit browser-based assignment by manager/admin (highest priority)
--
-- Safe forward migration — only adds values to existing enum.
-- Production has 0 client_ownership rows so no data migration needed.

ALTER TYPE ownership_change_reason_enum ADD VALUE IF NOT EXISTS 'ERP_DERIVED';
ALTER TYPE ownership_change_reason_enum ADD VALUE IF NOT EXISTS 'MANUAL_ASSIGNMENT';

-- Index to speed up the "who owned this client on this date?" attribution query
-- and the "does any manual assignment exist for this client?" check in the pipeline.
CREATE INDEX IF NOT EXISTS idx_ownership_reason
  ON client_ownership (client_id, change_reason, effective_from);
