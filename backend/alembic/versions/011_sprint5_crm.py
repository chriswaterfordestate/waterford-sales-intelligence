"""011 - Sprint 5 CRM layer: support requests, account health, contact fields.

Adds the CRM operational layer on top of the approved Sprint 4 schema:
  - crm_support_requests table
  - crm_activities.contact_person
  - crm_opportunities.potential (LOW/MEDIUM/HIGH)
  - crm_follow_ups.calendar_event_uid (future Outlook Graph sync hook)
  - crm_follow_ups.assigned_to_rep_id (separate from creator)
  - crm_health_config table with seeded thresholds

All changes are idempotent (IF NOT EXISTS / ADD COLUMN IF NOT EXISTS).
Safe to apply against a clean Sprint 4 database or re-apply.

Revision ID: 011
Revises: 010
Create Date: 2026-09-11
"""
from alembic import op
import os

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql_path = os.path.join(os.path.dirname(__file__), "011_sprint5_crm.sql")
    with open(sql_path, "r") as f:
        op.execute(f.read())


def downgrade() -> None:
    op.execute("""
        -- Remove Sprint 5 additions in reverse order
        DROP TABLE IF EXISTS crm_health_config;
        ALTER TABLE crm_follow_ups
            DROP COLUMN IF EXISTS assigned_to_rep_id,
            DROP COLUMN IF EXISTS calendar_event_uid;
        ALTER TABLE crm_opportunities
            DROP COLUMN IF EXISTS potential;
        ALTER TABLE crm_activities
            DROP COLUMN IF EXISTS contact_person;
        DROP TABLE IF EXISTS crm_support_requests;
    """)
