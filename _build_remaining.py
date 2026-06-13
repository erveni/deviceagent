#!/usr/bin/env python3
"""Generic remaining-builder for a daily plan of any DATE.

Usage: python3 _build_remaining.py 2026-06-08
Diffs daily_plan_<DATE>.json against every success row in
daily_plan_<DATE>*results*.csv and writes the not-yet-successful jobs to
daily_plan_<DATE>_REMAIN.json. Prints the remaining count on stdout (for the
auto-retry loop / dashboard).
"""
import csv, json, glob, sys
from collections import Counter

if len(sys.argv) < 2:
    print("usage: _build_remaining.py <DATE e.g. 2026-06-08>", file=sys.stderr)
    sys.exit(2)
DATE = sys.argv[1]
BALANCED = f"daily_plan_{DATE}.json"
RESULTS = sorted(set(glob.glob(f"daily_plan_{DATE}*results*.csv")))
OUT = f"daily_plan_{DATE}_REMAIN.json"


def norm(v):
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("", "null", "none") else s


def key(platform, client_id, campaign_id, biz_name, keyword_text):
    return (norm(platform).lower(), norm(client_id), norm(campaign_id),
            norm(biz_name).lower(), norm(keyword_text).lower())


done = set()
for f in RESULTS:
    try:
        for r in csv.DictReader(open(f)):
            if r.get("status") == "success":
                done.add(key(r["platform"], r["client_id"], r["campaign_id"],
                             r["biz_name"], r["keyword"]))
    except FileNotFoundError:
        pass

bal = json.load(open(BALANCED))
all_jobs = [j for w in bal["waves"] for j in w]
delta = [j for j in all_jobs
         if key(j.get("platform"), j.get("client_id"), j.get("campaign_id"),
                j.get("biz_name"), j.get("keyword_text")) not in done]

json.dump({"generated_at": bal.get("generated_at"), "total_jobs": len(delta),
           "_source": f"REMAIN auto-retry of {DATE} daily", "waves": [delta]},
          open(OUT, "w"), indent=1)

print(f"REMAIN {DATE}: {len(delta)}", file=sys.stderr)
print(f"remaining split: {dict(Counter(j['platform'] for j in delta))}", file=sys.stderr)
print(len(delta))
