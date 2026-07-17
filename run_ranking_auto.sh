#!/bin/bash
# Autonomous ranking runner for any DATE/scope.
# Usage: ./run_ranking_auto.sh 2026-06-08 [never_ranked|stale|all_due]
# Builds the due-set (if not already), runs it RESIDENTIAL via the audit path with
# inline OCR screenshot validation, then loops re-running only errors/ocr_no_answer
# (RETRY_KEEP_NORANK=1 → success+no_rank are terminal) until 0 remain or no-progress.
set -u
cd /Users/seolocalph/projects/device-agent

DATE="${1:?usage: run_ranking_auto.sh <DATE> [scope]}"
SCOPE="${2:-never_ranked}"
KW_IDS="/tmp/ranking_kw_ids_${DATE}.json"
CSV="/Users/seolocalph/projects/device-agent/rabbitmq_audit_results_${DATE}_ranking.csv"
# append_row date-splits CSV into <base>_<rowdate>.csv — match all of them for retry diffing.
CSV_GLOB="/Users/seolocalph/projects/device-agent/rabbitmq_audit_results_${DATE}_ranking*.csv"
LOG="/private/tmp/ranking_auto_${DATE}.log"

export SSL_CERT_FILE=$(python3 -c "import certifi;print(certifi.where())")
_SECRET=$(aws secretsmanager get-secret-value --secret-id aeo-admin/prod --profile aeo-admin --region us-east-1 --query SecretString --output text)
export EXECUTOR_TOKEN=$(printf '%s' "$_SECRET" | python3 -c "import sys,json;print(json.load(sys.stdin).get('EXECUTOR_TOKEN',''))")
# build_ranking_dueset.py reads /api/ranking-reports, which is Bearer-gated.
export READ_API_TOKEN=$(printf '%s' "$_SECRET" | python3 -c "import sys,json;print(json.load(sys.stdin).get('READ_API_TOKEN',''))")
unset _SECRET
set -a; source .env.dev; set +a
# RANKING is RESIDENTIAL — .env.dev sets PROXY_PORT=7000 (mobile); force 10001.
export PROXY_HOST=gate.decodo.com PROXY_PORT=10001
export PROXY_BASE_USER=user-spmqebjuzf PROXY_PASSWORD="${DECODO_PASS:?set DECODO_PASS in .env.dev}" USE_SNI_RELAY=0
export DATE AUDIT_CSV="$CSV" KEYWORD_IDS_FILE="$KW_IDS"

# auto-detect live phones; ranking caps workers (router stability — the audit path
# does many more proxy handshakes/job than the daily, so keep this modest, default 6).
eval "$(python3 probe_phones.py 2>/tmp/probe_rank_${DATE}.log)"   # DOWN=... GOOD=N
export DEVICE_EXCLUDE="${DEVICE_EXCLUDE:-$DOWN}"
CAP="${WORKERS_CAP:-6}"
WORKERS=$(( GOOD < CAP ? GOOD : CAP )); export WORKERS
echo "[rank ${DATE}] $(date) START scope=$SCOPE WORKERS=$WORKERS DEVICE_EXCLUDE='${DEVICE_EXCLUDE:-none}'" | tee -a "$LOG"

# 1) build due-set if not present
if [ ! -f "$KW_IDS" ]; then
  echo "[rank ${DATE}] building due-set (scope=$SCOPE)…" | tee -a "$LOG"
  SCOPE="$SCOPE" python3 build_ranking_dueset.py >>"$LOG" 2>&1
fi
[ -f "$KW_IDS" ] || { echo "[rank ${DATE}] FATAL: no kw-ids file" | tee -a "$LOG"; exit 1; }
echo "[rank ${DATE}] kw-ids: $(python3 -c "import json;print(len(json.load(open('$KW_IDS'))))") keywords" | tee -a "$LOG"

# 2) clean proxies, base run
pkill -f "gost -C"; pkill -f sni_relay.py; sleep 1
pgrep -f reconnect_watcher >/dev/null || nohup ./reconnect_watcher.sh >/tmp/rw.log 2>&1 &
# SKIP_BASE=1 resumes an interrupted run: skip the full base wave so the retry loop
# runs ONLY the not-yet-good pairs (prior OCR-validated success+no_rank are preserved).
if [ "${SKIP_BASE:-0}" = "1" ]; then
  echo "[rank ${DATE}] SKIP_BASE=1 — resuming from saved results (no base wave)" | tee -a "$LOG"
else
  echo "[rank ${DATE}] base run…" | tee -a "$LOG"
  python3 -u run_ranking.py >>"$LOG" 2>&1
fi

# 3) retry loop: only errors/ocr_no_answer re-run (success+no_rank terminal)
prev=-1; stable=0; rem=0
for round in $(seq 1 40); do
  rem=$(EXCLUDE_SUCCESS="$CSV_GLOB" RETRY_KEEP_NORANK=1 DRY_RUN=1 python3 run_ranking.py 2>/dev/null | sed -n 's/.*would run \([0-9]*\) ranking.*/\1/p')
  rem="${rem:-0}"
  echo "[rank ${DATE} retry $round] $(date) remaining=$rem" | tee -a "$LOG"
  [ "$rem" -eq 0 ] && { echo "[rank ${DATE}] ALL DONE — 0 errors remaining" | tee -a "$LOG"; break; }
  if [ "$rem" -eq "$prev" ]; then stable=$((stable+1)); else stable=0; fi
  if [ "$stable" -ge 4 ]; then echo "[rank ${DATE}] NO PROGRESS 4 rounds at $rem — stopping for review" | tee -a "$LOG"; break; fi
  prev=$rem
  pkill -f "gost -C"; pkill -f sni_relay.py; sleep 1
  echo "[rank ${DATE} retry $round] re-running $rem errors…" | tee -a "$LOG"
  EXCLUDE_SUCCESS="$CSV_GLOB" RETRY_KEEP_NORANK=1 python3 -u run_ranking.py >>"$LOG" 2>&1
done
echo "[rank ${DATE}] $(date) FINISHED remaining=$rem  csv=$CSV" | tee -a "$LOG"
