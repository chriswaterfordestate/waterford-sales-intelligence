"""
Phase 1 Category A retroactive resolution.

Runs retroactive_resolve against the 9 commercial ERP debtor codes that already
have confirmed MCR aliases but were imported before the aliases were registered.

Safe to run multiple times — resolve_debtor_alias is idempotent.
Does NOT create new canonical clients.
Does NOT touch any Category B/C/D debtors.

Usage: python3 -m scripts.run_cat_a_retroactive [--dry-run]
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault('DATABASE_URL',
    'postgresql://waterford:waterford_dev@localhost:5432/waterford_si')
os.environ.setdefault('APP_ENV', 'development')

from app.config import get_settings
get_settings.cache_clear()
from app.services.import_engine.db_ops import get_conn
from app.services.import_engine.retroactive_resolve import resolve_debtor_alias

# These 9 debtor codes already have confirmed MCR aliases and confirmed client IDs.
# The alias is already in client_source_aliases — we only need to retroactively
# resolve the PENDING_MAPPING raw rows from final_sales_fy2026.csv.
# resolve_debtor_alias is idempotent: if alias exists, it skips registration and
# proceeds directly to resolving pending rows.
CATEGORY_A = [
    'WOOL0001',   # Woolworths (Pty) Ltd → Woolworths Food
    'SHOPR001',   # Shoprite Checkers (Pty) Ltd → Shoprite Checkers
    'PICKMA05',   # PnP Phillipi DC → Pick n Pay DCs
    'PICKMA15',   # PnP Eastport Distribution Cent → Pick n Pay DCs
    'ONEDAY01',   # OneDayOnly Offers (Pty) Ltd → OneDayOnly
    'SOLL0001',   # Solly Kramer's Parkhurst → Solly Kramers Parkhurst
    'MAKROW01',   # Makro Woodmead → Makro
    'MAKROCOR',   # Makro Cornubia → Makro
    'RUEDA001',   # Rueda Wine Consulting (Pty)Ltd → Rueda Wine Consulting
    # Makrova1 is also Cat A — add here
    'MAKROVA1',   # Makro Vaal → Makro
    # SOLL0001 = same as SOL001 (both = Solly Kramers Parkhurst): different ERP codes for same
    # business across different files. SOL001 alias is confirmed; SOLL0001 needs alias+resolve.
    'SOLL0001',   # Solly Kramer's Parkhurst (final_sales_fy2026 code) → Solly Kramers Parkhurst
]

def main(dry_run: bool = False):
    conn = get_conn()
    try:
        from psycopg2.extras import RealDictCursor
        totals = {'resolved': 0, 'skipped': 0, 'failed': 0}

        for debtor_code in CATEGORY_A:
            # Get the confirmed canonical client for this debtor
            with conn.cursor(cursor_factory=RealDictCursor) as c:
                c.execute("""
                    SELECT c.id::text, c.canonical_name
                    FROM client_source_aliases csa
                    JOIN data_sources ds ON ds.id = csa.source_id
                    JOIN clients c ON c.id = csa.client_id
                    WHERE ds.source_code = 'ERP_EXPORT'
                      AND csa.source_code = %s
                      AND csa.match_status = 'ACTIVE'
                      AND csa.match_confidence = 'CONFIRMED'
                    LIMIT 1
                """, (debtor_code,))
                alias_row = c.fetchone()

                # Also count pending rows
                c.execute("""
                    SELECT COUNT(*) AS pending
                    FROM import_raw_rows irr
                    JOIN import_batches ib ON ib.id = irr.batch_id
                    JOIN data_sources ds ON ds.id = ib.source_id
                    WHERE ds.source_code = 'ERP_EXPORT'
                      AND irr.row_status = 'PENDING_MAPPING'
                      AND irr.raw_data->>'debtor' = %s
                """, (debtor_code,))
                pending = c.fetchone()['pending']

            if not alias_row:
                print(f"  ✗ {debtor_code}: no confirmed alias found — skipping")
                continue

            canonical_name = alias_row['canonical_name']
            canonical_id = alias_row['id']
            print(f"  {debtor_code} → {canonical_name}: {pending} pending rows")

            if dry_run:
                print(f"    [DRY RUN] would resolve {pending} rows")
                continue

            result = resolve_debtor_alias(
                conn, debtor_code, canonical_id,
                source_code='ERP_EXPORT',
                confirmed_by='phase1_cat_a'
            )
            conn.commit()

            r = result.get('resolved', 0)
            s = result.get('skipped', 0)
            f = result.get('failed', 0)
            totals['resolved'] += r
            totals['skipped']  += s
            totals['failed']   += f
            status = '✓' if f == 0 else '⚠'
            print(f"    {status} resolved={r} skipped={s} failed={f}")

        print(f"\nTotal: resolved={totals['resolved']} skipped={totals['skipped']} failed={totals['failed']}")
        return totals

    finally:
        conn.close()


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    if dry_run:
        print("=== DRY RUN — no changes committed ===")
    print("Phase 1 Category A retroactive resolution")
    print("=" * 50)
    main(dry_run=dry_run)
