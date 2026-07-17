#!/bin/bash
# Stale backlog re-rank — ALL 3 platforms in ONE process so the fleet runs
# ChatGPT / Perplexity / Gemini simultaneously (Gemini via CDP, wipe-proof).
# Target = union of stale keywords from stale_as_of_2026-06-28.csv (1046 kw).
# device-106 (USB test phone) excluded. RETRY_KEEP_NORANK=1 → no_rank is a valid
# result (and the prompt now puts unranked businesses last), so only errors retry.
set -u
cd /Users/seolocalph/projects/device-agent
export PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:$PATH"
LOG=/private/tmp/rerank_stale_all_2026-06-28.log
log(){ echo "[stale-all $(date '+%F %T')] $*" | tee -a "$LOG"; }

set -a; source .env.dev; set +a
export SSL_CERT_FILE=$(python3 -c "import certifi;print(certifi.where())")
export EXECUTOR_TOKEN=$(aws secretsmanager get-secret-value --secret-id aeo-admin/prod --profile aeo-admin --region us-east-1 --query SecretString --output text | python3 -c "import sys,json;print(json.load(sys.stdin).get('EXECUTOR_TOKEN',''))")
export PROXY_PROVIDER=decodo PROXY_HOST=gate.decodo.com PROXY_PORT=10001 \
       PROXY_USER=user-spmqebjuzf PROXY_PASS="${DECODO_PASS:?set DECODO_PASS}" \
       PROXY_TARGET=country-us
# Gemini fix: the audit's GostManager reads PROXY_BASE_USER/PROXY_PASSWORD (not
# PROXY_USER/PROXY_PASS) and defaulted to the MOBILE account user-spknlt0736 +
# SNI relay — Google resets gemini.google.com on that path. The DAILY uses the
# RESIDENTIAL account user-spmqebjuzf with NO relay, which Gemini accepts (and
# ChatGPT/Perplexity work too). Match it: residential account + relay off.
export PROXY_BASE_USER=user-spmqebjuzf PROXY_PASSWORD="${DECODO_PASS}"
export USE_SNI_RELAY=0
export ONLY_ONLINE=1 DATE=2026-06-28 PLATFORMS=chatgpt,perplexity,gemini
export AEO_SKIP_PREFLIGHT=1
export KEYWORD_IDS_FILE=/tmp/rank_stale_all.json
export AUDIT_CSV="$PWD/rabbitmq_audit_results_2026-06-28_stale.csv"
export EXCLUDE_SUCCESS="$PWD/rabbitmq_audit_results_2026-06-28_stale*.csv"
export RETRY_KEEP_NORANK=1   # FRESH FULL RE-RUN (2026-06-30): no_rank is terminal (prompt puts unranked last) — only errors retry, else genuine no_rank would retry 5x
export GEMINI_RESET=0        # FRESH FULL RE-RUN: match the proven daily flow (residential acct + relay off already set) — no per-capture cookie reset
export DEVICE_EXCLUDE=device-106
export GEMINI_CDP_DEBUG=1     # surface cdp_js_frame (ChatGPT) + gemini CDP capture debug

python3 -c "import websocket" 2>/dev/null || { log "FATAL: websocket-client missing (needed for Gemini CDP)"; exit 1; }
[ -f "$KEYWORD_IDS_FILE" ] || { log "FATAL: target ids file missing ($KEYWORD_IDS_FILE)"; exit 1; }
log "starting stale re-rank — 1046 kw x chatgpt,perplexity,gemini(CDP), excl device-106"
for round in 1 2 3 4 5; do
  log "round $round (skips success+no_rank via EXCLUDE_SUCCESS)..."
  python3 -u run_ranking.py >>"$LOG" 2>&1
  if tail -25 "$LOG" | grep -q "nothing to run"; then log "no remaining jobs — complete after round $round"; break; fi
  pkill -f "gost -C" 2>/dev/null; sleep 2
done
log "STALE RE-RANK COMPLETE -> rabbitmq_audit_results_2026-06-28_stale*.csv"
