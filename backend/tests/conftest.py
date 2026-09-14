"""
Root conftest.py — manages DATABASE_URL_SYNC for the test suite.

Test suites:
  - acceptance_gate, dc_002_regression, historical_products, erp_structural:
    use waterford_si_test (no real data needed, just schema)
  - sprint3_integration:
    use waterford_si (needs real FY2026 data for reporting tests)

The DATABASE_URL_SYNC env variable controls which DB the FastAPI app connects to.
We set it per-test-module using autouse fixtures.
"""
import pytest
import os

PROD_DSN = "host=localhost dbname=waterford_si user=waterford password=waterford_dev"
TEST_DSN  = "host=localhost dbname=waterford_si_test user=waterford password=waterford_dev"


def pytest_configure(config):
    """Set default DSN to test DB before any tests run."""
    os.environ.setdefault('DATABASE_URL_SYNC', TEST_DSN)


def pytest_collection_modifyitems(items):
    """
    Mark integration tests so they can reset the DSN.
    Integration tests need the production DB (real FY2026 data).
    """
    for item in items:
        if 'sprint3_integration' in str(item.fspath):
            item.add_marker(pytest.mark.integration)


# Tests that require the production DB (real FY2026/FY2027 data)
PROD_DB_MODULES = ('sprint3_integration', 'test_sprint4', 'test_sprint5', 'test_sprint6')


@pytest.fixture(autouse=True)
def set_db_for_test(request):
    """Per-test: set DATABASE_URL_SYNC based on test module."""
    fspath = str(request.fspath)
    needs_prod = any(m in fspath for m in PROD_DB_MODULES)
    os.environ['DATABASE_URL_SYNC'] = PROD_DSN if needs_prod else TEST_DSN
    yield
    # Restore test DB as default after each test
    os.environ['DATABASE_URL_SYNC'] = TEST_DSN
