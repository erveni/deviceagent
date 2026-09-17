#!/bin/bash
# Generic autonomous daily runner for any DATE.
# Usage: ./run_daily_auto.sh 2026-06-08
# Assumes the plan daily_plan_<DATE>.json already exists (built by the dashboard
# or build_daily_plan.py). Runs the base wave, then loops the REMAIN rebuild +
# rerun until 0 remaining (100%) or no-progress for 4 rounds.
set -u
cd /Users/seolocalph/projects/device-agent

DATE="${1:?usage: run_daily_auto.sh <DATE e.g. 2026-06-08>}"
PLAN="${DAILY_PLAN_PATH:-daily_plan_${DATE}.json}"
REMAIN="${DAILY_REMAIN_PATH:-daily_plan_${DATE}_REMAIN.json}"
export DAILY_PLAN_PATH="$PLAN" DAILY_REMAIN_PATH="$REMAIN"
LOG="/private/tmp/daily_auto_${DATE}.log"

# New typed plans always resume from successful slot IDs, including on the first
# invocation. Never replay a completed base wave when an operator restarts this.
EIGHT_DAILY=$(python3 -c "import json,sys; print(int(json.load(open(sys.argv[1])).get('daily_protocol') in ('eight-v1','daily-backfill-v1')))" "$PLAN") || exit 2
if [ "$EIGHT_DAILY" = "1" ]; then
  export SKIP_BASE=1 ROLLING_RETRY=0
  DAILY_MAX_ROUNDS="${DAILY_MAX_ROUNDS:-3}"
else
  DAILY_MAX_ROUNDS="${DAILY_MAX_ROUNDS:-60}"
fi
case "$DAILY_MAX_ROUNDS" in
  ''|*[!0-9]*|0) echo "DAILY_MAX_ROUNDS must be a positive integer" >&2; exit 2 ;;
esac

export SSL_CERT_FILE=$(python3 -c "import certifi;print(certifi.where())")
export EXECUTOR_TOKEN=$(aws secretsmanager get-secret-value --secret-id aeo-admin/prod --profile aeo-admin --region us-east-1 --query SecretString --output text | python3 -c "import sys,json;print(json.load(sys.stdin).get('EXECUTOR_TOKEN',''))")
_ov_provider="${PROXY_PROVIDER:-}"   # a caller-exported provider wins over .env.dev
set -a; source .env.dev; set +a
[ -n "$_ov_provider" ] && export PROXY_PROVIDER="$_ov_provider"
if [ "$EIGHT_DAILY" = "1" ]; then
  export SKIP_BASE=1 ROLLING_RETRY=0
  export DAILY_BUDGET_MB="${DAILY_BUDGET_MB:-12000}"
  export DAILY_BALANCE_FLOOR_MB="${DAILY_BALANCE_FLOOR_MB:-9000}"
  export DAILY_METER_LEDGER="${DAILY_METER_LEDGER:-daily_meter_${DATE}.jsonl}"
fi
# RESIDENTIAL daily proxy. Default Decodo; set PROXY_PROVIDER=dataimpulse in .env.dev
# to switch to the DataImpulse gateway (TEMPORARY, while Decodo funding). Runs AFTER
# the .env.dev source so it wins over stale proxy host/port. Note: DataImpulse only
# targets country-US (no per-zip), so geo is coarser than Decodo's zip targeting.
if [ "${PROXY_PROVIDER:-decodo}" = "dataimpulse" ]; then
  export PROXY_PROVIDER=dataimpulse \
         PROXY_HOST=gw.dataimpulse.com PROXY_PORT=823 \
         PROXY_USER="${DATAIMPULSE_USER:?set DATAIMPULSE_USER in .env.dev (gitignored)}" \
         PROXY_PASS="${DATAIMPULSE_PASS:?set DATAIMPULSE_PASS in .env.dev (gitignored)}" \
         USE_SNI_RELAY=0 PROXY_TARGET=country-us
  echo "[daily ${DATE}] proxy: DataImpulse (TEMPORARY — Decodo funding)" | tee -a "$LOG"
elif [ "${PROXY_PROVIDER:-decodo}" = "evomi" ]; then
  # Evomi residential via HTTP endpoint :1000 (gost http connector, like Rayobyte);
  # targeting + sticky session go in the password (_country-US_session-<sid>). State-
  # level only (no zip) — fine for the daily, which targets country-US. ~$0.49/GB.
  export PROXY_PROVIDER=evomi \
         PROXY_HOST=core-residential.evomi.com PROXY_PORT=1000 \
         PROXY_USER="${EVOMI_USER:?set EVOMI_USER in .env.dev (gitignored)}" \
         PROXY_PASS="${EVOMI_PASS:?set EVOMI_PASS in .env.dev (gitignored)}" \
         USE_SNI_RELAY=0 PROXY_TARGET=country-us
  echo "[daily ${DATE}] proxy: Evomi (HTTP :1000, state-level, ~\$0.49/GB)" | tee -a "$LOG"
elif [ "${PROXY_PROVIDER:-decodo}" = "rayobyte" ]; then
  # Rayobyte residential via HTTP endpoint :8000 (gost uses an http connector for it);
  # targeting + sticky session go in the password. TRIAL creds — watch bandwidth.
  export PROXY_PROVIDER=rayobyte \
         PROXY_HOST=la.residential.rayobyte.com PROXY_PORT=8000 \
         PROXY_USER="${RAYOBYTE_USER:?set RAYOBYTE_USER in .env.dev (gitignored)}" \
         PROXY_PASS="${RAYOBYTE_PASS:?set RAYOBYTE_PASS in .env.dev (gitignored)}" \
         USE_SNI_RELAY=0 PROXY_TARGET=country-us
  echo "[daily ${DATE}] proxy: Rayobyte (HTTP :8000, TRIAL)" | tee -a "$LOG"
else
  export PROXY_PROVIDER=decodo \
         PROXY_HOST=gate.decodo.com PROXY_PORT=10001 \
         PROXY_USER=user-spmqebjuzf \
         PROXY_PASS="${DECODO_PASS:?set DECODO_PASS in .env.dev (gitignored) — never hardcode}" \
         USE_SNI_RELAY=0 PROXY_TARGET=country-us
  echo "[daily ${DATE}] proxy: Decodo residential (gate.decodo.com:10001)" | tee -a "$LOG"
fi
export ONLY_ONLINE=1
# Auto-detect which phones are actually alive (adb + app health) and size the run
# to them — no stale hardcoded exclude list. Caller can still override by exporting
# DEVICE_EXCLUDE / MAX_PARALLEL before invoking.
if [ -z "${DEVICE_EXCLUDE:-}" ] || [ -z "${MAX_PARALLEL:-}" ]; then
  eval "$(python3 probe_phones.py 2>/tmp/probe_${DATE}.log | grep -E '^(DOWN|GOOD)=')"
  export DEVICE_EXCLUDE="${DEVICE_EXCLUDE:-$DOWN}"
  export MAX_PARALLEL="${MAX_PARALLEL:-$GOOD}"
fi
# Test phone125 and repeatedly failing108 are not release candidates.
if [ "$EIGHT_DAILY" = "1" ]; then export DEVICE_EXCLUDE="${DEVICE_EXCLUDE:+$DEVICE_EXCLUDE,}device-108,device-125"; fi
echo "[daily ${DATE}] phones: MAX_PARALLEL=$MAX_PARALLEL  DEVICE_EXCLUDE='${DEVICE_EXCLUDE:-none}'" | tee -a "$LOG"

echo "[daily ${DATE}] $(date) START" | tee -a "$LOG"
if [ ! -f "$PLAN" ]; then echo "[daily ${DATE}] FATAL: $PLAN not found — build it first" | tee -a "$LOG"; exit 1; fi
echo "[daily ${DATE}] plan jobs: $(python3 -c "import json;print(json.load(open('$PLAN'))['total_jobs'])")" | tee -a "$LOG"

# Fleet mutex: block until any other daily/ranking run frees the fleet, then hold it
# for this whole run. Closes the gate race where the 20:00 auto-daily slipped past
# daily_full_auto's pgrep check during a resumed run's REMAIN-round gaps (2026-08-21).
source ./_fleet_lock.sh
fleet_lock_acquire "daily-${DATE}"   # NOT piped: a pipe subshell would fire the EXIT-release early

pkill -f "gost -C"; pkill -f sni_relay.py; sleep 1
pgrep -f reconnect_watcher >/dev/null || nohup ./reconnect_watcher.sh >/tmp/rw.log 2>&1 &
# SKIP_BASE=1 resumes an interrupted run: skip the full-plan base wave so the retry
# loop runs ONLY the REMAIN set (already-successful pairs are preserved, not redone).
if [ "${SKIP_BASE:-0}" = "1" ]; then
  echo "[daily ${DATE}] SKIP_BASE=1 — resuming from saved results (no base wave)" | tee -a "$LOG"
else
  echo "[daily ${DATE}] base run..." | tee -a "$LOG"
  python3 -u run_rolling_plan.py "$PLAN" >>"$LOG" 2>&1
fi

prev=-1; stable=0; cnt=0
for round in $(seq 1 "$DAILY_MAX_ROUNDS"); do
  cnt=$(python3 _build_remaining.py "$DATE" 2>>"$LOG") || { echo "Daily reconciliation failed; no retry launched" >&2; exit 2; }
  echo "[daily ${DATE} retry $round] $(date) remaining=$cnt" | tee -a "$LOG"
  if [ "$cnt" -eq 0 ]; then echo "[daily ${DATE}] ALL SUCCESS — 100%" | tee -a "$LOG"; break; fi
  if [ "$cnt" -eq "$prev" ]; then stable=$((stable+1)); else stable=0; fi
  if [ "$stable" -ge 4 ]; then echo "[daily ${DATE}] NO PROGRESS 4 rounds at $cnt — stopping for review" | tee -a "$LOG"; break; fi
  prev=$cnt
  pkill -f "gost -C"; pkill -f sni_relay.py; sleep 1
  pgrep -f reconnect_watcher >/dev/null || nohup ./reconnect_watcher.sh >/tmp/rw.log 2>&1 &
  echo "[daily ${DATE} retry $round] running $cnt jobs..." | tee -a "$LOG"
  python3 -u run_rolling_plan.py "$REMAIN" >>"$LOG" 2>&1
  run_rc=$?
  if [ "$EIGHT_DAILY" = "1" ] && [ "$run_rc" -ne 0 ]; then
    # A rolling wave can return non-zero when one or more transient dispatches
    # fail.  Keep the supervisor alive: _build_remaining below is the source of
    # truth and the next round must retry those slots.  Exiting here was the
    # reason interrupted stale runs were left half-finished.
    echo "Daily wave returned status $run_rc; preserving results and continuing retry loop" | tee -a "$LOG"
  fi
done
# Reconcile after the final attempt too; the pre-attempt count is not final.
cnt=$(python3 _build_remaining.py "$DATE" 2>>"$LOG") || exit 2
echo "[daily ${DATE}] $(date) FINISHED remaining=$cnt" | tee -a "$LOG"
if [ "$EIGHT_DAILY" = "1" ] && [ "$cnt" -ne 0 ]; then
  echo "[daily ${DATE}] INCOMPLETE: bounded retries exhausted; preserve results and review" | tee -a "$LOG"
  exit 3
fi
