"""006 - Sprint 2.5 NSM-confirmed decisions

NSM decisions implemented:
1. NORMANPA → new client: NGF Paarden Eiland (separate branch from NORM0002)
2. CAMPSBAY → new client: Divine Inspiration Trading / Kove Collection (Nathalie)
3. DIST0002 → new client: separate Distriliq CPT entity (different brand/manager)
4. LEGACY01 → new distributor + client: Legacy Liquors (independent)
5. Waterford Chenin Blanc = Old Vine Project Chenin Blanc → new product WCB + SKU WCB001
6. Special - Waterford Bubbly = Waterford Cap Classique → new product MCC + SKU MCC001
7. Waterford Cab Sauv 1.5L → new SKU CAB1L
8. Product aliases: Pecan Stream Sauv Blanc, Grenache Noir, Cab Sauv 375ml (confirmed)
9. All name variants for WCB001 and MCC001 seeded across ERP, NGF SalesOut, NGF Monthly

Revision ID: 006
Revises: 005
Create Date: 2026-09-10
"""
from alembic import op
import os

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql_path = os.path.join(os.path.dirname(__file__), "006_sprint25_decisions.sql")
    with open(sql_path, "r") as f:
        sql = f.read()
    op.execute(sql)


def downgrade() -> None:
    op.execute("""
        DELETE FROM client_source_aliases WHERE confirmed_by = 'NSM';
        DELETE FROM product_source_aliases WHERE confirmed_by = 'NSM';
        DELETE FROM asp_versions WHERE id IN (
            SELECT md5(s)::uuid FROM (VALUES
                ('asp-wcb-fy27'),('asp-wcb-fy26'),('asp-mcc-fy27'),('asp-mcc-fy26'),
                ('asp-cab1l-fy27'),('asp-cab1l-fy26')
            ) AS t(s));
        DELETE FROM product_skus WHERE sku_code IN ('WCB001','MCC001','CAB1L');
        DELETE FROM products WHERE product_code IN ('WCB','MCC');
        DELETE FROM clients WHERE id IN (
            md5('cl-ngf-paarden-eiland')::uuid, md5('cl-kove-collection')::uuid,
            md5('cl-distriliq-cpt-dist0002')::uuid, md5('cl-legacy-liquors')::uuid);
        DELETE FROM distributors WHERE distributor_code = 'LEGACY_LIQ';
    """)
