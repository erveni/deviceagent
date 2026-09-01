#!/bin/bash
# Install Microsoft Edge on every fleet phone, once the nightly has released them.
#
# Copilot only answers logged out inside Edge, so every phone that will run a Copilot
# job needs it. The APK is pulled off device-101 rather than the Play Store: the fleet
# has no Google accounts, and a sideload keeps every phone on one known version.
#
# Edge ONLY. The device-agent APK is deliberately not installed here: `install -r`
# leaves the old code running, and Android 13+ ignores the shell accessibility
# re-toggle after a force-stop, so an unattended app install would leave the fleet with
# a dead AccessibilityService and break the next nightly. That one needs a hand on each
# phone.
set -u

APK="${APK:-$HOME/apks/edge_151.0.4129.101.apk}"
LOG="${LOG:-/private/tmp/edge_fleet_install.log}"
FLEET_LOCK="${FLEET_LOCK:-/tmp/fleet.lock}"
PKG="com.microsoft.emmx"
MAX_WAIT_S="${MAX_WAIT_S:-21600}"   # 6h ceiling so a stuck nightly can't hang this forever

say(){ echo "[edge-install $(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

[ -f "$APK" ] || { say "APK missing: $APK"; exit 1; }

say "waiting for the nightly to finish (lock=$FLEET_LOCK)"
waited=0
while [ "$waited" -lt "$MAX_WAIT_S" ]; do
  running=0
  pgrep -f "run_rolling_plan.py" >/dev/null 2>&1 && running=1
  pgrep -f "daily_full_auto.sh" >/dev/null 2>&1 && running=1
  [ -f "$FLEET_LOCK" ] && running=1
  [ "$running" -eq 0 ] && break
  sleep 60
  waited=$((waited + 60))
done
if [ "$waited" -ge "$MAX_WAIT_S" ]; then
  say "gave up waiting after ${MAX_WAIT_S}s — fleet still busy, NOT installing"
  exit 1
fi
# The runner tears down forwards and releases phones as it exits; give it room.
say "fleet idle after ${waited}s — settling"
sleep 120

# Read serials line by line: mDNS names containing "(2)" are shell syntax unquoted.
adb devices | awk -F'\t' 'NR>1 && $2=="device" {print $1}' > /tmp/_edge_serials.txt
total=$(wc -l < /tmp/_edge_serials.txt | tr -d ' ')
say "installing on $total phones"

ok=0; skip=0; fail=0
while IFS= read -r s; do
  [ -z "$s" ] && continue
  have=$(adb -s "$s" shell "pm list packages $PKG" 2>/dev/null | tr -d '\r')
  if [ -n "$have" ]; then
    cur=$(adb -s "$s" shell "dumpsys package $PKG" 2>/dev/null | grep -m1 versionCode | tr -d '\r')
    say "SKIP  $s (already has Edge:$cur)"
    skip=$((skip + 1))
    continue
  fi
  res=$(adb -s "$s" install -r "$APK" 2>&1 | tail -1)
  if echo "$res" | grep -q Success; then
    vc=$(adb -s "$s" shell "dumpsys package $PKG" 2>/dev/null | grep -m1 versionCode | tr -d '\r')
    say "OK    $s$vc"
    ok=$((ok + 1))
  else
    say "FAIL  $s $res"
    fail=$((fail + 1))
  fi
done < /tmp/_edge_serials.txt

say "done: ok=$ok skip=$skip fail=$fail (log: $LOG)"
