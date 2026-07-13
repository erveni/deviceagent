#!/bin/bash
# 764-corrections re-capture. Fresh captures for the FABRICATED_BAD_RANK (549) +
# MISSING_SCREENSHOT (215) backlog -> 565 mapped records -> 498 (kw_id,platform)
# captures (199 archived keywords SKIPPED per user 2026-07-12). Per-platform
# frozen-id run; geo fixes (kw_geo_override + make_job_record fallback) live.
# Afterward: back-date each capture to ALL its dates in /tmp/corr764_captures.json
# via consolidate_ranking.py (USE_14DAY=0), validate, then ship.
set -u
cd /Users/seolocalph/projects/device-agent
export PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:$PATH"
LOG=/private/tmp/corr764.log
log(){ echo "[corr764 $(date '+%F %T')] $*" | tee -a "$LOG"; }

set -a; source .env.dev; set +a
export SSL_CERT_FILE=$(python3 -c "import certifi;print(certifi.where())")
export PROXY_PROVIDER=decodo PROXY_HOST=gate.decodo.com PROXY_PORT=10001 \
       PROXY_USER=user-spmqebjuzf PROXY_PASS="${DECODO_PASS:?set DECODO_PASS}" \
       PROXY_TARGET=country-us
export PROXY_BASE_USER=user-spmqebjuzf PROXY_PASSWORD="${DECODO_PASS}"
export USE_SNI_RELAY=0
export ONLY_ONLINE=1 DATE=2026-07-12
export AEO_SKIP_PREFLIGHT=1
export AUDIT_CSV="$PWD/rabbitmq_audit_results_corr764.csv"
export EXCLUDE_SUCCESS="$PWD/rabbitmq_audit_results_corr764*.csv"
export RETRY_KEEP_NORANK=1 GEMINI_RESET=0
export GEMINI_CDP_DEBUG=1

python3 -c "import websocket" 2>/dev/null || { log "FATAL: websocket-client missing"; exit 1; }

for plat in perplexity chatgpt gemini; do
  export PLATFORMS=$plat
  export KEYWORD_IDS_FILE=/tmp/corr764_kwids_$plat.json
  [ -f "$KEYWORD_IDS_FILE" ] || { log "SKIP $plat: $KEYWORD_IDS_FILE missing"; continue; }
  for round in 1 2 3; do
    log "corr764 $plat round $round..."
    python3 -u run_ranking.py >>"$LOG" 2>&1
    if tail -25 "$LOG" | grep -q "nothing to run"; then log "$plat complete after round $round"; break; fi
    pkill -f "gost -C" 2>/dev/null; sleep 2
  done
done
log "CORR764 ALL COMPLETE -> rabbitmq_audit_results_corr764*.csv"
