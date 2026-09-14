#!/usr/bin/env python3
"""Export canonical MCR client mappings for production bootstrap."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault('DATABASE_URL_SYNC',
    'host=localhost dbname=waterford_si user=waterford password=waterford_dev')
os.environ.setdefault('APP_ENV', 'development')

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

conn = psycopg2.connect(os.environ['DATABASE_URL_SYNC'])

def q(v): return 'NULL' if v is None else "'{}'".format(str(v).replace("'","''"))

print(f"-- Waterford SI MCR Export — {datetime.utcnow().isoformat()}Z")
print("-- Load after migrations 001-011 on fresh production DB.")
print("-- DO NOT load raw transaction data from this file — re-import via Import Centre.")
print()

with conn.cursor(cursor_factory=RealDictCursor) as c:
    # Canonical clients
    c.execute("SELECT id::text,canonical_name,trading_name,outlet_type::text,tier::text,territory_id::text,notes,is_deleted FROM clients WHERE is_deleted=FALSE ORDER BY canonical_name")
    rows = c.fetchall()
    if rows:
        vals = ',\n'.join(f"  ({q(r['id'])}::uuid,{q(r['canonical_name'])},{q(r['trading_name'])},{q(r['outlet_type'])}::outlet_type_enum,{q(r['tier'])}::client_tier_enum,{q(r['territory_id'])}::uuid,{q(r['notes'])},{str(r['is_deleted']).upper()})" for r in rows)
        print(f"-- {len(rows)} canonical clients")
        print(f"INSERT INTO clients(id,canonical_name,trading_name,outlet_type,tier,territory_id,notes,is_deleted) VALUES\n{vals}\nON CONFLICT(id) DO NOTHING;\n")

    # Active confirmed aliases
    c.execute("""SELECT client_id::text,source_id::text,source_code,source_name,matched_by,confirmed_by
                 FROM client_source_aliases WHERE match_status='ACTIVE' AND match_confidence='CONFIRMED'
                 ORDER BY source_code""")
    aliases = c.fetchall()
    if aliases:
        vals = ',\n'.join(f"  ({q(a['client_id'])}::uuid,{q(a['source_id'])}::uuid,{q(a['source_code'])},{q(a['source_name'])},'CONFIRMED'::match_confidence_enum,'ACTIVE'::match_status_enum,{q(a['matched_by'])},{q(a['confirmed_by'])})" for a in aliases)
        print(f"-- {len(aliases)} confirmed source aliases")
        print(f"INSERT INTO client_source_aliases(client_id,source_id,source_code,source_name,match_confidence,match_status,matched_by,confirmed_by) VALUES\n{vals}\nON CONFLICT DO NOTHING;\n")

    # Client ownership
    c.execute("SELECT client_id::text,rep_id::text,territory_id::text,effective_from,effective_to,change_reason::text FROM client_ownership ORDER BY effective_from")
    own = c.fetchall()
    if own:
        vals = ',\n'.join(f"  ({q(o['client_id'])}::uuid,{q(o['rep_id'])}::uuid,{q(o['territory_id'])}::uuid,{q(str(o['effective_from']))},{q(str(o['effective_to']) if o['effective_to'] else None)},{q(o['change_reason'])}::ownership_change_reason_enum)" for o in own)
        print(f"-- {len(own)} ownership records")
        print(f"INSERT INTO client_ownership(client_id,rep_id,territory_id,effective_from,effective_to,change_reason) VALUES\n{vals}\nON CONFLICT DO NOTHING;\n")

conn.close()
print("-- End MCR Export")
