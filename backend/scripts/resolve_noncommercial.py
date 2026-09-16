"""
Non-commercial MCR resolution.

Creates category-level canonical clients for non-commercial ERP debtor codes
and runs the retroactive resolver. Transactions are classified by the existing
classifier (DTC_SALE, EXPORT_SALE) and excluded from commercial market view by
DC rules — no market distortion.

Categories:
  PRIVATE_DTC   — Private Clients, Online Clients, Wine Club, Legacy Members
  TASTING_ROOM  — Tasting Room (Cash Accounts), Tasting Room - Tour Operators
  INTERNAL      — Internal-*, Staff Accounts, Non Wine Sales, Bulk Wine, Transfer
  EXPORT        — Export-EUR/USD/ZAR/GBP, Private Client - Exports
                  (large individual export clients get own canonicals)

Usage: python3 -m scripts.resolve_noncommercial [--dry-run]
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault('DATABASE_URL',
    'postgresql://waterford:waterford_dev@localhost:5432/waterford_si')
os.environ.setdefault('APP_ENV', 'development')

from app.config import get_settings; get_settings.cache_clear()
from app.services.import_engine.db_ops import get_conn, s, run, q
from app.services.import_engine.retroactive_resolve import resolve_debtor_alias

DRY_RUN = '--dry-run' in sys.argv

# Category definitions
DTC_GROUPS    = {'Private Clients', 'Online Clients', 'Wine Club', 'Legacy Members'}
TASTING_GROUPS = {'Tasting Room (Cash Accounts)', 'Tasting Room - Tour Operators'}
INTERNAL_GROUPS = {
    'Internal - Samples', 'Internal - Samples Lab Testing', 'Internal - Promotions',
    'Internal - Entertainment', 'Internal - Donations & Gifts', 'Internal - Harvest Festival',
    'Internal - Incentives', 'Internal - Stock Accounts', 'Internal - Competitions',
    'Internal - Staff Allocations', 'Internal - Wine Shows & Exhibi',
    'Staff Accounts', 'Non Wine Sales Accounts', 'Bulk Wine & Grape Sales',
    'Transfer - Non-Bonded Location',
}
EXPORT_GROUPS = {
    'Export - EUR', 'Export - USD', 'Export - ZAR', 'Export - GBP',
    'Private Client - Exports',
}

# Large individual export clients get own canonical clients
INDIVIDUAL_EXPORT_CANONICALS = {
    # drname → (canonical_name, outlet_type, tier)
    'RAKQ Limited':                   ('RAKQ Limited (UK)',     'WHOLESALE', 'KEY_ACCOUNT'),
    'SA Wineimport ApS':              ('SA Wineimport ApS',     'WHOLESALE', 'KEY_ACCOUNT'),
    'Unique Holland Wijnimport B.V.': ('Unique Holland Wijnimport', 'WHOLESALE', 'KEY_ACCOUNT'),
    'CAPE ARDOR LLC':                 ('Cape Ardor LLC (USA)',  'WHOLESALE', 'KEY_ACCOUNT'),
    'Namibia Wine Merchants Pty Ltd': ('Namibia Wine Merchants','WHOLESALE', 'KEY_ACCOUNT'),
    'WoW Beverages Ltd':              ('WoW Beverages Ltd',     'WHOLESALE', 'KEY_ACCOUNT'),
    'CAPREO GmbH':                    ('Capreo GmbH',           'WHOLESALE', 'KEY_ACCOUNT'),
    'Cassidy Wines Ltd':              ('Cassidy Wines Ltd',     'WHOLESALE', 'KEY_ACCOUNT'),
    'Indian Ocean Export Co Pty Ltd': ('Indian Ocean Export Co','WHOLESALE', 'KEY_ACCOUNT'),
    'Eastern Trading':                ('Eastern Trading',       'WHOLESALE', 'KEY_ACCOUNT'),
    'MBM Resource Trading Int Ltd':   ('MBM Resource Trading Int', 'WHOLESALE', 'KEY_ACCOUNT'),
}

# Category anchor canonicals
CATEGORY_ANCHORS = {
    'PRIVATE_DTC':   ('Waterford Private Clients (DTC)',     'RETAIL',  'RETAIL',   DTC_GROUPS),
    'TASTING_ROOM':  ('Waterford Tasting Room',              'RETAIL',  'ON_TRADE', TASTING_GROUPS),
    'INTERNAL':      ('Waterford Internal Accounts',         'WHOLESALE','WHOLESALE',INTERNAL_GROUPS),
    'EXPORT_OTHER':  ('Waterford Export Clients (Other)',    'WHOLESALE','KEY_ACCOUNT',EXPORT_GROUPS),
}

EXPORT_TERRITORY_ID  = 'ae6f0fb3-9e55-1cd0-3cf3-920083df1d36'  # EXPORT territory
NATIONAL_TERRITORY_ID = '55f7332d-1552-5a9e-4f3b-56b8c260f1a1' # NATIONAL

def main():
    conn = get_conn()
    
    # Get all pending unaliased debtors
    unresolved = q(conn, """
        SELECT 
            irr.raw_data->>'debtor'    AS code,
            MAX(irr.raw_data->>'drname')    AS drname,
            MAX(irr.raw_data->>'drgrpname') AS drgrpname,
            COUNT(*) AS rows,
            SUM((irr.raw_data->>'bottles')::numeric) AS bottles
        FROM import_raw_rows irr
        JOIN import_batches ib ON ib.id = irr.batch_id
        JOIN data_sources ds ON ds.id = ib.source_id
        WHERE ds.source_code = 'ERP_EXPORT'
          AND irr.row_status = 'PENDING_MAPPING'
          AND irr.raw_data->>'debtor' NOT IN (
              SELECT csa.source_code FROM client_source_aliases csa
              JOIN data_sources ds2 ON ds2.id = csa.source_id
              WHERE ds2.source_code = 'ERP_EXPORT' AND csa.match_status = 'ACTIVE'
          )
        GROUP BY irr.raw_data->>'debtor'
    """)
    
    print(f"Pending unaliased debtors: {len(unresolved)}")
    if DRY_RUN:
        print("DRY RUN — no database changes")
    print()
    
    # Ensure category anchor clients exist
    anchor_ids = {}
    for cat, (canonical, outlet_type, tier, _) in CATEGORY_ANCHORS.items():
        existing = s(conn, "SELECT id::text FROM clients WHERE canonical_name=%s AND is_deleted=FALSE", (canonical,))
        if existing:
            anchor_ids[cat] = existing
        elif not DRY_RUN:
            run(conn, """
                INSERT INTO clients (canonical_name, outlet_type, tier, territory_id, is_active, 
                    notes, created_by)
                VALUES (%s, %s, %s, %s::uuid, TRUE, %s, 'mcr_noncommercial')
            """, (canonical, outlet_type, tier, 
                  EXPORT_TERRITORY_ID if cat.startswith('EXPORT') else NATIONAL_TERRITORY_ID,
                  f'Category anchor for {cat} non-commercial ERP debtor codes. '
                  f'Transactions classified as DTC_SALE/EXPORT_SALE, excluded from market view.'))
            anchor_ids[cat] = s(conn, "SELECT id::text FROM clients WHERE canonical_name=%s", (canonical,))
            print(f"  Created anchor: {canonical}")
        else:
            anchor_ids[cat] = f"dry_{cat}"
            print(f"  Would create anchor: {canonical}")
    
    # Individual export canonicals
    individual_export_ids = {}
    for drname, (canonical, outlet_type, tier) in INDIVIDUAL_EXPORT_CANONICALS.items():
        existing = s(conn, "SELECT id::text FROM clients WHERE canonical_name=%s AND is_deleted=FALSE", (canonical,))
        if existing:
            individual_export_ids[drname] = existing
        elif not DRY_RUN:
            run(conn, """
                INSERT INTO clients (canonical_name, outlet_type, tier, territory_id, is_active,
                    notes, created_by)
                VALUES (%s, %s, %s, %s::uuid, TRUE, %s, 'mcr_noncommercial')
            """, (canonical, outlet_type, tier, EXPORT_TERRITORY_ID,
                  f'Individual export client. EXPORT_SALE tx-type, excluded from domestic commercial view.'))
            individual_export_ids[drname] = s(conn, "SELECT id::text FROM clients WHERE canonical_name=%s", (canonical,))
            print(f"  Created export canonical: {canonical}")
        else:
            individual_export_ids[drname] = f"dry_{canonical}"
            print(f"  Would create: {canonical}")
    
    print()
    
    # Counters
    clients_created = len([c for c in anchor_ids.values() if not c.startswith('dry')])
    # (include individual export clients)
    aliases_created = 0
    rows_resolved = 0
    rows_excluded = 0
    
    # Process each unresolved debtor
    for row in unresolved:
        code, drname, drgrpname, nrows, nbottles = row
        grp = drgrpname or ''
        
        # Determine target canonical
        target_client_id = None
        
        # Individual export clients
        if drname in INDIVIDUAL_EXPORT_CANONICALS:
            target_client_id = individual_export_ids.get(drname)
        # Export groups
        elif grp in EXPORT_GROUPS:
            target_client_id = anchor_ids.get('EXPORT_OTHER')
        # DTC/private
        elif grp in DTC_GROUPS:
            target_client_id = anchor_ids.get('PRIVATE_DTC')
        # Tasting room
        elif grp in TASTING_GROUPS:
            target_client_id = anchor_ids.get('TASTING_ROOM')
        # Internal/non-commercial
        elif grp in INTERNAL_GROUPS:
            target_client_id = anchor_ids.get('INTERNAL')
        # Prefix-based DTC
        elif any(grp.startswith(p) for p in ('Private', 'Wine Club', 'Internal', 'Staff', 'Legacy')):
            if 'Export' in grp:
                target_client_id = anchor_ids.get('EXPORT_OTHER')
            else:
                target_client_id = anchor_ids.get('PRIVATE_DTC')
        else:
            continue  # Skip: not in non-commercial categories → commercial remainder
        
        if not target_client_id or target_client_id.startswith('dry'):
            if DRY_RUN:
                print(f"  DRY: {code:12} {str(drname)[:35]:<37} → {target_client_id}")
            continue
        
        result = resolve_debtor_alias(conn, code, target_client_id,
                                       confirmed_by='mcr_noncommercial')
        if result.get('alias_registered'):
            aliases_created += 1
        rows_resolved += result.get('resolved', 0)
        
        if result.get('errors'):
            print(f"  ERROR {code}: {result['errors'][:1]}")
    
    if not DRY_RUN:
        conn.commit()
    
    print()
    print("="*60)
    print(f"Non-commercial resolution {'DRY RUN' if DRY_RUN else 'complete'}")
    print(f"  Clients created:  {clients_created + len(individual_export_ids)}")
    print(f"  Aliases created:  {aliases_created}")
    print(f"  Rows resolved:    {rows_resolved:,}")
    
    if not DRY_RUN:
        remaining = s(conn, """
            SELECT COUNT(DISTINCT irr.raw_data->>'debtor')
            FROM import_raw_rows irr
            JOIN import_batches ib ON ib.id = irr.batch_id
            JOIN data_sources ds ON ds.id = ib.source_id
            WHERE ds.source_code='ERP_EXPORT' AND irr.row_status='PENDING_MAPPING'
              AND irr.raw_data->>'debtor' NOT IN (
                  SELECT csa.source_code FROM client_source_aliases csa
                  JOIN data_sources ds2 ON ds2.id = csa.source_id
                  WHERE ds2.source_code='ERP_EXPORT' AND csa.match_status='ACTIVE'
              )
        """)
        print(f"  Remaining unaliased: {remaining}")
    conn.close()

if __name__ == '__main__':
    main()
