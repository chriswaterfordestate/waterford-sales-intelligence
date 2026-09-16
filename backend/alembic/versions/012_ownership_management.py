"""012 — Ownership management: ERP_DERIVED and MANUAL_ASSIGNMENT reasons.

Adds two new change_reason values to ownership_change_reason_enum:
  ERP_DERIVED      — ownership inferred from ERP srepname (historical baseline)
  MANUAL_ASSIGNMENT — explicit browser-based assignment (highest priority)

Also adds an index on (client_id, change_reason, effective_from) for
efficient priority-check queries in the ownership derivation pipeline.

Revision ID: 012
Revises: 011
Create Date: 2026-09-14
"""
from alembic import op
import os

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql_path = os.path.join(os.path.dirname(__file__), "012_ownership_management.sql")
    with open(sql_path, "r") as f:
        op.execute(f.read())


def downgrade() -> None:
    # Enum values cannot be removed in PostgreSQL without recreating the type.
    # In practice, downgrade of an enum-value addition is a no-op.
    # The index can be dropped safely.
    op.execute("DROP INDEX IF EXISTS idx_ownership_reason;")
