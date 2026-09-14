"""010 - Historical discontinued products: Waterford Pinot Noir and Estate Sauvignon Blanc

NSM confirmed September 2026:
- Waterford Pinot Noir: legitimate historical product, discontinued, NOT deleted
- Waterford Estate Sauvignon Blanc: legitimate historical product, discontinued,
  SEPARATE from Elgin SB — must never merge
Both remain canonical for historical reporting; is_active=FALSE for current selling.

Revision ID: 010
Revises: 009
Create Date: 2026-09-10
"""
from alembic import op
import os

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql_path = os.path.join(os.path.dirname(__file__), "010_historical_discontinued_products.sql")
    with open(sql_path, "r") as f:
        op.execute(f.read())


def downgrade() -> None:
    op.execute("""
        DELETE FROM product_source_aliases WHERE id IN (
            md5('psa010-ERP-Waterford Pinot Noir')::uuid,
            md5('psa010-ERP-Waterford Estate Sauv Blanc')::uuid);
        DELETE FROM product_skus WHERE sku_code IN ('PNOIR001','WSB001');
        DELETE FROM products WHERE product_code IN ('PNOIR','WSB');
    """)
