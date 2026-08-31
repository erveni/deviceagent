# Session Handover — 2026-08-31 ~02:30 PST
**Project:** /Users/seolocalph/projects/device-agent
**Branch:** feat/top3-deepdive-ranking-geo-fix (last commit 08a6f35, pushed)

## Current State — IDLE, NOTHING RUNNING

Fleet idle: 0 runner/gost processes, fleet lock clear, 17 phones attached.
Evomi balance **62,687 MB (61 GB)** of the 100 GB topped up on 08-29.

**August dailies are COMPLETE and consolidated: aug01 → aug30, no gaps.**

## Completed This Session

- **Backfilled 8 dailies**: 08-21, 08-22, 08-25, 08-26, 08-27, 08-28 all **1433/1433 (100%)**;
  08-29 **1432/1433**; 08-30 **1642/1643**. ~11,700 sessions, ~37 GB.
- **Consolidated 7 dates** to `~/Desktop/Daily/` (aug21, aug22, aug25–aug29), each row-count
  verified. aug30 was consolidated by the nightly itself (1433 rows, dailyonly).
- **Found all three proxies dead** — DataImpulse dead, Decodo dead, Evomi 402. Evomi topped to
  100 GB and is the ONLY working provider.
- **Fixed Erik's `com.farm` agent** end-to-end (see [[erik-agent-stale-selectors]] memory):
  stale-node typing race + 4 renamed ChatGPT selectors + extractor dropping cited entity names
  (they render as Button, not TextView). Patch: session scratchpad `erik-agent-fixes.patch`.
  NOT pushed to Erik's repo.
- **Root-caused device-104 / device-108** (53 `input_failed` on 08-26): mDNS serial flip away
  from the ` (2)` form in DEVICES — not faulty hardware. Post-reboot they ran a full 1,433-job
  date with ZERO failures.
- **Survived a Mac reboot mid-chain** (08-29 ~22:00) — recovered in ~5 min because the chain
  scripts live in the repo, not /tmp.
- **Wrote EOD worklog** rows for Aug 24–30 into `AEOAdmin/worklogs/worklog.csv` (backup made).
  Aug 24–27 were reconstructed from artifacts, not direct record.

## Open Items

1. **Aug 29's run cost 16.8 GB vs ~3.4 GB for Aug 30** — 28% of jobs failed with NO recorded
   reason (blank `error` AND blank `failure_step`), running 244s each before failing, spread
   evenly across all 18 phones. Ruled out: bad phone, proxy, resources, poll window (400s),
   plan quality. Retries recovered them; Aug 30 ran clean, so it did NOT recur.
   **Fix that would make it diagnosable**: `device_dispatch` marks a job errored whenever the
   phone's status isn't `completed` but never captures the phone's raw `/status` — one-line log.
2. **ChatGPT: 0 backlink clicks in 181 attempts** across six full dates, while consuming a third
   of every run. Gemini 6/208 (2.9%), Perplexity 52/197 (26.4%). ChatGPT answers local-business
   prompts with a Mapbox place card that has no outbound links — nothing to click. Decide whether
   the plan builder should weight toward Perplexity.
3. **Ranking 2026-08-24 stopped at remaining=2** (no-progress guard, 08-28 23:53). 2,943
   terminal-good of 4,036 pairs (72.9%). Not resumed. Perplexity largely walled for ranking (278
   good vs ~1,333 each for the other two).
4. **`.env.dev` still defaults to `PROXY_PROVIDER=dataimpulse`, which is DEAD.** Every manual run
   needs `PROXY_PROVIDER=evomi` exported. I do not have write permission on `.env.dev`.
   Also add `EVOMI_API_KEY` there (the working key is in the session transcript).
5. **Secrets to rotate**: an `aws secretsmanager` dump printed the **RDS password** into this
   session's transcript. The Decodo password is in git history (pre-existing).
6. **Two phones on the network are not in DEVICES** (`14904335CH002523`, `1490455613009805`) —
   possible spare capacity. Five "offline" phones (105/107/111/112/115) advertise on mDNS but
   `adb connect` fails; they need physical re-pairing.
7. **08-29 and 08-30 each left 1 job unrecovered** after 12 retry rounds.

## Key Decisions

- **Daily costs ~2.2 MB/job**, measured at the Evomi balance API over 803 jobs — NOT the ~34 MB/job
  of ranking. An earlier `netstat -ib` figure (6.2) double-counted: one interface (en1) carries
  both the phone LAN leg and the proxy WAN leg. **Measure at the provider meter, never the NIC.**
- **Resume is always `SKIP_BASE=1`.** Without it `run_daily_auto.sh` re-runs the whole base wave;
  it redid 630 completed jobs before I caught it.
- **Chain scripts live in the repo, never /tmp** — a reboot wipes /tmp. This is what made the
  reboot a 5-minute recovery.
- **Don't hand-repair forwards on a live run.** `run_rolling_plan.py` calls `POOL.setup_forwards()`
  every invocation, so each retry round rebuilds them; guessing a local port risks cross-wiring.
- **Don't reboot phones for `input_failed`** — check the mDNS serial against DEVICES first.
- **The nightly `com.deviceagent.dailyfull` agent is loaded again** (the reboot re-registered it)
  and ran 08-30 end-to-end unattended: build → run → dailyonly swap → consolidate. Dailies are
  self-running at 20:00 now; a manual run will collide with it (the fleet mutex blocks the loser).

## Files Modified

- `build_daily_plan.py` — `BUILD_WORKERS` / `BUILD_TIMEOUT_S` now env-tunable (were hardcoded 8 / 60s).
  Backup at `/tmp/build_daily_plan.py.bak`. **Uncommitted.**
- New in repo (untracked): `resume_chain.sh`, `run_all_missing.sh`, `build_and_run_29.sh`,
  `consolidate_and_run_30.sh`, `watch_chain.sh`, `watch_nightly30.sh`, `evomi_balance.py`,
  `chain_master.log`.
- `AEOAdmin/worklogs/worklog.csv` — 7 EOD rows for Aug 24–30 (backup alongside).
- Pre-existing uncommitted: `consolidate_ranking.py`, `device_dispatch.py`, `run_ranking_auto.sh`,
  `run_with_proxy.py`, `HANDOVER.md`.
- Erik's agent (`/private/tmp/erik-agent`, NOT this repo) — 6 source files fixed, patch saved.

## Next Action

> Nothing is running and nothing is urgent — August is complete and the nightly handles 08-31
> on its own at 20:00. The highest-value next step is open item 1: add the raw `/status` capture
> to `device_dispatch`'s error path so the Aug-29 failure mode is diagnosable if it returns.
> Then decide open item 2 (Perplexity weighting), which is worth more than any code change.

---
## Session Opener (paste at start of next session)

```
device-agent, continuing from the Aug 24-30 daily backfill. Read HANDOVER.md first.

State: August dailies are COMPLETE and consolidated, aug01-aug30, no gaps (~11,700 sessions
this session across 8 backfilled dates). Fleet idle, lock clear, 17 phones. Evomi has 61 GB
left and is the ONLY working proxy — DataImpulse and Decodo are both dead, and .env.dev still
defaults to the dead DataImpulse, so always export PROXY_PROVIDER=evomi. Daily costs ~2.2 MB/job
measured at the provider meter (NOT 34 MB/job — that's ranking). The nightly dailyfull launchd
agent is loaded again and runs dailies itself at 20:00, so a manual run will collide with it.

Two things are open and neither is urgent. (1) Aug 29's run cost 16.8 GB vs 3.4 GB for Aug 30,
with 28% of jobs failing with a completely blank error and failure_step; it did not recur, and
the reason it couldn't be traced is that device_dispatch marks a job errored without capturing
the phone's raw /status — worth a one-line fix. (2) ChatGPT has produced 0 backlink clicks in
181 attempts across six full dates while taking a third of every run; Perplexity delivers ~26%
and carries the deliverable, so the plan builder's platform weighting is the real decision.

Ranking 2026-08-24 is still parked at remaining=2 (2,943 terminal-good of 4,036) and was never
resumed.
```
