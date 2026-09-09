#!/bin/bash
# Durable full daily driver (launchd-safe): build -> merge Mae -> wake fleet -> run -> consolidate.
# Usage: ./daily_full_auto.sh [YYYY-MM-DD]   (default: today, local PST)
# Designed to run unattended under com.deviceagent.dailyfull LaunchAgent — survives
# session teardown and reboots. Mae source is the tracked mae_plan.json (Mae excluded
# from the deliverable via the dailyonly-swap before consolidation).
set -u
export PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
# node lives under nvm (not on the launchd PATH) — the Ollama-fallback build-server
# needs it. Resolve the newest installed version and prepend its bin.
NVM_BIN=$(ls -d "$HOME"/.nvm/versions/node/*/bin 2>/dev/null | sort -V | tail -1)
[ -n "$NVM_BIN" ] && export PATH="$NVM_BIN:$PATH"
cd /Users/seolocalph/projects/device-agent

DATE="${1:-$(date +%Y-%m-%d)}"
PLAN="${DAILY_PLAN_PATH:-daily_plan_${DATE}.json}"
export DAILY_PLAN_PATH="$PLAN"
DONLY="daily_plan_${DATE}.dailyonly.json"
WITHMAE="daily_plan_${DATE}.withmae.json"
LOG="/private/tmp/dailyfull_${DATE}${DAILY_RUN_LABEL:+_$DAILY_RUN_LABEL}.log"
say(){ echo "[dailyfull ${DATE} $(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

say "START"
# Idempotency: if today's run already finished, do nothing (prevents a manual
# kickstart + the 20:00 timer from double-running the same day).
if grep -q "ALL DONE" "$LOG" 2>/dev/null; then say "already completed today, exit"; exit 0; fi
export SSL_CERT_FILE=$(python3 -c "import certifi;print(certifi.where())")
TOK=$(aws secretsmanager get-secret-value --secret-id aeo-admin/prod --profile aeo-admin --region us-east-1 --query SecretString --output text 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('EXECUTOR_TOKEN',''))")
[ ${#TOK} -eq 64 ] || { say "FATAL: bad EXECUTOR_TOKEN (len ${#TOK})"; exit 1; }

# 1) ensure the plan exists (build only if missing — a pre-staged bare plan is kept)
if [ -s "$PLAN" ]; then
  say "plan already present, skip build"
else
  say "building plan…"
  _ov_provider="${PROXY_PROVIDER:-}"   # a caller-exported provider wins over .env.dev
  set -a; source .env.dev 2>/dev/null; set +a
  [ -n "$_ov_provider" ] && export PROXY_PROVIDER="$_ov_provider"
  # Eight-type daily uses deterministic backend templates, not DeepSeek/Ollama.
  # Require the deployed capability; never silently use a stale local backend.
  say "building eight-type daily against configured/deployed backend"
  DATE="$DATE" PLAN_PATH="$PLAN" EXECUTOR_TOKEN="$TOK" BUILD_TIMEOUT_S="${BUILD_TIMEOUT_S:-180}" \
    python3 -u build_daily_plan.py >>"$LOG" 2>&1 || { say "FATAL: daily build failed"; exit 1; }
  [ -s "$PLAN" ] || { say "FATAL: build produced no $PLAN"; exit 1; }
fi

# 1b) sanity: reject a DeepSeek-starved partial plan (normal ~1300-1400 pre-Mae jobs).
JOBS=$(python3 -c "import json;print(json.load(open('$PLAN'))['total_jobs'])" 2>/dev/null || echo 0)
EIGHT_DAILY=$(python3 -c "import json;print(int(json.load(open('$PLAN')).get('daily_protocol')=='eight-v1'))")
if [ "$EIGHT_DAILY" = "1" ]; then
  python3 -c "import json,sys;from daily_prompt_plan import validate_typed_plan;validate_typed_plan(json.load(open(sys.argv[1])))" "$PLAN" || exit 2
elif [ "${JOBS:-0}" -lt 800 ]; then
  say "FATAL: plan has only ${JOBS} jobs (<800) — likely DeepSeek drop; NOT running. Delete $PLAN + rebuild once funded."
  exit 1
fi
say "plan job count ok: ${JOBS}"

# 2) merge Mae from tracked mae_plan.json — no-op if already merged (guarded inside)
python3 - "$DATE" >>"$LOG" 2>&1 <<'PY'
import json, sys, os
DATE=sys.argv[1]; PLAN=os.environ.get('DAILY_PLAN_PATH',f"daily_plan_{DATE}.json")
p=json.load(open(PLAN))
if p.get('daily_protocol')=='eight-v1':
    print('[dailyfull] eight-type protocol: no separate210-session Mae override'); raise SystemExit(0)
flat=lambda pl:[j for w in pl.get("waves",[]) for j in w]
if "Mae's Childcare" in {j.get("biz_name") for j in flat(p)}:
    print(f"[dailyfull] Mae already present, skip merge"); raise SystemExit(0)
json.dump(p, open(f"daily_plan_{DATE}.dailyonly.json","w"))
mae=[j for w in json.load(open("mae_plan.json"))["waves"] for j in w]
p.setdefault("waves",[]).extend(mae[i:i+10] for i in range(0,len(mae),10))
p["total_jobs"]=p.get("total_jobs",0)+len(mae)
json.dump(p, open(PLAN,"w"))
print(f"[dailyfull] merged Mae {len(mae)} -> total_jobs={p['total_jobs']}")
PY

# 2b) OPTIONAL Copilot trial slice. Unset = no change at all; Perplexity runs in full.
# Set COPILOT_SLICE=N to move N Perplexity jobs onto Copilot for ONE night so its
# backlink rate can be compared against Perplexity's 26% before any real swap.
# The nightly runs unattended from a LaunchAgent, which carries no env, so the trial is
# armed by dropping the job count into .copilot_slice. It is consumed and DELETED here:
# a one-night trial must not quietly become the permanent config because nobody
# remembered to unset it.
if [ "$EIGHT_DAILY" != "1" ] && [ -z "${COPILOT_SLICE:-}" ] && [ -f .copilot_slice ]; then
  COPILOT_SLICE="$(tr -dc '0-9' < .copilot_slice)"
  rm -f .copilot_slice
  say "copilot slice armed for tonight only: ${COPILOT_SLICE:-none} (marker consumed)"
fi
if [ "$EIGHT_DAILY" != "1" ] && [ -n "${COPILOT_SLICE:-}" ]; then
  COPILOT_SLICE="$COPILOT_SLICE" python3 slice_copilot_into_plan.py "$PLAN" >>"$LOG" 2>&1 \
    && say "copilot slice applied (${COPILOT_SLICE} jobs)" \
    || say "WARN: copilot slice failed — continuing with the unmodified plan"
fi

# 3) wake + unlock fleet
python3 - >>"$LOG" 2>&1 <<'PY'
import subprocess
from device_dispatch import DEVICES
out=subprocess.run(["adb","devices"],capture_output=True,text=True).stdout
online={l.split("\t")[0] for l in out.splitlines() if "\tdevice" in l}
n=0
for label,ser in DEVICES:
    if label in ("device-108","device-125") or ser not in online: continue
    for k in ("KEYCODE_WAKEUP","KEYCODE_MENU"):
        subprocess.run(["adb","-s",ser,"shell","input","keyevent",k],stdin=subprocess.DEVNULL,capture_output=True,timeout=15)
    subprocess.run(["adb","-s",ser,"shell","input","swipe","540","1600","540","400"],stdin=subprocess.DEVNULL,capture_output=True,timeout=15)
    n+=1
print(f"[dailyfull] woke {n} phones")
PY

# 4) fleet-idle wait (only other DAILY runs; ignore run_ranking)
for i in $(seq 1 40); do
  pgrep -f "run_rolling_plan|run_daily_auto" >/dev/null 2>&1 || { say "fleet idle"; break; }
  say "fleet busy, wait"; sleep 30
done

# 5) run daily to 100%
say "launching run_daily_auto"
./run_daily_auto.sh "$DATE" >>"$LOG" 2>&1
RUN_RC=$?
say "run_daily_auto exited rc=$RUN_RC"

if [ "$EIGHT_DAILY" = "1" ]; then
  OUT="${DAILY_DELIVERY_DIR:-daily_delivery_${DATE}_$(date +%s)}"
  python3 tools/consolidate_typed_daily.py "$PLAN" "$OUT" >>"$LOG" 2>&1 || exit 2
  if [ "$RUN_RC" -ne 0 ]; then
    say "INCOMPLETE — partial typed successes preserved in $OUT; no completion marker"
    exit "$RUN_RC"
  fi
  say "ALL DONE — typed slots consolidated in $OUT (legacy credits not re-imported)"
  exit 0
fi

# 6) consolidate Mae-excluded: swap plan -> dailyonly
if [ "$EIGHT_DAILY" != "1" ] && [ -s "$DONLY" ]; then
  mv "$PLAN" "$WITHMAE"; cp "$DONLY" "$PLAN"; say "swapped plan -> dailyonly"
fi
DATE="$DATE" python3 _consolidate_daily.py >>"$LOG" 2>&1
say "consolidate rc=$?"
if [ "$EIGHT_DAILY" != "1" ] && [ -s "$WITHMAE" ]; then
  mv "$WITHMAE" "$PLAN"; say "restored withmae plan"
fi
say "ALL DONE"
