"""
FY2027 Target data tests — migration 015.
Proves:
  1. All 13 sources reconcile to PDF monthly-cell sums
  2. Negative values are preserved exactly
  3. Channels have correct channel_id (not rep/territory)
  4. Rose-Mary 500ml and Library Collection (DLIB) exist in product master
  5. Werner Briedenhann has no targets (not supplied)
  6. KZN is territory-level
  7. All 19 negative cells are in the database
  8. Total row count = 1970
  9. Correct constraint: exactly one owner per target row
"""
import os, psycopg2
import pytest
from psycopg2.extras import RealDictCursor

os.environ['DATABASE_URL_SYNC'] = \
    'host=localhost dbname=waterford_si user=waterford password=waterford_dev'

DSN = 'host=localhost dbname=waterford_si user=waterford password=waterford_dev'

# Expected sum_monthly values per source (from authoritative PDF monthly cells)
EXPECTED_MONTHLY_SUMS = {
    'HEADOFFICE.pdf': 130_742,
    'HELENA.pdf':       2_200,
    'JANE_S.pdf':      21_977,
    'KOLISWA.pdf':     27_827,
    'KZN.pdf':         17_454,
    'MAGGIE.pdf':       4_300,
    'NATHALIE.pdf':    58_632,
    'SANDILE.pdf':     17_173,
    'SERGIO.pdf':      43_934,
    'CELLAR_DOOR.pdf': 21_156,
    'EVENTS.pdf':       1_543,
    'EXPORTS.pdf':     62_290,
    'PVT_CLIENTS.pdf': 24_135,
}


def conn():
    return psycopg2.connect(DSN)


class TestTargetReconciliation:

    def setup_method(self):
        self.db = conn()

    def teardown_method(self):
        self.db.close()

    def _src_sum(self, source_doc: str) -> int:
        with self.db.cursor() as c:
            c.execute(
                "SELECT COALESCE(SUM(target_bottles), 0)::int "
                "FROM targets WHERE source_document = %s AND created_by='migration_015'",
                (source_doc,)
            )
            return c.fetchone()[0]

    def test_headoffice_total(self):
        assert self._src_sum('HEADOFFICE.pdf') == EXPECTED_MONTHLY_SUMS['HEADOFFICE.pdf']

    def test_helena_total(self):
        assert self._src_sum('HELENA.pdf') == EXPECTED_MONTHLY_SUMS['HELENA.pdf']

    def test_jane_total(self):
        assert self._src_sum('JANE_S.pdf') == EXPECTED_MONTHLY_SUMS['JANE_S.pdf']

    def test_koliswa_total(self):
        assert self._src_sum('KOLISWA.pdf') == EXPECTED_MONTHLY_SUMS['KOLISWA.pdf']

    def test_kzn_total(self):
        assert self._src_sum('KZN.pdf') == EXPECTED_MONTHLY_SUMS['KZN.pdf']

    def test_maggie_total(self):
        assert self._src_sum('MAGGIE.pdf') == EXPECTED_MONTHLY_SUMS['MAGGIE.pdf']

    def test_nathalie_total(self):
        assert self._src_sum('NATHALIE.pdf') == EXPECTED_MONTHLY_SUMS['NATHALIE.pdf']

    def test_sandile_total(self):
        assert self._src_sum('SANDILE.pdf') == EXPECTED_MONTHLY_SUMS['SANDILE.pdf']

    def test_sergio_total(self):
        assert self._src_sum('SERGIO.pdf') == EXPECTED_MONTHLY_SUMS['SERGIO.pdf']

    def test_cellar_door_total(self):
        assert self._src_sum('CELLAR_DOOR.pdf') == EXPECTED_MONTHLY_SUMS['CELLAR_DOOR.pdf']

    def test_events_total(self):
        assert self._src_sum('EVENTS.pdf') == EXPECTED_MONTHLY_SUMS['EVENTS.pdf']

    def test_exports_total(self):
        assert self._src_sum('EXPORTS.pdf') == EXPECTED_MONTHLY_SUMS['EXPORTS.pdf']

    def test_pvt_clients_total(self):
        assert self._src_sum('PVT_CLIENTS.pdf') == EXPECTED_MONTHLY_SUMS['PVT_CLIENTS.pdf']

    def test_koliswa_july_kas001_is_327(self):
        """Spot-check: Koliswa July KAS001 = 327 per source PDF."""
        with self.db.cursor() as c:
            c.execute("""
                SELECT t.target_bottles::int
                FROM targets t
                JOIN reps r ON r.id = t.rep_id
                JOIN product_skus ps ON ps.id = t.product_sku_id
                JOIN financial_periods fp ON fp.id = t.financial_period_id
                WHERE r.rep_code = 'KOL001' AND ps.sku_code = 'KAS001'
                  AND fp.calendar_month = 7 AND t.created_by='migration_015'
            """)
            assert c.fetchone()[0] == 327


class TestNegativeTargets:

    def setup_method(self):
        self.db = conn()

    def teardown_method(self):
        self.db.close()

    def test_exactly_19_negative_cells(self):
        """All 19 negative monthly target cells are preserved as-is."""
        with self.db.cursor() as c:
            c.execute(
                "SELECT COUNT(*) FROM targets "
                "WHERE target_bottles < 0 AND created_by='migration_015'"
            )
            assert c.fetchone()[0] == 19

    def test_koliswa_pecan_chenin_july_is_negative_44(self):
        """Koliswa July Pecan Stream Chenin = -44 (preserved, not zeroed)."""
        with self.db.cursor() as c:
            c.execute("""
                SELECT t.target_bottles::int
                FROM targets t
                JOIN reps r ON r.id = t.rep_id
                JOIN product_skus ps ON ps.id = t.product_sku_id
                JOIN financial_periods fp ON fp.id = t.financial_period_id
                WHERE r.rep_code = 'KOL001' AND ps.sku_code = 'PSC001'
                  AND fp.calendar_month = 7 AND t.created_by='migration_015'
            """)
            assert c.fetchone()[0] == -44

    def test_cellar_door_rose_mary_1500_negatives(self):
        """Cellar Door Rose-Mary 1.5L has 4 negative months (Nov/Dec/Jan/Feb)."""
        with self.db.cursor() as c:
            c.execute("""
                SELECT COUNT(*) FROM targets t
                JOIN channels ch ON ch.id = t.channel_id
                JOIN product_skus ps ON ps.id = t.product_sku_id
                WHERE ch.channel_code = 'DTC' AND ps.sku_code = 'RM1500'
                  AND t.target_bottles < 0 AND t.created_by='migration_015'
            """)
            assert c.fetchone()[0] == 4


class TestChannelTargets:

    def setup_method(self):
        self.db = conn()

    def teardown_method(self):
        self.db.close()

    def test_channel_targets_have_channel_id_not_rep(self):
        """All channel targets must use channel_id, not rep_id or territory_id."""
        with self.db.cursor() as c:
            c.execute("""
                SELECT COUNT(*) FROM targets t
                JOIN target_sets ts ON ts.id = t.target_set_id
                WHERE ts.target_level = 'CHANNEL'
                  AND (t.rep_id IS NOT NULL OR t.territory_id IS NOT NULL)
                  AND t.created_by = 'migration_015'
            """)
            assert c.fetchone()[0] == 0

    def test_cellar_door_channel_code_is_dtc(self):
        with self.db.cursor() as c:
            c.execute("""
                SELECT DISTINCT ch.channel_code
                FROM targets t JOIN channels ch ON ch.id = t.channel_id
                WHERE t.source_document = 'CELLAR_DOOR.pdf' AND t.created_by='migration_015'
            """)
            assert c.fetchone()[0] == 'DTC'

    def test_events_channel_exists(self):
        with self.db.cursor() as c:
            c.execute("SELECT COUNT(*) FROM channels WHERE channel_code = 'EVENTS'")
            assert c.fetchone()[0] == 1

    def test_private_clients_channel_exists(self):
        with self.db.cursor() as c:
            c.execute("SELECT COUNT(*) FROM channels WHERE channel_code = 'PRIVATE_CLIENTS'")
            assert c.fetchone()[0] == 1


class TestProductMaster:

    def setup_method(self):
        self.db = conn()

    def teardown_method(self):
        self.db.close()

    def test_rose_mary_500ml_exists(self):
        with self.db.cursor() as c:
            c.execute("SELECT bottle_size_ml FROM product_skus WHERE sku_code = 'RM500'")
            row = c.fetchone()
            assert row is not None and row[0] == 500

    def test_dlib_exists(self):
        with self.db.cursor() as c:
            c.execute("SELECT sku_code FROM product_skus WHERE sku_code = 'DLIB'")
            assert c.fetchone() is not None

    def test_library_collection_product_exists(self):
        with self.db.cursor() as c:
            c.execute("SELECT product_code FROM products WHERE product_code = 'DLIB'")
            assert c.fetchone() is not None

    def test_nathalie_rose_mary_500ml_targets_loaded(self):
        """NATHALIE.pdf has 4,200 Rose-Mary 500ml bottles in March."""
        with self.db.cursor() as c:
            c.execute("""
                SELECT t.target_bottles::int
                FROM targets t
                JOIN reps r ON r.id = t.rep_id
                JOIN product_skus ps ON ps.id = t.product_sku_id
                JOIN financial_periods fp ON fp.id = t.financial_period_id
                WHERE r.rep_code = 'NAT001' AND ps.sku_code = 'RM500'
                  AND fp.calendar_month = 3 AND t.created_by='migration_015'
            """)
            assert c.fetchone()[0] == 4200


class TestDataIntegrity:

    def setup_method(self):
        self.db = conn()

    def teardown_method(self):
        self.db.close()

    def test_total_row_count(self):
        with self.db.cursor() as c:
            c.execute("SELECT COUNT(*) FROM targets WHERE created_by='migration_015'")
            assert c.fetchone()[0] == 1970

    def test_exactly_one_owner_per_row(self):
        """target_has_owner: exactly one of rep_id/territory_id/channel_id must be set."""
        with self.db.cursor() as c:
            c.execute("""
                SELECT COUNT(*) FROM targets
                WHERE (rep_id IS NOT NULL)::int + (territory_id IS NOT NULL)::int
                      + (channel_id IS NOT NULL)::int != 1
            """)
            assert c.fetchone()[0] == 0

    def test_kzn_is_territory_level(self):
        with self.db.cursor() as c:
            c.execute("""
                SELECT COUNT(*) FROM targets t
                JOIN territories tr ON tr.id = t.territory_id
                WHERE tr.territory_code = 'KZN' AND t.rep_id IS NOT NULL
                  AND t.created_by='migration_015'
            """)
            assert c.fetchone()[0] == 0

    def test_werner_has_no_targets(self):
        with self.db.cursor() as c:
            c.execute("""
                SELECT COUNT(*) FROM targets t JOIN reps r ON r.id = t.rep_id
                WHERE r.rep_code = 'WER001'
            """)
            assert c.fetchone()[0] == 0

    def test_three_target_sets(self):
        with self.db.cursor() as c:
            c.execute("SELECT COUNT(*) FROM target_sets WHERE created_by='migration_015'")
            assert c.fetchone()[0] == 3

    def test_old_mvp_seed_removed(self):
        """The incorrect July/August Gauteng placeholder must be gone."""
        with self.db.cursor() as c:
            c.execute("SELECT COUNT(*) FROM target_sets WHERE id='b8dc1af2-88b4-f7ae-4799-72898968471b'")
            assert c.fetchone()[0] == 0
