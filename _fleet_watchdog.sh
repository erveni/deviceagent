#!/bin/bash
# Fleet watchdog — auto-detects dropped phones and recovers them within ~3 min.
#   tick every 180s:
#     count >= EXPECT        -> healthy (log only on state change)
#     SEVER_MIN <= count < EXPECT -> per-phone recovery, NON-disruptive:
#         missing phone answering HTTP :8765 -> POST /adb/rearm (v0.9.50)
#         then adb connect its fresh mDNS ip:port
#     count < SEVER_MIN      -> fleet severed -> adb kill-server/start-server
#         (disruptive to in-flight jobs; only used when the run is burning anyway)
# Never touches phones that are attached. Stop: pkill -f _fleet_watchdog.sh
# Log: /private/tmp/fleet_watchdog.log  (hourly LLM check-in reads this)
set -u
EXPECT=8
SEVER_MIN=4
LOG=/private/tmp/fleet_watchdog.log
PIDFILE=/private/tmp/fleet_watchdog.pid
FLEET_IPS="192.168.0.100 192.168.0.102 192.168.0.103 192.168.0.104 192.168.0.106 192.168.0.120 192.168.0.121 192.168.0.122"

[ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null && { echo "already running (pid $(cat "$PIDFILE"))"; exit 0; }
echo $$ > "$PIDFILE"
log(){ echo "[watchdog $(date '+%F %T')] $*" >> "$LOG"; }
log "started (expect=$EXPECT sever_min=$SEVER_MIN)"

count_devices(){ adb devices 2>/dev/null | grep -cE $'\tdevice$'; }

# serials currently attached (mDNS names + ip:port forms)
attached_blob(){ adb devices 2>/dev/null | grep -E $'\tdevice$' | cut -f1; }

recover_phone(){  # $1 = ip
  local ip="$1"
  # skip if any attached serial resolves to this ip via mdns OR direct ip:port serial
  local blob; blob=$(attached_blob)
  if echo "$blob" | grep -q "^$ip:"; then return 0; fi
  local mdns_line serial port
  mdns_line=$(adb mdns services 2>/dev/null | grep "_adb-tls-connect" | grep " $ip:" | head -1)
  if [ -n "$mdns_line" ]; then
    serial=$(echo "$mdns_line" | cut -f1)
    if echo "$blob" | grep -qF "$serial"; then return 0; fi   # attached under mDNS name
    # advertised but not attached -> try plain connect first
    port=$(echo "$mdns_line" | grep -oE "$ip:[0-9]+" | cut -d: -f2)
    r=$(adb connect "$ip:$port" 2>&1)
    log "  $ip advertised, connect:$port -> $r"
    echo "$r" | grep -q "^connected" && return 0
  fi
  # no (working) advertisement -> rearm over HTTP if the agent answers
  if curl -s -m 3 "http://$ip:8765/health" | grep -q '"ok":true'; then
    r=$(curl -s -m 10 -X POST "http://$ip:8765/adb/rearm")
    log "  $ip rearm -> $r"
    sleep 6
    mdns_line=$(adb mdns services 2>/dev/null | grep "_adb-tls-connect" | grep " $ip:" | head -1)
    port=$(echo "$mdns_line" | grep -oE "$ip:[0-9]+" | cut -d: -f2)
    if [ -n "${port:-}" ]; then
      r=$(adb connect "$ip:$port" 2>&1); log "  $ip post-rearm connect:$port -> $r"
    else
      log "  $ip re-armed but no mDNS advert yet (auto-connect may pick it up)"
    fi
  else
    log "  $ip missing and no HTTP — cannot recover remotely (needs hourly loop / hands)"
  fi
}

# keep-alive: touch every attached phone's HTTP server so the v0.9.51 on-device
# self-heal watchdog sees "Mac contact" and never cycles a healthy/busy phone
# (CDP traffic doesn't touch :8765, so without this a long CDP job looks silent).
keepalive_all(){
  local port=18960 s
  while IFS= read -r s; do
    port=$((port+1))
    adb -s "$s" forward "tcp:$port" tcp:8765 >/dev/null 2>&1
    curl -s -m 2 "http://127.0.0.1:$port/ping" >/dev/null 2>&1
    adb -s "$s" forward --remove "tcp:$port" >/dev/null 2>&1
  done < <(attached_blob)
}

last_state="init"
tick=0
while true; do
  n=$(count_devices)
  tick=$((tick+1))
  keepalive_all
  if [ "$n" -ge "$EXPECT" ]; then
    state="healthy"
    [ "$state" != "$last_state" ] && log "healthy: $n devices"
    # heartbeat every ~1h so the log proves the watchdog is alive
    [ $((tick % 20)) -eq 0 ] && log "heartbeat: $n devices"
  elif [ "$n" -ge "$SEVER_MIN" ]; then
    state="degraded"
    log "DEGRADED: $n/$EXPECT devices — per-phone recovery"
    for ip in $FLEET_IPS; do recover_phone "$ip"; done
    log "recovery pass done: now $(count_devices) devices"
  else
    state="severed"
    log "SEVERED: only $n devices — bouncing adb server"
    adb kill-server 2>/dev/null; sleep 3; adb start-server 2>/dev/null; sleep 25
    n2=$(count_devices); log "after server bounce: $n2 devices"
    if [ "$n2" -lt "$EXPECT" ]; then
      for ip in $FLEET_IPS; do recover_phone "$ip"; done
      log "post-bounce recovery: $(count_devices) devices"
    fi
  fi
  last_state="$state"
  sleep 180
done
