"""Sprint 2.5 migration 008: Product corrections — CABMAG rename, product source aliases

Alembic wrapper for 008_product_corrections.sql.
All schema/data changes are in the SQL file.

Revision ID: 008
Revises: 007
Create Date: 2026-09-11
"""
from alembic import op
import os

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql_path = os.path.join(os.path.dirname(__file__), "008_product_corrections.sql")
    with open(sql_path, "r") as f:
        op.execute(f.read())


def downgrade() -> None:
    # Data migrations — downgrade not supported
    pass
