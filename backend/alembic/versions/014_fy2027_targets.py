"""014 — FY2027 authoritative target data: 9 reps/territory, per-SKU, per-month.

Replaces the incorrect MVP Gauteng seed (migration 005) with the full
authoritative dataset extracted from the 9 supplied target PDFs.

Sources:
  HEADOFFICE.pdf  → HO001 (NSM / Head Office)
  HELENA.pdf      → HEL001 (Helena Pires)
  JANE_S.pdf      → JAN001 (Jane Simon)
  KOLISWA.pdf     → KOL001 (Koliswa Jayiya)
  KZN.pdf         → KZN territory (no rep; Staff KwaZulu-Natal)
  MAGGIE.pdf      → MAG001 (Maggie Colman)
  NATHALIE.pdf    → NAT001 (Nathalie Watkins)
  SANDILE.pdf     → SAN001 (Sandile Yende)
  SERGIO.pdf      → SER001 (Sergio King)

Deferred (not included): CELLAR_DOOR, EVENTS, EXPORTS, PVT_CLIENTS
Not supplied: Werner Briedenhann (WER001)

Grain: rep_id (territory_id for KZN) × product_sku_id × financial_period_id
Only non-zero months are stored. Negative carry-overs treated as 0.

Revision ID: 014
Revises: 013
Create Date: 2026-09-15
"""
from alembic import op
import os

revision    = "014"
down_revision = "013"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    sql_path = os.path.join(os.path.dirname(__file__), "014_fy2027_targets.sql")
    with open(sql_path, "r") as f:
        op.execute(f.read())


def downgrade() -> None:
    """Remove migration 014 target data; restore the original MVP seed stub."""
    op.execute("""
        -- Remove the correct data
        DELETE FROM targets WHERE created_by = 'migration_014';
        DELETE FROM target_sets WHERE created_by = 'migration_014';

        -- Re-insert the original (incorrect) MVP seed so downgrade chain is valid
        INSERT INTO target_sets (id, financial_year_id, set_name, is_active,
            target_level, source_document, approved_by, approved_at, notes, created_by)
        VALUES (
            'b8dc1af2-88b4-f7ae-4799-72898968471b',
            '711c05f1-fb11-13d3-71e6-5c7c926e5dfe',
            'FY2027 Initial — Gauteng Combined', TRUE, 'TERRITORY',
            'Sergio King FY2027 Target Sheet (K+S+H combined)',
            'system', NOW(),
            'MVP territory-level targets only (downgraded from 014).',
            'system'
        );
        INSERT INTO targets (id, target_set_id, territory_id, financial_period_id,
            target_bottles, target_rand_value, source_document, notes, created_by)
        VALUES
            ('b8187d1b-0d8b-a31c-1ec8-c2baa909e9cc',
             'b8dc1af2-88b4-f7ae-4799-72898968471b',
             'abbf9648-42ab-9760-61ff-f3ebaeaa4602',
             'b62e09e7-1dcf-871d-f751-61d3211ff48a',
             3557, 657045,
             'Sergio King FY2027 Target Sheet',
             'Combined K+S+H Gauteng July 2026 (original MVP seed).', 'system'),
            ('9c9d09f1-ccb0-2a3f-50b3-72d82c102bc0',
             'b8dc1af2-88b4-f7ae-4799-72898968471b',
             'abbf9648-42ab-9760-61ff-f3ebaeaa4602',
             'ff33766f-1d50-e169-67e3-316053193007',
             3953, 784286,
             'Sergio King FY2027 Target Sheet',
             'Combined K+S+H Gauteng August 2026 (original MVP seed).', 'system');
    """)
