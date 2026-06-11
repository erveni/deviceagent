#!/usr/bin/env python3
"""Build /tmp/campaign_addr.json — maps aeo_plan_id -> campaign search_address.

run_ranking.py resolves audit geo from the CAMPAIGN's search_address rather than
the business row, because a single business may run campaigns in several different
locations (multi-location), and new/free-trial businesses often have a bare
business record with the real address only on the campaign. The campaigns API
route (/api/client-aeo-plans) is RBAC-gated, so this reads client_aeo_plans
straight from the prod DB.

Run this before a ranking run (run_ranking.py loads the file if present; without
it, geo falls back to the business address — the old, multi-location-incorrect
behavior).

Requires psycopg2 and DATABASE_URL (read-only DB user is enough — see
AEOAdmin/docs/DATABASE_ACCESS.md §3, or pull the owner URL from Secrets Manager):

  export DATABASE_URL=$(aws secretsmanager get-secret-value \\
    --secret-id aeo-admin/prod --profile aeo-admin --region us-east-1 \\
    --query SecretString --output text \\
    | python3 -c "import sys,json;print(json.load(sys.stdin)['DATABASE_URL'])")
  python3 build_campaign_addr.py
"""
import json
import os
import sys

import psycopg2

OUT = os.environ.get("CAMPAIGN_ADDR_OUT", "/tmp/campaign_addr.json")


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL required — pull it from Secrets Manager aeo-admin/prod "
                 "(see the module docstring) or use a read-only DB user.")

    conn = psycopg2.connect(url, sslmode="require")
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, NULLIF(TRIM(search_address), '') "
                "FROM client_aeo_plans "
                "WHERE NULLIF(TRIM(search_address), '') IS NOT NULL")
            rows = cur.fetchall()
    finally:
        conn.close()

    addr = {str(plan_id): search_address for plan_id, search_address in rows}
    with open(OUT, "w") as fh:
        json.dump(addr, fh)
    print(f"wrote {OUT}: {len(addr)} campaigns with a search_address")
    return 0


if __name__ == "__main__":
    sys.exit(main())
