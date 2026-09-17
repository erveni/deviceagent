# DeviceAgent operations runbook

This is the repeatable setup for a second Mac mini. Do not copy result CSVs,
`.env.dev`, proxy passwords, APKs, logs, or `/tmp` snapshots between hosts.

## First-time Mac mini setup

```bash
git clone https://github.com/DeviceFarm1/device-agent.git
cd device-agent
git checkout feat/top3-deepdive-ranking-geo-fix
brew install android-platform-tools gost
python3 -m pip install -r requirements.txt  # if present on the checkout
aws configure --profile aeo-admin
cp .env.dev.example .env.dev       # fill credentials from the approved secret store
./gradlew :app:assembleDebug
```

The host must have the `aeo-admin` AWS profile and access to the
`aeo-admin/prod` Secrets Manager secret. Never commit `.env.dev` or tokens.

## Phone onboarding

Enable USB debugging, connect the phone, accept the RSA prompt, and confirm:

```bash
adb devices
adb -s <serial> install -r app/build/outputs/apk/debug/app-debug.apk
adb -s <serial> shell settings put secure enabled_accessibility_services \
  com.deviceagent/com.deviceagent.AgentAccessibilityService
adb -s <serial> shell settings put secure accessibility_enabled 1
adb -s <serial> shell am start -n com.deviceagent/.MainActivity
adb -s <serial> forward tcp:<8765+device_index> tcp:8765
curl http://127.0.0.1:<8765+device_index>/health
```

The health response must report `accessibility: true`. Keep unstable phones in
`DEVICE_EXCLUDE`; do not silently reuse a phone already held by another run.

## Daily planning and execution

Legacy/stale Daily plans are generated first and reviewed before execution.
The current typed planner writes eight slots per campaign/location. The mixed
planner fields are deterministic: five `mode=type` and three `mode=voice`.
Voice execution is not enabled until the voice executor integration is tested.

```bash
python3 build_daily_eight.py --help
./run_daily_auto.sh YYYY-MM-DD
```

`run_daily_auto.sh` owns the fleet lock, refreshes remaining jobs, and retries
failed slots. Use `SKIP_BASE=1` only when resuming saved results. A run is
complete only when its remaining count is zero.

## Ranking

Build a complete due-set from the live catalog and ranking history before
starting ranking. The normal wrapper includes the cost-release gate:

```bash
./run_ranking_auto.sh YYYY-MM-DD stale
```

If the Admin catalog endpoint is unavailable, reconstruct the catalog snapshots
from the authorized RDS source only after verifying the row counts; never run
from a partial API response. The runner must show the correct `DATE`, cutoff,
keyword count, platform set, and warmup canary before the main queue starts.

## Consolidation

Backfill consolidation accepts only successful durable rows and deduplicates by
`backfill_slot_id`:

```bash
python3 tools/consolidate_daily_backfill.py PLAN.json \
  /absolute/path/daily-successes.csv
```

The generated `.report.json` must show `complete: true`, zero missing slots,
date-faithful timestamps, and the expected platform set. Sample/planned CSVs
must remain clearly named and must never be imported as successful execution.

## Parallel Mac minis

Each host uses the same fleet lease and must have a disjoint phone allow-list.
Do not start two runners against the same phone pool. Split plans by date or
explicit slot ranges, give each host a distinct `AUDIT_CSV`, and consolidate
only after both result sets are complete and deduplicated.

## Verification checklist

Before shipping a result:

1. `git status` contains no secrets or generated artifacts.
2. Every phone health check is reachable and accessibility-enabled.
3. The plan has the expected slot count and platform/mode split.
4. The runner reports remaining `0`.
5. CSV timestamps match their declared dates; errors are excluded from success
   imports.
