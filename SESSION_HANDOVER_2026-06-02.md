# Session Handover — SEO rank pipeline (2026-06-02)

_Read this first to continue in a fresh session. Supersedes `SEO_PIPELINE_HANDOVER.md` (kept
for the pre-this-session backstory)._

---

## TL;DR — where we landed

The on-device **Google SERP rank + screenshot pipeline works end-to-end** through a residential
Decodo proxy. It produces **SerpApi-compatible JSON** (organic + local-pack with rich fields) and
**two framed screenshots** (local pack + organic), clean, no captcha.

The whole session's earlier "every Decodo IP is captcha'd, it's hopeless" conclusion was **WRONG** —
it was a measurement artifact + a **burned phone**. See the discovery below.

A new private repo was created and pushed: **`DeviceFarm1/seo-device-agent`**
(`main` = README only; `develop` = the clean code bundle).

---

## 🔑 THE DISCOVERY (don't relearn this the hard way)

**Google flags the PHONE (device/Chrome fingerprint), not just the IP.** Earlier in the session
~25+ automated searches + repeated `pm clear`s on the **Samsung (device-101)** got *that device*
fingerprinted → it then hit `/sorry/index` captcha on **every** IP, including IPs the other agent
had *proven clean*. A **fresh phone** (Infinix device-102) on the **same Decodo account + same IP
pool** returned clean SERPs immediately.

Corollaries / rules:
- **Don't over-query one phone.** Each phone has a budget before Google challenges it on all IPs.
  Rotate phones, pace requests, don't repeatedly wipe Chrome.
- `pm clear` did NOT un-flag the Samsung → the flag is device-level, not just cookies. **Samsung
  device-101 is burned for Google** (cooldown unknown; assume it needs to rest / may need a
  different approach).
- A second measurement trap: my `uiautomator dump` + grep "clean" checks were **false negatives** —
  the Chrome "notifications" FRE dialog masked the `/sorry` page in the dump, and the address bar
  truncates `sorry/index`→`sorry/in`. **Trust the screenshot, or the app's own parse — not ad-hoc
  dump greps.**

---

## What was BUILT this session (all in the device-agent working tree, uncommitted)

1. **Two screenshots instead of one** — `executeGoogleSerpStatic` now shoots the **local/Maps pack**
   AND the **organic** block. Response: `screenshot_local_b64` / `screenshot_organic_b64`;
   `seo_dispatch.py` saves `<stem>_local.png` / `<stem>_organic.png`.
2. **Content-anchored framing** (was header-text, which broke when Google labelled the pack
   "With outdoor seating"): `FlowEngine.scrollToLocalPackTop()` aligns on the first
   `Rated X out of 5` card; `scrollToOrganicTop()` on the organic block. Generic helper
   `scrollNodeToTop(finder)`.
3. **Parser: themed local packs** — when there's no "Places"/"Businesses" header, anchor the local
   cluster on the rated cards above the "More places/businesses" footer (else 0 local parsed).
4. **Rich per-result fields** parsed from the a11y tree:
   - Local: `reviews`, `reviews_original`, `price`, `type`, `address`, `description` — extracted from
     the **card container's `content-desc`** (Google packs the whole card into ONE string, e.g.
     `"Little Foot Preschool  Rated 5.0 out of 5,  (12)  ·  Bilingual preschools 20+ years in
     business Open now · Serves San Francisco"`) using substring regexes (strip Unicode bidi
     isolates U+2066/U+2069 first).
   - Organic: `snippet`, `displayed_link`.
5. **SerpApi-compatible JSON output** (`seo_dispatch.py::_to_serpapi`): `search_metadata`,
   `search_parameters` (incl. `--location` → `location_requested`, `device:"mobile"`),
   `search_information`, `local_results.places[]`, `organic_results[]`, `target_ranking`,
   `screenshots`. **Omitted (impossible on-device):** `place_id`, `lsig`, `gps_coordinates`,
   `thumbnail`/`favicon`, `redirect_link`, `snippet_highlighted_words`, `raw_html_file`,
   `total_results`.

**Files changed (uncommitted in `~/projects/device-agent`):**
`app/src/main/java/com/deviceagent/FlowEngine.kt`, `AgentHttpServer.kt`, `app/build.gradle.kts`
(v0.8.0-seo, versionCode 10), `seo_dispatch.py`. Plus untracked: `seo_proxy_run.py`,
`sni_relay.py`, `test_residential_one.py`, `seo_results/`, `SEO_PIPELINE_HANDOVER.md`, this file.

**Built APK:** `app/build/outputs/apk/debug/app-debug.apk` (current, ~09:53 build) — versionCode 10,
v0.8.0-seo, with all the above. **Installed on Infinix device-102.**
⚠️ `/health` reports a HARDCODED `"0.7.1-b64"` (`AgentHttpServer.kt:21 APP_VERSION_NAME`) — IGNORE
it; use `adb shell dumpsys package com.deviceagent | grep version` for the real version
(versionCode=10 = the SEO build).

---

## Proven results (live, clean, no captcha)

- `best coffee shop austin` / `epoch.coffee` via Austin AT&T residential → 8 organic + 3 local,
  both screenshots framed correctly.
- `bilingual childcare near me` / San Francisco (Bay Area Comcast residential) → 10 organic + 3
  local; **all new local fields populated** (e.g. "Mis Pequeños Angelitos — 5.0, 26 reviews, Day
  care center, 1955 San Jose Ave, 7+ years in business"); organic `snippet`+`displayed_link`
  populated. JSON + 2 PNGs delivered + copied to `~/Desktop/seo_audit_screenshots/`.

---

## ▶️ HOW TO RUN (the working recipe)

```bash
cd ~/projects/device-agent
set -a; source .env.dev; set +a          # has PROXY_PASSWORD etc. (gitignored)
export PROXY_PASSWORD="$PROXY_PASS" MAC_IP="$(ipconfig getifaddr en1)"   # this Mac = en1 = 192.168.0.164

# 1) install current SEO APK on a FRESH (non-burned) phone + bring up a residential tunnel
FRESH="adb-1490455615007763-aoRAJa._adb-tls-connect._tcp"   # Infinix device-102
adb -s "$FRESH" install -r app/build/outputs/apk/debug/app-debug.apk
TEST_SERIAL="$FRESH" TEST_ZIP=94117 TEST_STATE=CA python3 test_residential_one.py
#   -> [ipinfo] ... org=<real ISP>   [tunnel] UP   (gost left running on :11001)

# 2) run the audit (single shot; --retries 0 so it doesn't hammer the IP)
SEO_HTTP_TIMEOUT_S=420 python3 seo_dispatch.py --serial "$FRESH" \
  --keyword "bilingual childcare near me" --location "San Francisco, California" \
  --out seo_results --retries 0 --local-port 8805
#   -> seo_results/<slug>_<ts>.json  + _local.png + _organic.png

# 3) ALWAYS tear down after (don't burn Decodo bandwidth / the phone)
pkill -f gost
adb -s "$FRESH" shell am force-stop net.typeblog.socks
```

Geo: `gost_manager.py` preflight resolves `country-us-zip-<zip>` → falls back zip→region→country.
**`country-us` MUST precede `zip-`** in the username or Decodo returns a random GLOBAL IP (we saw
Indonesia/Bangladesh). Residential = `gate.decodo.com:10001` (mobile = :7000, needs the SNI relay).

---

## ⚠️ Gotchas / don't-repeat

- Don't test on a phone you've already hammered (Samsung device-101 is burned).
- Don't trust `uiautomator dump` greps for captcha detection (FRE dialog masks the page) — screenshot.
- `gost` CANNOT chain to Decodo **mobile** (`0x03`); mobile needs `sni_relay.py` dialing Decodo
  directly (relay edits already in the tree). Residential accepts IP-CONNECT → gost-direct, no relay.
- The `app-debug.apk` can be **stale** (gradle "up-to-date" / old timestamp) — verify with `dumpsys`
  after install; rebuild with `./gradlew :app:assembleDebug` if needed.
- `type`/`address`/`description` local extraction is **best-effort regex** on the card content-desc;
  it worked for coffee + childcare but may need tuning on other verticals — verify against a live SERP.

---

## 📦 The new repo: `DeviceFarm1/seo-device-agent` (PRIVATE)

- `main` = `README.md` only (initial). `develop` = 34-file clean bundle (app + SEO runners +
  `gost_manager.py` + docs). Default branch = `main` (user may want `develop`).
- It's a **fresh snapshot** (own history), built in `/tmp/seo-device-agent` and pushed — the
  `device-agent` working tree was NOT modified by the push.
- Secrets scrubbed: no password; the 3 Decodo usernames (`spx491gvtx`/`spmqebjuzf`/`spknlt0736`)
  replaced with `REPLACE_ME`. `.env.dev` excluded; `.env.dev.example` included.
- User said: **"we will also put the daily search here"** → this repo is the home for daily SEO runs.

---

## Open / next steps

1. **Decide whether to commit the SEO changes in the original `device-agent` repo** (they're only in
   the new repo as a snapshot; `device-agent` still has them uncommitted on branch
   `feature/superproxy-dispatch`).
2. **Build the "daily search" runner** in `seo-device-agent` (the user's stated next goal) — a
   scheduled multi-keyword/multi-business SEO audit, presumably reading a catalog like
   `aeo-appium/clients_audit_targets.json` and rotating across fresh phones.
3. Optionally set `develop` as the repo's default branch.
4. Tune local-field regexes across more verticals; consider sitelinks parsing for organic.
5. Scale thinking: on-device is intermittent (phone-burn risk). For high volume, a SERP API could be
   the data backbone with the device used for proof screenshots — but on-device alone works on fresh
   phones at low volume.

---

## Quick reference

| Thing | Value |
|---|---|
| This Mac LAN IP | `192.168.0.164` (en1) |
| Working phone | Infinix **device-102** = `adb-1490455615007763-aoRAJa._adb-tls-connect._tcp` (v0.8.0-seo installed, accessibility on, SocksDroid on) |
| Burned phone | Samsung **device-101** = `adb-R83L103VCVH-uvv2pp._adb-tls-connect._tcp` (flagged for Google; was dropping from adb) |
| Other fresh phones | several Infinix in `adb devices` (have SocksDroid + Chrome; need the SEO APK installed) |
| Residential proxy | `gate.decodo.com:10001`, creds in `device-agent/.env.dev` (`PROXY_PASSWORD`) |
| SEO app | `com.deviceagent` v0.8.0-seo (versionCode 10), HTTP `:8765` |
| Tunnel bringup | `test_residential_one.py` (also on `docs/mobile-proxy-setup` branch + in new repo) |
| Proxy lib | `gost_manager.py` (in `aeo-appium/`, copied into new repo) — tier preflight zip→region→country |
| New repo | https://github.com/DeviceFarm1/seo-device-agent (private) |
