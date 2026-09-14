"""003 - Waterford master data seed

APPROVED TO LOAD (CONFIRMED data only):
- 10 reps with territory assignments
- 9 rep/territory SCD-2 ownership records
- 13 products, 15 SKUs
- 15 ASP versions (FY27 target sheet prices, approved)
- 4 confirmed client groups
- 26 confirmed canonical clients (distributors + WC + GAU)
- 56 confirmed client source aliases

DO NOT LOAD (not in this migration):
- 49 PROBABLE client aliases → via review queue
- 21 UNRESOLVED clients → via review queue
- THE004 (Lord Charles Hotel second code) → UNRESOLVED until NSM confirms
- CAS001 → DO_NOT_MATCH — excluded from MCR entirely
- Individual rep targets → Phase 2 Target Entry UI
- Historical transaction data → Sprint 5+

Revision ID: 003
Revises: 002
Create Date: 2026-09-09
"""
from alembic import op
import os

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql_path = os.path.join(os.path.dirname(__file__), "003_waterford_master_seed.sql")
    with open(sql_path, "r") as f:
        sql = f.read()
    op.execute(sql)


def downgrade() -> None:
    op.execute("""
        DELETE FROM client_source_aliases;
        DELETE FROM client_ownership;
        DELETE FROM clients;
        DELETE FROM client_groups;
        DELETE FROM asp_versions;
        DELETE FROM product_skus;
        DELETE FROM products;
        DELETE FROM rep_territory_assignments;
        DELETE FROM reps;
    """)
