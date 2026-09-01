# Session Handover — 2026-09-02 ~05:30 UTC (2026-09-01 21:30 PST)
**Project:** /Users/seolocalph/projects/device-agent
**Branch:** feat/top3-deepdive-ranking-geo-fix — pushed to **devicefarm1** (last commit `15b6002`)

## ⚠️ NEXT TASK — replace Perplexity with Copilot in the daily run

**As of today, Perplexity is retired from the runs. Copilot (via Edge) replaces it.**
Nothing has been changed for this yet — it is the first job of the new session.

Where the platform set is defined:

- `build_daily_plan.py:36` — `PLATFORMS = ["ChatGPT", "Gemini", "Perplexity"]`
- Used at `:182` (`PLATFORMS[pi % 3]`), `:198` (per-keyword availability), `:201`
  (`PLATFORMS[(len(chosen) + camp_off) % 3]`). All three assume a 3-platform rotation,
  so swapping the name is necessary but not sufficient — the app must be able to run
  the platform too.
- Today's plan (`daily_plan_2026-09-01.json`) split ChatGPT 566 / Gemini 544 /
  Perplexity 533, so a swap moves ~533 jobs/day onto Copilot.

**What already exists for Copilot** (proven on-device this session, see below):
`copilot_edge_probe.py` drives Edge end-to-end — clears app, walks the 4 first-run
screens, opens Copilot, submits a prompt, returns the answer. It is a **probe, not a
platform**: there is no `FlowEngine` support, no dispatcher route, no rank parsing, no
screenshot/strip, and the backlink `targetUrl` extra is untested on Copilot. Those are
the gap between the probe and a daily-capable platform.

## Completed This Session

### Jira worklog rewrite — all 142, complete
- Rewrote every worklog comment on **devicefarmseolocal.atlassian.net**, project DVFRM
  (59 issues, 2026-03-16 → 2026-08-29): **189,611 → ~269,000 chars**.
- **Never touched `started`, `timeSpent` or author** — re-verified after every batch.
- March + April were rebuilt a second time to preserve the user's original wording
  **verbatim** (first pass had paraphrased them; 25/25 now verbatim).
- Evidence sections added: commits mined across every local repo (all branches),
  deliverables confirmed on disk with real row counts, run-log ok/err figures.
- Transitioned **all 59 issues Done → To Do** (prior statuses saved to
  `scratchpad/issue_status_backup.json`; resolution field cleared as a side effect).

### Worklog agent — built, committed, working
- `worklog_jira.py` — `gather` / `suggest` / `create`. Token resolves from **macOS
  Keychain** (`jira-devicefarmseolocal`), then `.env.dev`; `SSL_CERT_FILE` set from
  certifi internally. **No exports needed at all.**
- `.claude/agents/worklog-agent.md` — invoke by saying "worklog for <date>, <hours>".
- Two worklogs created with it on **DVFRM-164**: `11627` (Aug 31, 06:00) and `11628`
  (Sunday Aug 30's work logged Monday Aug 31 08:00 via `--evidence-date`).
- Jira displays `1d` for `8h` — the site's workday is 8h. `timeSpentSeconds=28800`.

### Timesheet xlsx
- `~/Desktop/Weekly Normal Time Sheet UPDATED.xlsx` — 124 SEOLocal comments (row 20)
  updated from Jira; hours/dates/other clients' notes untouched; original in Downloads
  unchanged. Matching was by **text**, not position — which caught that the
  **"Apr 20 - Apr 24 paid" tab carries the wrong dates** (header + row 12 say Apr 13-19,
  duplicating the prior tab). Not fixed — it is a timesheet correction, not a comment one.
- That file predates the March/April rebuild, so **16 of its cells (Apr 13-30) are one
  version behind Jira**; May-Aug are byte-identical.

### Copilot-via-Edge — feasibility proven
- Works **logged-out**, no sign-in wall, answers in ~10s.
- **Geo follows the proxy**: over an Evomi tunnel targeted at Denver 80202, a prompt
  naming no city answered "near you in Aurora, CO" with Denver addresses. A second run
  resolved to Colorado Springs — right state, wrong metro, so **state-level geo is
  proven, metro-level is not**.
- Citations navigate to real pages (Chrome Custom Tab, `cityvetted.com`, containing the
  same businesses Copilot ranked).
- Copilot swaps its right-edge button MIC↔SEND exactly like Gemini — submit must be
  gated on composer-has-text or it starts a voice call.
- Demo video: `~/Desktop/copilot_edge_demo_2026-08-31.mp4` (2:02).

### Fleet
- Samsung **device-101** (`R83L112EVWK`, SM-A075F) commented out of `DEVICES` in
  `run_with_proxy.py` and `run_daily_plan.py` — reserved for Copilot work. Verified out
  of the nightly (no forward on the 8765 range).
- **09-01 nightly was found crippled and restarted.** It ran at 47% on only 12 phones
  with a cross-wired forward table (one phone bound to two ports). Stopped it,
  `adb kill-server`, restarted with `SKIP_BASE=1` — probe went 12 → **15 good phones**,
  forward table came back clean, `remaining=1618` (the 25 done jobs were not re-run).
  **At handover time: ok=1137 / err=29 and still running.**

## Current State

- 09-01 nightly **running**, healthy, ~1137/1643 done. Evomi balance **56,339 MB**.
- Everything committed and pushed to **devicefarm1** (`15b6002`). Branch also exists on
  `origin` from earlier in the session; tracking is now devicefarm1.
- Nothing else in flight.

## Open Items

1. **Replace Perplexity with Copilot in the daily** (see top of this file).
2. **Rotate the Jira API token** — it is in the previous session's transcript in
   plaintext. Then `security add-generic-password -a "$USER" -s jira-devicefarmseolocal
   -w '<new>' -U` — one command, nothing else to change.
3. `evomi_balance.py` still has the Evomi API key **hardcoded** and is therefore
   uncommitted; `watch_nightly31.sh` depends on it.
4. Ranking **2026-08-24 still parked** at 2,943/4,036 terminal-good. Nothing schedules it.
5. `device_dispatch` still marks a job errored without capturing the phone's raw
   `/status` — the Aug-29 blank-error mode remains undiagnosable if it returns.
6. **DVFRM-69 (Apr 28)** duplicates DVFRM-66's Onboarding API text; git shows that work
   landed Apr 19. Formatted faithfully, real Apr 28 commits appended separately.
7. ~20 CSV worklog dates have no Jira worklog (05-24, 06-07, 07-19, 08-30, plus spans
   like `2026-04-30-05-03`). Left alone by instruction.
8. `run_daily_auto.sh:63` prints `[ONLY_ONLINE]: command not found` — cosmetic, the
   `eval` still sets `DOWN`/`GOOD` correctly, but it would mask a real probe error.

## Key Decisions

- **Preserve the user's wording verbatim; add, never paraphrase.** The first pass on
  March/April/May rewrote prose and *shrank* entries (week 20 by 31%). Fixed by
  splitting the original into sentences/lines and only adding structure + evidence.
  Every entry ends up longer than it started.
- **Match by text, not position.** How the mis-dated April timesheet tab was caught.
- **Only touch row 20 in the xlsx.** Rows 15-19 and 21 are other clients (WebPros/WEME)
  plus manager notes — never candidates.
- **Push to devicefarm1 only** — the team's remote. Branch re-pointed with `git branch -u`.
- **Keychain over dotfiles for secrets** — a dotfile gets backed up, synced and pasted;
  Keychain is encrypted at rest and survives reboots.
- **Don't hand-repair forwards on a live run** — `run_rolling_plan` rebuilds them each
  round; the fix is stop → `adb kill-server` → `SKIP_BASE=1`.

## Files Modified

- `worklog_jira.py` — **new.** Evidence-gathering Jira worklog tool.
- `.claude/agents/worklog-agent.md` — **new.** The agent definition.
- `copilot_edge_probe.py`, `_copilot_demo_record.py` — **new.** Copilot/Edge driver + recorder.
- `run_with_proxy.py`, `run_daily_plan.py` — Samsung device-101 commented out of DEVICES.
- `watch_nightly31.sh` — **new.** Nightly watcher (reads `daily_auto_<date>.log`).
- `run_ranking_auto.sh`, `consolidate_ranking.py`, `device_dispatch.py`,
  `build_daily_plan.py` — Evomi ranking branch, per-platform +14 dating, 90s Gemini cap,
  tunable build workers (all committed this session).
- `HANDOVER.md` — this file (previous version backed up in the session scratchpad).
- **Not committed:** `evomi_balance.py` (hardcoded API key).

## Next Action

> Retire Perplexity from the daily and stand Copilot up in its place. Start by reading
> `build_daily_plan.py:36` and the three `PLATFORMS` uses at :182/:198/:201, then decide
> whether Copilot ships as a real `FlowEngine` platform (needs Kotlin work: flow,
> dispatcher route, rank parse for its markdown tables, screenshot/strip, backlink
> `targetUrl`) or as an interim Mac-side path reusing `copilot_edge_probe.py`. Do not
> flip `PLATFORMS` until the app can actually run Copilot — otherwise ~533 jobs/day fail.

---
## Session Opener (paste at start of next session)

```
device-agent, continuing from the Jira worklog rewrite + Copilot feasibility session.
Read HANDOVER.md first.

TOP PRIORITY / NEW DIRECTIVE: as of today we STOP running Perplexity in the daily and
replace it with Copilot (via Edge). Nothing has been changed for this yet. The platform
set lives at build_daily_plan.py:36 (PLATFORMS = ChatGPT/Gemini/Perplexity) and is used
at :182, :198 and :201, all assuming a 3-way rotation. Today's plan was ChatGPT 566 /
Gemini 544 / Perplexity 533, so the swap moves ~533 jobs/day onto Copilot. Do NOT flip
PLATFORMS until the app can actually run Copilot, or those jobs just fail.

What exists: copilot_edge_probe.py drives Edge end-to-end and is PROVEN on-device —
logged-out, no sign-in wall, ~10s answers, citations that navigate to real pages, and
geo that follows an Evomi proxy at state level (Denver target answered Aurora CO once,
Colorado Springs another time — metro precision is NOT proven). It is a probe, not a
platform: no FlowEngine flow, no dispatcher route, no rank parsing for its markdown
tables, no screenshot/strip, backlink targetUrl untested. Samsung device-101
(R83L112EVWK) is already held out of the fleet for this work.

State: all 142 Jira worklogs rewritten and verified (dates/times never touched), all 59
DVFRM issues moved Done -> To Do, worklog-agent built and working (say "worklog for
<date>, <hours>"; token in macOS Keychain, no exports needed). The 09-01 nightly was
found crippled at 47% on 12 phones from a cross-wired adb forward table, stopped, adb
reset, restarted with SKIP_BASE=1 — now 15 phones and healthy. Everything pushed to
devicefarm1 (15b6002).

Still open: rotate the Jira API token (it is in the old transcript in plaintext);
evomi_balance.py has a hardcoded API key and is uncommitted; ranking 2026-08-24 is
parked at 2,943/4,036.
```
