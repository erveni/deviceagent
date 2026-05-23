# device-agent

Android `com.deviceagent` app (Kotlin) that automates ChatGPT / Gemini / Perplexity via AccessibilityService, exposed over HTTP on phone port 8765. Plus Python runners that orchestrate the 10-phone fleet from the Mac.

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

## APK versioning

| Version | Commit | Notes |
|---|---|---|
| v0.6.x | 0b202a6 | Old. Pre-rolling-stability fix. |
| v0.7.0-phase1 | (no source on disk) | What's installed on Mac-1 fleet as of 2026-05-24 — versionCode 8. APK file lost. |
| v0.7.1-b64 | 8670bac | Current. versionCode 9. Inlines audit PNG as base64 in `/session` response → no `adb pull` round-trip. APK at `device-agent.apk` (root, tracked, May 24). |

### Deploying APK to a new Mac

```bash
cd ~/projects/device-agent && git pull
for s in $(adb devices | awk -F'\t' 'NR>1 && $2=="device" {print $1}'); do
  adb -s "$s" install -r device-agent.apk
done
# Then MANUALLY toggle Settings → Accessibility → DeviceAgent on each phone
# (Android 13+ doesn't honor the shell-trick `settings put secure
#  enabled_accessibility_services` after force-stop).
```

## Catalog file lives in aeo-appium

`audit_dispatch_http.py` reads `/Users/seolocalph/projects/aeo-appium/clients_audit_targets.json` for per-business audit config (`proxy.zip`, `biz_url`, city/state). See `aeo-appium/CLAUDE.md` for the entry shape + how to add a new business. Without an entry the dispatcher falls back to NY zip 10001 and the AI platform rejects the audit on geo-mismatch.

## See also

- `MAC_FLEET_SETUP.md` (in ~) — 800-line onboarding doc for a new Mac in the fleet
- `/Users/seolocalph/.claude/projects/-Users-seolocalph-projects/memory/` — point-in-time observations from past sessions
