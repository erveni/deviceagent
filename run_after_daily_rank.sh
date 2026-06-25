#!/bin/bash
# Deferred orchestrator: after the Jun-24 daily finishes ->
#   1) roll out APK v0.9.24 (gen-timeout 240s + chatgpt send fix) to the fleet
#   2) run rankings for the 336 stale/never-ranked keywords (all plan types),
#      all 3 platforms (~1008 jobs), with retry rounds (skip already-successful).
# Ranking REQUIRES the chatgpt fix on the fleet, so it only runs if the rollout
# succeeds (rollout aborts if the first phone doesn't come up clean).
set -u
cd /Users/seolocalph/projects/device-agent
LOG=/private/tmp/after_daily_rank.log
log(){ echo "[after-daily $(date '+%F %T')] $*" | tee -a "$LOG"; }

# 1) wait for the Jun-24 daily to finish
log "waiting for Jun-24 daily to finish..."
while pgrep -f "run_daily_mixed.sh 2026-06-24" >/dev/null 2>&1 || pgrep -f "run_with_proxy.py daily_plan_2026-06-24" >/dev/null 2>&1; do
  sleep 60
done
log "daily finished."

# 2) roll out v0.9.24 to the fleet (fleet_rollout re-checks daily=done, installs,
#    verifies per phone, aborts if the first phone is not clean)
log "rolling out APK v0.9.24 to the fleet..."
./fleet_rollout_v923.sh >>"$LOG" 2>&1
rc=$?
log "rollout exit=$rc"
if [ "$rc" -ne 0 ]; then
  log "ROLLOUT ABORTED — NOT running ranking (fleet may lack the chatgpt fix). Investigate, then run ranking manually."
  exit 1
fi

# 3) ranking run — 336 stale/never-ranked kw x 3 platforms, with retry rounds
set -a; source .env.dev; set +a
export SSL_CERT_FILE=$(python3 -c "import certifi;print(certifi.where())")
export EXECUTOR_TOKEN=$(aws secretsmanager get-secret-value --secret-id aeo-admin/prod --profile aeo-admin --region us-east-1 --query SecretString --output text | python3 -c "import sys,json;print(json.load(sys.stdin).get('EXECUTOR_TOKEN',''))")
export PROXY_PROVIDER=decodo PROXY_HOST=gate.decodo.com PROXY_PORT=10001 \
       PROXY_USER=user-spmqebjuzf PROXY_PASS="${DECODO_PASS:?set DECODO_PASS}" \
       USE_SNI_RELAY=0 PROXY_TARGET=country-us
export ONLY_ONLINE=1 DATE=2026-06-25 PLATFORMS=chatgpt,gemini,perplexity
export KEYWORD_IDS_FILE=/tmp/rank_target_kwids.json
export AUDIT_CSV="$PWD/rabbitmq_audit_results_2026-06-25_stale_full.csv"
export EXCLUDE_SUCCESS="$PWD/rabbitmq_audit_results_2026-06-25_stale_full*.csv"
export RETRY_KEEP_NORANK=1   # no_rank is terminal for INITIAL_RANKING (don't loop forever)

for round in 1 2 3 4; do
  log "ranking round $round (skips already-successful via EXCLUDE_SUCCESS)..."
  python3 -u run_ranking.py >>"$LOG" 2>&1
  # stop if nothing left to run (run_ranking prints 'nothing to run' and exits 0)
  if grep -q "nothing to run" <(tail -40 "$LOG"); then log "no remaining jobs — done after round $round"; break; fi
done
log "RANKING COMPLETE. results -> rabbitmq_audit_results_2026-06-25_stale_full*.csv"
