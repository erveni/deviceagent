#!/bin/bash
set -eu
cd /Users/seolocalph/projects/device-agent
PLAN="${1:?three-job smoke plan required}"
ARTIFACTS="${2:?new artifact directory required}"
python3 - "$PLAN" "$ARTIFACTS" <<'PY'
import json,sys
from pathlib import Path
from daily_prompt_plan import validate_typed_plan
p=json.load(open(sys.argv[1]));validate_typed_plan(p)
jobs=[j for w in p['waves'] for j in w]
assert len(jobs)==3 and {j['platform'] for j in jobs}=={'chatgpt','gemini','copilot'}
assert all(j.get('daily_slot_id') for j in jobs)
Path(sys.argv[2]).mkdir(exist_ok=False)
PY
set -a
source .env.dev
set +a
export PROXY_PROVIDER=evomi PROXY_HOST=core-residential.evomi.com PROXY_PORT=1000
export PROXY_USER="${EVOMI_USER:?}" PROXY_PASS="${EVOMI_PASS:?}" USE_SNI_RELAY=0
export PROXY_TARGET=country-us ONLY_ONLINE=1 MAX_PARALLEL=1 ROLLING_RETRY=0
export DEVICE_EXCLUDE=device-101,device-102,device-103,device-105,device-106,device-107,device-108,device-109,device-110,device-111,device-112,device-113,device-114,device-115,device-116,device-117,device-118,device-119,device-120,device-121,device-122,device-123,device-124,device-125
export DAILY_BUDGET_MB=100 DAILY_BALANCE_FLOOR_MB=29000
export DAILY_METER_LEDGER="$ARTIFACTS/meter.jsonl"
export DAILY_SMOKE_ARTIFACTS="$ARTIFACTS"
source ./_fleet_lock.sh
fleet_lock_acquire daily-eight-smoke
python3 tools/daily_smoke_runner.py "$PLAN"
