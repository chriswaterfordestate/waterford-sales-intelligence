#!/usr/bin/env bash
# Waterford Sales Intelligence — Production Bootstrap
# Run this once against a brand-new empty PostgreSQL database.
# Requires: DATABASE_URL or DATABASE_URL_SYNC environment variable set.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Waterford SI Bootstrap ==="
echo "Step 1/3: Applying migrations 001-011..."
cd "$BACKEND_DIR"
python3 -m alembic upgrade head

echo ""
echo "Step 2/3: Loading canonical MCR data (clients, aliases, ownership)..."
MCR_FILE="$SCRIPT_DIR/mcr_bootstrap.sql"
if [ ! -f "$MCR_FILE" ]; then
  echo "ERROR: $MCR_FILE not found. Cannot continue."
  exit 1
fi
# Extract psycopg2-compatible connection URL
DB_URL="${DATABASE_URL:-${DATABASE_URL_SYNC:-}}"
if [ -z "$DB_URL" ]; then
  echo "ERROR: Set DATABASE_URL or DATABASE_URL_SYNC before running bootstrap."
  exit 1
fi
# psql can use postgresql:// URLs directly
psql "$DB_URL" -f "$MCR_FILE" -q
echo "MCR data loaded."

echo ""
echo "Step 3/3: Verifying bootstrap..."
python3 << 'PYEOF'
import os, psycopg2
from psycopg2.extras import RealDictCursor
url = os.environ.get('DATABASE_URL') or os.environ.get('DATABASE_URL_SYNC', '')
conn = psycopg2.connect(url)
with conn.cursor(cursor_factory=RealDictCursor) as c:
    c.execute("SELECT COUNT(*) n FROM clients")
    clients = c.fetchone()['n']
    c.execute("SELECT COUNT(*) n FROM client_source_aliases WHERE match_status='ACTIVE'")
    aliases = c.fetchone()['n']
    c.execute("SELECT COUNT(*) n FROM reps WHERE employment_status='ACTIVE'")
    reps = c.fetchone()['n']
    c.execute("SELECT COUNT(*) n FROM products")
    products = c.fetchone()['n']
    c.execute("SELECT COUNT(*) n FROM crm_health_config")
    health = c.fetchone()['n']
conn.close()
print(f"  Clients: {clients}")
print(f"  Source aliases: {aliases}")
print(f"  Active reps: {reps}")
print(f"  Products: {products}")
print(f"  Health config rows: {health}")
if clients == 0: raise SystemExit("ERROR: No clients loaded — bootstrap may have failed")
PYEOF

echo ""
echo "=== Bootstrap complete. ==="
echo "Next steps:"
echo "  1. Re-import sales data (FY2026 + FY2027) via the Import Centre in the web app."
echo "  2. Map Clerk users to reps via the Users/Access admin screen."
