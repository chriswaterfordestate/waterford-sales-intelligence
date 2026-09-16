"""
Category B MCR Commit Script.

Creates canonical clients for all 392 Category B debtor codes from the approved
preview (cat_b_preview.csv) and runs the retroactive resolver for each.

Rules applied:
  - Each debtor code gets its own canonical client (all are CREATE_CANONICAL in preview)
  - La Colombe (LACOL001) and La Petite Colombe (LAPET001) are separate clients
  - No DTC/private/internal accounts created (all are commercial ERP clients)
  - Source debtor codes preserved as ERP_EXPORT aliases
  - No fuzzy merging: each ERP name maps to one canonical

Groups:
  INDEPENDENT  → outlet_type from ERP_GROUP mapping
  TOPS         → outlet_type BOTTLE_STORE
  LIQUOR_CITY  → outlet_type BOTTLE_STORE
  PICARDI      → outlet_type BOTTLE_STORE
  ULTRA        → outlet_type BOTTLE_STORE
  PRESTONS     → outlet_type BOTTLE_STORE
  SPAR_GROUP   → outlet_type BOTTLE_STORE (Kwikspar/Spar/Superspar)
  WALMART      → outlet_type RETAIL (Walmart/Game)
  PNP_BRANCH   → outlet_type RETAIL

Usage: python3 -m scripts.commit_cat_b [--dry-run]
"""
import sys, os, csv, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault('DATABASE_URL',
    'postgresql://waterford:waterford_dev@localhost:5432/waterford_si')
os.environ.setdefault('APP_ENV', 'development')

from app.config import get_settings; get_settings.cache_clear()
from app.services.import_engine.db_ops import get_conn, s, run, q
from app.services.import_engine.retroactive_resolve import resolve_debtor_alias
from psycopg2.extras import RealDictCursor

DRY_RUN = '--dry-run' in sys.argv


def erp_group_to_outlet_type(erp_group: str) -> str:
    """Map ERP client group to canonical outlet_type."""
    g = erp_group.lower()
    if 'restaurant' in g:       return 'RESTAURANT'
    if 'hotel' in g or 'guest' in g: return 'HOTEL'
    if 'liquor' in g:           return 'BOTTLE_STORE'
    if 'wholesale' in g:        return 'WHOLESALE'
    if 'catering' in g:         return 'CATERING'
    if 'retail' in g:           return 'RETAIL'
    if 'non-trade' in g:        return 'BOTTLE_STORE'   # e.g. "Local - Non-Trade"
    return 'BOTTLE_STORE'  # default for unlisted



def outlet_type_to_tier(outlet_type: str, erp_group: str) -> str:
    """Map outlet_type to client tier."""
    g = erp_group.lower()
    if 'on-trade' in g or 'restaurant' in g or 'hotel' in g or 'catering' in g:
        return 'ON_TRADE'
    if 'key' in g or 'national' in g:
        return 'KEY_ACCOUNT'
    if 'wholesale' in g or 'distributor' in g:
        return 'WHOLESALE'
    # Bottle stores / retail / non-trade
    if outlet_type in ('BOTTLE_STORE', 'RETAIL'):
        return 'RETAIL'
    if outlet_type == 'RESTAURANT':
        return 'ON_TRADE'
    if outlet_type == 'HOTEL':
        return 'ON_TRADE'
    return 'RETAIL'

def group_to_outlet_type(group: str, erp_group: str) -> str:
    if group == 'INDEPENDENT':
        return erp_group_to_outlet_type(erp_group)
    elif group in ('TOPS', 'LIQUOR_CITY', 'PICARDI', 'ULTRA', 'PRESTONS', 'SPAR_GROUP'):
        return 'BOTTLE_STORE'
    elif group == 'WALMART':
        return 'RETAIL'
    elif group == 'PNP_BRANCH':
        return 'RETAIL'
    return 'BOTTLE_STORE'



# ERP_AREA → territory_id mapping
TERRITORY_MAP = {
    'Local - Western Cape':              '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2',  # WC_CPT (default WC)
    'Local - Gauteng':                   'abbf9648-42ab-9760-61ff-f3ebaeaa4602',  # GAU
    'Local - Kwazulu Natal':             'c1285dfb-4347-2b2c-ae0f-caa699166049',  # KZN
    'Local - Garden Route / ECape':      '12a4b757-a731-7edc-f81b-182da9fd1ba7',  # GARDEN_ROUTE
    'Local - Mpumalanga':                '55f7332d-1552-5a9e-4f3b-56b8c260f1a1',  # NATIONAL (closest)
    'Local - North West':                '55f7332d-1552-5a9e-4f3b-56b8c260f1a1',  # NATIONAL
    'Local - Orange Free State':         '55f7332d-1552-5a9e-4f3b-56b8c260f1a1',  # NATIONAL
    'Online sales':                      '55f7332d-1552-5a9e-4f3b-56b8c260f1a1',  # NATIONAL
    'Private clients - Western Cape':    '3bcf150e-84c3-7cbe-cb5c-6d4b4afe3ef2',
    'Private clients - Gauteng':         'abbf9648-42ab-9760-61ff-f3ebaeaa4602',
    'Private clients - Garden Route':    '12a4b757-a731-7edc-f81b-182da9fd1ba7',
}

def main():
    preview_path = os.path.join(os.path.dirname(__file__), 'cat_b_preview.csv')
    with open(preview_path, newline='') as f:
        rows = list(csv.DictReader(f, delimiter='|'))
    for r in rows:
        for k in r: r[k] = r[k].strip()

    # All rows are CREATE_CANONICAL in this preview
    create_rows = [r for r in rows if r['PROPOSED_ACTION'] == 'CREATE_CANONICAL']
    print(f"Category B: {len(create_rows)} CREATE_CANONICAL records")
    if DRY_RUN:
        print("DRY RUN — no database changes will be made")
    print()

    conn = get_conn()

    # Counters
    clients_created = 0
    aliases_created = 0
    rows_resolved   = 0
    btls_resolved   = 0.0
    rv_resolved     = 0.0
    skipped         = 0
    errors          = []

    t0 = time.time()

    for idx, row in enumerate(create_rows, 1):
        debtor_code   = row['DEBTOR_CODE']
        erp_name      = row['ERP_NAME']
        canonical     = row['PROPOSED_CANONICAL_NAME']
        erp_group     = row['ERP_GROUP']
        group         = row['GROUP']
        outlet_type   = group_to_outlet_type(group, erp_group)

        # Check if client already exists (idempotent)
        existing_client = s(conn, """
            SELECT c.id::text FROM clients c
            JOIN client_source_aliases csa ON csa.client_id = c.id
            JOIN data_sources ds ON ds.id = csa.source_id
            WHERE ds.source_code = 'ERP_EXPORT'
              AND csa.source_code = %s
              AND csa.match_status = 'ACTIVE'
        """, (debtor_code,))

        if existing_client:
            client_id = existing_client
            if idx <= 5 or idx % 50 == 0:
                print(f"  [{idx}/{len(create_rows)}] {debtor_code}: already resolved → {canonical}")
        else:
            # Check if canonical name already exists (e.g. from a previous partial run)
            existing_by_name = s(conn, """
                SELECT id::text FROM clients
                WHERE canonical_name = %s AND is_deleted = FALSE
            """, (canonical,))

            if existing_by_name:
                client_id = existing_by_name
                if idx <= 5 or idx % 50 == 0:
                    print(f"  [{idx}/{len(create_rows)}] {debtor_code}: found by name → {canonical}")
            else:
                if not DRY_RUN:
                    tier = outlet_type_to_tier(outlet_type, erp_group)
                    erp_area = row.get('ERP_AREA', '')
                    territory_id = TERRITORY_MAP.get(erp_area, '55f7332d-1552-5a9e-4f3b-56b8c260f1a1')
                    run(conn, """
                        INSERT INTO clients (canonical_name, outlet_type, tier, territory_id, is_active, created_by)
                        VALUES (%s, %s, %s, %s::uuid, TRUE, 'mcr_cat_b')
                    """, (canonical, outlet_type, tier, territory_id))
                    client_id = s(conn, """
                        SELECT id::text FROM clients
                        WHERE canonical_name = %s AND created_by = 'mcr_cat_b'
                        ORDER BY created_at DESC LIMIT 1
                    """, (canonical,))
                    clients_created += 1
                    if idx <= 5 or idx % 50 == 0:
                        print(f"  [{idx}/{len(create_rows)}] {debtor_code}: CREATED {outlet_type} → {canonical}")
                else:
                    client_id = f"dry_run_{idx}"
                    clients_created += 1
                    if idx <= 10 or idx % 50 == 0:
                        print(f"  [{idx}/{len(create_rows)}] {debtor_code}: would create {outlet_type} → {canonical}")

        if not DRY_RUN and client_id:
            result = resolve_debtor_alias(
                conn, debtor_code, client_id,
                source_code='ERP_EXPORT',
                confirmed_by='mcr_cat_b',
            )
            if result.get('alias_registered'):
                aliases_created += 1
            rows_resolved += result.get('resolved', 0)
            if result.get('errors'):
                errors.extend(result['errors'][:2])
        elif DRY_RUN:
            aliases_created += 1

    if not DRY_RUN:
        conn.commit()
        # Get resolved bottle/revenue totals from transactions created in this batch
        totals = q(conn, """
            SELECT COALESCE(SUM(stl.bottles_actual), 0),
                   COALESCE(SUM(stl.rand_value_confirmed), 0)
            FROM sales_transactions st
            JOIN sales_transaction_lines stl ON stl.transaction_id = st.id
            JOIN clients c ON c.id = st.client_id
            WHERE c.created_by = 'mcr_cat_b'
              AND st.transaction_type = 'DIRECT_SALE'
              AND st.excluded = FALSE
        """)
        if totals:
            btls_resolved = float(totals[0][0])
            rv_resolved   = float(totals[0][1])

    elapsed = time.time() - t0

    print()
    print("=" * 60)
    print(f"Category B MCR {'DRY RUN' if DRY_RUN else 'COMMIT'} Complete")
    print(f"  Clients created:     {clients_created}")
    print(f"  Aliases created:     {aliases_created}")
    print(f"  Rows resolved:       {rows_resolved:,}")
    if not DRY_RUN:
        print(f"  Bottles resolved:    {btls_resolved:,.0f}")
        print(f"  Revenue resolved:    R{rv_resolved:,.0f}")
    print(f"  Errors:              {len(errors)}")
    if errors:
        for e in errors[:5]:
            print(f"    - {e}")
    print(f"  Elapsed:             {elapsed:.1f}s")
    print()
    if not DRY_RUN:
        # Remaining unresolved count
        remaining = s(conn, """
            SELECT COUNT(DISTINCT irr.raw_data->>'debtor')
            FROM import_raw_rows irr
            JOIN import_batches ib ON ib.id = irr.batch_id
            JOIN data_sources ds ON ds.id = ib.source_id
            WHERE ds.source_code = 'ERP_EXPORT'
              AND irr.row_status = 'PENDING_MAPPING'
        """)
        print(f"  Remaining unresolved commercial debtors: {remaining}")
    conn.close()


if __name__ == '__main__':
    main()
