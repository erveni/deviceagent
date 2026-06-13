#!/usr/bin/env python3
"""Build the ranking due-set from the live catalog (lastRunAt source of truth).

/api/ranking-reports is empty now, so staleness comes from /api/keywords.lastRunAt
(validated 2026-06-09: 483 never-ranked, 0 stale). This:
  1. refreshes /tmp/{biz,kw,clients,rr}_admin.json (the runner reads these),
  2. computes due keyword ids for SCOPE, writes /tmp/ranking_kw_ids_<DATE>.json,
  3. prints counts (DRY-friendly preview for the dashboard).

env: DATE (default today-ish anchor), SCOPE in {never_ranked|stale|all_due}
     EXECUTOR_TOKEN required.
"""
from __future__ import annotations
import json, os, sys, urllib.request
import datetime as dt
from collections import Counter

ADMIN = "https://jjm59vpn3y.us-east-1.awsapprunner.com"
TOKEN = os.environ["EXECUTOR_TOKEN"]
DATE = os.environ.get("DATE", "2026-06-08")
SCOPE = os.environ.get("SCOPE", "never_ranked")
PLATFORMS = 3
KW_IDS_OUT = f"/tmp/ranking_kw_ids_{DATE}.json"


def get(path):
    req = urllib.request.Request(f"{ADMIN}{path}", headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def parse_dt(s):
    if not s:
        return None
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None


def active(o):
    return o.get("isActive") or o.get("status") == "active"


print(f"fetching live catalog… (scope={SCOPE}, date={DATE})", flush=True)
bizs = get("/api/businesses")
kws_all = get("/api/keywords")
clients = get("/api/clients")
try:
    rr = get("/api/ranking-reports")
except Exception:
    rr = []

kws_active = [k for k in kws_all if active(k)]
# refresh the snapshots the runner reads
for path, payload in [("/tmp/biz_admin.json", bizs), ("/tmp/kw_admin.json", kws_active),
                      ("/tmp/clients_admin.json", clients), ("/tmp/rr_admin.json", rr)]:
    json.dump(payload, open(path, "w"))

cutoff = dt.datetime.fromisoformat(f"{DATE}T00:00:00+00:00") - dt.timedelta(days=14)

never, stale = [], []
for k in kws_active:
    if k.get("archivedAt"):
        continue
    lr = parse_dt(k.get("lastRunAt"))
    if lr is None:
        never.append(k)
    elif lr < cutoff:
        stale.append(k)

scope_kws = {"never_ranked": never, "stale": stale, "all_due": never + stale}[SCOPE]
kw_ids = sorted({k["id"] for k in scope_kws})
json.dump(kw_ids, open(KW_IDS_OUT, "w"))

biz_by_id = {b["id"]: b for b in bizs}
by_biz = Counter()
for k in scope_kws:
    b = biz_by_id.get(k.get("businessId"))
    by_biz[(b or {}).get("name") or f"biz{k.get('businessId')}"] += 1

print(f"\n=== RANKING DUE-SET ({SCOPE}) ===")
print(f"never-ranked keywords : {len(never)}")
print(f"stale (>14d) keywords : {len(stale)}")
print(f"SELECTED ({SCOPE})    : {len(kw_ids)} keywords")
print(f"TOTAL JOBS (x{PLATFORMS} platforms): {len(kw_ids) * PLATFORMS}")
print(f"businesses covered    : {len(by_biz)}")
print(f"kw-ids file           : {KW_IDS_OUT}")
print("top businesses:", dict(by_biz.most_common(8)))
