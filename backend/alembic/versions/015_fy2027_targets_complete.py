"""015 — FY2027 targets complete: all 13 sources, negatives, channels, RM500, DLIB.

Forward migration that corrects and extends migration 014:
  - Removes target_bottles >= 0 constraint (negatives are valid planning adjustments)
  - Adds channel_id to targets; updates owner constraint to exactly-one-of rep/territory/channel
  - Adds Rose-Mary 500ml (RM500) to product_skus
  - Adds Library Collection (DLIB) canonical product and SKU (ERP-confirmed: L17-L25 prefix codes)
  - Adds EVENTS and PRIVATE_CLIENTS channels
  - Adds CHANNEL-level target set
  - Replaces migration_014 data with corrected full dataset
  - Loads all 13 sources: 9 rep/territory + 4 channels = 1,970 rows, 19 negative cells preserved
  - UNRESOLVED: Special - &Beyond Wines (EXPORTS, 4000 btls) — identity unconfirmed

Revision ID: 015
Revises: 014
"""
from alembic import op
import sqlalchemy as sa
import os, subprocess, psycopg2

revision     = "015"
down_revision = "014"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    sql_path = os.path.join(os.path.dirname(__file__), "015_fy2027_targets_complete.sql")
    with open(sql_path, "r") as f:
        op.execute(f.read())


def downgrade() -> None:
    op.execute("""
        DELETE FROM targets WHERE created_by = 'migration_015';
        DELETE FROM target_sets WHERE created_by = 'migration_015';
        DELETE FROM product_skus WHERE created_by = 'migration_015';
        DELETE FROM products WHERE created_by = 'migration_015';
        DELETE FROM channels WHERE id IN (
            'a0000001-0000-4000-a000-000000000001',
            'a0000001-0000-4000-a000-000000000002'
        );
        ALTER TABLE targets DROP CONSTRAINT IF EXISTS target_has_owner;
        ALTER TABLE targets ADD CONSTRAINT target_has_owner CHECK (
            (rep_id IS NOT NULL) OR (territory_id IS NOT NULL)
        );
        ALTER TABLE targets DROP COLUMN IF EXISTS channel_id;
        ALTER TABLE targets ADD CONSTRAINT targets_target_bottles_check CHECK (target_bottles >= 0);
    """)
