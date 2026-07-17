# New Mac Mini Setup — device-agent fleet

Bring-up guide for a **new Mac Mini** joining the phone fleet. Written for Claude to
execute step by step. Every step has a verification command — **do not proceed past a
step whose verification fails.**

Companion docs: `CLAUDE.md` (architecture + decisions), `RUN.md` (day-to-day run
commands), `~/MAC_FLEET_SETUP.md` (older long-form onboarding).

---

## 0. What this machine does

The Mac drives ~10–25 Android phones over adb. Each phone runs `com.deviceagent`
(an AccessibilityService + an HTTP server on phone port `8765`) which automates
ChatGPT / Gemini / Perplexity. Python runners on the Mac build a job set, stand up a
per-job proxy chain, dispatch to a phone, and write results to CSV.

Traffic path per job:

```
run_ranking.py (Mac)
   -> gost listener on Mac  (127.0.0.1:16xxx -> gate.decodo.com:10001, per-job zip)
   -> socksdroid on phone   (SOCKS client pointed at the Mac's gost port)
   -> phone's browser/app   (exits from a residential IP in the target zip)
```

Both halves are mandatory: **no socksdroid on the phone = no proxy = wrong geo =
rejected audits.**

---

## 1. Requirements

| Component | Version / source | Why |
|---|---|---|
| macOS | 13+ | host |
| Homebrew | latest | installs gost, adb |
| Python | **3.14** (python.org framework build) | runners hardcode `/Library/Frameworks/Python.framework/Versions/3.14/bin` on PATH |
| `gost` | homebrew `gost` | the Mac-side proxy chain |
| `adb` | Android platform-tools | phone control |
| AWS CLI | v2 + profile `aeo-admin` | fetches `EXECUTOR_TOKEN` / `READ_API_TOKEN` from Secrets Manager |
| Python pkgs | `certifi`, `websocket-client`, `pika`, `Pillow`, `numpy` | TLS roots, Gemini CDP, RabbitMQ, screenshot OCR |
| Repos | `device-agent`, `aeo-appium` | runners + per-business audit catalog |

### 1.1 Install

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install gost android-platform-tools awscli
```

Install Python 3.14 from python.org (**not** brew — the runners reference the framework
path explicitly), then:

```bash
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pip install \
  certifi websocket-client pika Pillow numpy
```

**Verify:**
```bash
gost -V && adb version && aws --version
python3 -c "import certifi, websocket, pika, PIL, numpy; print('py deps OK')"
```

### 1.2 Repos

```bash
mkdir -p ~/projects && cd ~/projects
git clone https://github.com/DeviceFarm1/device-agent.git
git clone <aeo-appium remote> aeo-appium
```

`aeo-appium/clients_audit_targets.json` is **required** — `audit_dispatch_http.py` reads
it for per-business audit config (proxy zip, biz_url, city/state). Without an entry the
dispatcher falls back to NY zip 10001 and the AI platform rejects the audit on
geo-mismatch.

**Verify:**
```bash
test -f ~/projects/aeo-appium/clients_audit_targets.json && echo "catalog OK"
```

---

## 2. Credentials

### 2.1 AWS profile

```bash
aws configure --profile aeo-admin      # region us-east-1
```

**Verify** (must print `True True`):
```bash
aws secretsmanager get-secret-value --secret-id aeo-admin/prod \
  --profile aeo-admin --region us-east-1 --query SecretString --output text \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('EXECUTOR_TOKEN' in d, 'READ_API_TOKEN' in d)"
```

### 2.2 `.env.dev`

Create `~/projects/device-agent/.env.dev` (**gitignored — never commit it**). Copy the
values from an existing fleet Mac or the password manager. Required keys:

```
DECODO_PASS=<decodo proxy password>
PROXY_USER=user-spmqebjuzf
```

> **Residential vs mobile.** Ranking runs **residential**: `PROXY_HOST=gate.decodo.com`,
> `PROXY_PORT=10001`, account `user-spmqebjuzf`, **relay OFF** (`USE_SNI_RELAY=0`).
> The mobile account (`spknlt0736`, port 7000) + SNI relay makes Google reset
> `gemini.google.com`. `.env.dev` sets `PROXY_PORT=7000`; the ranking scripts override
> it to 10001 — do not "fix" that.

**Pitfall #1:** if you skip `set -a; source .env.dev; set +a`, `PROXY_USER` is empty,
gost auth fails, and **every job dies with a TLS RST**. Cost 5h+ on 2026-05-22.

**Verify:**
```bash
cd ~/projects/device-agent && set -a && source .env.dev && set +a
[ -n "$DECODO_PASS" ] && echo "DECODO_PASS loaded" || echo "MISSING"
```

---

## 3. Phone provisioning

Every phone needs **four** things. Missing any one = it fails every job.

1. adb wireless pairing (survives reboot via `~/.android/adbkey`)
2. `com.deviceagent` — **must match the fleet build** (currently `0.9.52-keepalive-fix`, versionCode 71)
3. `net.typeblog.socks` (socksdroid)
4. Accessibility enabled for `com.deviceagent`

### 3.1 Pair over wireless

On the phone: Settings → Developer options → **Wireless debugging** → *Pair device with
pairing code*.

```bash
adb pair 192.168.0.X:PORT       # pairing port + code from the phone
adb connect 192.168.0.X:PORT    # connect port (different from the pairing port)
```

**Verify** — the phone must appear as an mDNS TLS serial:
```bash
adb devices | grep _adb-tls-connect
```

### 3.2 Get the exact fleet APKs

**Do not trust `device-agent.apk` in the repo** — it drifts from what's deployed. Pull
the live build off a working fleet phone:

```bash
SRC=<serial of a known-good phone>
adb -s "$SRC" pull "$(adb -s "$SRC" shell pm path com.deviceagent | tr -d '\r' | sed 's/^package://' | head -1)" /tmp/deviceagent_live.apk
adb -s "$SRC" pull "$(adb -s "$SRC" shell pm path net.typeblog.socks | tr -d '\r' | sed 's/^package://')" /tmp/socksdroid.apk
```

### 3.3 Provision a phone

```bash
T=<target serial>

adb -s "$T" install -r /tmp/socksdroid.apk

# Agent: a pre-installed build may be signed with a DIFFERENT key ->
#   INSTALL_FAILED_UPDATE_INCOMPATIBLE: signatures do not match
# In that case uninstall first. Try -r, fall back to uninstall+install.
adb -s "$T" install -r /tmp/deviceagent_live.apk \
  || { adb -s "$T" uninstall com.deviceagent; adb -s "$T" install /tmp/deviceagent_live.apk; }

# Enable accessibility. MUST come AFTER the install has settled — running it
# immediately after `install` silently no-ops and reads back null.
sleep 3
adb -s "$T" shell settings put secure enabled_accessibility_services \
    com.deviceagent/com.deviceagent.AgentAccessibilityService
adb -s "$T" shell settings put secure accessibility_enabled 1
```

**Verify** (the only check that matters — all three fields):
```bash
adb -s "$T" forward tcp:8999 tcp:8765
curl -s http://127.0.0.1:8999/health; echo
adb -s "$T" forward --remove tcp:8999
# expect: {"ok":true,"version":"0.9.52-keepalive-fix","versionCode":71,"accessibility":true,...}
```

If `accessibility` is false or the setting reads back `null`, re-run the two `settings
put` lines. The shell trick **does** work on a fresh install (incl. Android 15); it is
unreliable only **after a force-stop**, where a manual toggle in Settings →
Accessibility may be required.

### 3.4 Register phones in `DEVICES`

**Phones are not auto-discovered.** `run_with_proxy.py` holds a hardcoded `DEVICES` list
and `ONLY_ONLINE=1` only *prunes* it. A phone absent from `DEVICES` is ignored no matter
how healthy it is.

Add one tuple per phone:

```python
DEVICES = [
    ("device-101", "adb-R83L112EVWK-PydBnX._adb-tls-connect._tcp"),
    # ...
]
```

The **hardware core** is the token right after `adb-` (e.g. `R83L112EVWK`). It never
changes. The trailing hash and any ` (2)` duplicate-counter rotate on reconnect —
`_hw_core()` matches on the stable part, so a serial flip does not break the entry.

**Verify** — every phone you provisioned must read GOOD:
```bash
cd ~/projects/device-agent && python3 probe_phones.py
# DOWN=<phones not reachable>   GOOD=<count>
```

---

## 4. Auto-reconnect LaunchAgent

Makes the fleet self-heal on boot. **This is the only piece that survives a reboot** —
set it up or you will re-connect phones by hand every restart.

`~/Library/LaunchAgents/com.deviceagent.fleet.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>            <string>com.deviceagent.fleet</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/&lt;USER&gt;/projects/device-agent/_fleet_boot.sh</string>
    </array>
    <key>RunAtLoad</key>        <true/>
    <key>KeepAlive</key>        <true/>
    <key>ThrottleInterval</key> <integer>30</integer>
    <key>StandardOutPath</key>  <string>/private/tmp/fleet_launchd.out</string>
    <key>StandardErrorPath</key><string>/private/tmp/fleet_launchd.err</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.deviceagent.fleet.plist
```

`_fleet_boot.sh` starts the adb server (mDNS auto-reconnects paired phones), explicitly
`adb connect`s anything still advertising, then execs `_fleet_watchdog.sh` so launchd's
KeepAlive keeps the whole chain alive.

**Verify:**
```bash
launchctl list | grep com.deviceagent.fleet    # must show a PID
```

> **Do not** `adb kill-server` to "fix" things — it thrashes the mDNS backend.
> `_fleet_boot.sh` only bounces the server if it is up but sees zero devices.

> **Duplicate transports are expected and harmless.** `_fleet_boot.sh` adds an IP
> transport (`192.168.0.x:port`) alongside the mDNS one, so `adb devices` shows ~2x
> entries. They are inert: `DEVICES` holds `adb-<hwcore>-…` serials and `_hw_core()`
> can't match an IP transport, so no phone is double-counted. Do not "clean them up" —
> the watchdog re-adds them.

---

## 5. Smoke test

```bash
cd ~/projects/device-agent
python3 probe_phones.py                          # GOOD=<n> matches your phone count
export SSL_CERT_FILE=$(python3 -c "import certifi;print(certifi.where())")
SCOPE=all_due DATE=$(date +%F) python3 build_ranking_dueset.py
```

The dueset builder must print `SELECTED (all_due): <n> keywords` and write
`/tmp/ranking_kw_ids_<DATE>.json` plus `/tmp/{biz,kw,clients,rr}_admin.json`.
`rr_admin.json` should be **tens of thousands of rows** — if it's `[]` or tiny, the
ranking-reports fetch failed and every keyword will look never-ranked.

---

## 6. Running

```bash
cd ~/projects/device-agent
SKIP_BASE=1 ONLY_ONLINE=1 WORKERS_CAP=20 ./run_ranking_auto.sh $(date +%F) all_due
```

| Flag | Meaning |
|---|---|
| `SKIP_BASE=1` | **Resume.** Skips the base wave and enters the retry loop, which is the only path that applies `EXCLUDE_SUCCESS`. Without it a restart **redoes every already-captured pair.** |
| `ONLY_ONLINE=1` | Prune `DEVICES` to phones adb sees right now (by hardware core, so serial flips still resolve). |
| `WORKERS_CAP=N` | Upper bound. `WORKERS = min(GOOD, CAP)`. Set it above your phone count to auto-size to whatever is reachable. |

### Key behaviours

- **Resume is CSV-driven.** `EXCLUDE_SUCCESS` reads
  `rabbitmq_audit_results_<DATE>_ranking*.csv` and skips pairs already `success`/`no_rank`.
  Results live in the repo dir and survive reboots — **`/tmp` does not.**
- **`/tmp` is wiped by a reboot.** The dueset + admin snapshots vanish. The runner
  rebuilds them automatically when `/tmp/ranking_kw_ids_<DATE>.json` is absent.
- **The run dies with its parent shell.** It is not daemonised — a Mac reboot or a
  terminal/agent restart kills it. Progress is safe (CSV) but you must relaunch.
- **Worker cap.** The audit path does far more proxy handshakes per job than the daily.
  Historically capped at 6 for router stability; 19+ has run fine on a healthy LAN.
  If you see widespread proxy errors, lower `WORKERS_CAP` first.

---

## 6b. Operational workflows

### Re-running a specific list (admin-sent bad captures)

Admin periodically sends a CSV of report rows whose captures were bad (no screenshot,
stale image, or a rank rejected as likely-fabricated) with columns:
`report_id, date, client_id, client, biz_name, city, state, keyword_id, keyword,
platform, rank_position, status, verdict, reason`.

Re-run **exactly those `(keyword_id, platform)` pairs** — not all 3 platforms per
keyword, or you re-capture slots that were fine and risk regressing them.

1. **Group targets by platform** and write one kw-ids file per platform
   (`/tmp/rerun_{cg,px,gm}.json` = flat arrays of int keyword ids).
2. **Force the freshness gate off.** These rows are `status=success` in prod, so the
   runner would skip them as "fresh". Write `/tmp/rr_admin.json` as `[]` → every target
   becomes `INITIAL_RANKING` and actually runs.
3. **Run one pass per platform** with `PLATFORMS=<one>` + its `KEYWORD_IDS_FILE`, sharing
   one `AUDIT_CSV` and `EXCLUDE_SUCCESS` glob so passes dedupe against each other.
4. **Set `RETRY_KEEP_NORANK=1`** so a genuine `no_rank` is terminal and only errors retry.
5. Put priority clients in their own first pass so they land early and can be verified
   before the bulk runs.

> Restore a real `rr_admin.json` (re-run `build_ranking_dueset.py`) before any normal
> run — an empty one disables freshness skipping fleet-wide.

### Consolidating a deliverable

`consolidate_ranking.py` globs `rabbitmq_audit_results_<DATE>_ranking*.csv`, keeps one
OCR-validated `success` per `(campaign_id, platform)`, and writes to
`~/Desktop/Rankings/`. **We produce CSVs; we never import — admin does.**

Dating (pick deliberately, it is the whole ballgame):

| Mode | Date used | When |
|---|---|---|
| default | keyword's `createdAt` | initial ranking of new keywords |
| `USE_RUN_DATE=1` | the run date | stale re-run = a fresh current reading |
| `USE_14DAY=1` | last rank **+14d** (the missed bi-weekly slot) | backfilling a missed cadence slot |

`keyword_id = campaign_id % 10000`. Screenshots are re-dated (copied) into the
slot-date folder so the S3 key matches the CSV date.

**Two traps:**

- `USE_14DAY` reads **one date per keyword**, but staleness is per
  `(keyword, platform)`. A keyword due only on perplexity while chatgpt is fresh takes
  the *fresh* date → `+14` lands **in the future**. Date per-slot, not per-keyword.
- For a re-run replacing specific report rows, date each row at **its own slot's
  original date** (the `date` column of the admin list) and carry `report_id`, so admin
  can import onto the exact reports.

> A capture measured today must not be dated to a slot it never measured — the
> screenshot is visibly from the capture date and will contradict the row.

### Verifying a rank is real

`status=success` means inline OCR validated the screenshot (bad ones are demoted to
`ocr_no_answer`). Beyond that, a capture is trustworthy when `rank_context`
(`[RANK: X/Y]`) agrees with the numbered list in `response_text`, and the business
actually appears at position X. `[RANK: Y/Y]` is the "does not genuinely rank"
convention — an unranked business placed last, **not** a rank of Y.

---

## 7. Verification checklist

Run in order. Every line must pass before the machine is fleet-ready.

```bash
gost -V                                                   # gost installed
adb version                                               # adb installed
python3 -c "import certifi, websocket, pika, PIL, numpy"  # py deps
aws secretsmanager get-secret-value --secret-id aeo-admin/prod \
  --profile aeo-admin --region us-east-1 >/dev/null       # AWS creds
test -f ~/projects/device-agent/.env.dev                  # proxy creds
test -f ~/projects/aeo-appium/clients_audit_targets.json  # audit catalog
launchctl list | grep com.deviceagent.fleet               # auto-reconnect
python3 ~/projects/device-agent/probe_phones.py           # GOOD == phone count
```

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Every job dies with TLS RST | `.env.dev` not sourced → empty `PROXY_USER` | `set -a; source .env.dev; set +a`. Confirm: `ps -p <pid> -E \| tr ' ' '\n' \| grep PROXY_USER` |
| Gemini connection reset | Mobile account + SNI relay | Residential `user-spmqebjuzf`, port 10001, `USE_SNI_RELAY=0` |
| `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | Pre-installed agent signed with another key | `adb uninstall com.deviceagent` then install |
| `/health` empty, accessibility `null` | `settings put` raced the install | Wait, re-apply both `settings put` lines |
| Phone healthy but never used | Not in `DEVICES` | Add its `(label, serial)` tuple |
| One worker fails every job (`http fail`) | mDNS serial flipped (`x` → `x (2)`) | `_hw_core()` normally absorbs it; if the probe still says DOWN, update the serial in `DEVICES` |
| adb forwards vanish mid-run | adb server reset | Re-create `adb -s <serial> forward tcp:{8765+i} tcp:8765` in pruned `DEVICES` order |
| Phone advertises in mDNS but `adb connect` → **Connection refused** | Stale mDNS record; wireless debugging off/port rotated | **Physical toggle required** on the handset |
| Restart redoes finished work | `SKIP_BASE` not set | Always `SKIP_BASE=1` when resuming |
| Everything looks stale / all never-ranked | `rr_admin.json` empty | Re-run `build_ranking_dueset.py`; needs `READ_API_TOKEN` |
| Locked keywords missing from the run | `/api/keywords` hides `status='locked'` by default | Builder must call `?includeLocked=true` (locked = "won-but-rankable") |

---

## 9. Gotchas that have cost real hours

- **Quote mDNS serials.** They can contain ` (2)` — unquoted, the shell parses `(2)` as
  syntax. Always `adb -s "$SERIAL"`.
- **`adb` eats stdin.** In `while read` loops, redirect: `adb ... </dev/null`, or the
  loop consumes its own input and processes only the first device.
- **Never commit secrets.** `.env.dev` is gitignored. Do not hardcode `PROXY_PASSWORD`
  in a script — source `.env.dev` and use `"${DECODO_PASS:?}"`.
- **A live run grabs any adb-connected phone**, including a USB test phone. Unplug it or
  set `DEVICE_EXCLUDE=device-NNN` before isolating a phone for manual testing.
- **`adb install -r` does not reload a running service.** On-device behaviour changes
  need force-stop + accessibility off/on.
- **After `am force-stop com.deviceagent`** the accessibility binding is cleared and the
  shell trick may not restore it — a manual toggle may be needed.
- **`/health`'s version is a build-time constant** — it can lie after a version bump if
  the process wasn't restarted.
