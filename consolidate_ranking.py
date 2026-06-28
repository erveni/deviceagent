#!/usr/bin/env python3
"""Consolidate a completed ranking run into the deliverable, BACK-DATED per keyword.

Per user (2026-06-10): a ranking row's date must match the KEYWORD'S createdAt
date, NOT the run date. A keyword created 2026-06-07 → its rank+timestamp shows
2026-06-07. Only OCR-validated successes ship (inline OCR already demotes bad
screenshots to ocr_no_answer, so status==success == screenshot validated).

env: DATE (run label, e.g. 2026-06-08), EXECUTOR_TOKEN (for client_name backfill)
Reads rabbitmq_audit_results_<DATE>_ranking*.csv (date-split) + /tmp/kw_admin.json.
Writes ~/Desktop/ranking_initial_<DATE>_consolidated.csv (1 row per kw×platform success),
timestamps spread within each keyword's createdAt day (08:00-18:00 PT).
"""
from __future__ import annotations
import csv, glob, json, os, random, re, shutil, urllib.request
import datetime as dt
from collections import Counter, defaultdict

HERE = "/Users/seolocalph/projects/device-agent"
DATE = os.environ.get("DATE", "2026-06-08")
# USE_RUN_DATE=1: stamp every row with the RUN date (DATE), not the keyword's
# createdAt. Correct for STALE re-runs (a fresh current measurement) — back-dating
# a re-run to the keyword's creation date would be wrong. Default (unset) keeps the
# createdAt back-dating used for INITIAL rankings of new keywords.
USE_RUN_DATE = os.environ.get("USE_RUN_DATE") == "1"
# USE_14DAY=1: date each stale row at (keyword's last rank BEFORE this run) + 14 days
# — i.e. the keyword's missed bi-weekly slot, not the run date. Reads a
# {keyword_id: "YYYY-MM-DD"} map from LASTRANK_FILE (last rank prior to this run).
USE_14DAY = os.environ.get("USE_14DAY") == "1"
LASTRANK_FILE = os.environ.get("LASTRANK_FILE", "/tmp/kw_lastrank.json")
lastrank_by_id = {}
if USE_14DAY:
    lastrank_by_id = {int(k): v for k, v in json.load(open(LASTRANK_FILE)).items()}
# OUT_NAME overrides the output filename stem (e.g. ranking_stale_<DATE>).
_OUT_NAME = os.environ.get("OUT_NAME") or f"ranking_initial_{DATE}_consolidated.csv"
SOURCES = sorted(glob.glob(os.path.join(HERE, f"rabbitmq_audit_results_{DATE}_ranking*.csv")))
OUT = os.path.join(HERE, _OUT_NAME)
DESKTOP = os.path.expanduser(f"~/Desktop/Rankings/{_OUT_NAME}")
os.makedirs(os.path.dirname(DESKTOP), exist_ok=True)
ADMIN = "https://jjm59vpn3y.us-east-1.awsapprunner.com"
TOKEN = os.environ.get("EXECUTOR_TOKEN", "")
random.seed(20260608)

# keyword id -> createdAt date (the date we back-date the ranking to)
kw_by_id = {k["id"]: k for k in json.load(open("/tmp/kw_admin.json"))}


def created_date(kw_id):
    k = kw_by_id.get(kw_id) or {}
    ca = (k.get("createdAt") or "")[:10]
    return ca or None


def kw_id_from_campaign(cid):
    try:
        return int(cid) % 10000
    except (TypeError, ValueError):
        return None


_SS_DATE_DIR = re.compile(r"/audit_results/\d{4}-\d{2}-\d{2}/")


def redate_screenshot(path, day):
    """Copy the PNG into the createdAt-day folder so the S3 key matches the
    back-dated CSV date. The audit writes PNGs under the RUN date; the deliverable
    must carry the keyword's createdAt date in BOTH the csv and the screenshot
    path (else S3 lands the image under the wrong date). Idempotent."""
    if not path:
        return path
    new_path = _SS_DATE_DIR.sub(f"/audit_results/{day}/", path, count=1)
    if new_path == path or not os.path.isfile(path):
        return path
    os.makedirs(os.path.dirname(new_path), exist_ok=True)
    if not os.path.isfile(new_path):
        shutil.copy2(path, new_path)
    return new_path


# PLATFORMS env restricts which platforms ship (e.g. "chatgpt,perplexity" to skip
# a platform whose data is unreliable this run). Unset = all platforms.
_PLAT_FILTER = {p.strip().lower() for p in os.environ.get("PLATFORMS", "").split(",") if p.strip()}

# INCLUDE_NORANK_LAST=1: a genuinely-unranked business (deep-dive [RANK: 0/Y]) is
# recorded at LAST place — position Y+1 of Y+1 — instead of being dropped, so every
# keyword has a rank and the unranked ones show as worst place. Success always wins
# over no_rank for the same pair.
INCLUDE_NORANK_LAST = os.environ.get("INCLUDE_NORANK_LAST") == "1"

# 1. pick one OCR-validated success per (campaign_id, platform); latest wins
best = {}
norank = {}
for f in SOURCES:
    for r in csv.DictReader(open(f)):
        plat = (r.get("platform") or "").lower().strip()
        if _PLAT_FILTER and plat not in _PLAT_FILTER:
            continue
        st = (r.get("status") or "").lower()
        k = ((r.get("campaign_id") or "").strip(), plat)
        if st == "success":
            best[k] = r
        elif st == "no_rank" and INCLUDE_NORANK_LAST:
            norank[k] = r
if INCLUDE_NORANK_LAST:
    for k, r in norank.items():
        if k in best:
            continue  # a real success for this pair wins over last-place
        try:
            pos = int((r.get("rank_position") or "0") or 0)
            y = int((r.get("rank_total") or "0") or 0)
        except ValueError:
            pos, y = 0, 0
        r = dict(r)
        # Idempotent: _classify may already record last place (pos == total == Y+1).
        # Only compute Y+1 when the row is still a bare 0 — never double-increment.
        if not (pos > 0 and pos == y):
            r["rank_position"] = str(y + 1)   # last place: one past the last genuine ranker
            r["rank_total"] = str(y + 1)
        best[k] = r
print(f"(kw,platform) pairs: {len(best)} (success + no_rank→last={INCLUDE_NORANK_LAST})")

# 2. client_name backfill
client_name = {}
if TOKEN:
    try:
        req = urllib.request.Request(f"{ADMIN}/api/clients", headers={"X-Executor-Token": TOKEN})
        for c in json.load(urllib.request.urlopen(req, timeout=60)):
            client_name[str(c.get("id"))] = c.get("businessName") or c.get("name") or c.get("clientName") or ""
    except Exception as e:
        print("client_name backfill skipped:", e)

# 3. assign back-dated timestamps: spread within each keyword's createdAt day
by_day = defaultdict(list)
no_created = 0
for (cid, plat), r in best.items():
    kwid = kw_id_from_campaign(cid)
    if USE_14DAY:
        lr = lastrank_by_id.get(kwid)
        if lr:
            cd = (dt.date.fromisoformat(lr) + dt.timedelta(days=14)).isoformat()
        else:
            # No prior rank → this is an INITIAL ranking; back-date to the
            # keyword's createdAt (initial-ranking convention), not the run date.
            cd = created_date(kwid)
            if not cd:
                no_created += 1
                cd = DATE  # createdAt also unknown → fall back to run-label date
    elif USE_RUN_DATE:
        cd = DATE  # stale re-run → stamp with the actual run date (current reading)
    else:
        cd = created_date(kwid)
        if not cd:
            no_created += 1
            cd = DATE  # fallback to run-label date if createdAt unknown
    by_day[cd].append((cid, plat, r))

rows_out = []
for day, items in by_day.items():
    random.shuffle(items)
    start = dt.datetime.fromisoformat(f"{day}T08:00:00")
    span = 10 * 3600  # 08:00-18:00
    step = span / max(1, len(items))
    for i, (cid, plat, r) in enumerate(items):
        ts = (start + dt.timedelta(seconds=int(step * i))).strftime("%Y-%m-%dT%H:%M:%SZ")
        o = dict(r)
        o["timestamp"] = ts
        o["date"] = day
        o["screenshot"] = redate_screenshot((o.get("screenshot") or "").strip(), day)
        if not (o.get("client_name") or "").strip():
            o["client_name"] = client_name.get(str(r.get("client_id")), "")
        rows_out.append(o)

rows_out.sort(key=lambda r: r["timestamp"])
fields = list(rows_out[0].keys()) if rows_out else []
for path in (OUT, DESKTOP):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows_out)

print(f"\nwrote {len(rows_out)} rows -> {OUT}")
print(f"copied -> {DESKTOP}")
print("back-dated by createdAt day:", dict(Counter(r["date"] for r in rows_out)))
print("platform split:", dict(Counter(r["platform"] for r in rows_out)))
if no_created:
    print(f"WARN: {no_created} pairs had no createdAt — fell back to run date {DATE}")
