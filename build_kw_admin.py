#!/usr/bin/env python3
"""Build /tmp/kw_admin.json from the prod DB — including LOCKED keywords.

run_ranking.py reads /tmp/kw_admin.json as its keyword catalog. The /api/keywords
endpoint EXCLUDES status='locked' keywords, so locked-but-rankable winners (which
still need bi-weekly ranking / hold-checks) were silently dropped from runs. This
reads the keywords table directly so locked keywords are included.

Requires psycopg2 + DATABASE_URL (pull from Secrets Manager aeo-admin/prod).
"""
import json
import os
import sys

import psycopg2

OUT = os.environ.get("KW_ADMIN_OUT", "/tmp/kw_admin.json")


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL required — pull it from Secrets Manager aeo-admin/prod.")

    conn = psycopg2.connect(url, sslmode="require")
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, business_id, client_id, keyword_text, aeo_plan_id, "
                "       is_active, status, "
                "       to_char(created_at, 'YYYY-MM-DD\"T\"HH24:MI:SS.MS\"Z\"'), "
                "       archived_at "
                "FROM keywords")
            rows = cur.fetchall()
    finally:
        conn.close()

    out = [{
        "id": r[0], "businessId": r[1], "clientId": r[2], "keywordText": r[3],
        "aeoPlanId": r[4], "isActive": r[5], "status": r[6], "createdAt": r[7],
        "archivedAt": r[8].isoformat() if r[8] else None,
    } for r in rows]

    with open(OUT, "w") as fh:
        json.dump(out, fh)
    locked = sum(1 for o in out if o["status"] == "locked")
    print(f"wrote {OUT}: {len(out)} keywords ({locked} locked included)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
