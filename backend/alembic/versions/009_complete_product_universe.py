"""Sprint 2.5 migration 009: Complete product universe — all current and historical SKUs

Alembic wrapper for 009_complete_product_universe.sql.
All schema/data changes are in the SQL file.

Revision ID: 009
Revises: 008
Create Date: 2026-09-11
"""
from alembic import op
import os

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql_path = os.path.join(os.path.dirname(__file__), "009_complete_product_universe.sql")
    with open(sql_path, "r") as f:
        op.execute(f.read())


def downgrade() -> None:
    # Data migrations — downgrade not supported
    pass
