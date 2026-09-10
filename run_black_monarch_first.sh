#!/bin/bash
# Dedicated import-first stale ranking for Black Monarch Motoring Center Point.
set -u
export PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
cd /Users/seolocalph/projects/device-agent || exit 1

DATE=2026-09-06
CATALOG_DIR="$PWD/_snapshots_2026-09-02"
KW_IDS="$PWD/tools/black_monarch_keywords.json"
CSV="$PWD/rabbitmq_audit_results_${DATE}_ranking_black_monarch.csv"
CSV_GLOB="$PWD/rabbitmq_audit_results_${DATE}_ranking_black_monarch*.csv"
KW_MAP="$PWD/black_monarch_${DATE}_last_rank_by_keyword.json"
PP_MAP="$PWD/black_monarch_${DATE}_last_rank_by_platform.json"
OUT="ranking_stale_black_monarch_${DATE}_consolidated.csv"
LOG="$PWD/black_monarch_first.log"
ROLLOUT_DEVICES=device-101,device-102,device-103,device-104,device-106,device-108,device-109,device-110,device-113,device-116,device-117,device-118,device-119,device-120,device-121,device-122,device-123
EXCLUDES=device-105,device-107,device-111,device-112,device-114,device-115,device-124,device-125
say(){ echo "[black-monarch $(date '+%F %T')] $*" | tee -a "$LOG"; }

launchctl disable "gui/$(id -u)/com.deviceagent.dailyfull" 2>/dev/null || true
[ -s "$KW_IDS" ] && [ -s "$CATALOG_DIR/kw_admin.json" ] && [ -s "$CATALOG_DIR/rr_admin.json" ] || {
  say "FATAL: dedicated manifest or durable catalog missing"; exit 1;
}
python3 tools/build_stale_date_maps.py "$DATE" "$CATALOG_DIR/rr_admin.json" "$KW_MAP" "$PP_MAP" >>"$LOG" 2>&1 || exit 1

say "START five keywords x three platforms on all17 connected production phones"
PROXY_PROVIDER=evomi SKIP_BASE=1 WORKERS_CAP=17 RANK_RETRY_ROUNDS=12 \
  RANK_CATALOG_DIR="$CATALOG_DIR" KEYWORD_IDS_FILE="$KW_IDS" AUDIT_CSV="$CSV" \
  DEVICE_EXCLUDE="$EXCLUDES" PLATFORMS=chatgpt,gemini,copilot FORCE_RERANK=1 \
  AEO_SKIP_PREFLIGHT=1 EVOMI_TIER_CACHE_TTL_S=300 RANK_SHUFFLE_JOBS=1 \
  RANK_COST_ROLLOUT=copilot-wifi-v1 RANK_COPILOT_OFFLINE_BOOTSTRAP=1 \
  RANK_COPILOT_WIFI_SETTLE=1 RANK_COPILOT_WIFI_ROLLOUT=1 \
  RANK_COPILOT_WIFI_ROLLOUT_DEVICES="$ROLLOUT_DEVICES" RANK_ALLOW_QUARANTINED_DEVICE_108=1 \
  RANK_COPILOT_MIN_VERSION=88 RANK_SINGLE_ATTEMPT=1 \
  ./run_ranking_auto.sh "$DATE" stale >>"$LOG" 2>&1
rc=$?

set -a; source .env.dev; set +a
remaining=$(DATE="$DATE" FORCE_RERANK=1 RANK_CATALOG_DIR="$CATALOG_DIR" KEYWORD_IDS_FILE="$KW_IDS" \
  AUDIT_CSV="$CSV" EXCLUDE_SUCCESS="$CSV_GLOB" RETRY_KEEP_NORANK=1 DRY_RUN=1 \
  PLATFORMS=chatgpt,gemini,copilot WORKERS=1 python3 run_ranking.py 2>>"$LOG" |
  sed -n 's/.*would run \([0-9]*\) ranking.*/\1/p')
if [ "$remaining" != "0" ]; then
  say "INCOMPLETE rc=$rc remaining=${remaining:-unknown}; no deliverable written"
  exit 3
fi

successes=$(python3 - "$CSV_GLOB" <<'PY'
import csv,glob,sys
pairs=set()
for path in glob.glob(sys.argv[1]):
    for row in csv.DictReader(open(path)):
        if (row.get('status') or '').lower()=='success':
            pairs.add(((row.get('campaign_id') or '').strip(),(row.get('platform') or '').lower().strip()))
print(len(pairs))
PY
)
if [ "$successes" != "15" ]; then
  say "INCOMPLETE: reconciliation is terminal but only $successes/15 validated successes; no deliverable written"
  exit 3
fi

say "consolidating dedicated Black Monarch deliverable"
DATE="$DATE" RANK_CATALOG_DIR="$CATALOG_DIR" USE_14DAY=1 \
  LASTRANK_FILE="$KW_MAP" LASTRANK_PP_FILE="$PP_MAP" RANKING_SOURCES_GLOB="$CSV_GLOB" \
  OUT_NAME="$OUT" PLATFORMS=chatgpt,gemini,copilot python3 consolidate_ranking.py >>"$LOG" 2>&1 || exit 1
python3 tools/verify_stale_consolidation.py "$DATE" "$PWD/$OUT" "$KW_MAP" "$PP_MAP" \
  "$CATALOG_DIR/kw_admin.json" >>"$LOG" 2>&1 || exit 1
[ "$(python3 -c "import csv;print(len(list(csv.DictReader(open('$PWD/$OUT')))))")" = "15" ] || {
  say "FATAL: dedicated deliverable is not exactly15 rows"; exit 1;
}
say "COMPLETE + VERIFIED -> $PWD/$OUT and ~/Desktop/Rankings/$OUT"
