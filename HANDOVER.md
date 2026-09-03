# Session Handover — 2026-09-04 ~00:20 PST
**Project:** /Users/seolocalph/projects/device-agent
**Branch:** feat/top3-deepdive-ranking-geo-fix — pushed to **devicefarm1** (`bbba26c`)

## ⚠️ TWO BLOCKERS FOUND AT THE END OF THIS SESSION — START HERE

### 1. `build-session` REJECTS `copilot` — this is why no Copilot ran tonight

```
POST /api/llm/build-session {"keyword_id":47,"platform":"copilot"}
-> HTTP 400 {"error":"platform must be one of chatgpt, gemini, perplexity"}
```

`build_daily_plan.py` assigned Copilot correctly — the 2026-09-03 build log line 12 reads
`platform split: {'ChatGPT': 502, 'Gemini': 475, 'Copilot': 461}` — and then line 32:
`WARN: dropped 461 sessions on persistent build-session failure`, all Copilot. The plan
shipped 977 jobs instead of ~1650 and **zero Copilot ran**.

Everything on OUR side is ready (app v77 on 17/17, dispatcher, ranking path). The gate is
the AEOAdmin endpoint's platform whitelist. Two ways forward:

- **Proper:** AEOAdmin adds `copilot` to the accepted list.
- **Stopgap:** request the prompt under an accepted platform and dispatch it to Copilot.
  The daily prompt is conversational, platform-agnostic copy ("Anyone tried X for Y near
  Z?"), so this is very likely safe — but VERIFY the returned prompt has no
  platform-specific wording before relying on it.

### 2. DeepSeek is OUT OF BALANCE right now

```
platform=chatgpt    -> HTTP 500 "DeepSeek API error 402: Insufficient Balance"
platform=perplexity -> HTTP 500 (same)
```

Tomorrow's 20:00 build will fail completely unless topped up. This is the known
"build hangs at `fetching N build-session prompts`" symptom — check this BEFORE
debugging anything else in the chain.

### 3. Perplexity is NOT fully retired — `mae_plan.json`

`PLATFORMS` is `["ChatGPT","Gemini","Copilot"]` (37e665a) but `mae_plan.json` is a tracked,
PRE-BUILT file merged in after the rotation: `{ChatGPT:70, Gemini:70, Perplexity:70}`.
Those 70 Perplexity jobs ran tonight. Edit that file to finish the retirement.

## Completed This Session

- **Copilot shipped as a real in-app platform** (`EdgeCopilotFlow.kt`): audit/ranking
  flow, daily flow, and backlink clicking. Copilot answers only inside Edge —
  copilot.microsoft.com in Chrome is a hard sign-in wall.
- **Perplexity retired** from `build_daily_plan.py` (`PLATFORMS` + both `FORCE_PLATFORM`
  pins) — 37e665a.
- **Fleet: app v77 + accessibility on 17/17, Edge on 16/17.** `deploy_agent_fleet.sh`
  tracked (d3f6d41); it rebinds accessibility unattended — the "manual toggle per phone"
  in CLAUDE.md was WRONG and is corrected.
- **Ranking dispatcher understands Copilot** (69fd3d2) + rank-marker gate (a44b4fa).
- **Name-matching fix** (51eb828): a business listed WITHOUT its trailing city segment
  was judged absent from its own #1 listing and demoted as a fabrication. Fires on ALL
  platforms — 183 of 395 `ocr_no_answer` rows across the last 6 ranking CSVs carry a
  comma-segment `biz_name` (138 perplexity, 45 chatgpt).
- **Async sessions v77** (68fe119): `/session {"async":true}` + `/result` polling.
- **Measured bandwidth analysis** written into `PROXY_COST_SPEC.md` §9 (df226fc,
  corrected in 2d303ad).

## Key Measurements (all at the provider meter, not modelled)

| | |
|---|---|
| Daily | 1.96 MB/job, 91% success (1,702 jobs) |
| Ranking single-pass | 16.55 MB/job (21 jobs), 16.98 MB/job (230 jobs) |
| Copilot | **8.99 MB/job — cheapest**; ChatGPT 16.28; Gemini 24.38 |
| Daily backlinks 2026-09-02 | **Perplexity 51%**, Gemini 33%, ChatGPT **0%** |
| Copilot under 15-worker load | 45% success (36/80) vs ChatGPT 83%, Gemini 69% |
| Evomi remaining | ~45.8 GB — ~14 nights of daily; stale set needs ~53 GB+, does NOT fit |
| Decodo | REFUSING AUTH (`rejected by the SOCKS5 server (1 3)`) since 2026-09-02 |

## Things I Got Wrong (do not repeat)

- **Never measured 34 MB/job.** I inherited it from a 2026-08-29 note and presented it as
  measured "with retries", then derived a "51% retry amplification" from the gap. Both
  corrected in 2d303ad. The retry multiplier has NEVER been metered — one
  `run_ranking_auto.sh` run with balance reads either side would settle it.
- **The async fix did NOT reduce the ranking failure rate** (65% vs 67%). The
  `RemoteDisconnected` happens on the OPENING request, not from holding one open — only
  1 of 230 jobs died while polling. Don't re-attempt it expecting a different result.
- **Changed `PLATFORMS` without verifying the backend accepts the value.** That is
  blocker #1 above.

## Open Items

1. Unblock Copilot in `build-session` (whitelist or stopgap) — nothing else matters until
   this is done; Copilot cannot run in the daily at all.
2. Top up DeepSeek or tomorrow's build fails.
3. Remove Perplexity from `mae_plan.json`.
4. **Copilot's Edge weak spot:** every job `pm clear`s Edge, forcing a 4-screen first-run.
   Under concurrency that caused 23 of its 40 errors (`reset_edge` x12, `open_copilot`
   x11). Fix = clear cookies/site data instead of a full wipe so the FRE never re-runs.
5. Decodo: dashboard check — exhausted, suspended, or rotated again?
6. One phone (`...S003287`) has no Edge; adb bulk transfer hangs. Needs a physical bounce.
7. Ranking stale set: 3,287 jobs remaining, does not fit in the Evomi balance.

## Next Action

> Verify what the daily prompt looks like when requested under an accepted platform, then
> either get `copilot` whitelisted in AEOAdmin's `/api/llm/build-session` or ship the
> stopgap mapping. Check DeepSeek balance first — both platforms 402'd at 00:15.

---
## Session Opener (paste at start of next session)

```
device-agent, continuing the Perplexity->Copilot switchover.
Read HANDOVER.md first.

Copilot is fully built and deployed (app v77 on 17/17 phones, Edge on 16/17, ranking
dispatcher + backlink + rank gate all done, Perplexity retired from PLATFORMS in
37e665a). It measured CHEAPEST per job of any platform: 8.99 MB vs ChatGPT 16.28 and
Gemini 24.38.

BUT zero Copilot jobs ran on 2026-09-03. AEOAdmin's /api/llm/build-session rejects it:
HTTP 400 "platform must be one of chatgpt, gemini, perplexity". All 461 assigned Copilot
sessions were dropped and the night shipped 977 jobs instead of ~1650. Fix that first —
either whitelist copilot server-side, or request the prompt under an accepted platform
and dispatch to Copilot (the daily prompt is platform-agnostic conversational copy, but
verify before trusting it).

Also urgent: DeepSeek returned 402 Insufficient Balance at 00:15, so tomorrow's 20:00
build will fail unless topped up. And Perplexity is not fully retired — mae_plan.json is
a tracked pre-built file with 70 Perplexity jobs that bypasses PLATFORMS.

Known weak spot to fix after: Copilot pm-clears Edge every job, forcing a 4-screen
first-run walk; under 15-worker concurrency that gave 45% success vs ChatGPT 83% /
Gemini 69%. Fix = clear cookies instead of a full wipe.
```
