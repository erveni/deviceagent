#!/bin/bash
# Fleet boot-recovery — run at Mac login by the com.deviceagent.fleet LaunchAgent.
# 1) start the adb server (triggers mDNS auto-reconnect of paired phones — pairing
#    survives reboot via ~/.android/adbkey), 2) explicitly connect any advertised-
#    but-unattached phones, 3) exec into the watchdog so launchd KeepAlive keeps the
#    whole thing alive (if the watchdog dies, launchd re-runs this = re-reconnect too).
# Dark/inbound-blocked phones still need a physical wireless-debug toggle.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
cd /Users/seolocalph/projects/device-agent || exit 1
LOG=/private/tmp/fleet_boot.log
log(){ echo "[boot $(date '+%F %T')] $*" >> "$LOG"; }

log "login — starting adb server"
# On a fresh boot adb isn't running, so start-server alone lets mDNS auto-connect
# paired phones. Only bounce if the server is already up but sees 0 devices (a
# hung server) — an unconditional kill-server thrashes the mDNS backend.
adb start-server >/dev/null 2>&1
sleep 25   # let mDNS auto-connect paired phones
if [ "$(adb devices 2>/dev/null | grep -cE $'\tdevice$')" -eq 0 ]; then
  adb kill-server >/dev/null 2>&1; sleep 2; adb start-server >/dev/null 2>&1; sleep 20
fi

# connect any phone advertising _adb-tls-connect that isn't attached yet
adb mdns services 2>/dev/null | grep "_adb-tls-connect" \
  | grep -oE "192\.168\.0\.[0-9]+:[0-9]+" | sort -u | while IFS= read -r ipp; do
  [ -n "$ipp" ] && adb connect "$ipp" >/dev/null 2>&1
done
sleep 3
log "adb up — devices=$(adb devices 2>/dev/null | grep -cE $'\tdevice$')"

# clear any stale watchdog pidfile so the guard doesn't refuse to start
rm -f /private/tmp/fleet_watchdog.pid
log "exec fleet watchdog"
exec bash /Users/seolocalph/projects/device-agent/_fleet_watchdog.sh
