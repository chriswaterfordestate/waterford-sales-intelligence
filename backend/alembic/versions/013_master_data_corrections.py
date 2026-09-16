"""013 — Master data corrections: Sergio King status + Makro store aliases.

Revises: 012
Changes:
  1. SER001 Sergio King: employment_status RESIGNED → ACTIVE, end_date/departure cleared.
     The Sergio/Nathalie WC redistribution was never approved; the seed was incorrect.
  2. 19 additional Makro ERP store-code aliases registered to the existing Makro canonical.

Revision ID: 013
Revises: 012
Create Date: 2026-09-14
"""
from alembic import op
import os

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql_path = os.path.join(os.path.dirname(__file__), "013_master_data_corrections.sql")
    with open(sql_path, "r") as f:
        op.execute(f.read())


def downgrade() -> None:
    # Reverse Sergio change only — alias rows are idempotent and safe to leave
    op.execute("""
        UPDATE reps
        SET    employment_status = 'RESIGNED',
               end_date          = '2026-06-30',
               departure_reason  = 'Resigned. WC accounts redistributed to Nathalie (KAM) and new Brand Managers.',
               updated_at        = NOW()
        WHERE  rep_code = 'SER001';
    """)
