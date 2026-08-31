#!/bin/bash
# Watch the 2026-08-31 nightly: plan build, fleet size, progress, cost/job, stalls, end.
# Baseline balance is captured at 20:00 before the run so MB/job is measured at the
# Evomi meter (the NIC double-counts — see CLAUDE.md).
cd /Users/seolocalph/projects/device-agent
# Per-job OK/ERR lines land in daily_auto_<date>.log; dailyfull_<date>.log only
# carries the driver stages (build, launch, consolidate). Watch both.
L=/private/tmp/daily_auto_2026-08-31.log
DRV=/private/tmp/dailyfull_2026-08-31.log
BASE=62391.79
cnt() { local n; n=$(grep -cE "$1" "$L" 2>/dev/null | head -1); [ -z "$n" ] && n=0; echo "$n"; }
last_ok=0; bad=0; said_fleet=0; said_jobs=0; hot=0
while true; do
  ok=$(cnt '\] OK '); err=$(cnt '\] ERR ')
  bal=$(python3 ./evomi_balance.py 2>/dev/null); [ -z "$bal" ] && bal=ERR

  if ! pgrep -f "[d]aily_full_auto" >/dev/null 2>&1; then
    echo "NIGHTLY 08-31 ENDED $(date '+%T') ok=$ok err=$err balance=${bal}MB"
    grep -E "ALL DONE|FATAL|ALL SUCCESS|NO PROGRESS|consolidate rc=" "$DRV" "$L" 2>/dev/null | tail -4
    ls -la ~/Desktop/Daily/aug31*.csv 2>/dev/null | awk '{print "  shipped: "$NF" "$5"B"}'
    break
  fi

  # one-shot: plan size and the pruned fleet (confirm samsung device-101 is absent)
  if [ "$said_jobs" -eq 0 ]; then
    j=$(grep -oE "plan job count ok: [0-9]+" "$DRV" 2>/dev/null | tail -1)
    [ -n "$j" ] && { echo "08-31 $j"; said_jobs=1; }
    f=$(grep -E "FATAL" "$DRV" 2>/dev/null | tail -1)
    [ -n "$f" ] && echo "*** $f"
  fi
  if [ "$said_fleet" -eq 0 ]; then
    o=$(grep -oE "phones: MAX_PARALLEL.*" "$DRV" 2>/dev/null | tail -1)
    [ -n "$o" ] && { echo "08-31 fleet: $o"; said_fleet=1; }
  fi

  case "$bal" in ERR) :;; *)
    [ "${bal%.*}" -lt 5000 ] 2>/dev/null && echo "*** BALANCE LOW ${bal}MB ok=$ok err=$err"
    # Aug-29 cost blowout signature: >6 MB/job sustained (normal daily is ~2.2)
    tot=$((ok+err))
    if [ "$tot" -gt 200 ]; then
      d=$(python3 -c "print(f'{($BASE-$bal)/$tot:.1f}')" 2>/dev/null)
      big=$(python3 -c "print(1 if ($BASE-$bal)/$tot > 6 else 0)" 2>/dev/null)
      [ "$big" = "1" ] && { hot=$((hot+1)); [ "$hot" -eq 3 ] && echo "*** COST BLOWOUT 08-31 ${d} MB/job (normal 2.2) ok=$ok err=$err bal=${bal}MB"; } || hot=0
    fi
  ;; esac

  rem=$(grep -oE "remaining=[0-9]+" "$L" 2>/dev/null | tail -1 | cut -d= -f2); [ -z "$rem" ] && rem=9999
  if [ "$err" -gt 5 ] && [ "$ok" -eq "$last_ok" ] && [ "$rem" -gt 20 ]; then
    bad=$((bad+1)); [ "$bad" -ge 3 ] && { echo "*** STALLED 08-31 ok frozen at $ok err=$err remaining=$rem"; bad=0; }
  else bad=0; fi

  if [ $((ok/400)) -gt $((last_ok/400)) ]; then
    d=$(python3 -c "print(f'{($BASE-$bal)/max($ok+$err,1):.1f}')" 2>/dev/null)
    echo "progress 08-31 ok=$ok err=$err balance=${bal}MB (${d} MB/job)"
  fi
  last_ok=$ok
  sleep 300
done
