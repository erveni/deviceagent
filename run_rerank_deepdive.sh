#!/bin/bash
# Deep-dive re-rank (v0.9.31-top10-deepdive on the fleet): re-rank EVERY
# non-success (kw,platform) pair — the failures (Citedlogic now has geo, plus
# transient input/gen-timeout recovered over rounds) AND the no_rank rows
# (re-checked with the deeper prompt: does the business rank beyond the top-10 /
# "next page"?). RETRY_KEEP_NORANK is UNSET so no_rank re-runs. Still-0 results
# get recorded as last place (Y+1) at the consolidate step. device-106 excluded.
set -u
cd /Users/seolocalph/projects/device-agent
export PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:$PATH"
LOG=/private/tmp/rerank_deepdive_2026-06-28.log
log(){ echo "[deepdive $(date '+%F %T')] $*" | tee -a "$LOG"; }

set -a; source .env.dev; set +a
export SSL_CERT_FILE=$(python3 -c "import certifi;print(certifi.where())")
export EXECUTOR_TOKEN=$(aws secretsmanager get-secret-value --secret-id aeo-admin/prod --profile aeo-admin --region us-east-1 --query SecretString --output text | python3 -c "import sys,json;print(json.load(sys.stdin).get('EXECUTOR_TOKEN',''))")
export PROXY_PROVIDER=decodo PROXY_HOST=gate.decodo.com PROXY_PORT=10001 \
       PROXY_USER=user-spmqebjuzf PROXY_PASS="${DECODO_PASS:?set DECODO_PASS}" \
       PROXY_BASE_USER=user-spmqebjuzf PROXY_PASSWORD="${DECODO_PASS}" \
       USE_SNI_RELAY=0 PROXY_TARGET=country-us
export ONLY_ONLINE=1 DATE=2026-06-28 PLATFORMS=chatgpt,perplexity
export AEO_SKIP_PREFLIGHT=1
export KEYWORD_IDS_FILE=/tmp/rank_target_rankable.json
export AUDIT_CSV="$PWD/rabbitmq_audit_results_2026-06-28_deepdive.csv"
# Skip only confirmed successes (from v928/geofix/this run); re-rank failures AND no_rank.
export EXCLUDE_SUCCESS="$PWD/rabbitmq_audit_results_2026-06-2[678]_*.csv"
# RETRY_KEEP_NORANK intentionally UNSET → no_rank pairs re-run with the deep-dive prompt.
export DEVICE_EXCLUDE=device-106

[ -f "$KEYWORD_IDS_FILE" ] || { log "FATAL: target ids file missing ($KEYWORD_IDS_FILE)"; exit 1; }
log "starting deep-dive re-rank — all non-success pairs x chatgpt,perplexity, excl device-106"
for round in 1 2 3 4 5; do
  log "round $round (skips successes via EXCLUDE_SUCCESS)..."
  python3 -u run_ranking.py >>"$LOG" 2>&1
  if tail -25 "$LOG" | grep -q "nothing to run"; then log "no remaining jobs — complete after round $round"; break; fi
  pkill -f "gost -C" 2>/dev/null; sleep 2
done
log "DEEP-DIVE RE-RANK COMPLETE -> rabbitmq_audit_results_2026-06-28_deepdive*.csv"
