#!/bin/bash
# Run rankings for the 336 stale/never-ranked keywords (all plan types) x 3
# platforms (~1008 jobs), with retry rounds. Rollout of v0.9.24 already done.
# Excludes flaky device-117 and the USB test phone (device-106 is unauthorized,
# so ONLY_ONLINE skips it). Uses the 3.14 framework python (has certifi; the
# project's tested interpreter) so spawned `python3` subprocesses match.
set -u
cd /Users/seolocalph/projects/device-agent
export PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:$PATH"
LOG=/private/tmp/stale_rank_2026-06-25.log
log(){ echo "[stale-rank $(date '+%F %T')] $*" | tee -a "$LOG"; }

set -a; source .env.dev; set +a
export SSL_CERT_FILE=$(python3 -c "import certifi;print(certifi.where())")
export EXECUTOR_TOKEN=$(aws secretsmanager get-secret-value --secret-id aeo-admin/prod --profile aeo-admin --region us-east-1 --query SecretString --output text | python3 -c "import sys,json;print(json.load(sys.stdin).get('EXECUTOR_TOKEN',''))")
export PROXY_PROVIDER=decodo PROXY_HOST=gate.decodo.com PROXY_PORT=10001 \
       PROXY_USER=user-spmqebjuzf PROXY_PASS="${DECODO_PASS:?set DECODO_PASS}" \
       USE_SNI_RELAY=1 PROXY_TARGET=country-us
export ONLY_ONLINE=1 DEVICE_EXCLUDE=device-117 DATE=2026-06-25 PLATFORMS=chatgpt,gemini,perplexity
export AEO_SKIP_PREFLIGHT=1   # kill per-job preflight curl (Decodo session-churn / rc=28 source)
# Only the RANKABLE subset (120 kw with usable address+url); the other 216
# targets lack business address/URL in AEOAdmin and can't be audit-ranked.
export KEYWORD_IDS_FILE=/tmp/rank_target_rankable.json
export AUDIT_CSV="$PWD/rabbitmq_audit_results_2026-06-25_rankable.csv"
export EXCLUDE_SUCCESS="$PWD/rabbitmq_audit_results_2026-06-25_rankable*.csv"
export RETRY_KEEP_NORANK=1

[ -f "$KEYWORD_IDS_FILE" ] || { log "FATAL: target ids file missing ($KEYWORD_IDS_FILE)"; exit 1; }
log "starting stale/never ranking — 336 kw x 3 platforms (~1008 jobs), excl device-117"
for round in 1 2 3 4 5; do
  log "round $round (skips already-successful via EXCLUDE_SUCCESS)..."
  python3 -u run_ranking.py >>"$LOG" 2>&1
  if tail -25 "$LOG" | grep -q "nothing to run"; then log "no remaining jobs — complete after round $round"; break; fi
  pkill -f "gost -C" 2>/dev/null; sleep 2
done
log "STALE RANKING COMPLETE -> rabbitmq_audit_results_2026-06-25_stale_full*.csv"