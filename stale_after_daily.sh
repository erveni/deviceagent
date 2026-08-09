#!/bin/bash
# Run the stale (all_due) ranking AFTER the daily finishes, then consolidate per-platform +14.
# Durable (launchd one-shot): waits for the dailyfull ALL DONE marker so it never collides
# with the 20:00 daily on the fleet. Usage: ./stale_after_daily.sh [YYYY-MM-DD] (default today).
set -u
export PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
cd /Users/seolocalph/projects/device-agent

DATE="${1:-$(date +%Y-%m-%d)}"
LOG="/private/tmp/staleafter_${DATE}.log"
KW_IDS="/tmp/ranking_kw_ids_${DATE}.json"
DAILY_LOG="/private/tmp/dailyfull_${DATE}.log"
say(){ echo "[staleafter ${DATE} $(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

say "START (waiting for daily to finish first)"
source ~/.deviceagent-ops/rank_env.sh
export SSL_CERT_FILE=$(python3 -c "import certifi;print(certifi.where())")

# 1) wait for the daily to complete (ALL DONE marker) AND no daily run procs. Up to ~10h.
for i in $(seq 1 1200); do
  if grep -q "ALL DONE" "$DAILY_LOG" 2>/dev/null && ! pgrep -f "run_rolling_plan|run_daily_auto" >/dev/null 2>&1; then
    say "daily done — proceeding to stale"; break
  fi
  sleep 30
done

# 2) ensure dueset exists (rebuild fresh if a reboot wiped /tmp). rr snapshot stays pre-rank
#    because only the ranking run writes rank rows, and it hasn't run yet.
if [ ! -s "$KW_IDS" ] || [ ! -s /tmp/rr_admin.json ]; then
  say "dueset missing — rebuilding"
  DATE="$DATE" SCOPE=all_due python3 build_ranking_dueset.py >>"$LOG" 2>&1
fi
[ -s "$KW_IDS" ] || { say "FATAL: no dueset $KW_IDS"; exit 1; }

# 3) wake + unlock fleet
python3 - >>"$LOG" 2>&1 <<'PY'
import subprocess
from device_dispatch import DEVICES
out=subprocess.run(["adb","devices"],capture_output=True,text=True).stdout
online={l.split("\t")[0] for l in out.splitlines() if "\tdevice" in l}
n=0
for label,ser in DEVICES:
    if label=="device-125" or ser not in online: continue
    for k in ("KEYCODE_WAKEUP","KEYCODE_MENU"):
        subprocess.run(["adb","-s",ser,"shell","input","keyevent",k],stdin=subprocess.DEVNULL,capture_output=True,timeout=15)
    subprocess.run(["adb","-s",ser,"shell","input","swipe","540","1600","540","400"],stdin=subprocess.DEVNULL,capture_output=True,timeout=15)
    n+=1
print(f"[staleafter] woke {n} phones")
PY

# 4) run stale to convergence
say "launching run_ranking_auto ${DATE} all_due (WORKERS_CAP=18)"
WORKERS_CAP=18 ./run_ranking_auto.sh "$DATE" all_due >>"$LOG" 2>&1
say "run_ranking_auto exited rc=$?"

# 5) build per-kw + per-platform last-rank maps from the pre-run rr snapshot (date < DATE, max)
python3 - "$DATE" >>"$LOG" 2>&1 <<'PY'
import json, sys
DATE=sys.argv[1]
d=json.load(open("/tmp/rr_admin.json"))
recs=d if isinstance(d,list) else list(d.values())
perkw={}; pp={}
for r in recs:
    kw=r.get("keywordId"); plat=(r.get("platform") or "").lower(); dt=r.get("date")
    if kw is None or not dt or dt>=DATE: continue
    perkw[str(kw)]=max(perkw.get(str(kw),""), dt)
    k=f"{kw}|{plat}"; pp[k]=max(pp.get(k,""), dt)
json.dump(perkw, open(f"/tmp/kw_lastrank_before_{DATE}.json","w"))
json.dump(pp, open(f"/tmp/kw_lastrank_pp_{DATE}.json","w"))
print(f"[staleafter] lastrank maps: perkw={len(perkw)} pp={len(pp)}")
PY

# 6) consolidate per-platform +14
say "consolidating (+14 per-platform)"
DATE="$DATE" USE_14DAY=1 \
  LASTRANK_FILE="/tmp/kw_lastrank_before_${DATE}.json" \
  LASTRANK_PP_FILE="/tmp/kw_lastrank_pp_${DATE}.json" \
  OUT_NAME="ranking_stale_${DATE}_consolidated.csv" \
  python3 consolidate_ranking.py >>"$LOG" 2>&1
say "consolidate rc=$?"
say "ALL DONE -> ~/Desktop/Rankings/ranking_stale_${DATE}_consolidated.csv"

# 7) self-unload the one-shot agent so it doesn't re-fire on next login/reboot
launchctl unload ~/Library/LaunchAgents/com.deviceagent.staleafter.plist 2>/dev/null || true
