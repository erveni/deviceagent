#!/bin/bash
# Roll APK v0.9.23 (gen-timeout 240s) to the wifi fleet AFTER the Jun-24 daily
# finishes. Excludes the USB test phone (149145555W006477). Per phone: install -r,
# re-assert accessibility (shell trick), relaunch, verify /health version+a11y.
# Defensive: if the FIRST phone ends without accessibility, abort the rest (so we
# don't break the whole fleet's a11y unattended).
set -u
cd /Users/seolocalph/projects/device-agent
APK=/tmp/device-agent-v924.apk
LOG=/private/tmp/fleet_rollout_v923.log
A11Y="com.deviceagent/com.deviceagent.AgentAccessibilityService"
log(){ echo "[rollout $(date '+%F %T')] $*" | tee -a "$LOG"; }

log "waiting for Jun-24 daily to finish before rolling out..."
while pgrep -f "run_daily_mixed.sh 2026-06-24" >/dev/null 2>&1 || pgrep -f "run_with_proxy.py daily_plan_2026-06-24" >/dev/null 2>&1; do
  sleep 60
done
log "daily finished — starting rollout"

idx=0; ok=0; bad=0; first=1
for s in $(adb devices | awk -F'\t' 'NR>1 && $2=="device"{print $1}' | grep "_adb-tls-connect"); do
  lport=$((8901+idx)); idx=$((idx+1))
  log "[$s] install -r"
  adb -s "$s" install -r "$APK" >/dev/null 2>&1 || { log "[$s] install FAILED"; bad=$((bad+1)); continue; }
  adb -s "$s" shell settings put secure enabled_accessibility_services "$A11Y" >/dev/null 2>&1
  adb -s "$s" shell settings put secure accessibility_enabled 1 >/dev/null 2>&1
  adb -s "$s" shell monkey -p com.deviceagent -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
  sleep 4
  adb -s "$s" forward tcp:$lport tcp:8765 >/dev/null 2>&1
  h=$(curl -s -m 8 http://localhost:$lport/health 2>/dev/null)
  adb -s "$s" forward --remove tcp:$lport >/dev/null 2>&1
  ver=$(echo "$h" | python3 -c "import sys,json;print(json.load(sys.stdin).get('versionCode'))" 2>/dev/null)
  a11y=$(echo "$h" | python3 -c "import sys,json;print(json.load(sys.stdin).get('accessibility'))" 2>/dev/null)
  log "[$s] versionCode=$ver accessibility=$a11y"
  if [ "$ver" = "42" ] && [ "$a11y" = "True" ]; then ok=$((ok+1)); else
    bad=$((bad+1))
    if [ "$first" = "1" ]; then
      log "ABORT: first phone did not come up clean (ver=$ver a11y=$a11y) — stopping rollout to avoid breaking the fleet. Investigate + roll manually."
      exit 1
    fi
  fi
  first=0
done
log "ROLLOUT DONE — ok=$ok bad=$bad (test phone 149145555W006477 left on its existing build)"
