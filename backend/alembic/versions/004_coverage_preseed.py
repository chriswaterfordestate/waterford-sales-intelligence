"""004 - Coverage pre-seed

Pre-populates data_coverage with known status for all FY26 and FY27 periods
BEFORE any data imports run. This ensures YoY calculations correctly show N/A
for known missing periods from day one.

Critical pre-seeds:
- NGF Monthly JHB Jul 25 = MISSING (no data exists anywhere — permanent baseline gap)
- NGF Monthly KZN Jul 25 = MISSING (same)
- NGF Monthly CPT Jul 25 = MISSING (data is in NGF_SALESOUT source instead)
- VDP Gauteng ALL of FY26 = NOT_APPLICABLE (VDP not active in FY26)
- All ERP periods = MISSING (becomes COVERED when ERP CSV imported)

Revision ID: 004
Revises: 003
Create Date: 2026-09-09
"""
from alembic import op
import os

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql_path = os.path.join(os.path.dirname(__file__), "004_coverage_preseed.sql")
    with open(sql_path, "r") as f:
        sql = f.read()
    op.execute(sql)


def downgrade() -> None:
    op.execute("DELETE FROM data_coverage;")
