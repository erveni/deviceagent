# CitedLogic Capture — Handover (continue on another device / new session)

**Status as of 2026-06-10:** All 4 engines capture BOTH deliverables (full-answer stitched
screenshot + cleaned scraped text), verified end-to-end on one phone. What remains is the
production deployment (fleet APK rollout + the real 500-row proxied S3 run).

CitedLogic capture is a **separate workflow** from the AEO daily/ranking pipeline. It reuses the
phone fleet + capture mechanism but **only outputs to S3** (`s3://aeo-rank-screenshots/`,
profile `aeo-admin`) — two files per job: a PNG → `screenshotKey`, a JSON → `rawKey`. It never
touches AEOAdmin, the catalog, or the DB.

---

## 1. What's DONE and verified ✅

All four engines produce a **stitched full-answer PNG** + a **cleaned `answerText`** (with the full
raw scrape kept in `answerTextRaw`). Verified on device-114 (Infinix X6725, Android 15), geo-correct:

| Engine | How it localizes | Verified |
|---|---|---|
| chatgpt / gemini / perplexity | by **proxy exit IP** (metro residential proxy) | ✅ screenshot + text |
| google-maps | by the **URL viewport `@lat,lng`** (NOT proxy IP, NOT GPS) | ✅ Atlanta map-pack |

**Verified APK build: `v0.9.2-maps-nearme` (versionCode 18)** — committed as `device-agent.apk`.

### Key mechanisms (don't relearn these the hard way)
- **Capture endpoint** `type=capture` (`AgentHttpServer.kt`): types the prompt VERBATIM (no audit
  template), requires only `prompt`+`platform`, returns `response_text` + `screenshot_frames`.
- **Screenshot = scroll-and-stitch.** The phone grabs up to `maxFrames` (default 6) overlapping
  frames scrolling **DOWN** (down-only — scrolling UP triggers Chrome pull-to-refresh and RELOADS
  the page). The Mac stitches them (`citedlogic_stitch.py`, numpy overlap-detect) into one tall PNG.
  Chrome crop margins strip the fixed status/URL/input bars (else they repeat + collapse the stitch).
- **Text cleaning** (`_clean_answer_text` in `citedlogic_capture.py`): strips UI chrome + the echoed
  prompt → `answerText`; full raw kept in `answerTextRaw` (preserves Perplexity sources/citations).
- **ChatGPT** needs a post-generation popup dismiss ("Share your precise location" → "No thanks")
  and a render settle, or its answer paints only partially. Bottom-crop 215 (taller composer).
- **Google Maps geo**: navigate to `https://www.google.com/maps/search/<query>/@<lat>,<lng>,13z`
  and **STRIP "near me"** from the query — otherwise Maps resolves "near me" to the device's real
  location and ignores the viewport. With coords + no "near me", it returns the right metro even
  without a proxy. Maps stitch crop: top 150 / bottom 60.

---

## 2. File map (everything CitedLogic)

| File | Role |
|---|---|
| `citedlogic_capture.py` | Per-job core: CSV→jobs, `{DATE}`→UTC, capture via dispatch, text clean, S3/local upload, idempotent. `CL_LOCAL_ONLY=1` writes locally + skips S3. `CAPTURE_ENGINES` = 3 AI + google-maps. |
| `citedlogic_consumer.py` | RabbitMQ consumer (`citedlogic_jobs` queue) → `run_one` → S3 → ack. Fair-share prefetch, ack-after-completion, requeue-on-fail, auto-reconnect, heartbeat. |
| `citedlogic_publish.py` | Reads MASTER CSV, stamps true-UTC `{DATE}`, publishes to `citedlogic_jobs`. **Currently publishes AI engines only — google-maps is HELD** (flip this on when ready). |
| `citedlogic_status.py` | S3 progress monitor (done/total by engine). |
| `citedlogic_stitch.py` | Vertical frame stitcher (PIL+numpy). Has an offline self-test: `python3 citedlogic_stitch.py <screenshot.png>` (0px drift = OK). |
| `audit_dispatch_http.py` | Shared dispatch. Capture mode via `capture_prompt=` param: sends `type=capture`, `_write_stitched_screenshot`, `_capture_has_answer` OCR gate, per-engine crop, lat/lng passthrough. Ranking path unchanged. |
| `app/.../AgentHttpServer.kt` | `handleCaptureSession` + `executeCaptureSessionStatic` (capture flow, multi-frame, google-maps branch). |
| `app/.../FlowEngine.kt` | `navigateGoogleMapsSearch` (coords + strip near-me), `dismissGoogleConsent`. |
| `device-agent.apk` | Built v0.9.2-maps-nearme — install this on the test device. |

**NOT in the repo (copy to the new device manually):**
- `~/Downloads/citedlogic-MASTER-jobs.csv` (500 rows = 25 metros × 5 verticals × 4 engines)
- `~/Downloads/CitedLogic-Device-Farm-Capture-Instructions.md` (the spec)
- `.env.dev` (gitignored — RabbitMQ + proxy creds)

---

## 3. Set up + test on a NEW device (the part you asked for)

### 3a. Phone prep (per phone)
The new APK's debug signature differs from the fleet's old build, so a plain `install -r` FAILS
(`INSTALL_FAILED_UPDATE_INCOMPATIBLE`). Do uninstall + install:
```bash
S=<adb-serial>                      # from `adb devices`
adb -s "$S" uninstall com.deviceagent
adb -s "$S" install device-agent.apk
adb -s "$S" shell monkey -p com.deviceagent -c android.intent.category.LAUNCHER 1
# Enable accessibility (shell-trick worked on Infinix/Android-15; else toggle by hand):
adb -s "$S" shell settings put secure enabled_accessibility_services com.deviceagent/com.deviceagent.AgentAccessibilityService
adb -s "$S" shell settings put secure accessibility_enabled 1
# Brightness up so screenshots aren't dark:
adb -s "$S" shell settings put system screen_brightness_mode 0
adb -s "$S" shell settings put system screen_brightness 255
# For exact-GPS (only strictly needed if you rely on device GPS): install FakeGPS
#   (com.blogspot.newapphorizons.fakegps) and: adb shell appops set <pkg> android:mock_location allow
adb -s "$S" forward tcp:19990 tcp:8765
curl -s http://localhost:19990/health   # expect version 0.9.2-maps-nearme, accessibility:true
```

### 3b. Quick single-capture smoke test (no proxy — proves the flow + stitch)
```bash
adb -s "$S" shell "touch /sdcard/Android/data/com.deviceagent/files/screenshots/.bf"
curl -s --max-time 300 -X POST http://localhost:19990/session -H "Content-Type: application/json" \
  -d '{"type":"capture","platform":"google-maps","prompt":"best med spa near me","lat":33.749,"lng":-84.388,"maxFrames":6}' > /tmp/r.json
# pull frames + stitch:
mkdir -p /tmp/fr; for f in $(adb -s "$S" shell "find /sdcard/Android/data/com.deviceagent/files/screenshots/ -name 'capture_*_f*.png' -newer /sdcard/Android/data/com.deviceagent/files/screenshots/.bf" | tr -d '\r' | sort); do adb -s "$S" pull "$f" /tmp/fr/; done
python3 -c "from citedlogic_stitch import stitch_frames; import glob; print(stitch_frames(sorted(glob.glob('/tmp/fr/*.png')),'/tmp/stitched.png',top_crop=150,bottom_crop=60))"
open /tmp/stitched.png   # should show the Atlanta map-pack
```
Swap `platform` to chatgpt/gemini/perplexity (drop lat/lng) to test the AI engines.

### 3c. Local-only batch (writes files, NO S3) — verify before uploading
```bash
set -a; source .env.dev; set +a
export PROXY_HOST=gate.decodo.com PROXY_PORT=10001 \
       PROXY_BASE_USER=user-spmqebjuzf PROXY_PASSWORD='<decodo residential pw>' USE_SNI_RELAY=0
export DATE=$(date -u +%Y-%m-%d) CL_AWS_PROFILE=aeo-admin CL_LOCAL_ONLY=1 WORKERS=6
python3 citedlogic_capture.py            # writes to citedlogic_local/<key path>, no S3
```
Drop `CL_LOCAL_ONLY=1` to upload to S3 for real. Watch progress: `python3 citedlogic_status.py`.

### 3d. Proxy notes
- AI engines NEED the residential proxy for correct metro geo (`PROXY_PORT=10001`,
  `PROXY_BASE_USER=user-spmqebjuzf`, `USE_SNI_RELAY=0`). Google Maps does NOT (coords handle geo)
  but running it through the proxy is harmless.
- gost per-job ports are 16001-16101; if running alongside another dispatch process, offset them
  (`audit_dispatch_http._GOST_PORTS`) to avoid bind conflicts.

---

## 4. TODO (next session / new device)

1. **Roll APK v0.9.2 to the fleet** (uninstall+reinstall per §3a). Can't `install -r` over v0.7.1.
2. **Enable google-maps in `citedlogic_publish.py`** — it currently publishes AI rows only. Flip the
   hold so all 500 rows (incl. the 125 google-maps) publish.
3. **Run the real 500-row pass** with proxy + S3: `citedlogic_publish.py` → `WORKERS=6
   citedlogic_consumer.py` → watch `citedlogic_status.py` to 500/500.
4. Optional polish: the ChatGPT inline "Click to open side panel" residual in cleaned text;
   per-metro proxy precision (coords→city-zip).

## 5. Gotchas / learnings
- Captures fail (90s+ page loads, generation timeouts) when the home network is saturated (e.g. an
  AEO ranking run with 10 parallel proxied sessions). On a free network they succeed reliably.
- Maps "near me" → device location (wrong metro); strip it, use `@coords`.
- Scrolling UP in Chrome = pull-to-refresh = page reload. Only scroll DOWN; screenshot frames as you go.
- `{DATE}` is true UTC — right now (Manila evening) that's the *previous* local calendar day.
