# Session Handover — 2026-07-19 (device-agent)

**Project:** /Users/seolocalph/projects/device-agent
**Branch:** feat/top3-deepdive-ranking-geo-fix (commit `72d950d`, synced to `devicefarm1/dev`)

---

## Current State (ranking backlog — 2026-07-17 due-set) — ✅ COMPLETE

- **Real 100% delivered.** Consolidated: `~/Desktop/Rankings/ranking_stale_2026-07-17_consolidated.csv` (**4,569 rows**, 0 skipped) — success 4,543 + no_rank 12 + **14 salvaged**. Per-slot dated (each pair `last_rank+14`), range 2026-05-26..07-18, ZERO future dates, junk excluded. No backfill.
- **Run + daemon STOPPED** (marker `.ranking_2026-07-17.done` set, LaunchAgent unloaded). Fleet-connect agent (`com.deviceagent.fleet`) still up. Fleet idle.
- **Root cause of the "residue" found + FIXED** (commit `abf201d`, local): the 12 grease/cooking-oil keywords weren't unanswerable — `_rank_inconsistent` split list-item names on a plain hyphen, truncating "Ace Grease Service - St. Louis" → "Ace Grease Service", failing the name match → genuine `[RANK:1/x]` rejected as fabrication → `ocr_no_answer` forever. Fix: split on em/en dash only. Verified. (My earlier "OCR timing race" diagnosis was wrong.)
- 5 junk pairs correctly excluded: kw 55 ×3 (Leo Lapuerta duplicate botox of kw 47/biz 8), kw 4562 ×2 (test keyword).
- Salvage verified genuine 12/12 (Ace Grease really is at each claimed rank) — no fabrications shipped.

## Completed This Session

- **Admin re-run list (rerun_needed_2026-07-17.csv, 95 pairs)** → 94/95 captured, per-slot consolidated to `~/Desktop/Rankings/ranking_rerun_2026-07-17_consolidated.csv`. **User imported it + uploaded screenshots.** Hazwash = legit #1 (false-negative rejection); Natural Scalp = 19/19 real decline. 1 straggler: kw 4169 perplexity (ocr_no_answer).
- **Fleet grown 11 → 19 phones.** Added 8 new Infinix X6725/Android 15 as device-118..125 (needed socksdroid install + uninstall/reinstall of agent 0.9.52 due to signature mismatch on their shipped 0.6.3). Recovered device-117 (stale `(2)` serial). 6 phones (105,107,111,112,114,115) still physically down — need wireless-debug toggle on the handset.
- **Locked-keyword due-set bug fixed** — `build_ranking_dueset.py` now calls `/api/keywords?includeLocked=true` (API hides status='locked' by default = "won-but-rankable"). Due-set corrected 1,248→1,583 kw / 3,555→4,560 jobs (~22% was dropped). Verified every due pair genuinely stale.
- **De-hardcoded Decodo password** in run_ranking_auto.sh → `${DECODO_PASS}` from .env.dev.
- **MACMINI_SETUP.md** written — full new-machine bring-up guide for Claude.
- **Committed + pushed to `devicefarm1/dev`** (commit 72d950d). NOT main, NOT develop.
- **Ranking LaunchAgent installed** (`com.deviceagent.ranking`) — survives Mac reboots (run died ~7× today, twice from reboots).

## Key Decisions

- **Detach long runs** via `nohup … & disown` (PPID 1) so session/task restarts don't kill them; only a Mac reboot does — hence the LaunchAgent.
- **Resume with `SKIP_BASE=1`** always — the base wave doesn't apply EXCLUDE_SUCCESS and would redo all banked pairs. Results live in repo CSVs (survive reboot); /tmp does not.
- **no_rank counts as terminal/done**, not a failure — forcing it to "success" would fabricate a rank. Gate = zero error-only pairs, not literal 100%.
- **kw 55 stays excluded** (duplicate business record), kw 4562 excluded (test data). Real 100% excludes these 5.
- **Consolidation dating = per-(kw,platform) last_rank + 14d** (missed slot), NOT per-keyword (causes future dates), NOT run date.

## Files Modified (this session)

- `run_with_proxy.py` — device-117 serial fix + device-118..125 (COMMITTED 72d950d)
- `build_ranking_dueset.py` — includeLocked=true (COMMITTED 72d950d)
- `run_ranking_auto.sh` — de-hardcoded password (COMMITTED 72d950d)
- `MACMINI_SETUP.md` — new-machine setup doc (COMMITTED 72d950d)
- `_ranking_daemon.sh` — NEW ranking-run supervisor (uncommitted, local)
- `~/Library/LaunchAgents/com.deviceagent.ranking.plist` — NEW LaunchAgent (local)
- `_consolidate_rerun_2026-07-17.py` — re-run per-slot consolidator (uncommitted)

## Open Items (pick up next)

1. **Ranking backlog convergence** — let the daemon grind the 16 real to done/plateau. On `NO PROGRESS`, bring the stuck grease list to the user by name; consolidate the rest.
2. **Consolidation decisions (BLOCK consolidation):**
   - Backfill 368 multi-slot rows? → **recommend NO** (creates fabricated-date rows w/ July screenshots under earlier dates).
   - Filter ~90 future-dated leftovers? → **recommend YES** (pairs from old pre-fix due-set compute past today).
3. **NEW TASK — evaluate `feature/develop` branch as the next device-agent / new run approach.**
   - Repo: https://github.com/DeviceFarm1/device-agent/tree/feature/develop
   - Plan: **scan it first** (`git fetch devicefarm1 feature/develop`, diff vs current — what changed in run/dispatch/agent), then **test** before adopting. Do NOT switch production runs to it until scanned + tested. **Do NOT push to `develop` or `feature/develop`** (user directive).
4. **Rotate the Decodo proxy password** — still in git history (back to initial commit).
5. **kw 4169 perplexity** re-run straggler (ocr_no_answer) — never delivered.
6. 6 dark phones (105,107,111,112,114,115) need physical wireless-debug toggle to rejoin.

## Next Action

> Ranking backlog is DONE (deliverable ready for admin import). Next: (1) the `feature/develop` TEST step — scan is done (it's a Kotlin/Ktor Android-native rewrite: on-device NordVPN/SuperProxy, device-owner, custom IME; removes the Mac Python pipeline). Build + install on ONE spare phone, exercise the Ktor routes, isolated from the live fleet. Do NOT push to develop/feature/develop. (2) Rotate the Decodo password (in git history).

---

## Session Opener (paste at start of next session)

```
Continuing device-agent. Ranking backlog (2026-07-17 due-set) is at 99.54%
(4,554/4,575), grinding the last 16 real pairs (grease/cooking-oil ChatGPT
cluster + 4 crystal-shop) via the com.deviceagent.ranking LaunchAgent
(240s timeout, reboot-durable). 5 junk pairs correctly excluded (kw 55
duplicate botox, kw 4562 test) — real 100% = 4,570. Code fixes committed +
pushed to devicefarm1/dev (72d950d); NOT main/develop. LaunchAgent files
(_ranking_daemon.sh + plist) are local/uncommitted.

NEW TASK the user wants started while the backlog finishes: scan then test
the feature/develop branch (https://github.com/DeviceFarm1/device-agent/tree/
feature/develop) as a potential new device-agent / new way of running —
git fetch + diff vs current first, report what changed, do NOT adopt or push
to develop/feature/develop until scanned + tested.

Consolidation is blocked on two user decisions: backfill 368 multi-slot rows
(rec: no) and filter ~90 future-dated leftovers (rec: yes). Also open: rotate
the Decodo password (in git history), kw 4169 perplexity straggler, 6 dark
phones needing physical toggle. Start by fetching + diffing feature/develop.
```
