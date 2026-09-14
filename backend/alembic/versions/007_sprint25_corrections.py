"""Sprint 2.5 migration 007: Sprint 2.5 ERP corrections — CAB1L disambiguation, ASP cleanup

Alembic wrapper for 007_sprint25_corrections.sql.
All schema/data changes are in the SQL file.

Revision ID: 007
Revises: 006
Create Date: 2026-09-11
"""
from alembic import op
import os

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql_path = os.path.join(os.path.dirname(__file__), "007_sprint25_corrections.sql")
    with open(sql_path, "r") as f:
        op.execute(f.read())


def downgrade() -> None:
    # Data migrations — downgrade not supported
    pass
