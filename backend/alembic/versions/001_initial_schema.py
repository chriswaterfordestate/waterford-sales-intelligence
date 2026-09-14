"""001 - Initial schema

Applies the complete waterford_schema_v1.sql — all 42 tables, enums,
indexes, triggers, and reporting views.

AMBER items incorporated:
- exclusion_rule / exclusion_context / exclusion_evaluated_at on sales_transactions
- rep_id REMOVED from sales_transactions (derived from client_ownership at query time)
- case_size_required on import_raw_rows
- distributor_entity_id nullable FK on clients
- target_sets.target_level distinguishes TERRITORY (MVP) from REP (Phase 2)

Revision ID: 001
Revises: (base)
Create Date: 2026-09-09
"""
from alembic import op
import os

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Read the approved schema SQL file
    schema_path = os.path.join(os.path.dirname(__file__), "001_schema.sql")
    with open(schema_path, "r") as f:
        sql = f.read()
    op.execute(sql)


def downgrade() -> None:
    # Drop everything — only for development reset
    op.execute("""
        DROP SCHEMA public CASCADE;
        CREATE SCHEMA public;
        GRANT ALL ON SCHEMA public TO waterford;
        GRANT ALL ON SCHEMA public TO public;
    """)
