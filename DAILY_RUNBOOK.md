# Daily Run Runbook

How the daily fleet job is built, run, and shipped. The daily runs every day across
the 10-phone fleet, querying ChatGPT / Gemini / Perplexity for each active business's
keywords (and clicking the backlink where one is configured).

> Companion docs: `CLAUDE.md` (architecture), `MAC_FLEET_SETUP.md` (new-Mac onboarding).

---

## 1. What a daily is

One daily ≈ **1,318 sessions**:

- **~208 active businesses** (across all active clients)
- × **~2 active keywords each** (≈439 business+keyword combos)
- × **3 platforms** (ChatGPT, Gemini, Perplexity)

Each `(keyword, platform)` is one session. The number drifts day to day as the active
book of business changes — it is **not** a fixed value.

---

## 2. Plan-build rules (`build_daily_plan.py`)

Per the user directive (2026-06-08). When building or verifying a plan, ALL must hold:

1. **8 sessions max per CAMPAIGN/location** (`CAP = 8`). If a campaign has more than 8
   active keywords, sample down to 8.
2. **Active keywords only** — `active(o) = o.get("isActive") or o.get("status") ==
   "active"`. The keyword's **business** and **client** must also be active. (This is
   the "~5 active keywords" you'll often see — it's whatever is active, capped at 8.)
3. **12 sessions for the 3 priority locations** (`PRIORITY_TARGET = 12`):
   - Black Car IQ Lindon (business_id **1**)
   - AppsTango 3300 Triumph (business_id **4**)
   - Leo Lapuerta MD — 1919 La Branch (matched on campaignName "1919 La Branch",
     business_id **8**)

   To reach 12 with fewer than 12 keywords, a keyword is repeated on a platform not
   yet used for it.
4. **One platform per keyword**, round-robin across `[ChatGPT, Gemini, Perplexity]`;
   grouping is by `campaignName`, so multi-location businesses (e.g. Leo) are capped
   and targeted **per location**.
5. **Exclude Free-Trial plan IDs** (ranking-only, never daily) via
   `EXCLUDE_PLAN_IDS_FILE` (default `/tmp/exclude_plan_ids.json`).
6. **Force-cover** rules: certain campaign/location must get a session on a named
   platform (silent-platform alerts) — see `FORCE_PLATFORM` / `FORCE_KEYWORD`.

### Verify a built plan

- Max jobs/campaign is **12 for the 3 priority campaigns only**, **≤8 for all
  others**, and **none over 12**.

```bash
python3 - <<'PY'
import json, collections
p = json.load(open("daily_plan_2026-06-28.json"))
jobs = [j for w in p["waves"] if isinstance(w, list) for j in w]
by = collections.Counter(j["campaign_id"] for j in jobs)
over = {c: n for c, n in by.items() if n > 12}
print("total jobs:", len(jobs), "| campaigns:", len(by), "| max:", max(by.values()))
print("OVER CAP (should be empty):", over)
PY
```

### Build a plan

```bash
cd ~/projects/device-agent
set -a; source .env.dev; set +a
# CRITICAL: restore the free-trial exclude list first — it lives in /tmp and vanishes.
cp -f exclude_plan_ids.backup.json /tmp/exclude_plan_ids.json
EXECUTOR_TOKEN=<token> DATE=2026-06-28 python3 build_daily_plan.py
# DRY_RUN=1 prints the distribution + priority/force-cover checks without writing.
```

---

## 3. Run the daily (`run_daily_auto.sh`)

Runs the base wave, then loops a **REMAIN rebuild + rerun** until ~100% or no progress.

```bash
cd ~/projects/device-agent
set -a; source .env.dev; set +a
bash run_daily_auto.sh 2026-06-28          # plan must already exist
```

- `ONLY_ONLINE=1` and `probe_phones.py` auto-size the run to live phones
  (`DEVICE_EXCLUDE` = down phones, `MAX_PARALLEL` = good count). Override by exporting
  `DEVICE_EXCLUDE` / `MAX_PARALLEL` before invoking.
- Retries trigger on `input failed`, `navigate`, `proxy_unreachable`,
  `generation timeout` — these are **normal transients** that recover on retry
  (~8% per run). The loop stops at `remaining=0` or after **4 rounds with no
  progress**.
- `SKIP_BASE=1` resumes an interrupted run (skips the full base wave, goes straight to
  REMAIN retries).
- A `reconnect_watcher.sh` is launched in the background to keep flaky phones online.
- Log: `/private/tmp/daily_auto_<DATE>.log`. Per-day results:
  `daily_plan_<DATE>_results_<rowdate>.csv`.

### Catch-up / chaining

To run missed days back-to-back after another job finishes, use a small wait-then-run
chain (see `daily_chain_after_geofix.sh` for the pattern): it waits for the prior job
to exit, restores the exclude list, then runs `run_daily_auto.sh` for each date.

---

## 4. Logging / ship rules

1. **Verify `timestamp[:10] == date` for every row before shipping any daily
   deliverable.** Per-day consolidators are sed-cloned from the prior day, which only
   rewrites *string* date literals — a *numeric* date window (`dt.datetime(Y, M, D)`)
   gets missed, so `timestamp` silently stays on the old date while `date` is correct.
   This bit Jun 18–21. Prefer deriving any date window from the `DATE` variable
   (`dt.date.fromisoformat(DATE)`), never a hardcoded literal.
2. **Restore the exclude list before every build/REMAIN rebuild** —
   `cp -f exclude_plan_ids.backup.json /tmp/exclude_plan_ids.json`. It lives in `/tmp`
   and disappears; without it, free-trial campaigns leak into the daily.
3. Daily session results are cumulative in `solace_pilot_results.csv` (importer reads
   by header name — known column-drift). Audit/ranking results are date-split into
   `rabbitmq_audit_results_<DATE>*.csv`.

---

## 5. Pitfalls

- **Env sourcing is mandatory**: `set -a; source .env.dev; set +a` before any run, or
  `PROXY_USER` is empty and every job dies with TLS RST.
- **mDNS adb serials containing `(2)` must be shell-quoted** (`adb -s "$serial"`) and
  read TAB-separated; unquoted, the shell parses `(2)` as syntax, and `adb shell`
  inside a `while read` loop consumes the piped serial list (read serials into an
  array first).
- **A live run grabs ANY adb-connected phone** (including a USB test phone) via
  hardware-core serial resolution — unplug or `DEVICE_EXCLUDE` the test phone first.
- **Daily Gemini is unaffected by ranking-prompt changes** — different code path
  (backlink/save flow; success = generation happened + backlink click in-window).
