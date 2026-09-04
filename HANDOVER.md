# Session Handover — 2026-09-04 19:20 PST
**Project:** /Users/seolocalph/projects/device-agent
**Branch:** feat/top3-deepdive-ranking-geo-fix — pushed to **devicefarm1** (`8cd47f0`)

## Result: Copilot 28% -> 90-98%, at parity with ChatGPT/Gemini

Run finished 19:16 **ALL SUCCESS 100%** (461/461 Copilot, 572/572 ChatGPT, 545/545
Gemini unique jobs), consolidated to `~/Desktop/Daily/sep04_daily_ALL_SUCCESS_consolidated.csv`.
Post-fix window 14:08-19:16, every attempt incl. retries: **Copilot 441/489 = 90%**,
ChatGPT 490/587 = 83%, Gemini 498/565 = 88%. Best 60-row stretch: Copilot 61/62 = 98%,
thirteen of fourteen phones at 100%. Two Mac-side changes, no APK deployed:

| lever | env | effect |
|---|---|---|
| Copilot in-flight cap | `COPILOT_MAX_PARALLEL=4` (`run_rolling_plan.py`) | 28% -> 52% alone. Rate tracks concurrent Copilot sessions from the pool: ~70% at 1, 28-38% at ~5, 8% at ~15, 0/7 at 8. Chrome platforms unaffected. |
| `pm clear` Edge from the Mac before each Copilot job | `COPILOT_PM_CLEAR=1` | 52% -> 98%. The app's Settings-UI wipe logs `clearData -> true` and sometimes leaves the previous conversation on screen (device-113 0/4, device-120 2/6 -> both 100%). |

Kept OFF: `GOST_DNS_BYPASS` (default 0). Evomi refuses DoT `8.8.8.8:853` with 501 (241 in
the nightly's logs) but dialing DNS direct from this GMT+8 Mac geo-shifts resolution to
APAC edges and dropped Copilot 8/9 -> 1/6. The 501s are a wasted round trip, not a cause.

## Also fixed today
- `copilot` accepted by AEOAdmin `/api/llm/build-session` (`95d16f9`, pushed to origin).
  Last night's build dropped all 461 Copilot sessions on a 400; tonight's carried them.
- DeepSeek 402 was never a build blocker: the local Ollama fallback already carried
  2026-09-03. Local build server now rebuilds `dist/` (it is gitignored and served stale
  route code); `BUILD_TIMEOUT_S` 60 -> 180.
- device-122 had no Edge (0/15): sideloaded `~/apks/edge_151.0.4129.101.apk`.
- 2026-09-03's deliverable was never consolidated (wrapper died after `ALL SUCCESS`):
  wrote `~/Desktop/Daily/sep03_daily_ALL_SUCCESS_consolidated.csv`, 977/977.

## Things I got wrong (each stated confidently; see CLAUDE.md Copilot table)
Sign-in wall -> exit rotation -> "the phone" -> Microsoft blocks the pool -> DNS bypass.
Every one came from a small or contaminated sample: unproxied phones, `uiautomator dump`
mid-job, tests silently on Decodo (`PROXY_HOST` from `.env.dev`), 8-tunnel bursts (407s
the nightly never sees), verifying a gost bypass by grepping the word. My own first
resume ran on dead DataImpulse because `PROXY_PROVIDER=evomi` lives only in the
LaunchAgent plist — caught at 0 rows.

## Open
1. **v78 APK** `0.9.61-edge-light-reset` — built, tested on the Samsung, UNCOMMITTED, not
   deployed. Its reset path is moot now (pm clear); it still carries two useful guards
   (InPrivate exit; refuses to type a prompt into Edge's URL bar). Low priority.
2. `mae_plan.json` still ships 70 Perplexity jobs. `.env.dev` `PROXY_HOST`/`PROXY_PROVIDER`
   are dead values; `run_daily_auto.sh`'s provider blocks are the truth.
3. device-102: dead AccessibilityService, needs hands. 8 stale `DEVICES` entries.
4. `sni_relay.py` :853 change (`09e5f85`) is inert for the nightly (`USE_SNI_RELAY=0`).
5. Tonight's 20:00 LaunchAgent: this run writes `ALL DONE` on completion, so it will skip.

## Session opener
```
device-agent. Read HANDOVER.md + CLAUDE.md "Copilot: cap it at 4". Copilot is at 98%
via COPILOT_MAX_PARALLEL=4 + per-job pm clear (Mac-side, run_rolling_plan.py). Do NOT
re-chase the sign-in sheet, exit rotation, or DNS bypass — all measured wrong. Test only
on the run's real provider (source run_daily_auto.sh's evomi block), never uiautomator
mid-job, never many test tunnels at once.
```
