#!/bin/bash
# Wait for the import-first Black Monarch deliverable, then resume general stale.
set -u
export PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
cd /Users/seolocalph/projects/device-agent || exit 1
LOG="$PWD/stale_after_black_monarch.log"
OUT="$PWD/ranking_stale_black_monarch_2026-09-06_consolidated.csv"
say(){ echo "[stale-after-black $(date '+%F %T')] $*" | tee -a "$LOG"; }

launchctl disable "gui/$(id -u)/com.deviceagent.dailyfull" 2>/dev/null || true
say "waiting for Black Monarch verified deliverable"
while pgrep -f '/run_black_monarch_first.sh' >/dev/null 2>&1; do sleep 30; done

if [ ! -s "$OUT" ] || ! grep -q 'COMPLETE + VERIFIED' "$PWD/black_monarch_first.log"; then
  say "HOLD: Black Monarch stopped without verified deliverable; general stale not started"
  exit 3
fi
rows=$(python3 -c "import csv;print(len(list(csv.DictReader(open('$OUT')))))")
if [ "$rows" != "15" ]; then
  say "HOLD: Black Monarch deliverable has $rows rows, expected15"
  exit 3
fi

say "Black Monarch verified15/15; starting general stale supervisor"
launchctl bootout "gui/$(id -u)/com.deviceagent.stalebeforesep10" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.deviceagent.stalebeforesep10.plist"
say "general stale handoff complete"
