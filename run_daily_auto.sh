#!/bin/bash
# Generic autonomous daily runner for any DATE.
# Usage: ./run_daily_auto.sh 2026-06-08
# Assumes the plan daily_plan_<DATE>.json already exists (built by the dashboard
# or build_daily_plan.py). Runs the base wave, then loops the REMAIN rebuild +
# rerun until 0 remaining (100%) or no-progress for 4 rounds.
set -u
cd /Users/seolocalph/projects/device-agent

DATE="${1:?usage: run_daily_auto.sh <DATE e.g. 2026-06-08>}"
PLAN="daily_plan_${DATE}.json"
REMAIN="daily_plan_${DATE}_REMAIN.json"
LOG="/private/tmp/daily_auto_${DATE}.log"

export SSL_CERT_FILE=$(python3 -c "import certifi;print(certifi.where())")
export EXECUTOR_TOKEN=$(aws secretsmanager get-secret-value --secret-id aeo-admin/prod --profile aeo-admin --region us-east-1 --query SecretString --output text | python3 -c "import sys,json;print(json.load(sys.stdin).get('EXECUTOR_TOKEN',''))")
set -a; source .env.dev; set +a
# RESIDENTIAL daily proxy (validated) + balanced/stable knobs
export PROXY_USER=user-spmqebjuzf PROXY_PASS='Klf0oAnRcz96Da=6fv' PROXY_HOST=gate.decodo.com PROXY_PORT=10001 USE_SNI_RELAY=0 PROXY_TARGET=country-us
export ONLY_ONLINE=1
# Auto-detect which phones are actually alive (adb + app health) and size the run
# to them — no stale hardcoded exclude list. Caller can still override by exporting
# DEVICE_EXCLUDE / MAX_PARALLEL before invoking.
if [ -z "${DEVICE_EXCLUDE:-}" ] || [ -z "${MAX_PARALLEL:-}" ]; then
  eval "$(python3 probe_phones.py 2>/tmp/probe_${DATE}.log)"   # sets DOWN=... GOOD=N
  export DEVICE_EXCLUDE="${DEVICE_EXCLUDE:-$DOWN}"
  export MAX_PARALLEL="${MAX_PARALLEL:-$GOOD}"
fi
echo "[daily ${DATE}] phones: MAX_PARALLEL=$MAX_PARALLEL  DEVICE_EXCLUDE='${DEVICE_EXCLUDE:-none}'" | tee -a "$LOG"

echo "[daily ${DATE}] $(date) START" | tee -a "$LOG"
if [ ! -f "$PLAN" ]; then echo "[daily ${DATE}] FATAL: $PLAN not found — build it first" | tee -a "$LOG"; exit 1; fi
echo "[daily ${DATE}] plan jobs: $(python3 -c "import json;print(json.load(open('$PLAN'))['total_jobs'])")" | tee -a "$LOG"

pkill -f "gost -C"; pkill -f sni_relay.py; sleep 1
pgrep -f reconnect_watcher >/dev/null || nohup ./reconnect_watcher.sh >/tmp/rw.log 2>&1 &
echo "[daily ${DATE}] base run..." | tee -a "$LOG"
python3 -u run_rolling_plan.py "$PLAN" >>"$LOG" 2>&1

prev=-1; stable=0; cnt=0
for round in $(seq 1 60); do
  cnt=$(python3 _build_remaining.py "$DATE" 2>>"$LOG")
  echo "[daily ${DATE} retry $round] $(date) remaining=$cnt" | tee -a "$LOG"
  if [ "$cnt" -eq 0 ]; then echo "[daily ${DATE}] ALL SUCCESS — 100%" | tee -a "$LOG"; break; fi
  if [ "$cnt" -eq "$prev" ]; then stable=$((stable+1)); else stable=0; fi
  if [ "$stable" -ge 4 ]; then echo "[daily ${DATE}] NO PROGRESS 4 rounds at $cnt — stopping for review" | tee -a "$LOG"; break; fi
  prev=$cnt
  pkill -f "gost -C"; pkill -f sni_relay.py; sleep 1
  pgrep -f reconnect_watcher >/dev/null || nohup ./reconnect_watcher.sh >/tmp/rw.log 2>&1 &
  echo "[daily ${DATE} retry $round] running $cnt jobs..." | tee -a "$LOG"
  python3 -u run_rolling_plan.py "$REMAIN" >>"$LOG" 2>&1
done
echo "[daily ${DATE}] $(date) FINISHED remaining=$cnt" | tee -a "$LOG"
