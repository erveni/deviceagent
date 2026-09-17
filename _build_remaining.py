#!/usr/bin/env python3
"""Generic remaining-builder for a daily plan of any DATE.

Usage: python3 _build_remaining.py 2026-06-08
Diffs daily_plan_<DATE>.json against every success row in
daily_plan_<DATE>*results*.csv and writes the not-yet-successful jobs to
daily_plan_<DATE>_REMAIN.json. Prints the remaining count on stdout (for the
auto-retry loop / dashboard).
"""
import csv, json, glob, sys, os
from collections import Counter
from daily_prompt_plan import remaining_jobs

if len(sys.argv) < 2:
    print("usage: _build_remaining.py <DATE e.g. 2026-06-08>", file=sys.stderr)
    sys.exit(2)
DATE = sys.argv[1]
BALANCED = os.environ.get('DAILY_PLAN_PATH',f"daily_plan_{DATE}.json")
RESULTS_GLOB = os.environ.get(
    'DAILY_RESULTS_GLOB', os.path.splitext(BALANCED)[0] + '*results*.csv'
)
RESULTS = sorted(set(glob.glob(RESULTS_GLOB)))
OUT = os.environ.get('DAILY_REMAIN_PATH',f"daily_plan_{DATE}_REMAIN.json")
bal = json.load(open(BALANCED))
is_backfill = bal.get('daily_protocol') == 'daily-backfill-v1'


def norm(v):
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("", "null", "none") else s


def key(platform, client_id, campaign_id, biz_name, keyword_text):
    return (norm(platform).lower(), norm(client_id), norm(campaign_id),
            norm(biz_name).lower(), norm(keyword_text).lower())


def valid_mocked_location(row):
    try:
        lat, lng = float(row.get('mocked_latitude') or 0), float(row.get('mocked_longitude') or 0)
    except (TypeError, ValueError):
        return False
    return lat != 0 and lng != 0


rows = []
for f in RESULTS:
    try:
        for r in csv.DictReader(open(f)):
            if r.get("status") == "success" and (not is_backfill or valid_mocked_location(r)):
                rows.append(r)
    except FileNotFoundError:
        pass

all_jobs = [j for w in bal["waves"] for j in w]
delta = remaining_jobs(bal,rows)

json.dump({"generated_at": bal.get("generated_at"), "total_jobs": len(delta),
           "daily_protocol": bal.get("daily_protocol"), "target_date": DATE, "is_remaining": True,
           "_source": f"REMAIN auto-retry of {DATE} daily", "waves": [delta]},
          open(OUT, "w"), indent=1)

print(f"REMAIN {DATE}: {len(delta)}", file=sys.stderr)
print(f"remaining split: {dict(Counter(j['platform'] for j in delta))}", file=sys.stderr)
print(len(delta))
