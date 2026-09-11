#!/bin/bash
# Resume the preserved 2026-09-02 stale ranking before any 2026-09-10 daily.
# Durable and fail-closed: the daily LaunchAgent stays disabled; ranking stops at
# the reserved daily balance floor and requires explicit review before daily.
set -u
export PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
cd /Users/seolocalph/projects/device-agent || exit 1

DATE=2026-09-02
FLOOR_MB="${FLOOR_MB:-9000}"
LOG="$PWD/stale_before_sep10_daily.log"
MARK="$PWD/.stale_${DATE}_complete"
KW_DATE_MAP="$PWD/stale_${DATE}_last_rank_by_keyword.json"
PP_DATE_MAP="$PWD/stale_${DATE}_last_rank_by_platform.json"
CATALOG_DIR="$PWD/_snapshots_2026-09-02"
KW_IDS="$CATALOG_DIR/ranking_kw_ids_${DATE}.json"
ROLLOUT_DEVICES=device-103,device-104,device-106,device-108,device-109,device-110,device-113,device-116,device-117,device-118,device-119,device-120,device-121,device-122,device-123
EXCLUDES=device-101,device-102,device-105,device-107,device-111,device-112,device-114,device-115,device-124,device-125

say(){ echo "[stale-before-daily $(date '+%F %T')] $*" | tee -a "$LOG"; }
balance(){ python3 evomi_balance.py 2>/dev/null | tr -d '\r'; }
stop_tree(){
  local root="$1" children child
  children=$(pgrep -P "$root" 2>/dev/null || true)
  for child in $children; do stop_tree "$child"; done
  kill -TERM "$root" 2>/dev/null || true
}

# The user's ordering is an invariant, including across reboots.
launchctl disable "gui/$(id -u)/com.deviceagent.dailyfull" 2>/dev/null || true
launchctl bootout "gui/$(id -u)/com.deviceagent.dailyfull" 2>/dev/null || true
[ -f "$MARK" ] && { say "stale already complete; September 10 daily remains held for review"; exit 0; }
[ -s "$CATALOG_DIR/biz_admin.json" ] && [ -s "$CATALOG_DIR/kw_admin.json" ] && \
  [ -s "$CATALOG_DIR/rr_admin.json" ] && [ -s "$KW_IDS" ] || {
  say "FATAL: durable September2 ranking snapshot is incomplete"; exit 1;
}

# Freeze dates from records strictly before the historical run label. These files
# survive /tmp cleanup and must never be rebuilt from same-day results.
if [ ! -s "$KW_DATE_MAP" ] || [ ! -s "$PP_DATE_MAP" ]; then
  python3 tools/build_stale_date_maps.py "$DATE" "$CATALOG_DIR/rr_admin.json" "$KW_DATE_MAP" "$PP_DATE_MAP" >>"$LOG" 2>&1 || {
    say "FATAL: could not freeze stale-date maps"; exit 1;
  }
fi

current=$(balance); whole=${current%.*}
if [ -z "$whole" ] || [ "$whole" -le "$FLOOR_MB" ]; then
  say "PAUSED before launch: balance=${current:-unknown} MB floor=${FLOOR_MB} MB"
  exit 0
fi

say "START balance=${current} MB floor=${FLOOR_MB} MB devices=${ROLLOUT_DEVICES}"
PROXY_PROVIDER=evomi SKIP_BASE=1 WORKERS_CAP=15 \
  RANK_CATALOG_DIR="$CATALOG_DIR" KEYWORD_IDS_FILE="$KW_IDS" \
  DEVICE_EXCLUDE="$EXCLUDES" PLATFORMS=chatgpt,gemini,copilot \
  AEO_SKIP_PREFLIGHT=1 EVOMI_TIER_CACHE_TTL_S=300 RANK_OFFLINE_OCR_RECOVERY=1 RANK_TRUST_ADB_ONLINE=1 \
  RANK_COST_ROLLOUT=copilot-wifi-v1 \
  RANK_COPILOT_OFFLINE_BOOTSTRAP=1 RANK_COPILOT_WIFI_SETTLE=1 \
  RANK_COPILOT_WIFI_ROLLOUT=1 RANK_COPILOT_WIFI_ROLLOUT_DEVICES="$ROLLOUT_DEVICES" \
  RANK_ALLOW_QUARANTINED_DEVICE_108=1 \
  RANK_CACHE_LOW_COST_ROLLOUT=1 RANK_CACHE_LOW_COST_DEVICES="$ROLLOUT_DEVICES" \
  RANK_CHATGPT_LOW_COST_RELEASED=1 RANK_GEMINI_LOW_COST_RELEASED=1 \
  RANK_CACHE_MIN_VERSION=92 \
  RANK_GEMINI_PROMPT_FREE=1 RANK_GEMINI_SAME_ANSWER_REFRAME=1 \
  RANK_COPILOT_MIN_VERSION=88 RANK_SINGLE_ATTEMPT=1 \
  ./run_ranking_auto.sh "$DATE" stale >>"$LOG" 2>&1 &
runner=$!

while kill -0 "$runner" 2>/dev/null; do
  sleep 60
  current=$(balance); whole=${current%.*}
  say "balance=${current:-unknown} MB runner=${runner}"
  if [ -z "$whole" ] || [ "$whole" -le "$FLOOR_MB" ]; then
    say "FLOOR reached; stopping owned ranking tree (daily remains disabled)"
    stop_tree "$runner"
    wait "$runner" 2>/dev/null || true
    exit 0
  fi
done
wait "$runner"; rc=$?

set -a; source .env.dev; set +a
remaining=$(DATE="$DATE" RANK_CATALOG_DIR="$CATALOG_DIR" KEYWORD_IDS_FILE="$KW_IDS" \
  AUDIT_CSV="$PWD/rabbitmq_audit_results_${DATE}_ranking.csv" \
  EXCLUDE_SUCCESS="$PWD/rabbitmq_audit_results_${DATE}_ranking*.csv" \
  RETRY_KEEP_NORANK=1 DRY_RUN=1 PLATFORMS=chatgpt,gemini,copilot WORKERS=1 \
  python3 run_ranking.py 2>>"$LOG" | sed -n 's/.*would run \([0-9]*\) ranking.*/\1/p')
if [ "$remaining" = "0" ]; then
  say "ranking converged; consolidating by each platform's prior date +14"
  DATE="$DATE" RANK_CATALOG_DIR="$CATALOG_DIR" USE_14DAY=1 LASTRANK_FILE="$KW_DATE_MAP" LASTRANK_PP_FILE="$PP_DATE_MAP" \
    OUT_NAME="ranking_stale_${DATE}_consolidated.csv" PLATFORMS=chatgpt,gemini,copilot \
    python3 consolidate_ranking.py >>"$LOG" 2>&1 || { say "FATAL: consolidation failed"; exit 1; }
  python3 tools/verify_stale_consolidation.py "$DATE" \
    "$PWD/ranking_stale_${DATE}_consolidated.csv" "$KW_DATE_MAP" "$PP_DATE_MAP" "$CATALOG_DIR/kw_admin.json" \
    >>"$LOG" 2>&1 || { say "FATAL: stale-date verification failed"; exit 1; }
  touch "$MARK"
  say "STALE COMPLETE + DATES VERIFIED; September 10 daily is eligible but remains held for review"
else
  say "STOPPED rc=${rc} remaining=${remaining:-unknown}; September 10 daily remains disabled"
fi
