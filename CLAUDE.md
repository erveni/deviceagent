# device-agent

Android `com.deviceagent` app (Kotlin) that automates ChatGPT / Gemini / Copilot via AccessibilityService, exposed over HTTP on phone port 8765. Plus Python runners that orchestrate the 10-phone fleet from the Mac.

## Commands

```bash
# Android build (Gradle)
./gradlew :app:assembleDebug      # build debug APK
./gradlew :app:installDebug       # install on connected device
./gradlew clean

# Python runners (stdlib only — no requirements.txt)
python3 run_with_proxy.py /path/to/daily_plan.json   # wave-based fleet runner (production)
python3 run_daily_plan.py /path/to/daily_plan.json   # legacy rolling runner
```

## Architecture

- `app/src/main/java/com/deviceagent/` — single Android module. `AgentAccessibilityService` + `AgentHttpServer` (port 8765) + `FlowEngine` (per-platform automation) + `MqttManager` (heartbeat).
- `run_with_proxy.py` — production fleet runner. One gost per wave, sequential socksdroid, parallel sessions.
- `run_daily_plan.py` — older rolling-dispatch variant.

## Key Decisions

- Backlinks use `AccessibilityNodeInfo.extras["AccessibilityNodeInfo.targetUrl"]`, not CDP. Different from the aeo-appium ADB path.
- After `am force-stop com.deviceagent`, accessibility binding is cleared — must re-enable via `settings put secure enabled_accessibility_services com.deviceagent/...`.
- mDNS ADB serials containing `(2)` MUST be shell-quoted (`adb -s "{serial}"`); unquoted, the shell parses `(2)` as syntax.

## Don'ts

- Don't commit a rebuilt `device-agent.apk` without bumping `versionCode`/`versionName` in `app/build.gradle.kts`.
- Don't hardcode credentials in `run_*.py`. Move to env vars before pushing.
- Don't resolve a phone by picking the SHORTEST matching mDNS name. Some phones are live
  under the `(2)` variant and some under the bare one; resolve against what
  `adb devices` actually lists. Guessing produced three "dead phone" reports on
  2026-09-04 that were all healthy (device-104, device-110).
- Don't dispatch a test job to a phone without waking it first
  (`KEYCODE_WAKEUP`, `KEYCODE_MENU`, swipe up). A locked phone returns
  `reset_edge failed`, which reads exactly like a real Edge fault.
- Don't run `uiautomator dump` while a job is in flight — see the Copilot section.

---

## solace_consumer.py — RabbitMQ consumer for the 10-phone fleet

Subscribes to `local_device_manager_jobs_queue` on the dev RabbitMQ broker, calls AEOAdmin `/api/llm/build-session` to enrich each job, dispatches to a phone via the audit/daily flow, publishes the result back to the broker.

### Canonical start (env sourcing is MANDATORY)

```bash
cd ~/projects/device-agent
set -a; source .env.dev; set +a
EXECUTOR_TOKEN=<token from AEOAdmin/.env> \
DISPATCH_ENABLED=1 \
DISPATCH_MAX_WORKERS=<phone-count> \
HEARTBEAT_INTERVAL_S=60 \
SSL_CERT_FILE=$(python3 -c "import certifi;print(certifi.where())") \
nohup python3 solace_consumer.py > /tmp/consumer_$(date +%Y%m%d_%H%M%S).log 2>&1 &
```

**Pitfall #1**: If you skip `set -a; source .env.dev; set +a`, `PROXY_USER` is empty, gost auth fails, every job dies with TLS RST. Lost 5h+ on 2026-05-22 to this. Verify via:

```bash
ps -p <pid> -E | tr ' ' '\n' | grep PROXY_USER
# expected: PROXY_USER=user-spmqebjuzf
```

### Auto-reconnect (commit a7f9a56, 2026-05-24)

`main()` wraps `start_consuming()` in a `while True` loop catching `StreamLostError` / `AMQPConnectionError` / `ConnectionClosed` / `ChannelClosed`. AWS MQ drops idle TCP sockets every ~60s. The pika BlockingConnection can't send AMQP heartbeats while build-session is mid-call (the LLM call blocks the pika I/O thread for ~15s), so the broker closes the socket. Without the wrapper the process dies — happened twice on 2026-05-23 (PIDs 99381 + 81776, both `StreamLostError ConnectionResetError(54)`).

Backoff: 2s → 4s → 8s → ... → 60s (max). Resets to 2s on a clean cycle.

### Heartbeat (commit a7f9a56)

Background thread prints every `HEARTBEAT_INTERVAL_S` seconds (default 60):

```
[heartbeat] ts=2026-05-23T17:30:29Z in_flight=10 received=220 success=108 error=45 crashed=0 last_completed=2026-05-23T17:00:13Z
```

`in_flight` = received − success − error − crashed. If `last_completed` doesn't move for >10 min while `in_flight > 0`, the dispatch threads are hung on dead phones — bounce the phones (`am force-stop com.deviceagent` + relaunch + accessibility re-toggle).

### Fair-share consumer

`channel.basic_qos(prefetch_count=DISPATCH_MAX_WORKERS)` + `_PHONE_SLOTS.acquire()` before ack means a saturated Mac stops pulling, broker routes to a Mac with free capacity. No coordination layer needed. Ack happens via `connection.add_callback_threadsafe(channel.basic_ack)` because the dispatch runner runs in a worker thread.

### CSV output paths

| Mode | Path |
|---|---|
| Daily sessions | `solace_pilot_results.csv` (cumulative — known column-drift bug; importer reads by header name) |
| Audit (ranking) | `rabbitmq_audit_results_<DATE>.csv` (date-split via `append_row` using row timestamp; commit a7f9a56) |

Audit screenshots write to `aeo-appium/audit_results/<DATE>/<Platform>/kw<ID>_<plat>_<unix>.png`.

## Proxy providers (measured 2026-08-28)

Read the real Evomi balance — do not estimate it:

```bash
curl -H "x-apikey: $EVOMI_API_KEY" https://api.evomi.com/public
# products.rpc.balance_mb = Core Residential, the product the runners use
```

- **Evomi** Core Residential (`core-residential.evomi.com:1000`), zip-tier targeting
  verified. `gost_manager` probes the ladder zip -> city -> region -> country.
- **Rayobyte** targets by CITY, not zip: probed `zip-32504` (Pensacola) exits West Palm
  Beach and `state-texas` exits Rhode Island, silently. `gost_manager` emits
  `-country-US-city-<city>` and consults `rayobyte_no_pool_cities.json` — a CACHE, never
  a live probe: the account is concurrency-capped, so probing mid-run both stalls setup
  and steals a session slot from the phones. Refresh it with `sweep_rayobyte_cities.py`
  while the fleet is idle.
- A city belongs in that cache only on evidence of MANY attempts with ZERO successes.
  Repeated `proxy_unreachable` alone is not enough — Draper looked dead in the retry log
  but succeeds 22/81, and three working cities were wrongly cached on one bad probe.

A "success" row is not proof of correct geo: malformed catalog cities
(`Stables Way Alpharetta`, `th street New York`) scored ~11/27 successes, which means
the provider silently widened to a country-wide exit rather than failing.

## Rank parsing: the answer wins over the prompt's example (2026-08-28)

Both audit prompt templates embed an EXAMPLE rank, and the app's a11y parse takes the
FIRST `[RANK: X/Y]` in the page text — which is the example whenever the prompt bubble
is in the tree. On the 2026-08-24 set that put the literal `19/19` into **166 of 753**
ChatGPT success rows; several were really #1. 144 rows were repaired in place
(backups in the session scratchpad) and 68 more were corrected live during the run.

`_parse_rank_markers()` in `audit_dispatch_http.py` re-parses `response_text` Mac-side
and the answer wins over the app's value. The guard skips a match when the text just
before it introduces an example:

- ChatGPT template: `... set X EQUAL to Y (e.g. [RANK: 19/19])`
- Gemini template:  `... 3 rank -> 4th of 4 -> [RANK: 4/4]`

so the lookback matches `e.g.` OR `->` within 24 chars. Known cost: a real answer
phrased `... -> [RANK: 5/9]` is skipped. That is deliberate — losing a row beats
recording the prompt's example as a client's ranking.

`_recover_rank_via_ocr()` is the fallback for when the a11y read is completely empty
(logged-out ChatGPT renders the answer but yields no text): it OCRs the saved
screenshot with `tools/ocr_vision` and parses the rank from the pixels. It fires only
when no rank was found, and has been rare in practice.

## Gemini ranking path (corrected 2026-08-28)

Ranking drives Gemini through the **app-audit flow**, the same one ChatGPT/Perplexity
use. `GEMINI_CDP=1` restores the old CDP path; leave it unset.

The CDP path existed on the premise that logged-out Gemini wipes its answer ~3s after
render, so only a DOM read could catch it. **Measured on 2026-08-28, that premise is
wrong**: 238 app-flow Gemini rows that day each had a screenshot on disk, response text
AND a rank. Gemini does clear the chat (a "Deleted" toast appears), but only after the
app has already read the answer.

What the CDP path actually cost: `gemini_cdp_capture.py` attaches to an EXISTING
gemini tab and returns nothing — no text, no screenshot, no rank — when that tab isn't
ready. It produced `cdp_no_capture` on 621 of 622 Gemini jobs on 2026-08-26 (a whole
day lost) and 57% of all failures on 2026-08-28. The app flow also runs ~2.3x faster
(137s vs 321s median) because it skips the Chrome intent, the 9s sleep and the attach.

Screenshot chrome (promo banner, prompt bubble, stale composer) is stripped by
`cdp_strip_map_shot.py`, which now runs Gemini's strip JS too. That is screenshot-only
and post-audit: if it fails the app's own screenshot is kept, so the row is never lost.

### Gemini submit: never blind-tap the composer's right edge

Gemini swaps that button by state — MIC when the composer is empty, SEND once it has
text. `FlowEngine.submit()` used to fall back to a hardcoded tap at
`(0.864 * width, 0.925 * height)`, which on an empty composer opens **voice input** and
hangs the job until its generation timeout. Every blind tap is now gated on
`composerHasText()`; when the composer is empty the flow logs why and returns false so
the job fails fast as `input_failed` instead of stalling for minutes.

## APK versioning

| Version | Commit | Notes |
|---|---|---|
| v0.6.x | 0b202a6 | Old. Pre-rolling-stability fix. |
| v0.7.0-phase1 | (no source on disk) | What's installed on Mac-1 fleet as of 2026-05-24 — versionCode 8. APK file lost. |
| v0.7.1-b64 | 8670bac | versionCode 9. Inlines audit PNG as base64 in `/session` response → no `adb pull` round-trip. APK at `device-agent.apk` (root, tracked, May 24). |
| v72 `0.9.53-gemini-foreground-guard` | **NEVER COMMITTED** | What 15 of 17 fleet phones ran as of 2026-08-28. `git log --all -S"versionCode = 72"` finds nothing on any branch, local or remote — the tree it was built from is gone. Only recoverable as a binary: `adb shell pm path com.deviceagent` then `adb pull` off a phone still running it. |
| v73 `0.9.56-gemini-mic-guard` | this commit | Built from the v71 tree + the Gemini submit fix, so it does NOT contain whatever v72 added. Installed on one phone (`...W002563`) for testing, not the fleet. |

| v74 `0.9.57-copilot-edge` | c4c9f35 | Copilot as an in-app platform via Edge. Also fixed `/health` reporting a hardcoded version. |
| v75 `0.9.58-copilot-exit-guard` | 48dc401 | Names the "Copilot is currently unavailable" refused-exit screen instead of reporting a generic composer timeout. |
| v76 `0.9.59-edge-fre-virgin` | 7eaba66 | Edge first-run walk for a VIRGIN install (a `pm clear`ed Edge shows fewer screens than a never-launched one). Deployed 17/17. |
| v77 `0.9.60-async-session` | 68fe119 | `/session {"async":true}` + `/result` polling. Deployed 17/17 — still what the fleet runs as of 2026-09-04. |
| v78 `0.9.61-edge-light-reset` | 6ca6853 (source only) | Built + device-tested 2026-09-04, NOT deployed. Replaces the Edge storage wipe with in-app "Delete browsing data" (39s, no first-run walk) and adds an InPrivate-exit guard plus a check that refuses to type a prompt into Edge's ADDRESS BAR when Copilot is not open. Deliberately parked: it targets `reset_edge`, which stopped mattering once device-122 got Edge — the real Copilot loss was the proxy exit. |
| v79 `0.9.62-copilot-frame-top` | this commit | Copilot client shots: re-queries the prompt bubble before trusting a null (Copilot's virtualized tree drops it mid-layout), drags the page back down when list item 1 lands under the header, and splices the prompt band out of the PNG when a short answer leaves the page nothing to scroll. Measured before: 13/25 v77 shots on 2026-09-05 carried "Keep the entire response under 280 words." above item 1. Deployed fleet-wide 2026-09-05. |
`/health`'s version comes from HAND-MAINTAINED constants `APP_VERSION_NAME` /
`APP_VERSION_CODE` in `AgentHttpServer.kt` (~line 22), not from BuildConfig. They were
stale for years and `/health` lied after every bump; they are correct as of v77 and MUST
be edited alongside `app/build.gradle.kts`. Cross-check with
`adb -s <serial> shell dumpsys package com.deviceagent | grep versionCode`.

### Deploying APK to a new Mac

```bash
cd ~/projects/device-agent && git pull
for s in $(adb devices | awk -F'\t' 'NR>1 && $2=="device" {print $1}'); do
  adb -s "$s" install -r device-agent.apk
done
# Prefer ./deploy_agent_fleet.sh — it installs, force-stops, then RETRIES the
# accessibility rebind up to 5x while polling /health, and prints a list of any phone
# that still needs a hand. A single `settings put` does fail on Android 13+; the retry
# loop does not. It rebound 17/17 phones unattended on 2026-09-02 and 2026-09-03, so do
# NOT plan a deploy around walking the fleet by hand.
```

## JobRecord shape — dual-compat (2026-05-24)

The orchestrator team updated the JobRecord schema. Our consumer + publisher
now accept BOTH shapes (old and new) with fallbacks. Key differences:

| Field | OLD (pre-2026-05-24) | NEW (2026-05-24+) |
|---|---|---|
| Business name | `business.businessName` | `business.name` |
| Client info | `business.clientId`, `business.clientName` | `business.client.{clientName, accountId}` |
| Backlink URL | `detail.backlink.url` (string) | `detail.backlink.url` ({id, name, type} object) |
| Address detail | basic `addressLine1/city/state` | adds `addressLine2/3, zipCode, timezone, location{lat,lng}` |
| New top-level fields | — | `subscriptionId, business.category, business.website, detail.id, conversation.id, device{}, result.rankingRecord` |

Consumer reads with `biz.get("businessName") or biz.get("name")` style fallbacks
in `_handle_audit` and `_build_enriched_from_job`. Publisher's `_emit_business`
and `_emit_address` helpers emit both shapes side-by-side. Anything new the
orchestrator adds that we don't read yet is harmless extra data.

## Catalog file lives in aeo-appium

`audit_dispatch_http.py` reads `/Users/seolocalph/projects/aeo-appium/clients_audit_targets.json` for per-business audit config (`proxy.zip`, `biz_url`, city/state). See `aeo-appium/CLAUDE.md` for the entry shape + how to add a new business. Without an entry the dispatcher falls back to NY zip 10001 and the AI platform rejects the audit on geo-mismatch.

## Copilot (replaced Perplexity, 2026-09-02)

Perplexity is RETIRED. `build_daily_plan.py:36` is
`PLATFORMS = ["ChatGPT", "Gemini", "Copilot"]`, and the two `FORCE_PLATFORM` pins that
named Perplexity moved to Copilot as well.

Copilot answers ONLY inside Microsoft Edge (`com.microsoft.emmx`) — copilot.microsoft.com
in Chrome hits a hard sign-in wall with no skip. `EdgeCopilotFlow.kt` drives it and shares
none of the Chrome helpers. Measured facts that shaped it:

- Entry is the toolbar button `edge_location_bar_copilot_button`, not a URL.
- The composer swaps MIC <-> SEND by state exactly like Gemini, so submit is gated on
  composer-has-text or an empty composer starts a voice call.
- The answer is VIRTUALIZED: only near-viewport nodes are in the a11y tree and the
  viewport parks on the prompt, so a single read returns nothing. `readAnswer()` scrolls
  and accumulates; `waitForAnswer()` keys on the streaming indicator, not on text.
- The prompt bubble's text is a SIBLING of its `"Sent by you."` marker, not a child, so
  answer lines are filtered against that desc — otherwise the prompt's own
  `[RANK: 19/19]` example lands in the response.
- Copilot honors the existing audit template, so `extractRankingFromText` needs no change.
- Screenshots are framed by parking the PROMPT BUBBLE just off the top, not by targeting
  the rank line — the latter clips rank #1 on long lists.

### Copilot: cap it at 4 in flight and pm-clear Edge from the Mac (measured 2026-09-04)

Copilot went from 28% to **95%** (19/20; ChatGPT 31/31, Gemini 31/31 in the same
window) with two Mac-side changes and no APK. Both live in `run_rolling_plan.py`:

- `COPILOT_MAX_PARALLEL=4` — Copilot's rate tracks how many Copilot sessions are open
  at once from the same residential pool: ~70% one at a time, 28-38% at ~5 of 15
  (base wave), 8% at ~15 (retry rounds, almost all Copilot), 0/7 at 8 simultaneous.
  ChatGPT/Gemini are unaffected by the same load. A worker that cannot get a slot hands
  the Copilot job back and takes a Chrome job, so phones never idle.
- `COPILOT_PM_CLEAR=1` — the app resets Edge by driving Android's Settings UI; that
  logs `clearData -> true` and sometimes does not take (device-113 sat on the previous
  job's conversation and timed out walking a first-run that never came, 0/4). `adb
  shell pm clear com.microsoft.emmx` from the Mac before each Copilot dispatch cured it
  (113 -> 4/4, 120 2/6 -> 3/3). The phone log then shows a real first-run walk
  (`FRE: tapped 'Not now'` x2, `'Confirm'`).

Dead ends, each stated confidently that day and each wrong — do not re-chase:

| theory | why it looked right | what killed it |
|---|---|---|
| Microsoft sign-in wall | every manual test showed the sheet | all were unproxied or on a dead tunnel; hundreds of jobs succeeded |
| rotate the proxy exit | 3 hand-picked fresh sessions succeeded | 144 rotations in the retry round, 138 still failed |
| "it's the phone" | a 2x2 matrix tracked the phone | conflated `reset_edge` (stuck FRE) with `open_copilot` |
| Microsoft blocks the pool | ChatGPT fine, Copilot not | the same phones ran ~70% Copilot one at a time |
| DNS bypass (Evomi 501s on 8.8.8.8:853) | 241 real 501s in the nightly's logs | dialing DoT direct from a GMT+8 Mac resolved names for Asia: Google :443 targets moved to 172.217.26.x/142.250.207.x and Copilot fell 8/9 -> 1/6. `GOST_DNS_BYPASS` defaults OFF; the 501s are a wasted round trip, not the cause. |

`"open_copilot failed"` stays in `RETRY_TRIGGERS` as a cheap second attempt; it is not
the fix.

Diagnosis traps that manufactured false results that day:

- **Test through the same provider as the run.** `PROXY_PROVIDER=evomi` only changes
  the credential format; `PROXY_HOST` stays `gate.decodo.com` from `.env.dev`. Half a
  day of "Evomi" tests ran on Decodo. Source `run_daily_auto.sh`'s evomi block.
- **Never `uiautomator dump` mid-job** — it contends with the AccessibilityService. A
  15-phone probe that sampled screens during jobs reported ALL phones broken, including
  one that was 32/32 minutes earlier. Dump only after the job returns, or read
  `/sdcard/Android/data/com.deviceagent/files/logs/agent.log`.
- **Do not bring up many test sessions at once.** 8 tunnels in 24s drew 129 x `407` from
  Evomi; the rolling nightly never sees a 407.
- **Verify a gost bypass by the absence of an upstream `connect` record**, not by
  grepping the word "bypass" (that is the load line) or by a 302 (Evomi allows :443).
  A bypass belongs on the chain NODE; on the handler it loads and never matches.
- The nightly runs `USE_SNI_RELAY=0`; changes to `sni_relay.py` do not touch it.

## Daily plan build: DeepSeek 402 is already handled by Ollama (2026-09-04)

Do NOT treat "DeepSeek Insufficient Balance" as a blocker for the nightly build, and do
not top it up on that basis alone. `daily_full_auto.sh` routes the build through a LOCAL
api-server (`_build_server_lib.sh`, port 8788) whose `chatCompletion` falls back to Ollama
`qwen2.5:7b` on any DeepSeek error. This was already live on 2026-09-03: DeepSeek 402'd
all night and all 977 ChatGPT+Gemini prompts still built.

- The local server talks to the PROD RDS directly and runs build-only
  (`TRIAL_SWEEP_MINUTES=0`, so no Stripe/e-mail side effects).
- AEOAdmin's `dist/` is gitignored, so a pulled-but-unbuilt tree serves STALE route code.
  `start_build_server` now rebuilds before the dist check — that is how the `copilot`
  platform whitelist stayed invisible even after the source was fixed.
- `BUILD_TIMEOUT_S` defaults to 180 in the nightly. Ollama answers serially behind 8
  build workers; the DeepSeek-era 60s crowded that (see the note at
  `build_daily_plan.py:26`).
- Cost: ~61 min to build 1438 sessions, vs minutes on DeepSeek. Budget for it.

`copilot` is ACCEPTED by `/api/llm/build-session` as of AEOAdmin `95d16f9`. Before that it
returned `400 platform must be one of chatgpt, gemini, perplexity`, which silently dropped
all 461 Copilot sessions from the 2026-09-03 plan (977 jobs shipped instead of 1438).
Note the deployed App Runner instance only picks this up once the branch reaches `main`;
the nightly is unaffected because it builds against the local server.

## PROXY_PROVIDER lives in the LaunchAgent, not in .env.dev

`.env.dev` says `PROXY_PROVIDER=dataimpulse`, which is DEAD. The working value
(`evomi`) exists ONLY in `~/Library/LaunchAgents/com.deviceagent.dailyfull.plist`
under `EnvironmentVariables`. Launching `daily_full_auto.sh` by hand therefore runs the
entire night on a dead provider, and the only visible sign is one line:

```
[daily 2026-09-04] proxy: DataImpulse (TEMPORARY — Decodo funding)   # WRONG
[daily 2026-09-04] proxy: Evomi (HTTP :1000, state-level, ~$0.49/GB) # what it should say
```

Always hand-launch as `PROXY_PROVIDER=evomi ./daily_full_auto.sh <DATE>` and CHECK that
line. `PROXY_HOST` has the same problem — it stays `gate.decodo.com` regardless of
`PROXY_PROVIDER`.

## Fleet state (2026-09-04)

16 phones answer adb; 15 dispatch. Edge `151.0.4129.101` is on all 16.

- **device-102** — AccessibilityService is DEAD: `/health` returns nothing and its log
  repeats `not in foreground (?)`, where `?` means a null a11y root. It is in
  `DEVICE_EXCLUDE` for that reason and adb alone cannot revive it; it needs a hand on the
  phone. Do not "fix" it by reinstalling the APK.
- **device-122** (`...S003287`) — had NO Edge, so every Copilot job on it died
  `reset_edge failed` (0/15). Fixed by sideloading `~/apks/edge_151.0.4129.101.apk`;
  it went 4/5 within a minute. That phone is the one the earlier handover flagged as
  "adb bulk transfer hangs".
- **device-113 / device-120** — Copilot 0/4 and 2/6 from an Edge that the in-app wipe
  never actually cleared; `pm clear` fixed both on the spot and is now done per job.
- The other 8 entries in `DEVICES` have been dark for at least two nights — stale roster
  entries, not a regression. The plan is sized to the phones that answer.

## Async sessions (v77)

`/session` accepts `"async": true` -> 202 immediately, job runs on a worker thread, and
`/result` returns the same JSON the blocking POST does plus a `running` flag. The Mac
polls it (`AEO_ASYNC_SESSION=0` reverts). Measured: this did NOT move the ranking failure
rate (65% vs 67%) — the `RemoteDisconnected` happens on the OPENING request, not from
holding one open; only 1 of 230 jobs died while polling. Do not re-attempt this fix
expecting a different result; the remaining cause is the phone refusing connections at
connect time.

## See also

- `MAC_FLEET_SETUP.md` (in ~) — 800-line onboarding doc for a new Mac in the fleet
- `/Users/seolocalph/.claude/projects/-Users-seolocalph-projects/memory/` — point-in-time observations from past sessions
