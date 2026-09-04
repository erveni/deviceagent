# Session Handover — 2026-09-04 23:10 PST
**Project:** /Users/seolocalph/projects/device-agent
**Branch:** feat/top3-deepdive-ranking-geo-fix — pushed to **devicefarm1** (`2d87ead`)

## RUNNING RIGHT NOW — the 2026-09-02 stale ranking set, on Evomi

Launched 23:00:24 PST, `PLATFORMS=chatgpt,gemini,copilot PROXY_PROVIDER=evomi SKIP_BASE=1
WORKERS_CAP=15 ./run_ranking_auto.sh 2026-09-02 stale`. 14 workers (probe: 16 online,
device-102 DOWN by design, device-119 offline). Copilot capped at 4 in flight, Edge
pm-cleared from the Mac per Copilot job (both ported into the ranking path today).

- Progress: **434 of ~3531** (1177 keywords x 3 platforms) distinct successful pairs.
  ~3100 remain; at 14 phones expect ~8-10 h, i.e. into tomorrow morning.
- Log: `/private/tmp/ranking_auto_2026-09-02.log`. Results: `rabbitmq_audit_results_2026-09-02_ranking_*.csv`
  (timestamps are UTC with a SPACE: `2026-09-04 14:53:18` — a `T` in a compare matches nothing).
- Resume if it dies: same command. It re-runs only not-yet-good pairs.
- **Tomorrow 20:00** the daily LaunchAgent fires for 2026-09-05 and will contend for the
  fleet with a still-running ranking (fleet-lock waits 2 h then forces). Finish or stop
  the ranking before then.
- Consolidate when done: `consolidate_ranking.py` (USE_14DAY rules in memory). It now
  drops Perplexity by default — today's 20:47-23:00 run dispatched ~105 Perplexity jobs
  before `run_ranking.py`'s stale default was fixed (`64c30fa`); those rows are junk.

## Completed this session
- **Copilot 28% -> 90-98%** on the daily, at parity with ChatGPT/Gemini: `COPILOT_MAX_PARALLEL=4`
  + Mac-side `pm clear com.microsoft.emmx` per Copilot job (`run_rolling_plan.py`,
  `device_dispatch._run_session`, `run_ranking.py`). DNS bypass defaulted OFF (geo-shifts
  resolution to this GMT+8 Mac). Full story + five dead ends in CLAUDE.md "Copilot: cap it at 4".
- 2026-09-04 daily: 100% complete, consolidated (`sep04_daily_ALL_SUCCESS_consolidated.csv`, 1438/1438).
- 2026-09-03 deliverable recovered (`sep03_…`, 977/977) — its wrapper had died before consolidating.
- `copilot` whitelisted in AEOAdmin build-session (`95d16f9`, origin). Ollama build path hardened.
- Perplexity fully retired: `mae_plan.json` 70 -> Copilot, `run_ranking.py` default,
  `consolidate_ranking.py` default.
- device-122 got Edge; device-113/120 recovered by `pm clear`.
- v78 APK source committed (`6ca6853`) — NOT deployed; its reset path is moot now.

## Open items
1. **Watch the ranking run**, then consolidate. Check `pgrep -f '[r]un_ranking.py'` and
   the log; do not `pkill -f run_ranking` from a shell whose own command line contains
   that string (it killed the calling shell twice today — use `[r]un_ranking`).
2. **Evomi balance unknown** — no `EVOMI_API_KEY` on this Mac. Ranking ~17 MB/job x
   ~3100 ≈ 53 GB against ~40 GB estimated remaining. Balance-out shows as a wave of
   `input failed`. Get the key or the dashboard number.
3. `probe_phones.py` missed device-104 once (mDNS `(2)` name) — 1 phone, low priority.
4. device-102: dead AccessibilityService, needs hands. 8 stale `DEVICES` entries.
5. `.env.dev` `PROXY_PROVIDER`/`PROXY_HOST` are dead values; provider truth is
   `run_daily_auto.sh` / `run_ranking_auto.sh` blocks + the LaunchAgent plist.

## Key decisions
- Copilot is fixed by pacing + a real Edge wipe, not by exits/sign-in/DNS — measured.
- Ranking `WORKERS_CAP` raised 6 -> 15 (the 6 was a Rayobyte-era limit; Evomi carried 15 all day).
- Mae's Perplexity jobs relabelled Copilot (not deleted) — Copilot replaced Perplexity.

## Next action
> Check the ranking run is alive and how far it is; if finished, consolidate with
> `consolidate_ranking.py`; if still running at ~18:00, decide whether to stop it before
> the 20:00 daily.

---
## Session Opener (paste at start of next session)

```
device-agent. Read HANDOVER.md first, then CLAUDE.md "Copilot: cap it at 4".

The 2026-09-02 stale RANKING set is running (or was, if the Mac slept): Evomi,
PLATFORMS=chatgpt,gemini,copilot, 14 workers, Copilot capped at 4, launched 23:00 on
09-04, ~434/3531 pairs done at handover. Check `pgrep -f '[r]un_ranking.py'` and
/private/tmp/ranking_auto_2026-09-02.log. Resume with:
  PLATFORMS=chatgpt,gemini,copilot PROXY_PROVIDER=evomi SKIP_BASE=1 WORKERS_CAP=15 \
  ./run_ranking_auto.sh 2026-09-02 stale
When done, consolidate with consolidate_ranking.py (Perplexity rows are dropped by default).
Finish or stop it before the 20:00 daily on 09-05.

Copilot is SOLVED (28% -> 90-98%): in-flight cap + Mac-side pm clear. Do NOT re-chase the
sign-in sheet, proxy-exit rotation, or a DNS bypass — all measured wrong today. Perplexity
is gone everywhere. Evomi balance is unknown (no API key on this Mac) — ask for it.
```
