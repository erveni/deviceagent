#!/bin/bash
# Measure Evomi MB/job for ranking, per platform, once the fleet is free.
#
# Ranking is documented at ~34MB/job against the daily's 2.2MB, and finishing the
# current stale set (3287 jobs) would cost ~109GB — more than any balance on hand. So
# measure where that goes BEFORE buying traffic: read the Evomi balance, run a small
# segment per platform reading the balance between each, and report MB/job.
#
# Retries are OFF (run_ranking.py directly, not run_ranking_auto.sh). That is the point:
# it isolates the cost of ONE clean pass, so comparing the result against the documented
# 34MB shows how much of the real figure is retry amplification rather than the capture.
#
# Waits for the daily first — it runs on Evomi too and would contaminate the reading.
set -u
cd /Users/seolocalph/projects/device-agent

PER_PLATFORM="${PER_PLATFORM:-7}"
LOG="${LOG:-/private/tmp/ranking_cost_measure.log}"
KW="/tmp/ranking_cost_kw_ids.json"
CSV="/Users/seolocalph/projects/device-agent/rabbitmq_audit_results_costmeasure.csv"
MAX_WAIT_S="${MAX_WAIT_S:-43200}"   # 12h ceiling

say(){ echo "[cost $(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }
balance(){ python3 ./evomi_balance.py 2>/dev/null | tr -dc '0-9.'; }

say "waiting for the daily to finish (it also draws Evomi)"
waited=0
while [ "$waited" -lt "$MAX_WAIT_S" ]; do
  busy=0
  pgrep -f "run_rolling_plan.py" >/dev/null 2>&1 && busy=1
  pgrep -f "daily_full_auto.sh" >/dev/null 2>&1 && busy=1
  pgrep -f "run_daily_auto.sh" >/dev/null 2>&1 && busy=1
  [ -f /tmp/fleet.lock ] && busy=1
  [ "$busy" -eq 0 ] && break
  sleep 60
  waited=$((waited + 60))
done
[ "$waited" -ge "$MAX_WAIT_S" ] && { say "gave up waiting after ${MAX_WAIT_S}s"; exit 1; }
say "fleet idle after ${waited}s — settling"
sleep 120

_SECRET=$(aws secretsmanager get-secret-value --secret-id aeo-admin/prod --profile aeo-admin \
          --region us-east-1 --query SecretString --output text 2>/dev/null)
export EXECUTOR_TOKEN=$(printf '%s' "$_SECRET" | python3 -c "import sys,json;print(json.load(sys.stdin).get('EXECUTOR_TOKEN',''))")
export READ_API_TOKEN=$(printf '%s' "$_SECRET" | python3 -c "import sys,json;print(json.load(sys.stdin).get('READ_API_TOKEN',''))")
unset _SECRET
export SSL_CERT_FILE=$(python3 -c "import certifi;print(certifi.where())")

set -a; . ./.env.dev; set +a
export PROXY_PROVIDER=evomi
export PROXY_HOST=core-residential.evomi.com PROXY_PORT=1000 USE_SNI_RELAY=0 ONLY_ONLINE=1
export PROXY_BASE_USER="${EVOMI_USER:?set EVOMI_USER in .env.dev}"
export PROXY_PASSWORD="${EVOMI_PASS:?set EVOMI_PASS in .env.dev}"
export DATE=2026-09-02 AUDIT_CSV="$CSV" WORKERS=5

# Keywords that have NOT already succeeded, so the segment does real work.
python3 - "$PER_PLATFORM" > "$KW" <<'PY'
import csv, glob, json, sys
done = set()
for f in glob.glob("rabbitmq_audit_results_2026-09-02_ranking*.csv"):
    for r in csv.DictReader(open(f)):
        if r.get("status") == "success":
            done.add(str(r.get("keyword_id") or r.get("keyword")))
ids = [k for k in json.load(open("/tmp/ranking_kw_ids_2026-09-02.json")) if str(k) not in done]
json.dump(ids[: int(sys.argv[1])], sys.stdout)
PY
say "measuring $PER_PLATFORM keywords per platform (retries OFF)"

start=$(balance)
say "Evomi start: ${start} MB"
prev="$start"
for plat in chatgpt gemini copilot; do
  PLATFORMS="$plat" KEYWORD_IDS_FILE="$KW" python3 -u run_ranking.py >>"$LOG" 2>&1
  now=$(balance)
  used=$(python3 -c "print(round(float('$prev')-float('$now'),2))")
  n=$(python3 -c "
import csv, os
p = '$CSV'
rows = list(csv.DictReader(open(p))) if os.path.exists(p) else []
print(sum(1 for r in rows if r.get('platform') == '$plat'))" 2>/dev/null || echo 0)
  per=$(python3 -c "print(round($used / max($n, 1), 2))")
  say "$plat: ${used} MB over ${n} jobs = ${per} MB/job"
  prev="$now"
done
total=$(python3 -c "print(round(float('$start') - float('$prev'), 2))")
say "TOTAL ${total} MB  (documented figure is ~34 MB/job WITH retries)"
say "done — log: $LOG"
