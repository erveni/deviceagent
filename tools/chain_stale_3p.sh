#!/bin/bash
# Run per-date three-platform stale plans sequentially.
set -u
cd /Users/seolocalph/projects/device-agent

while ps -axo command | awk '$0 ~ /bash \.\/run_daily_auto\.sh 2026-09-09$/ { found=1 } END { exit !found }'; do
  sleep 20
done

for n in 10 11 12 13 14; do
  day="2026-09-${n}"
  PROXY_PROVIDER=evomi \
  DAILY_PLAN_PATH="/tmp/all_campaign_stale_3p_${day}.json" \
  DAILY_REMAIN_PATH="/tmp/all_campaign_stale_3p_${day}_REMAIN.json" \
  DAILY_RESULTS_GLOB="/tmp/all_campaign_stale_3p_${day}*results*.csv" \
  DAILY_MAX_ROUNDS=60 ONLY_ONLINE=1 MAX_PARALLEL=24 \
    bash ./run_daily_auto.sh "$day" >>"/private/tmp/all_campaign_stale_3p_${day}_supervisor.log" 2>&1 || true
done
