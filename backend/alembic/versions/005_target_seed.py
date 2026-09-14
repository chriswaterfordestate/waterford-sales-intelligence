"""005 - FY2027 target seed

Loads confirmed FY2027 Gauteng combined targets:
  July 2026:   3,557 btls | R657,045 (K+S+H combined)
  August 2026: 3,953 btls | R784,286 (K+S+H combined)

Loaded at TERRITORY level (target_level=TERRITORY, rep_id=NULL).
Individual rep splits are Phase 2 via Target Entry UI.
Sep 2026-Jun 2027 targets are not available — enter via UI.

Revision ID: 005
Revises: 004
Create Date: 2026-09-09
"""
from alembic import op
import os

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql_path = os.path.join(os.path.dirname(__file__), "005_target_seed.sql")
    with open(sql_path, "r") as f:
        sql = f.read()
    op.execute(sql)


def downgrade() -> None:
    op.execute("""
        DELETE FROM targets WHERE target_set_id = 'ts-fy27-gau-initial';
        DELETE FROM target_sets WHERE id = 'ts-fy27-gau-initial';
    """)
