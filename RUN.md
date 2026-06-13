# Running Dailies & Rankings (fleet Mac)

How to run a **daily** session batch or a **ranking** batch on the 10-phone fleet.
Everything runs **on the Mac** that has the phones (adb) + proxies. Residential proxy
for both. All runners loop-retry to 100% on their own.

> One-time prep before any run — export creds + cert bundle:
> ```bash
> cd ~/projects/device-agent
> export SSL_CERT_FILE=$(python3 -c "import certifi;print(certifi.where())")
> export EXECUTOR_TOKEN=$(aws secretsmanager get-secret-value --secret-id aeo-admin/prod --profile aeo-admin --region us-east-1 --query SecretString --output text | python3 -c "import sys,json;print(json.load(sys.stdin)['EXECUTOR_TOKEN'])")
> export DATABASE_URL=$(aws secretsmanager get-secret-value --secret-id aeo-admin/prod --profile aeo-admin --region us-east-1 --query SecretString --output text | python3 -c "import sys,json;print(json.load(sys.stdin)['DATABASE_URL'])")
> ```

## 0. Pre-flight check (always run first)

```bash
python3 probe_phones.py        # prints GOOD=<n> and DOWN=<excludes>
adb devices                    # raw adb list (sanity)
```
- **GOOD** = phones that pass adb + app-health. Need at least ~4 to make progress; 7–10 ideal.
- If phones are missing: `adb reconnect offline`, re-probe; 111–115 are usually physically down.

---

## 1. DAILY run

```bash
# (a) BUILD the balanced plan for a date (fresh live catalog, randomized prompts,
#     8/12-per-location caps, shuffled order). Writes daily_plan_<DATE>.json.
DATE=2026-06-15 python3 build_daily_plan.py
#     dry-run preview (no API calls, no plan written):
DATE=2026-06-15 DRY_RUN=1 python3 build_daily_plan.py

# (b) RUN to 100% (residential, auto-probes phones, retry loop until 0 remaining).
./run_daily_auto.sh 2026-06-15

# (c) CONSOLIDATE the deliverable (back-dated to each keyword's createdAt).
#     Use the dated balanced consolidator in _handover_scripts_2026-05-26/plans/.
( cd /Users/seolocalph/projects/_handover_scripts_2026-05-26/plans && python3 _consolidate_jun15_balanced.py )
# -> ~/Desktop/Daily/jun15_daily_ALL_SUCCESS_consolidated.csv
```

## 2. RANKING run

```bash
# (a) BUILD the due-set. SCOPE picks what's due:
#     never_ranked = initial rankings | stale = >14d old | all_due = both
SCOPE=stale DATE=2026-06-15 python3 build_ranking_dueset.py
#     (writes /tmp/ranking_kw_ids_2026-06-15.json + refreshes /tmp/{biz,kw,clients,rr}_admin.json)
#     Authoritative staleness = MAX(ranking_reports.date) from the DB (NOT keywords.lastRunAt).

# (b) refresh per-campaign geo (REQUIRED — geo resolves from campaign search_address):
python3 build_kw_admin.py          # DB kw catalog (INCLUDES status=locked)
python3 build_campaign_addr.py     # campaign search_address map

# (c) RUN to 100% (residential, inline OCR screenshot validation, retry loop).
./run_ranking_auto.sh 2026-06-15 stale

# (d) CONSOLIDATE.
#  - INITIAL (never-ranked):  date = each keyword's createdAt
DATE=2026-06-15 OUT_NAME=ranking_initial_2026-06-15_consolidated.csv python3 consolidate_ranking.py
#  - STALE (re-run):  date = each keyword's (last rank + 14 days)  -- the missed bi-weekly slot
python3 - <<PY
import os,json,psycopg2
c=psycopg2.connect(os.environ["DATABASE_URL"]).cursor()
c.execute("SELECT keyword_id, MAX(date) FROM ranking_reports WHERE date < %s GROUP BY keyword_id",("2026-06-15",))
json.dump({int(k):str(d) for k,d in c.fetchall() if d}, open("/tmp/kw_lastrank_before_2026-06-15.json","w"))
PY
DATE=2026-06-15 USE_14DAY=1 LASTRANK_FILE=/tmp/kw_lastrank_before_2026-06-15.json \
  OUT_NAME=ranking_stale_2026-06-15_consolidated.csv python3 consolidate_ranking.py
# -> ~/Desktop/Rankings/ranking_stale_2026-06-15_consolidated.csv
```

---

## Dating rules (important)

| Run type | Row date |
|---|---|
| Daily | each keyword's session, timestamped within the run day |
| Ranking — **initial** (never ranked) | keyword's **createdAt** |
| Ranking — **stale** (re-run) | **last rank + 14 days** (`USE_14DAY=1`) — the missed slot, NOT the run date |

## Gotchas
- **Geo per campaign:** ranking geo MUST come from the campaign `search_address`, not the business. Always run `build_kw_admin.py` + `build_campaign_addr.py` before a ranking run.
- **Locked keywords:** `/api/keywords` omits `status=locked`; the DB builders include them.
- **Geo-blocked:** campaigns with no `search_address` can't rank — team must fill the address first.
- **Proxies:** ranking caps workers at 6 (audit path does more handshakes). Daily auto-sizes to live phones.
- **"Done" = 100%:** runners loop until 0 remaining, or stop after 4 no-progress rounds (then needs a human).
- Logs: `/private/tmp/daily_auto_<DATE>.log`, `/private/tmp/ranking_auto_<DATE>.log`.

## Consolidator note
The daily balanced consolidators are date-stamped copies in
`~/projects/_handover_scripts_2026-05-26/plans/_consolidate_jun<DD>_balanced.py`.
Make a new one per date by copying the latest and substituting the date strings
(`2026-06-XX`, `2026, 6, XX`, `junXX`). Outputs go to `~/Desktop/Daily/` and `~/Desktop/Rankings/`.
