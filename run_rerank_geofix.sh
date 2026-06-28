#!/bin/bash
# Geo-fix re-rank: re-rank every NON-success (kw,platform) pair from the v928 run
# with the _city_to_zip geo fix (zip-less businesses now audit from their OWN
# city instead of the state's single default zip). Skips the 162 confirmed
# successes via EXCLUDE_SUCCESS; RETRY_KEEP_NORANK is UNSET so no_rank rows DO
# re-run (that's the whole point — most were false no_rank from wrong-city geo).
# device-106 (USB test phone) excluded so it stays free for Gemini testing.
set -u
cd /Users/seolocalph/projects/device-agent
export PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:$PATH"
LOG=/private/tmp/rerank_geofix_2026-06-27.log
log(){ echo "[rerank-geofix $(date '+%F %T')] $*" | tee -a "$LOG"; }

set -a; source .env.dev; set +a
export SSL_CERT_FILE=$(python3 -c "import certifi;print(certifi.where())")
export EXECUTOR_TOKEN=$(aws secretsmanager get-secret-value --secret-id aeo-admin/prod --profile aeo-admin --region us-east-1 --query SecretString --output text | python3 -c "import sys,json;print(json.load(sys.stdin).get('EXECUTOR_TOKEN',''))")
export PROXY_PROVIDER=decodo PROXY_HOST=gate.decodo.com PROXY_PORT=10001 \
       PROXY_USER=user-spmqebjuzf PROXY_PASS="${DECODO_PASS:?set DECODO_PASS}" \
       PROXY_BASE_USER=user-spmqebjuzf PROXY_PASSWORD="${DECODO_PASS}" \
       USE_SNI_RELAY=0 PROXY_TARGET=country-us
export ONLY_ONLINE=1 DATE=2026-06-27 PLATFORMS=chatgpt,perplexity
export AEO_SKIP_PREFLIGHT=1
export KEYWORD_IDS_FILE=/tmp/rank_target_rankable.json
export AUDIT_CSV="$PWD/rabbitmq_audit_results_2026-06-27_geofix.csv"
# Skip successes from BOTH the v928 run and this geofix run (across rounds).
export EXCLUDE_SUCCESS="$PWD/rabbitmq_audit_results_2026-06-2[67]_*.csv"
# RETRY_KEEP_NORANK intentionally UNSET → no_rank pairs re-run with the geo fix.
export DEVICE_EXCLUDE=device-106

[ -f "$KEYWORD_IDS_FILE" ] || { log "FATAL: target ids file missing ($KEYWORD_IDS_FILE)"; exit 1; }
log "starting geo-fix re-rank — non-success pairs x chatgpt,perplexity, excl device-106"
for round in 1 2 3 4 5; do
  log "round $round (skips successes via EXCLUDE_SUCCESS)..."
  python3 -u run_ranking.py >>"$LOG" 2>&1
  if tail -25 "$LOG" | grep -q "nothing to run"; then log "no remaining jobs — complete after round $round"; break; fi
  pkill -f "gost -C" 2>/dev/null; sleep 2
done
log "GEO-FIX RE-RANK COMPLETE -> rabbitmq_audit_results_2026-06-27_geofix*.csv"
