# Session Handover — 2026-09-07 10:45 PST
**Project:** /Users/seolocalph/projects/device-agent
**Branch:** feat/top3-deepdive-ranking-geo-fix — `71936b9` pushed to **devicefarm1**

## THE JOB FOR THE NEXT SESSION (user's words, verbatim)

> "investigate how can we make this work like not expensive we will not waste bandwidth
> right? no mistake, you can scan /Users/seolocalph/Downloads/pdtk-trial-2026-erven-004
> and /Users/seolocalph/Downloads/pdtk-trial-2026-erven-003 see if it has skills that we
> can use, also research anything on the internet how we can improve, please deploy agent
> each, have each like test also, tell me what you need."

Concrete plan:
1. Scan both pdtk-trial folders for skills relevant to proxy bandwidth, retry policy,
   screenshot validation, fleet orchestration. `003` has ~202 `SKILL.md` files (dirs:
   commands/ docs/ hooks/ lib/ manifest.json), `004` has ~34 (plus DEPLOY-AWS.md,
   FUNCTIONS.md, LESSONS.md, METHODOLOGY.md). Both are TRIAL licenses (LICENSE-TRIAL.md,
   WATERMARK.txt) — read the license before copying anything into the repo.
2. Web research: residential-proxy bandwidth reduction for mobile browser automation —
   block images/fonts/analytics (CDP `Network.setBlockedURLs` on Chrome; a filtering
   layer on gost for Edge/Copilot where CDP is not attached), HTTP/2 + compression,
   session reuse instead of per-job tunnels, no re-render for the clean screenshot.
3. Quantify EACH bandwidth driver with the Evomi meter (`evomi_balance.py`), one at a
   time, small samples: per-job gost preflight (1431 builds in one leg), OCR
   "no answer" re-capture (247), session rotation (221), `cdp_strip_map_shot` re-render
   (ChatGPT/Gemini), Edge `pm clear` per Copilot job (doubled the daily: 3.3 -> 8.5 GB).
4. Quantify each FAILURE class the same way: `async start failed: TimeoutError` (phone
   HTTP server refusing connects — ChatGPT 34, Gemini 35), `generation timeout`
   (ChatGPT 30, Gemini 45), `input failed` (26/35 — proxy exit quality), Copilot
   `navigate failed` 44 and `reset_edge failed` 23.
5. Fleet hygiene before any measurement: **device-125** (`1490455572008742`, the
   com.farm test phone) got into the ranking pool and went 0/116 — it must be excluded
   (`DEVICE_EXCLUDE` or roster); **device-108** went 0/55 — diagnose.
6. One agent per driver: each runs a small measured sample (meter before/after, N jobs,
   one platform), reports MB/attempt and success rate, and proposes the change. No
   change ships to the live set without a number.
7. Update `PROXY_COST_SPEC.md` and the cost page
   (https://claude.ai/code/artifact/ed7e7f74-a918-4b39-9382-030554620832) with the
   with-retries numbers below.

**Ask the user for:** (a) Evomi top-up BEFORE 20:00 today (tonight's daily needs
~8.5 GB, balance is 3.6 GB); (b) whether fixes may be tried on the live stale set or
only on small measured samples; (c) whether to park Gemini in the stale set (47%,
most expensive per success) until its generation timeouts are understood.

## Completed This Session (2026-09-05 -> 09-07)
- Free-trial re-rank for clients 323-327 delivered: `~/Desktop/Rankings/ranking_freetrial_2026-09-05_consolidated.csv`, 75 rows dated 2026-09-05, all 25 Copilot shots on v79 (0 prompt leaks).
- **v79 `0.9.62-copilot-frame-top`** (`c9e3936`) fleet-wide: no clipped #1, no prompt text in Copilot shots (bubble re-query, drag-back, prompt-band splice).
- **Ranking path pm-clears Edge** before every Copilot job (`149403a`); 104/113/119/123 went 0/20 -> 4/4.
- **Validator fix** (`71936b9`): Copilot en-dash inside business names no longer reads as a fabricated rank (29/30 false rejections replayed); `_name_candidates` gets a strict " - "-prefix candidate.
- `build_ranking_dueset.py` honors `ADMIN_BASE` + `ADMIN_TIMEOUT_S` (App Runner 502s the keywords endpoint at 120 s; local build server answers in <1 min).
- Daily 2026-09-05 (1648/1648) and 2026-09-06 (100%) delivered.
- Boot-safe chain: LaunchAgent `com.deviceagent.chain0906` -> `_chain_0906_agent.sh`, log `_chain_0906.log` (repo). Resumes daily then ranking with SKIP_BASE, yields 19:45-20:30, floors at 4 GB.
- Landmine removed: `com.deviceagent.staleafter` (RunAtLoad, date 2026-08-08 baked in) -> plist renamed `.disabled`.
- `/tmp` inputs rebuilt after the 09-06 08:28 reboot; copies in `_snapshots_2026-09-02/`.
- Memory notes: `device-102-revived-by-deploy-rebind`, `reboot-wipes-ranking-inputs`.

## Current State
- **Evomi balance 3,623 MB.** Chain PAUSED at the floor (`CHAIN PAUSED` line in `_chain_0906.log`). Nothing running on the fleet.
- Stale ranking 2026-09-02: **1384 / 3492 pairs good**, ~2000 left (chatgpt 488, gemini 432, copilot 464).
- Resume after top-up: `launchctl kickstart gui/$(id -u)/com.deviceagent.chain0906`.
- Tonight 20:00: `com.deviceagent.dailyfull` fires for 2026-09-07 on its own.

## Measured cost (Evomi meter, not modelled)
| workload | MB/attempt | MB/success | basis |
|---|---:|---:|---|
| Daily (with Edge pm clear) | 3.96 | 5.2 | 09-05: 8,537 MB / 2,155 attempts / 1,648 sessions; 09-06: 8,492 MB |
| Daily, spec value (pre pm-clear) | 1.96 | ~2.2 | 09-02 |
| Ranking, single pass (spec) | 17 | ~25 | 09-03, retries off |
| **Ranking, production with retries** | **29.2** | **52.3** | 09-07 04:04-09:54: 26,836 MB / 920 attempts / 513 successes |

Ledger of the 51 GB top-up (09-06 05:43 -> 09-07 09:54): daily 09-05 8.5 GB, guard-bug
warmup loop 3.3 GB (fixed), daily 09-06 8.5 GB, ranking 26.8 GB, left 3.6 GB.

## Why ranking fails and costs (09-07 04:04-09:54, 15 phones)
- Success: chatgpt 176/290 (61%), gemini 147/314 (47%), copilot 190/316 (60%). The daily runs the same phones at 95-100%.
- Extra page loads in that leg: 1431 gost preflight builds, 247 OCR "no answer" re-captures, 221 session rotations, 96 generation-timeout retries, 78 input_failed retries, 43 navigate retries, 30 "fabricated rank" re-captures.
- Median job: chatgpt 206 s, gemini 299 s, copilot 201 s; failures run longer than successes.
- Worst phones: device-125 0/116 (must not be in pool), device-108 0/55, device-104 22/49.

## Key Decisions
- **Ranking must not waste bandwidth**: every change is measured at the meter on a small sample before touching the live set (user's instruction "no mistake").
- Copilot cap stays 4 in flight; Edge pm clear stays (it is what made Copilot work) until its bandwidth is measured against an alternative.
- Chains that must survive boots are LaunchAgents with repo-side logs, never nohup.
- Never judge a run with `tail -N` on a results CSV (multi-line `response_text`); parse rows.
- Evomi for ranking (100% state / 97% city accuracy vs Rayobyte 91% / 82%).

## Files Modified (tracked)
- `app/src/main/java/com/deviceagent/EdgeCopilotFlow.kt`, `AgentHttpServer.kt`, `app/build.gradle.kts` — v79.
- `audit_dispatch_http.py` — Edge pm clear on ranking path; `_rank_inconsistent` en-dash fix; `_name_candidates` " - " candidate.
- `build_ranking_dueset.py` — `ADMIN_BASE`, `ADMIN_TIMEOUT_S`.
- `CLAUDE.md` — v79 row.
Untracked ops scripts (repo root): `_chain_0906_agent.sh`, `_chain_0906_daily_then_rank.sh` (old, do not run), `_balance_guard.sh` (old, superseded by the agent's guard), `_rebuild_dueset_0902.sh`, `evomi_balance.py` (**hardcodes the Evomi API key — move to `EVOMI_API_KEY` in `.env.dev`**), `_snapshots_2026-09-02/`.
LaunchAgents: `~/Library/LaunchAgents/com.deviceagent.chain0906.plist` (active), `com.deviceagent.staleafter.plist.disabled`.

## Next Action
> Ask for the Evomi top-up first (deadline 20:00). Then start the investigation: read the
> LICENSE-TRIAL.md in both pdtk folders, inventory their skills against the six drivers
> above, and spawn one measuring agent per driver on a 10-20 job sample each.

---
## Session Opener (paste at start of next session)

```
device-agent. Read HANDOVER.md first (2026-09-07). Then CLAUDE.md "Copilot: cap it at 4".

Job: make ranking NOT waste bandwidth. Measured: ranking costs 29 MB/attempt and
52 MB/success with retries (26.8 GB for 513 pairs on 09-07); daily is 8.5 GB/night since
the Edge pm clear. Success 47-61% on ranking vs 95-100% on the daily with the same
phones. Drivers to measure one by one at the Evomi meter: per-job gost preflight (1431
in one leg), OCR "no answer" re-captures (247), session rotations (221), cdp strip
re-render, Edge pm clear. Failure classes: async-start timeouts, generation timeouts,
input failed, Copilot navigate/reset_edge. device-125 (com.farm test phone) is in the
pool and must be excluded; device-108 went 0/55.

Scan /Users/seolocalph/Downloads/pdtk-trial-2026-erven-003 (~202 SKILL.md) and
.../pdtk-trial-2026-erven-004 (~34) for usable skills (check LICENSE-TRIAL.md first),
research the internet for bandwidth reduction in proxied mobile browser automation, and
deploy one agent per driver to test with a measured sample. No change to the live set
without a meter number.

State: Evomi balance 3.6 GB; tonight's 20:00 daily needs ~8.5 GB — ASK FOR A TOP-UP
FIRST. Stale ranking 2026-09-02 is at 1384/3492, paused by LaunchAgent
com.deviceagent.chain0906 at the 4 GB floor; resume with
`launchctl kickstart gui/$(id -u)/com.deviceagent.chain0906` after top-up.
```
