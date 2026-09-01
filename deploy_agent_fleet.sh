#!/bin/bash
# Deploy the current device-agent build to every online phone.
#
# Generalised from the one-off _deploy_v67.sh: WANT defaults to the versionCode in
# app/build.gradle.kts so this never needs editing per release. install -r alone does NOT reload the running
# AccessibilityService (it keeps serving old code), and force-stop clears the
# accessibility binding — so we install, force-stop, then re-assert accessibility and
# POLL /health until it reports versionCode 67 + accessibility (retrying the rebind,
# which Android 13+ doesn't always honor on the first try). Serials may contain
# " (2)" so read line-wise + quote; </dev/null keeps the read loop's stdin intact.
set -u
cd /Users/seolocalph/projects/device-agent
APK=app/build/outputs/apk/debug/app-debug.apk
WANT="${WANT:-$(sed -n 's/.*versionCode = \([0-9]*\).*/\1/p' app/build.gradle.kts)}"
i=0; OK=0; BAD=""
while IFS= read -r S; do
  i=$((i+1)); port=$((8800+i))
  echo "=== [$i] $S ==="
  adb -s "$S" install -r "$APK" </dev/null 2>&1 | tail -1
  adb -s "$S" shell am force-stop com.deviceagent </dev/null >/dev/null 2>&1
  sleep 1
  adb -s "$S" shell am start -n com.deviceagent/.MainActivity </dev/null >/dev/null 2>&1
  adb -s "$S" forward tcp:$port tcp:8765 </dev/null >/dev/null 2>&1
  got=""
  for try in 1 2 3 4 5; do
    adb -s "$S" shell settings put secure enabled_accessibility_services com.deviceagent/com.deviceagent.AgentAccessibilityService </dev/null >/dev/null 2>&1
    adb -s "$S" shell settings put secure accessibility_enabled 1 </dev/null >/dev/null 2>&1
    sleep 4
    H=$(curl -s -m 6 http://localhost:$port/health)
    got=$(echo "$H" | python3 -c "import sys,json;d=json.load(sys.stdin);print('%s|%s'%(d.get('versionCode'),d.get('accessibility')))" 2>/dev/null)
    [ "$got" = "$WANT|True" ] && break
  done
  echo "  health: ${got:-NO_RESPONSE}"
  if [ "$got" = "$WANT|True" ]; then OK=$((OK+1)); else BAD="$BAD $S"; fi
  adb -s "$S" forward --remove tcp:$port </dev/null >/dev/null 2>&1
done < <(adb devices | awk -F'\t' 'NR>1 && $2=="device"{print $1}')
echo "=========================================="
echo "v$WANT + accessibility OK on $OK of $i phone(s)."
[ -n "$BAD" ] && echo "NEEDS MANUAL ACCESSIBILITY TOGGLE:$BAD" || echo "All online phones good."
