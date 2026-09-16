"""
Category B preview generator.

Produces a structured preview of all 412 Category B unresolved commercial ERP
debtor codes proposed for canonicalisation. NO database changes are made.

The preview distinguishes:
  - INDEPENDENT: unique named standalone business
  - TOPS: Tops/SPAR franchise stores (multiple distinct trading entities)
  - LIQUOR_CITY: Liquor City franchise stores
  - PICARDI: Picardi Rebel chain stores
  - ULTRA: Ultra Liquors chain stores
  - PRESTONS: Prestons Liquor chain (Garden Route)
  - MAKRO_NEW: Makro store codes not yet aliased (map to existing Makro canonical)
  - CHAIN_OTHER: Other recognisable chains (Kwikspar, Spar, Pick n Pay KZN, Walmart)

Outputs: backend/scripts/cat_b_preview.csv  (UTF-8, pipe-delimited)
         backend/scripts/cat_b_preview_summary.txt
"""
import os, sys, csv, io
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault('DATABASE_URL',
    'postgresql://waterford:waterford_dev@localhost:5432/waterford_si')
os.environ.setdefault('APP_ENV', 'development')

from app.config import get_settings; get_settings.cache_clear()
from app.services.import_engine.db_ops import get_conn
from psycopg2.extras import RealDictCursor

# ── Classification rules ─────────────────────────────────────────────────────
def classify(code: str, name: str, grp: str, srepname: str) -> tuple[str, str]:
    """
    Returns (group_code, group_label) for display in the preview.
    group_code controls how bulk creation would work:
      - INDEPENDENT → one new canonical client per row
      - TOPS/LIQUOR_CITY/etc. → chain stores: one canonical per location, chain noted
      - MAKRO_NEW → alias to existing Makro canonical (no new canonical)
    """
    c = code.upper()
    n = name.upper()

    # Makro store codes → alias to existing Makro canonical (not a new client)
    if c.startswith('MAKRO') or c.startswith('MAKR') or c == 'MAKCAPGA':
        return ('MAKRO_ALIAS', 'Makro store (alias to existing Makro canonical)')

    # Tops chain
    if (c.startswith('TOPS') or 'TOPS' in n[:6]
            and ('TOPS' in c or c.startswith('TOPSL') or c.startswith('TOPSM')
                 or c.startswith('TOPSK') or c.startswith('TOPSG') or c.startswith('TOPSU')
                 or c.startswith('TOPSIS'))):
        return ('TOPS', 'Tops franchise location')

    # Liquor City
    if 'LIQUOR CITY' in n or c.startswith('LIQC') or c.startswith('LIQU0') or c.startswith('LIQL'):
        return ('LIQUOR_CITY', 'Liquor City franchise location')

    # Picardi Rebel
    if 'PICARD' in n or c.startswith('PICARD'):
        return ('PICARDI', 'Picardi Rebel chain store')

    # Ultra Liquors
    if 'ULTRA LIQUORS' in n or c.startswith('ULTR') or c.startswith('ULTRA0'):
        return ('ULTRA', 'Ultra Liquors chain store')

    # Prestons chain
    if 'PRESTONS' in n or 'PRESTON' in n or c.startswith('PREST'):
        return ('PRESTONS', 'Prestons Liquor chain (Garden Route)')

    # Kwikspar (Spar group)
    if 'KWIKSPAR' in n or 'SUPERSPAR' in n or c.startswith('KWIKS') or c.startswith('SPARW') or c == 'KWIK SPA':
        return ('SPAR_GROUP', 'Spar/Kwikspar/SuperSpar location')

    # Pick n Pay KZN branches (not DC)
    if c.startswith('PICKKZN') or 'PICK N PAY' in n:
        return ('PNP_BRANCH', 'Pick n Pay branch (not DC — separate from existing PnP DCs canonical)')

    # Walmart (Massmart group, separate from Makro)
    if c.startswith('WALM') or 'WALMART' in n:
        return ('WALMART', 'Walmart location (Massmart group — separate from Makro canonical)')

    # Mano's Restaurant vs Manoushe (different ERP codes, different businesses)
    if c == 'MANO0004':
        return ('INDEPENDENT', "Mano's Restaurant (distinct from Manoushe — confirmed separate)")

    return ('INDEPENDENT', 'Named independent venue or business')


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            # Get Cat A codes to exclude
            c.execute("""
                SELECT csa.source_code FROM client_source_aliases csa
                JOIN data_sources ds ON ds.id = csa.source_id
                WHERE ds.source_code = 'ERP_EXPORT'
                  AND csa.match_status = 'ACTIVE'
                  AND csa.match_confidence = 'CONFIRMED'
            """)
            cat_a_codes = {r['source_code'] for r in c.fetchall()}

            # All commercial open debtors
            c.execute("""
                SELECT
                  irr.raw_data->>'debtor'          AS debtor_code,
                  MAX(irr.raw_data->>'drname')      AS erp_name,
                  MAX(irr.raw_data->>'drgrpname')   AS erp_group,
                  MAX(irr.raw_data->>'srepname')    AS srepname,
                  MAX(irr.raw_data->>'sareaname')   AS area,
                  ROUND(SUM((irr.raw_data->>'bottles')::numeric))   AS bottles,
                  ROUND(SUM(CASE WHEN irr.raw_data->>'net' IS NOT NULL
                      THEN (irr.raw_data->>'net')::numeric ELSE 0 END)) AS net_rev,
                  COUNT(*) AS queue_rows
                FROM import_queue_items iq
                JOIN import_raw_rows irr ON irr.id = iq.import_raw_row_id
                JOIN import_batches ib ON ib.id = irr.batch_id
                JOIN data_sources ds ON ds.id = ib.source_id
                WHERE iq.status = 'OPEN'
                  AND ds.source_code = 'ERP_EXPORT'
                  AND iq.issue_type IN ('UNKNOWN_CLIENT','PROBABLE_CLIENT')
                  AND (irr.raw_data->>'drgrpname') IN (
                    'Local - Chain Stores','Local - Liquor Stores',
                    'Local - Hotels & Guest Houses','Local - Restaurants',
                    'Local - Distributors','Local - Non-Trade','Online Clients')
                GROUP BY irr.raw_data->>'debtor'
                ORDER BY net_rev DESC
            """)
            all_rows = c.fetchall()

    finally:
        conn.close()

    # Filter to Category B only
    cat_b_rows = []
    for r in all_rows:
        code = r['debtor_code']
        if code in cat_a_codes:
            continue  # Cat A — already resolved
        # Exclude Cat D patterns
        if (code.startswith('ZZ') or code.startswith('ZJHB') or code.startswith('ZDU')
                or (r['srepname'] or '').startswith('Staff ')
                or ((r['srepname'] or '').startswith('Private Clients'))
                or (r['bottles'] == 0 and r['net_rev'] > 5000)
                or (r['erp_group'] == 'Local - Non-Trade' and 'Holdings' in (r['erp_name'] or ''))
                or code in ('EXCLU001',)
                or (r['erp_group'] == 'Local - Non-Trade' and any(
                    k in (r['erp_name'] or '').upper()
                    for k in ('DELOITTE','ACTUARI','ARGON ASSET','NINETY ONE',
                              'JORDAN TERI','RETAIL INSIGHT','ITEC','TCW ','EXCEED')
                ))):
            continue  # Cat D
        # Exclude Cat C
        if (code.startswith('NORM') or code.startswith('DIST') or code == 'LEGACY02'
                or code == 'MANO0002' or code.startswith('UNITED')
                or code.startswith('BUTC') or code.startswith('BUTCH')):
            continue  # Cat C — needs human review
        cat_b_rows.append(r)

    # Classify each
    out_rows = []
    for r in cat_b_rows:
        grp_code, grp_label = classify(
            r['debtor_code'], r['erp_name'] or '',
            r['erp_group'] or '', r['srepname'] or '')
        out_rows.append({
            'PROPOSED_ACTION':  'ALIAS_EXISTING' if grp_code == 'MAKRO_ALIAS' else 'CREATE_CANONICAL',
            'GROUP':            grp_code,
            'GROUP_LABEL':      grp_label,
            'DEBTOR_CODE':      r['debtor_code'],
            'ERP_NAME':         r['erp_name'],
            'ERP_GROUP':        r['erp_group'],
            'ERP_REP':          r['srepname'],
            'ERP_AREA':         r['area'],
            'BOTTLES':          r['bottles'],
            'NET_REV_ZAR':      r['net_rev'],
            'QUEUE_ROWS':       r['queue_rows'],
            'PROPOSED_CANONICAL_NAME': r['erp_name'],  # Exact ERP name by default
        })

    # Write CSV
    out_dir = os.path.dirname(__file__)
    csv_path = os.path.join(out_dir, 'cat_b_preview.csv')
    fields = ['PROPOSED_ACTION','GROUP','GROUP_LABEL','DEBTOR_CODE','ERP_NAME',
              'ERP_GROUP','ERP_REP','ERP_AREA','BOTTLES','NET_REV_ZAR','QUEUE_ROWS',
              'PROPOSED_CANONICAL_NAME']
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter='|')
        w.writeheader()
        w.writerows(out_rows)

    # Summary
    by_group = defaultdict(lambda: {'count':0,'bottles':0,'rev':0})
    for r in out_rows:
        g = r['GROUP']
        by_group[g]['count']   += 1
        by_group[g]['bottles'] += int(r['BOTTLES'] or 0)
        by_group[g]['rev']     += int(r['NET_REV_ZAR'] or 0)

    summary_path = os.path.join(out_dir, 'cat_b_preview_summary.txt')
    lines = [
        "Category B Preview Summary",
        "=" * 60,
        f"Total proposed records: {len(out_rows)}",
        f"  CREATE_CANONICAL: {sum(1 for r in out_rows if r['PROPOSED_ACTION']=='CREATE_CANONICAL')}",
        f"  ALIAS_EXISTING:   {sum(1 for r in out_rows if r['PROPOSED_ACTION']=='ALIAS_EXISTING')}",
        "",
        f"{'Group':<20} {'Debtors':>8} {'Bottles':>10} {'Rev ZAR':>14}  Action",
        "-" * 70,
    ]
    for grp_code in sorted(by_group.keys()):
        g = by_group[grp_code]
        action = 'ALIAS_EXISTING' if grp_code == 'MAKRO_ALIAS' else 'CREATE_CANONICAL'
        lines.append(f"{grp_code:<20} {g['count']:>8} {g['bottles']:>10,} {g['rev']:>14,}  {action}")
    lines += [
        "-" * 70,
        f"{'TOTAL':<20} {len(out_rows):>8} "
        f"{sum(by_group[g]['bottles'] for g in by_group):>10,} "
        f"{sum(by_group[g]['rev'] for g in by_group):>14,}",
        "",
        "Full detail: cat_b_preview.csv (pipe-delimited, UTF-8)",
        "",
        "PROPOSED_ACTION key:",
        "  CREATE_CANONICAL  — new canonical client + alias from exact ERP name",
        "  ALIAS_EXISTING    — new alias to existing canonical (no new canonical)",
        "",
        "No database changes have been made.",
        "To commit: run commit_cat_b.py after reviewing this preview.",
    ]
    summary = '\n'.join(lines)
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(summary)

    print(summary)
    print(f"\nFiles written:\n  {csv_path}\n  {summary_path}")


if __name__ == '__main__':
    main()
