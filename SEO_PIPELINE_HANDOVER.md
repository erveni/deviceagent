# SEO Rank + Screenshot Pipeline — Session Handover

_Last updated: 2026-06-02. Status: **pipeline DONE & proven; blocked only on Google captcha via proxies.**_

## The task
Build a SerpApi-style **SEO rank + screenshot pipeline** on the device-agent fleet:
run a real Google search on an Android phone (Chrome), scrape **organic + local-pack
rankings (ads + active filters excluded)**, find the target business's position, and
capture a **proof screenshot** framed on the rankings. AEO (existing) ranks via AI
platforms; this is the **SEO** counterpart that searches Google directly.

---

## ✅ What's DONE and PROVEN (the on-device pipeline)

New `type:"seo"` flow in **`com.deviceagent`** (our app), all code uncommitted:

- **`FlowEngine.kt`** (~600 new lines):
  - `navigateToGoogleHome()` — google.com home, dismisses Chrome/consent dialogs, waits for search box.
  - `submitSearch(keyword)` — human submit: **tap exact-match autocomplete row** → IME-enter on the box (found by query text, any y) → keyboard enter. (`navigateToSerp` = `?q=` direct fallback.)
  - `parseSerp(target)` → **SerpApi-like JSON**: ordered `organic` (position, title, domain, url; ads excluded + counted), `local_pack` (name, rating; **sponsored excluded** + counted), `location`, `target.{organic_rank, local_rank}`.
    - Discriminators (ground-truthed): organic = `About this result` button; ad = `Why this ad?`; local card = `Rated X out of 5`. Local pack **region-scoped** to the `Places`/`Businesses`→`More places`/next-section span (so organic Yelp ratings aren't mistaken for local). Name junk filtered (`http`, ` · `, `Open …`, button labels). Target local match via domain **brand token** (`epoch.coffee`→"epoch"→"Epoch Coffee").
  - `scrollToTextTop(["Places","Businesses","Web results"])` — frames the screenshot on the **first content section** (local pack if present, else organic). MUST use **far-right edge swipes** (centre swipe pans the local-pack map) and **exact text match** (`findNode` uses `contains`, which wrongly matched "More places"). Calibrated band [180,440]; off-screen node clamps to ~`h-90`.
  - `clearSearchFilters()` — clears active filter chips (active = clickable `Remove <filter>` in top strip; click toggles off) so ranking is the **unfiltered default**.
  - Captcha/err handling: `waitForSerp` detects challenge phrases + `ERR_…`/"site can't be reached" (taps **Reload**); `solveChallenge()` ticks "I'm not a robot"; on hard block → status `blocked` + evidence screenshot + `challenge:true`.
- **`AgentHttpServer.kt`**: `type:"seo"` route → `executeGoogleSerpStatic` (reset → navigate → input → submit → wait → clear_filters → scroll_to_top_section + **screenshot** → scroll → parse). Response carries `serp{organic,local_pack,ads_excluded,local_ads_excluded,location,target}` + base64 screenshot.
- **APK**: `v0.8.0-seo`, versionCode 10. NOT copied to tracked root `device-agent.apk`. Nothing committed.

**Proven on Samsung SM-A075F (no proxy, before its IP got burned):**
- `personal injury lawyer austin` / `ramosjames.com` → organic **#7–#9**, local pack clean (Carlson[SPON] excluded, Sandoval/McMinn/TK), screenshot framed on the map.
- `best coffee shop austin` / `epoch.coffee` → local **Mozart's / Cosmic Pickle / Epoch**, screenshot on `Places`.
- `what is seo` (no local pack) → stops on **`Web results`**, 6 organic, local empty. ✓ scenario fallback works.

**Reference:** `seo-voice-rank/docs/SERP-PARSE-REFERENCE.md` (parse discriminators, ground-truthed against a live dump).

---

## ⛔ THE BLOCKER: Google reCAPTCHA through proxies

**The fleet has NEVER scraped Google** — audit/ranking goes through AI platforms
(ChatGPT/Gemini/Perplexity), so Google's "unusual traffic" reCAPTCHA was never solved
here (confirmed in signal-aeo memory). We're the first. The pipeline works whenever a
SERP loads; getting a **clean IP that Google won't challenge** is the unsolved problem —
this is exactly what SerpApi's infra exists to solve.

---

## ❌ What FAILED — do NOT repeat these

1. **Bare phone IP** — works ~half the time, but **burns** after rapid testing → persistent captcha. (I burned the Samsung with ~12 fast searches; it now re-challenges every new search.)
2. **Residential Decodo** (`.env.dev` `user-spmqebjuzf` @ `gate.decodo.com:10001`) — account is **DEAD** (memory: `received=348 success=0`). Live test gives Comcast/Spectrum IPs that **get the captcha**; sticky sessions **flaky** (1 call works, next two fail); gost chain DNS errors.
3. **gost + socksdroid + mobile creds** → **`ERR_CONNECTION_RESET`**. gost's SOCKS5 chain to Decodo **mobile** is broken on ports 7000 *and* 10001 even though direct `curl --socks5` works. gost only carries the phone tunnel for **residential @ 10001**. Don't pursue gost for mobile.
4. **SuperProxy mobile app path** — pages **load fine** (no reset), but the **`/search` request still gets the captcha** on the Verizon/T-Mobile IP (saw `97.135.181.187`, tun0 confirmed up). Also `sp.setup` is **flaky**: the free SuperProxy app shows ads and a `uiautomator dump` during ad-dismiss can time out (8s) and crash setup.
5. **`solveChallenge` "I'm not a robot"** — the tap registers, but on a flagged IP reCAPTCHA escalates straight to an **image puzzle** ("select all stairs") that can't be auto-solved. Clean IPs pass with just the checkbox.
6. **`dismiss_fre` step** (removed) — it re-navigated to google.com and left the page mid-load → `input failed`, esp. through a slow proxy. `navigateToGoogleHome` already dismisses dialogs. Don't add it back for the Google flow.
7. **Shell-toggling the farm agent's accessibility** (`settings put …`) — **half-binds** (listed but executor not connected; server closes connections, `HTTP 000`). Cycling it via the Settings UI **broke its server**. **FIX that worked: reinstall the farm agent APK** (`pm path` → `adb pull base.apk` → `adb install -r`) → `/health` returns `serverRunning:true, executorConnected:true`.

---

## 🔑 Infra facts (learned this session)

- **Two agent apps on the phone:**
  - `com.deviceagent` — **OUR SEO app**, HTTP on phone **:8765**, label **"DeviceAgent"** (no space). Runs the `type:seo` flow.
  - `com.farm.device.android.device.agent` — **FARM agent**, Ktor on phone **:7070** (adb-forward base 17070 + idx), label **"Device Agent"** (with space). Drives the SuperProxy app via `/superproxy`, `/superproxy/start`, `/superproxy/stop`. Must be healthy.
- `com.scheler.superproxy` — the **mobile VPN** app; connects the phone **directly** to Decodo Mobile (no Mac/gost). Profile is POSTed at runtime (the app is empty otherwise).
- **Mobile Decodo account:** `SUPERPROXY_USER=spx491gvtx`, `SUPERPROXY_PASS` in `.env.dev` (added this session). Username form `user-spx491gvtx-country-us`; **sticky** = append `-session-<id>-sessionduration-<min>` (mobile sticky **does** hold one IP — verified: 4 calls → one T-Mobile IP). Pool returns a **mix** (Verizon Fios, T-Mobile cellular, Comcast). Mobile gateway speaks SOCKS5 on :7000/:10001 via curl but **not via gost's sustained chain**.
- Production audit flow **rotates the Decodo session on a block** (`AUDIT_RETRY_TRIGGERS` → `sp.teardown` + `sp.setup`) — the documented retry pattern.
- **Samsung** = `device-idx 0` = `device-101` = serial `adb-R83L103VCVH-uvv2pp._adb-tls-connect._tcp`, SM-A075F Android 16. `MAC_IP=192.168.0.164` (this Mac, en1). Samsung wlan0 `192.168.0.178`.
- Phone is currently **reset**: no VPN, both proxy apps `pm clear`'d, gost stopped, forwards removed.

---

## ▶️ NEXT (open)

- **User will show the socksdroid option next** — possibly a working socksdroid/mobile route that dodges the captcha. Pick up there.
- **Decide IP/captcha strategy** (don't just tweak the username again — every Decodo IP gets challenged):
  1. **Hybrid** — ranking numbers from a real SERP API (SerpApi/DataForSEO), device only for the live proof screenshot.
  2. **Better IPs** — a SERP-grade or true-cellular proxy Google doesn't blanket-flag.
  3. **Rotate-on-captcha retry** — sticky cellular session + fresh IP per block, up to N tries (mirrors the audit flow). **NOT yet built.**
  4. **Captcha-solver service** (image puzzle) — costs money, ToS risk.

## How to run (once a clean IP exists)
```bash
# Direct (un-burned IP):
python3 seo_dispatch.py --keyword "best coffee shop austin" --target epoch.coffee \
  --serial adb-R83L103VCVH-uvv2pp._adb-tls-connect._tcp

# Mobile via SuperProxy (farm agent must be healthy):
set -a; source .env.dev; set +a
SEO_HTTP_TIMEOUT_S=420 python3 seo_superproxy_run.py --device-idx 0 \
  --keyword "best coffee shop austin" --target epoch.coffee
# Verify farm agent first: adb forward tcp:17070 tcp:7070; curl localhost:17070/health
#   -> {"serverRunning":true,"executorConnected":true}.  If not: reinstall its APK.
```

## Files touched this session (all UNCOMMITTED)
- `app/src/main/java/com/deviceagent/FlowEngine.kt` — SEO flow, parseSerp, scroll, filters, challenge
- `app/src/main/java/com/deviceagent/AgentHttpServer.kt` — `type:seo` route, `executeGoogleSerpStatic`, serp JSON
- `app/build.gradle.kts` — v0.8.0-seo (versionCode 10)
- `seo_dispatch.py` (direct), `seo_proxy_run.py` (gost rotation+precheck), `seo_superproxy_run.py` (mobile)
- `.env.dev` — added `SUPERPROXY_USER`/`SUPERPROXY_PASS`
- `CLAUDE.md` — SEO flow section + v0.8.0 row
- `seo-voice-rank/docs/SERP-PARSE-REFERENCE.md`
