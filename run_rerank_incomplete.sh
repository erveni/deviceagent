#!/bin/bash
# Retry the ChatGPT/Perplexity ranking pairs that are still error/flow_failed/ocr
# after the geofix run (the stubborn proxy/phone-failure tail — device_pool_timeout,
# generation timeout, RemoteDisconnected — usually recoverable on a fresh attempt).
# Skips success+no_rank (RETRY_KEEP_NORANK=1) so ONLY the failures re-run. Appends
# to the geofix CSV family so re-consolidation picks up the resolved rows.
set -u
cd /Users/seolocalph/projects/device-agent
export PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:$PATH"
LOG=/private/tmp/rerank_incomplete_2026-06-28.log
log(){ echo "[rerank-incomplete $(date '+%F %T')] $*" | tee -a "$LOG"; }

set -a; source .env.dev; set +a
export SSL_CERT_FILE=$(python3 -c "import certifi;print(certifi.where())" 2>/dev/null)
export EXECUTOR_TOKEN=$(aws secretsmanager get-secret-value --secret-id aeo-admin/prod --profile aeo-admin --region us-east-1 --query SecretString --output text | python3 -c "import sys,json;print(json.load(sys.stdin).get('EXECUTOR_TOKEN',''))")
export PROXY_PROVIDER=decodo PROXY_HOST=gate.decodo.com PROXY_PORT=10001 \
       PROXY_USER=user-spmqebjuzf PROXY_PASS="${DECODO_PASS:?set DECODO_PASS}" \
       PROXY_BASE_USER=user-spmqebjuzf PROXY_PASSWORD="${DECODO_PASS}" \
       USE_SNI_RELAY=0 PROXY_TARGET=country-us
export ONLY_ONLINE=1 DATE=2026-06-27 PLATFORMS=chatgpt,perplexity
export AEO_SKIP_PREFLIGHT=1
# restore the retry target from backup if /tmp was cleared
[ -f /tmp/rank_retry_incomplete.json ] || cp -f rank_retry_incomplete.backup.json /tmp/rank_retry_incomplete.json
export KEYWORD_IDS_FILE=/tmp/rank_retry_incomplete.json
export AUDIT_CSV="$PWD/rabbitmq_audit_results_2026-06-27_geofix.csv"
export EXCLUDE_SUCCESS="$PWD/rabbitmq_audit_results_2026-06-2[678]_*.csv"
export RETRY_KEEP_NORANK=1   # success+no_rank are terminal — ONLY retry failures

n=$(python3 -c "import json;print(len(json.load(open('/tmp/rank_retry_incomplete.json'))))" 2>/dev/null)
log "retrying $n keywords' failed CP pairs..."
for round in 1 2 3 4 5; do
  log "round $round..."
  python3 -u run_ranking.py >>"$LOG" 2>&1
  if tail -25 "$LOG" | grep -q "nothing to run"; then log "all resolved — complete after round $round"; break; fi
  pkill -f "gost -C" 2>/dev/null; sleep 2
done
log "INCOMPLETE RETRY COMPLETE -> appended to geofix CSV family"
