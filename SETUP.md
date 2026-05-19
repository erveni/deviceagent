# device-agent — Setup Guide

This repo contains **both** halves of the device-agent system:

| Component | Where it runs | Purpose |
|---|---|---|
| Android app (`app/`) | On each Android phone | Kotlin AccessibilityService + HTTP server on port 8765 that drives ChatGPT/Gemini/Perplexity UI |
| Python consumer (`solace_consumer.py`) | On the Mac mini | Pulls jobs from RabbitMQ, dispatches to phones via adb+gost, publishes results back |

Both pieces evolve together — they share the job/result schema with the upstream `job-scheduler` + `orchestrator` services. Don't split them into separate repos until that schema stabilises.

## Architecture

```
┌──────────────────── AWS (us-east-1) ─────────────────────┐    ┌────────── Mac mini ──────────┐
│  job-scheduler  ──▶  orchestrator  ──▶  RabbitMQ broker  │───▶│  solace_consumer.py (Python) │
│  (publishes CREATED jobs)         (prepares PENDING)     │    │   ↓ thread pool dispatch     │
│                                                          │    │  ┌─────────────────────────┐ │
│  AEOAdmin BE   ◀──────────────  results queue  ◀──────── │────│  │ 10 Android phones       │ │
│  (admin DB upsert)                                       │    │  │  + Decodo SOCKS proxy   │ │
└──────────────────────────────────────────────────────────┘    │  │  + socksdroid VPN       │ │
                                                                │  └─────────────────────────┘ │
                                                                └──────────────────────────────┘
```

## Prerequisites

On the Mac:

1. **macOS** (tested on Apple Silicon)
2. **Homebrew** — install from https://brew.sh
3. **Java 17+** for Gradle (`brew install openjdk@17`)
4. **Android Platform Tools** — provides `adb` (`brew install --cask android-platform-tools`)
5. **Python 3.10+** (`brew install python@3.12` or system Python 3.14+)
6. **gost** SOCKS5 proxy router (`brew install gost`)
7. **AWS CLI** with `aeo-admin` profile configured (for secret fetches)
8. **gh CLI** (`brew install gh`) for any GitHub operations

On each phone:

1. **socksdroid** APK installed (handles SOCKS5 → device VPN tunnel)
2. **com.deviceagent** APK installed (this repo's Android app)
3. Accessibility service for `com.deviceagent` **enabled** in Settings
4. **adb tcpip 5555** enabled and the phone paired with the Mac's adb server
5. **Mock location** app set to `com.deviceagent` in Developer Options

## Install (one-time per Mac)

```bash
# 1. Clone
git clone git@github.com:DeviceFarm1/device-agent.git
cd device-agent
git checkout dev      # production branch is TBD; current code lives on dev

# 2. Python deps (system Python or homebrew Python 3.12+)
python3 -m pip install --user pika certifi requests

# 3. Build & install Android app on each phone
./gradlew :app:assembleDebug
for s in $(adb devices | awk 'NR>1 && $2=="device" {print $1}'); do
  echo "Installing on $s"
  adb -s "$s" install -r -g app/build/outputs/apk/debug/app-debug.apk
done

# 4. Configure broker creds (DO NOT commit .env.dev)
cp .env.dev.example .env.dev
# Edit .env.dev — fill in RABBITMQ_PASSWORD, EXECUTOR_TOKEN, PROXY_USER, PROXY_PASS
# Pull RabbitMQ password:
aws --profile aeo-admin secretsmanager get-secret-value \
  --secret-id android-device-farm/dev/rabbitmq/broker/settings/admin \
  --query SecretString --output text
```

## Run (dev mode)

```bash
# Sanity-check phones are visible
adb devices

# Start consumer (dispatches to phones)
DISPATCH_ENABLED=1 ./start-dev.sh

# Watch the log
tail -f /tmp/consumer_dev_*.log
```

`start-dev.sh` sources `.env.dev`, exports `SSL_CERT_FILE` (required for macOS framework Python), and runs `solace_consumer.py` with `nohup`. It prints the PID and log path.

## Halt (clean shutdown)

```bash
# 1. Kill the consumer
pkill -9 -f solace_consumer.py

# 2. Kill any gost listeners
pkill -9 -f "gost -C"

# 3. Force-stop socksdroid on every phone (CRITICAL — otherwise the SOCKS
#    tunnel keeps consuming Decodo bandwidth silently after halt)
adb devices | grep -E '\tdevice$' | sed 's/\tdevice$//' | while IFS= read -r serial; do
  adb -s "$serial" shell am force-stop net.typeblog.socks </dev/null
done
```

## Multi-Mac setup

You can run this consumer on multiple Mac minis simultaneously — they all attach to the same `local_device_manager_jobs_queue` and RabbitMQ load-balances messages between them. Add a Mac:

1. Repeat the **Install** steps above on the new machine.
2. Use the **same** `.env.dev` (creds are shared per environment).
3. Run `./start-dev.sh` on each.
4. The broker will distribute jobs across all attached consumers.

Each Mac's consumer writes its own CSV log to `/tmp/consumer_dev_*.log`. Aggregate them at the end of a run for full visibility.

## Known caveats — read before changing anything

1. **Consumer acks on receive, not on completion.** `solace_consumer.py:480` acks the message the moment it hands the payload to the thread pool. Killing the consumer mid-flight means every in-flight job is lost from the broker (no requeue, no recovery from RMQ side). Only the source-of-truth DB (scheduler/orchestrator) can recover by resetting `PENDING → CREATED`.
2. **mDNS ADB serials containing `(2)` must be shell-quoted** in every adb command: `adb -s "$serial" shell ...`. Unquoted, the shell parses `(2)` as syntax.
3. **socksdroid must be force-stopped on every halt.** Otherwise it keeps the Decodo tunnel open and burns proxy bandwidth.
4. **Don't commit a rebuilt `device-agent.apk`** without bumping `versionCode`/`versionName` in `app/build.gradle.kts`.
5. **Don't hardcode credentials** in `run_*.py`, `solace_consumer.py`, or `audit_dispatch.py`. All secrets come from env vars sourced from `.env.dev` (or `.env.prod`).

## Switching environments

To switch from dev to prod, drop a `.env.prod` (gitignored by `.env.*` pattern) with the prod broker host + creds and:

```bash
# Edit start-dev.sh OR clone it to start-prod.sh, changing the source line:
#   source .env.prod
```

The queue names + routing keys are environment-agnostic in this codebase (they hard-code `local_*`-prefixed names), so a prod broker that uses the same names will work as-is.

## Glossary

- **consumer** — the Python script (`solace_consumer.py`) that subscribes to the work queue and dispatches to phones
- **gost** — a Go-based SOCKS5 proxy router; one process per wave/job that fronts Decodo
- **socksdroid** — Android app that creates a VPN tunnel routing all phone traffic through the gost listener on the Mac
- **wave** — a batch of N parallel sessions (one per phone) sharing one upstream proxy session
- **mDNS serial** — adb-over-Wi-Fi device identifier of the form `adb-XXXX-yyyy._adb-tls-connect._tcp`

## Where to look when things break

| Symptom | First place to check |
|---|---|
| Consumer can't connect to broker | `.env.dev` values + AWS security group on the broker EC2 |
| Jobs received but phone doesn't move | adb tcpip status + accessibility service enabled |
| Decodo "input_failed" cascades | rotate Decodo session (consumer does this; if persistent, check Decodo account) |
| `(2)` syntax errors in shell | unquoted adb serial — wrap in `"..."` |
| Bandwidth still draining after halt | socksdroid wasn't force-stopped on every phone |
