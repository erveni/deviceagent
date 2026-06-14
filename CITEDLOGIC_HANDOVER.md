# CitedLogic Capture — Handover

> Handover for a separate Claude/engineer picking up the **CitedLogic device-farm capture**
> work. Self-contained: what it is, the repo, how it works, how to run, current state, and
> the one remaining gap to go live. Written 2026-06-14.

---

## 1. What this is (one line)

We are a **capture vendor** for CitedLogic. For each row in a standing 500-row CSV we put a
phone at the row's `lat/lng`, run a prompt on the row's engine (ChatGPT / Gemini / Perplexity /
Google-Maps), capture a **screenshot + verbatim answer text**, and upload **two files** to
CitedLogic's S3. CitedLogic does all analysis — we do **not** parse, rank, or score.

Authoritative spec from the client: `CitedLogic-Device-Farm-Capture-Instructions.md`
(in `~/Downloads/`; mirror into the repo if you want it tracked).

---

## 2. Repo

- **Name:** `device-agent`  ·  **Remote:** `https://github.com/DeviceFarm1/device-agent.git`
- **Local:** `/Users/seolocal3/projects/device-agent`
- **Branch with the latest fleet work:** `feature/superproxy-dispatch`
- The CitedLogic pipeline lives in **`citedlogic/`** (Python package).
- Read `CLAUDE.md` first — it documents the whole device-agent fleet (the Android app + Python runners).

### Two halves
1. **The phone agent** — `app/src/main/java/com/deviceagent/` — an Android app (`com.deviceagent`)
   that automates ChatGPT/Gemini/Perplexity (via AccessibilityService) and Google search
   (Chrome), and exposes an **HTTP control API on port 8765**. This is the device-bound half.
2. **`citedlogic/`** — the Mac-side capture pipeline (pure-ish Python, stdlib + AWS CLI):
   parse CSV → run each row on a phone → screenshot + text → upload 2 files to S3.

---

## 3. The standing job list — `MASTER-jobs.csv`

- **500 rows = 25 metros × 5 verticals (dental, hvac, legal, medspa, restaurants) × 4 engines.**
- Every prompt is a `best <vertical> near me` (e.g. `best med spa near me`).
- **Run the SAME list EVERY day.** The only thing that changes day-to-day is `{DATE}` (UTC
  `YYYY-MM-DD`), which appears in `jobId`, `screenshotKey`, `rawKey`. New list only when
  CitedLogic expands coverage (~monthly).
- Columns: `jobId, engine, metro, lat, lng, promptText, screenshotKey, rawKey`.
- Current file: `~/Downloads/citedlogic-MASTER-jobs.csv` (123 KB). **Note:** `*.csv` is
  gitignored in this repo, so the CSV is local-only — keep a durable copy.

S3 bucket: **`s3://aeo-rank-screenshots/`**. Keys look like
`index/{DATE}/san-francisco-ca/p0/medspa/best-near-me/google-maps.png` (+ `.raw.json`).

---

## 4. The pipeline (`citedlogic/`) — all built + unit-tested

| module | role | side effects |
|---|---|---|
| `loader.py` | parse `MASTER-jobs.csv`, swap `{DATE}`, validate, emit jobs; route engine → `/session` body; group into waves | none (pure) |
| `capture.py` | per-row orchestrator: `dispatch → screenshot → text (device or OCR) → upload`; batch with failure isolation | injected `dispatch_fn` |
| `ocr.py` | extract verbatim `answerText` from a PNG | `TextractOcr` (AWS CLI) / `StubOcr` (tests) |
| `uploader.py` | build the `rawKey` JSON, upload PNG + JSON | `LocalBackend`/`AwsCliBackend`/`S3Backend` |
| `tests/` | `test_loader.py`, `test_capture.py`, `test_uploader.py` (pytest, no phone/AWS needed) | — |

### Engine → `/session` routing — INTEGRATED WITH THE CSV (`loader.session_body`)
- `chatgpt` / `gemini` / `perplexity` → `{"platform": engine, "prompt": promptText}`
  → handled by `handleDailySession` in the agent (the chat-automation flow).
- `google-maps` → `{"type":"seo", "keyword": promptText, "surface":"maps"}`
  → handled by `handleSeoSession` → `executeGoogleSerpStatic`. The **local/map pack** screenshot
  is the "near me" capture. (Agent ignores `surface` today — the SEO flow already shoots a
  local-pack proof screenshot; `surface` is a forward-compat hint.)
- GPS for every row: `loader.gps_for(job) → {"lat","lng"}` — set EXACTLY, never jittered.

### The capture seam (`capture.capture_job`)
`dispatch_fn(job) -> {"png_bytes": bytes, "answer_text": str|None, "device": str|None}`
is the **only device-bound part and is INJECTED**, so the whole pipeline is unit-tested with a
fake phone. Text priority: device text → else OCR the PNG. No PNG = hard failure. Empty answer =
uploaded with `answerPresent=false` (valid "engine said nothing").

---

## 5. The phone agent HTTP API (port 8765) — what `dispatch_fn` calls

All over LAN HTTP (no adb at runtime; see the `lan-control-no-adb` work this session):
- `POST /session` — run a job. Body is whatever `loader.session_body` returns, plus
  `"gps":{"lat","lng"}` to set device location. Response includes `status`, `step_log`,
  and `screenshot_b64` (the local/map-pack PNG, base64). For the SEO/maps path the local-pack
  shot is returned; for chat platforms the response carries the proof screenshot.
- `GET /screencap` — live full-screen PNG over LAN (no adb). Use if you need a raw shot.
- `GET /netstate` — `{tun0_up, tun0_addr}`, read-only VPN health.
- `POST /proxy/start` / `POST /proxy/stop` — proxy control (but per-app VPN is driven from
  SocksDroid's saved profile; see §7).
- `GET /screenshot?path=` — fetch an existing on-phone PNG (replaces `adb pull`).

---

## 6. How to run

```bash
PY=/Users/seolocal3/projects/seo-keyword-research/.venv/bin/python   # python3.14 venv

# 1) unit tests (no phones, no AWS)
$PY -m pytest citedlogic/tests -q

# 2) load today's plan from the real CSV (swaps {DATE}, groups into waves)
$PY -m citedlogic.loader ~/Downloads/citedlogic-MASTER-jobs.csv --wave-size 5 --out /tmp/plan.json
#   prints {total, engines, metros} to stderr; writes the wave plan JSON.

# 3) LIVE capture — NOT yet wired (see §8). The production dispatch_fn must be written.
```

Dependencies: stdlib + the venv `python3.14`. OCR uses the **`aws` CLI** (Textract); S3 upload
uses the `aws` CLI (`AwsCliBackend`) or `boto3` (`S3Backend`). Both use your existing AWS login.

---

## 7. One-time phone provisioning (already done on device-106 / 192.168.254.101)

For localized captures the phone needs: APK installed (`device-agent.apk`, versionCode ≥ 24),
AccessibilityService enabled, `appops set com.deviceagent android:mock_location allow` (for GPS),
and a **SocksDroid per-app VPN profile** (Per-app Proxy ON, Bypass OFF, App List =
`com.android.chrome`, server = Mac LAN IP:relay-port, Connect-on-Boot ON). The per-app profile is
critical: a full-device VPN black-holes the LAN control channel; routing **only Chrome** keeps the
agent reachable. See the `lan-control-no-adb` memory + `seo_lan_runner.py` for the whole story.

---

## 7b. How to use Decodo with NO runtime adb (the proxy chain)

This is the model the live runner should use. **adb is used ONLY for one-time provisioning**
(§7); at runtime the phone is driven entirely over LAN HTTP, and the proxy works like this:

**The chain:** `Chrome (phone) → SocksDroid per-app VPN → Mac sni_relay → Mac gost → Decodo → web`.

1. **On the Mac, bring up gost + sni_relay** (both bind `0.0.0.0`, so the phone reaches them over
   Wi-Fi — no `adb forward` needed). gost is a SOCKS5 listener that chains to `gate.decodo.com`
   with a **geo-pinned upstream username**; sni_relay sits in front because SocksDroid IP-CONNECTs
   and Decodo residential needs hostname-CONNECT (the relay recovers the host from the TLS SNI).
   Helpers already exist — reuse them:
   - `run_with_proxy.gost_start([spec])` + `seo_proxy_run._relay_start(RELAY_PORT, GOST_PORT)`
   - or just call `seo_lan_runner._bring_up_gost(geo)` which does both and returns the relay port.
   - Geo pin = the Decodo username: `user-<acct>-country-us-state-<st>-city-<city>-zip-<zip>-session-<sid>-sessionduration-<n>`.
     Build it from the metro (see `serp_fleet_worker._build_geo_suffix`). Verify the exit landed
     in the right city via `seo_lan_runner._ensure_localized` (geolocates the gost exit through
     ip-api and rotates fresh IPs until it's in-state). Decodo creds come from `.env.dev`
     (`set -a; source .env.dev; set +a`) — `PROXY_USER/PROXY_PASS/PROXY_HOST`.

2. **On the phone, the per-app VPN is already running from SocksDroid's SAVED PROFILE** (configured
   once in §7, Connect-on-Boot ON). It persistently dials `MAC_IP:RELAY_PORT` over Wi-Fi and routes
   **only `com.android.chrome`**. The runner does NOT start it.
   - ⚠️ **Do NOT use `POST /proxy/start` to start the VPN.** That fires SocksDroid's
     AdbStartActivity, which rebuilds the profile from intent extras WITHOUT per-app → full-device
     route → black-holes the LAN control channel (and you'd need adb to recover). The per-app
     setting only sticks when started from SocksDroid's own profile/toggle. This was the single
     biggest gotcha of the whole effort.
   - The relay port is fixed (`seo_proxy_run.RELAY_PORT`, currently 18764) — same port the saved
     profile dials, so the phone needs no reconfiguration between jobs.

3. **Swapping cities = re-pinning gost on the Mac, not touching the phone.** For each job: tear down
   the old gost session and bring up a new one pinned to the new metro's geo (same relay port). The
   phone keeps dialing the relay; only the Mac-side exit IP changes. Proven live: California→Texas
   across two jobs on the same phone.

4. **Health check, no adb:** `GET /netstate` → `{tun0_up}` tells you the per-app VPN is up before you
   search (so a job never silently runs from the phone's real IP). `GET /ping` proves control.

**Tradeoff:** the per-app VPN stays up between runs; while gost is down the phone's Chrome has a
tunnel-to-nowhere (no Chrome internet until gost is back). The agent control channel is unaffected.
Bring gost up for the duration of a batch, tear it down after.

Minimal end-to-end (what `dispatch_fn` does per job), no adb:
```
set -a; source .env.dev; set +a            # Decodo creds
# Mac side (per metro): h = _bring_up_gost(geo);  _ensure_localized(h, geo, label)
# Phone side (LAN):     GET http://<phone-ip>:8765/netstate   -> {"tun0_up": true}
#                       POST http://<phone-ip>:8765/session  {loader.session_body(job), gps:{lat,lng}}
#                       read screenshot_b64 from the response
# Mac side:             tear down gost/relay (_teardown_gost(h))
```

---

## 8. CURRENT STATE — what's done vs the gap

**Done & verified:**
- `citedlogic/` pipeline (loader/capture/ocr/uploader) — built, unit-tested.
- CSV → engine routing for all 4 engines (`loader.session_body`).
- The device half: GPS set (`/session gps`), Chrome SEO/map-pack flow, chat-platform flows,
  LAN screenshots — all working.
- **Proven live:** one CitedLogic `google-maps` row run end-to-end manually — SF medspa,
  `best med spa near me`, GPS 37.7749,-122.4194 → 3 local results (Ivy En Rose, Idan Med Spa,
  Nob Hill Aesthetics), map-pack screenshot captured. (Screenshot at `/tmp/nearme_mappack.png`
  when it was run.)

**THE GAP — the production `dispatch_fn` is not written.** `capture.py` injects it; only the
fake (tests) exists. To go live, write a real `dispatch_fn(job)` that:
1. sets the localized proxy for `job["metro"]` (bring up Mac gost/relay pinned to the metro — the
   exit IP must match the city), and confirms the per-app VPN is up (`GET /netstate`);
2. `POST /session` with `loader.session_body(job)` + `loader.gps_for(job)` to the phone's LAN IP;
3. reads `screenshot_b64` (→ `png_bytes`) and any device answer text from the response;
4. returns `{"png_bytes", "answer_text", "device"}`.

**The building blocks for this already exist** in `seo_lan_runner.py` (this session): gost/relay
bring-up + ZIP/geo pin (`_bring_up_gost`, `_ensure_localized`), `/netstate` check, and the
`/session` POST helper. The cleanest path is to factor those into a `dispatch_fn` and feed it to
`capture.capture_all(jobs, dispatch_fn, ocr, backend, device)`. Then schedule it daily (swap
`{DATE}` via `loader.utc_today()`).

Open questions to resolve when wiring live:
- **Metro → exit-IP pin:** each metro needs a Decodo geo (state/city/zip) so Chrome egresses that
  city. The CSV gives lat/lng + a `metro` slug, not a zip — build a metro→geo map (or reverse-
  geocode the lat/lng) for the gost pin. GPS alone localizes "near me" somewhat, but IP geo matters.
- **Chat platforms (chatgpt/gemini/perplexity):** these need accounts/sessions on the phone and a
  residential/NordVPN egress per the `nordvpn-engine-geo` memory — different from the Chrome SEO
  proxy path. Confirm the chat flow returns a usable proof screenshot + (ideally) answer text;
  otherwise OCR fills `answerText`.
- **Burned proxy pools:** captcha/blocked is frequent; reuse the rotate-on-blocked logic from
  `seo_lan_runner.py`.

---

## 9. Pointers / memory

Session memory lives in `/Users/seolocal3/.claude/projects/.../memory/` — relevant entries:
`citedlogic-capture-setup`, `lan-control-no-adb`, `daily-seo-engagement-only`,
`seo-proxy-decodo-setup`, `nordvpn-engine-geo`, `captcha-solved-serp-api`, `user-prefers-lan-control`.
Also read: `CLAUDE.md`, `SEO_PIPELINE_HANDOVER.md`, the prior `SESSION_HANDOVER_*.md`.
