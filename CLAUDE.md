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
