#!/usr/bin/env python3
"""Build the ranking due-set from ranking_reports (max(date) per keyword+platform).

Staleness comes from /api/ranking-reports — the table the cadence is actually
defined on. This:
  1. refreshes /tmp/{biz,kw,clients,rr}_admin.json (the runner reads these),
  2. computes due keyword ids for SCOPE, writes /tmp/ranking_kw_ids_<DATE>.json,
  3. prints counts (DRY-friendly preview for the dashboard).

The kw-ids file is a coarse keyword-level filter: a keyword is due when ANY of
its platforms is due. run_ranking.py re-derives the per-(keyword, platform) set
from rr_admin.json and skips pairs that are still fresh, so a keyword due on one
platform does not re-run the other two.

env: DATE (default today, UTC), SCOPE in {never_ranked|stale|all_due}
     EXECUTOR_TOKEN (catalog) and READ_API_TOKEN (ranking-reports) required.
"""
from __future__ import annotations
import json, os, sys, urllib.request
import datetime as dt
from collections import Counter

ADMIN = "https://jjm59vpn3y.us-east-1.awsapprunner.com"
TOKEN = os.environ["EXECUTOR_TOKEN"]
# /api/ranking-reports is gated by requireApiToken (Bearer), NOT X-Executor-Token.
# Sending the executor token 401s; a bare `except` here used to turn that 401 into
# an empty rr, which made every (kw, platform) pair look never-ranked downstream.
READ_TOKEN = os.environ["READ_API_TOKEN"]
DATE = os.environ.get("DATE", dt.datetime.now(dt.timezone.utc).date().isoformat())
SCOPE = os.environ.get("SCOPE", "never_ranked")
PLATFORMS = ("chatgpt", "gemini", "perplexity")
# Server caps limit at 5000, but App Runner truncates responses that large
# (IncompleteRead partway through the body). 1000 streams reliably.
RR_PAGE = 1000
# SNAP_DIR lets the dashboard preview a due-set into an isolated dir instead of
# clobbering the /tmp/*_admin.json snapshots a live run reads. Defaults to /tmp
# so the runner (run_ranking_auto.sh) behaves exactly as before.
SNAP_DIR = os.environ.get("SNAP_DIR", "/tmp")
os.makedirs(SNAP_DIR, exist_ok=True)
KW_IDS_OUT = f"{SNAP_DIR}/ranking_kw_ids_{DATE}.json"


def get(path, bearer=False, attempts=3):
    # The catalog routes authenticate via X-Executor-Token; /api/ranking-reports
    # is Bearer-gated instead (see requireApiToken in the api-server).
    headers = ({"Authorization": f"Bearer {READ_TOKEN}"} if bearer
               else {"X-Executor-Token": TOKEN})
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(f"{ADMIN}{path}", headers=headers)
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except Exception as e:
            # Retry transient truncation/timeouts; a 401 or 4xx will exhaust the
            # attempts and raise rather than degrade into an empty result.
            if attempt == attempts:
                raise
            print(f"  retry {attempt}/{attempts - 1} after {type(e).__name__}: {path}",
                  flush=True)


def fetch_ranking_reports_once():
    rows, offset, total = {}, 0, None
    while True:
        page = get(f"/api/ranking-reports?status=success&limit={RR_PAGE}&offset={offset}",
                   bearer=True)
        for r in page["data"]:
            rows[r["id"]] = r
        total = page["meta"]["total"]
        offset += RR_PAGE
        print(f"  ranking-reports {min(offset, total)}/{total} ({len(rows)} distinct)",
              flush=True)
        if offset >= total:
            break
    return rows, total


def fetch_ranking_reports(attempts=3):
    """Every successful ranking report, verified complete.

    Two failure modes must never pass silently — both end as a pair that looks
    never-ranked, which re-runs it and overwrites a real measurement (upsert key
    = keyword_id, platform, date):

      * a failed request (the old bare `except` turned a 401 into an empty rr);
      * a short fetch. The route paginates by offset over `ORDER BY created_at
        DESC` with no tiebreak, and created_at is noon-UTC-of-the-row's-date, so
        hundreds of rows share one value. A row inserted mid-fetch shifts every
        later page and drops rows from the result.

    So dedupe by id and require the distinct count to match the reported total.
    """
    for attempt in range(1, attempts + 1):
        rows, total = fetch_ranking_reports_once()
        if len(rows) == total:
            return list(rows.values())
        print(f"  short fetch: {len(rows)} distinct != {total} total — refetching",
              flush=True)
    sys.exit(f"FATAL: ranking-reports fetch incomplete after {attempts} attempts "
             f"({len(rows)}/{total}) — refusing to plan on partial history")


def active(o):
    return o.get("isActive") or o.get("status") == "active"


print(f"fetching live catalog… (scope={SCOPE}, date={DATE})", flush=True)
bizs = get("/api/businesses")
# includeLocked=true: /api/keywords hides status='locked' by default, but locked is
# "won-but-rankable" (out-of-rotation via sustained-win) and still needs ranking — the
# default filter silently dropped 335 due keywords / 1005 jobs. Locked rows carry
# isActive=True so active() below still admits them; isActive=False rows stay dropped.
kws_all = get("/api/keywords?includeLocked=true")
clients = get("/api/clients")
rr = fetch_ranking_reports()
print(f"ranking reports (success): {len(rr)}", flush=True)

kws_active = [k for k in kws_all if active(k)]
# refresh the snapshots the runner reads
for path, payload in [(f"{SNAP_DIR}/biz_admin.json", bizs), (f"{SNAP_DIR}/kw_admin.json", kws_active),
                      (f"{SNAP_DIR}/clients_admin.json", clients), (f"{SNAP_DIR}/rr_admin.json", rr)]:
    json.dump(payload, open(path, "w"))

cutoff = (dt.date.fromisoformat(DATE) - dt.timedelta(days=14)).isoformat()

# Latest successful ranking per (keyword_id, platform). `date` is the YYYY-MM-DD
# text column — compare lexicographically and never touch created_at, which is
# noon-UTC-of-the-row's-date rather than insert time.
latest = {}
for r in rr:
    kid, plat = r.get("keywordId"), (r.get("platform") or "").lower()
    if not kid or plat not in PLATFORMS:
        continue
    d = r.get("date") or (r.get("timestamp") or "")[:10]
    if not d:
        continue
    key = (kid, plat)
    if key not in latest or d > latest[key]:
        latest[key] = d

def due_platforms(kw_id):
    """Platforms whose latest successful ranking is missing or older than cutoff."""
    return [p for p in PLATFORMS
            if latest.get((kw_id, p)) is None or latest[(kw_id, p)] <= cutoff]


# A keyword is never_ranked when NO platform has ever ranked, and stale when it
# has at least one ranking and at least one platform is now due.
never, stale, due_jobs = [], [], 0
for k in kws_active:
    if k.get("archivedAt"):
        continue
    due = due_platforms(k["id"])
    if not due:
        continue
    due_jobs += len(due)
    ever_ranked = any(latest.get((k["id"], p)) for p in PLATFORMS)
    (stale if ever_ranked else never).append(k)

scope_kws = {"never_ranked": never, "stale": stale, "all_due": never + stale}[SCOPE]
kw_ids = sorted({k["id"] for k in scope_kws})
json.dump(kw_ids, open(KW_IDS_OUT, "w"))

biz_by_id = {b["id"]: b for b in bizs}
by_biz = Counter()
for k in scope_kws:
    b = biz_by_id.get(k.get("businessId"))
    by_biz[(b or {}).get("name") or f"biz{k.get('businessId')}"] += 1

scope_jobs = sum(len(due_platforms(k["id"])) for k in scope_kws)

print(f"\n=== RANKING DUE-SET ({SCOPE}) ===")
print(f"cutoff (14d before {DATE}) : {cutoff}")
print(f"never-ranked keywords : {len(never)}")
print(f"stale (>14d) keywords : {len(stale)}")
print(f"SELECTED ({SCOPE})    : {len(kw_ids)} keywords")
print(f"DUE JOBS (kw,platform): {scope_jobs}   [all_due total: {due_jobs}]")
print(f"businesses covered    : {len(by_biz)}")
print(f"kw-ids file           : {KW_IDS_OUT}")
print("top businesses:", dict(by_biz.most_common(8)))
