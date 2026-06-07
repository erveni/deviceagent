#!/bin/bash
# reconnect_watcher.sh — keep the ADB fleet healthy during long runs.
#
# Every INTERVAL seconds it:
#   1. `adb reconnect offline`  — revives mDNS phones whose ADB-over-Wi-Fi
#      connection flapped but the phone is still on the network (the common case).
#   2. re-dials each known TCP/IP phone (`adb connect ip:port`).
#   3. tries to re-discover any mDNS phone that fully dropped (`adb mdns services`).
#   4. on every reachable phone, keeps Wi-Fi on (`svc wifi enable`) — a no-op if
#      already on; the only thing recoverable remotely (a phone whose Wi-Fi is
#      truly off is unreachable by ADB and needs a physical touch).
#
# The dispatcher's POOL.acquire() re-checks `adb devices` each time, so any phone
# this script brings back is picked up by the IN-PROGRESS run automatically.
#
# Usage:  ./reconnect_watcher.sh            # runs until killed
#         INTERVAL=30 ./reconnect_watcher.sh
# Stop:   pkill -f reconnect_watcher.sh

INTERVAL="${INTERVAL:-45}"
# TCP/IP-attached phones (mDNS uses auto-discovery; these need an explicit dial).
TCP_PHONES="${TCP_PHONES:-192.168.0.165:34779}"
LOG="${LOG:-/private/tmp/reconnect_watcher.log}"

echo "[$(date '+%F %T')] watcher start (interval=${INTERVAL}s, tcp='${TCP_PHONES}')" >> "$LOG"

while true; do
  ts="$(date '+%T')"
  before="$(adb devices 2>/dev/null | grep -cw device)"

  # 1. revive flapped mDNS connections (only touches OFFLINE devices, never active ones)
  adb reconnect offline >/dev/null 2>&1

  # 2. re-dial known TCP/IP phones
  for ip in $TCP_PHONES; do adb connect "$ip" >/dev/null 2>&1; done

  # 3. nudge mDNS auto-discovery (harmless if nothing new)
  adb mdns services >/dev/null 2>&1

  # 4. keep Wi-Fi on for reachable phones (no-op if already on)
  for s in $(adb devices 2>/dev/null | awk '$2=="device"{print $1}'); do
    adb -s "$s" shell svc wifi enable >/dev/null 2>&1
  done

  after="$(adb devices 2>/dev/null | grep -cw device)"
  if [ "$after" != "$before" ]; then
    echo "[$ts] sweep: ${before} -> ${after} online (recovered $((after-before)))" >> "$LOG"
  else
    echo "[$ts] sweep: ${after} online (steady)" >> "$LOG"
  fi
  sleep "$INTERVAL"
done
