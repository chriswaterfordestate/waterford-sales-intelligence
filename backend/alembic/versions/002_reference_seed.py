"""002 - Reference data seed

Inserts structural reference records that never change:
- Financial years (FY2026 history, FY2027 current)
- Financial periods (24 months, 12 per FY)
- Channels (8)
- Territories (7)
- Distributors (4: NGF, VDP_GAU, Distriliq CPT, Distri George)
- Data sources (8 source connectors)

Revision ID: 002
Revises: 001
Create Date: 2026-09-09
"""
from alembic import op
import os

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql_path = os.path.join(os.path.dirname(__file__), "002_reference_seed.sql")
    with open(sql_path, "r") as f:
        sql = f.read()
    op.execute(sql)


def downgrade() -> None:
    op.execute("""
        DELETE FROM data_sources;
        DELETE FROM distributors;
        DELETE FROM territories;
        DELETE FROM channels;
        DELETE FROM financial_periods;
        DELETE FROM financial_years;
    """)
