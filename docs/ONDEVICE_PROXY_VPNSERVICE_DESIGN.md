# On-device proxy via VpnService — design

**Status:** proposed · **Date:** 2026-06-25 · **Owner:** erveni
**Goal:** route each phone's AI-platform traffic through Decodo from the phone
itself — no Mac-side `gost`, no `adb`-driven socksdroid, no wireless dependency.
This is the proxy leg of the broader "autonomous device-agent" vision (job pull,
mock-location, on-device Gemini CDP, result publish are separate docs).

---

## 1. Why (what the prototypes proved)

Tested 2026-06-24/25 on the Infinix X6725 (Android 15) test phone:

| Approach | Result | Lesson |
|---|---|---|
| Decodo SOCKS5 reachability (Mac) | ✅ `gate.decodo.com:10001/7000/10000` speak SOCKS5 | No protocol blocker |
| socksdroid → Decodo **direct** | ⚠️ tunnel came up (`tun0`, VPN badge, page loading) then **dropped ~20s in** | socksdroid protects its own upstream socket (no loop) but is unstable against Decodo's SOCKS5 |
| socksdroid → local **gost** → Decodo | ❌ `lookup gate.decodo.com on [::1]:53: connection refused` + would route-loop | A local upstream proxy behind a system VPN fails: its own DNS/outbound get captured by the tun unless its socket is **protected** |

**Conclusion:** the only robust on-device design is one where the component that
owns the TUN also owns the upstream dialer **and protects that dialer's sockets**
with `VpnService.protect()`. Off-the-shelf socksdroid + external gost cannot do
this. So: build the proxy into the device-agent app as a first-class `VpnService`.

This also removes the `~20s drop` unknown (we control reconnect) and deletes the
entire Mac-side `gost`/`socksdroid`/`adb-forward` stack.

---

## 2. Architecture

```
┌────────────────────────── phone (device-agent app) ──────────────────────────┐
│                                                                               │
│   Chrome / AI apps ──► TUN (VpnService) ──► tun2socks engine                   │
│                                                  │                            │
│                                                  ├─ TCP/UDP → SOCKS5 outbound  │
│                                                  │     to gate.decodo.com:10001│
│                                                  │     auth = per-job upstream │
│                                                  │     user (zip/country)      │
│                                                  │                            │
│                                                  └─ each outbound socket is    │
│                                                     VpnService.protect()'ed    │
│                                                     → bypasses TUN (no loop)   │
│                                                                               │
│   FlowEngine (existing) drives Chrome; ProxyController sets the upstream creds │
│   per job and (re)starts the tunnel before each session.                      │
└───────────────────────────────────────────────────────────────────────────────┘
                                   │ (only this leg leaves the phone)
                                   ▼
                          Decodo residential exit (US zip / CA country)
```

Key invariant: **the TUN owner and the Decodo dialer live in the same process**,
so the dialer's sockets can be `protect()`'ed. That is the one thing socksdroid +
gost could not give us.

---

## 3. Components

### 3.1 `AgentVpnService : VpnService`
- Builds the TUN: `Builder().addAddress("10.0.0.2",32).addRoute("0.0.0.0",0)`
  `.addDnsServer("8.8.8.8").setMtu(1500)`, `establish()` → TUN fd.
- Starts/stops the tun2socks engine with the current upstream config.
- Exposes `protect(fd)` to the engine (the whole point).
- Foreground service (persistent notification) so Android doesn't kill it.
- Idempotent `start(upstream)` / `stop()`; `reconfigure(upstream)` tears down +
  re-establishes with a new Decodo session (used for per-job IP rotation / retry).

### 3.2 tun2socks engine (the dialer)
Reads IP packets from the TUN fd, opens SOCKS5 connections to Decodo, relays.
**Hard requirement: a `protect` callback** invoked on every outbound socket
before connect.

Recommended implementation, in order of preference:

1. **gomobile AAR around `xjasonlyu/tun2socks`** (Go).
   - Pros: Go (same as our `gost`), small, actively maintained, pluggable
     `proxy.Dialer`; we wrap the dialer so each `DialContext` does
     `Java protect(fd)` then connects to Decodo SOCKS5 with auth. Full control.
   - Cons: we build/maintain the AAR (gomobile + a small `protectfd` JNI shim).
2. **sing-box / libbox** (the SFA "sing-box for Android" engine).
   - Pros: batteries-included — TUN inbound, SOCKS outbound w/ auth, DNS, and a
     platform `protect` interface already designed for Android VpnService.
   - Cons: heavier dependency; more config surface than we need.
3. **hev-socks5-tunnel** (C/JNI).
   - Pros: tiny, fast, YAML-config, SOCKS5 auth.
   - Cons: no built-in `protect` hook → we'd need a JNI shim that protects its
     sockets; harder to wire than the Go option. Not recommended for v1.

**Decision: option 1 (gomobile + xjasonlyu/tun2socks)** unless we want to adopt
sing-box wholesale. It mirrors what Outline/shadowsocks-android do and keeps the
stack in Go.

### 3.3 `ProxyController` (Kotlin, app-side)
- Owns the per-job upstream username built from `geo_target` logic (port the
  Python `geo_target` → Kotlin: parse real zip from `biz_address` (last 5-digit
  group), detect Canada by province/'Canada' → `country-ca`, else
  `country-us-zip-<zip>`; rotate `session-<rsid>` per job for a fresh exit IP).
- Format: `user-spmqebjuzf-session-<sid>-sessionduration-<min>-country-us-zip-<zip>`
  (or `-country-ca`). Same strings the Mac builds today — proven.
- Calls `AgentVpnService.reconfigure(upstream)` before each session; verifies the
  exit IP/geo via one request through the tunnel (mirror of `resolve_proxy_ip`).

---

## 4. DNS (the thing that bit gost-on-phone)
- The TUN advertises a DNS server (e.g. `8.8.8.8`). DNS queries enter the TUN and
  the engine must forward them **through the SOCKS upstream** (DNS-over-TCP to
  `8.8.8.8:53` via Decodo, or SOCKS5 UDP-ASSOCIATE).
- `xjasonlyu/tun2socks` handles this (it has a DNS handler that routes through the
  configured proxy). Confirm UDP/53 is relayed over SOCKS (TCP fallback if Decodo
  rejects UDP associate — Decodo residential typically does TCP).
- The engine's *own* socket to Decodo is `protect()`'ed so it resolves/connects on
  the real `wlan0`, never recursing into the TUN. (This is exactly what failed
  with gost: its DNS hit `[::1]:53` inside the captured namespace.)

---

## 5. Secrets
- `DECODO_PASS` must live on the phone. Options: (a) `BuildConfig` field injected
  at build time from CI/secret (not committed), or (b) `EncryptedSharedPreferences`
  provisioned once via the job payload / a one-time setup call.
- **Never** hardcode in source (see `.claude/rules/security.md`; the Mac copy is
  already in git history and must be rotated — see memory `decodo-pass-leaked-rotate`).
- Recommendation: `BuildConfig.DECODO_PASS` from a gitignored `local.properties` /
  CI secret; the username is non-secret (geo-targeted, derived per job).

---

## 6. Per-job lifecycle (replaces the Mac wave runner for one session)
1. Job arrives (MQTT `command/{deviceId}` — separate doc; foundation in `MqttManager`).
2. `ProxyController.upstreamFor(job)` → upstream username (geo-targeted, fresh sid).
3. `AgentVpnService.reconfigure(upstream)` → TUN up, engine dialing Decodo.
4. Verify exit IP/geo (1 request); if wrong/zip-unserved, fall back (nearest zip /
   country-us) and reconfigure.
5. `FlowEngine.fullDailySession(...)` (ChatGPT/Perplexity) **or** on-device Gemini
   CDP capture (separate doc) — unchanged automation, now over the local tunnel.
6. Publish result (MQTT/AEOAdmin). 
7. Next job: reconfigure with a new sid (rotates IP) — no teardown of the service.

Note: a single always-on `VpnService` with `reconfigure` per job is cheaper than
start/stop each time and avoids the Android VPN-consent dialog (granted once).

---

## 7. Build / deploy
- New module deps: the tun2socks AAR (vendored under `app/libs/` or a gomobile
  build step), plus `BIND_VPN_SERVICE` + foreground-service perms in the manifest.
- VPN consent: first run shows the system VPN dialog once; `VpnService.prepare()`.
  (Can be pre-granted via `appops set <pkg> ACTIVATE_VPN allow` at install, like we
  do for socksdroid — fits "adb for install only".)
- APK install still via adb (+ the Android-13 accessibility re-toggle). Bump
  `versionCode`/`versionName` (per CLAUDE.md don'ts).

---

## 8. Validation plan (on the test phone, USB)
1. Unit: `geo_target` Kotlin port matches Python on the known cases (Katy street-
   number→77450; Etobicoke→country-ca; Energy IL→nearest-served fallback).
2. Bring up `AgentVpnService` with a fixed `zip-10001` upstream → load
   `ipinfo.io/json` → assert US/NYC exit, **assert it stays up 5+ min** (the bar
   socksdroid-direct failed and gost-on-phone failed).
3. Rotate: `reconfigure` 5× with different sids → 5 different exit IPs, no drops.
4. CA: a `country-ca` upstream → Canadian exit.
5. End-to-end: one Gemini job through the on-device tunnel → response saved.
6. Soak: 50 sequential jobs, measure success rate vs the current Mac path (target ≥
   parity, i.e. ~97% Gemini / ~100% CP).

---

## 9. Risks / open questions
- **UDP/DNS over Decodo SOCKS5**: confirm Decodo supports UDP-ASSOCIATE; if not,
  force DNS-over-TCP in the engine. (Likely TCP-only on residential.)
- **Battery / thermals**: always-on VPN + AccessibilityService + Chrome on cheap
  hardware (Infinix) — monitor; may need wake-lock tuning.
- **Observability**: no Mac CSV. Need per-job result publish + the existing MQTT
  heartbeat to see fleet state. (Build the publisher alongside.)
- **gomobile maintenance**: a tiny Go AAR to keep building; pin versions.
- **Decodo stability from residential mobile IPs**: the `~20s drop` seen with
  socksdroid — verify our protected dialer + reconnect logic doesn't reproduce it
  (step 2/6 above are the gates).

---

## 10. Scope boundary
This doc covers the **proxy** only. The full autonomy build also needs: MQTT job
consumer (extend `MqttManager.messageArrived`), mock-location provider (replace adb
`appops`), on-device Gemini CDP capture (connect to local
`localabstract:chrome_devtools_remote`), and a result publisher. Those are tracked
separately; the VpnService is the prerequisite that unblocks "no wireless adb."
