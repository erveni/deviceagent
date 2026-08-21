#!/bin/bash
# Fleet mutex — one fleet-using run (daily OR ranking) at a time.
#
# Why: daily_full_auto's fleet-idle gate only pgrep'd for a live run_rolling_plan.
# A resumed run has gaps between its REMAIN rounds where no such process exists, so
# the 20:00 auto-daily slipped through the gate and ran concurrently with a manual
# catch-up — both cross-wired the fleet (2026-08-21 overlap thrash). A lock held for
# the WHOLE run lifetime closes that gap: the second run blocks until the first frees.
#
# Fail-safe by design: a lock whose holder PID is dead is treated as stale and taken;
# acquire waits at most ~2h then forces, so a bug can never deadlock the fleet;
# release only removes a lock this shell owns.
FLEET_LOCK="${FLEET_LOCK:-/tmp/fleet.lock}"

fleet_lock_release(){
  [ -f "$FLEET_LOCK" ] && [ "$(cut -d' ' -f1 "$FLEET_LOCK" 2>/dev/null)" = "$$" ] && rm -f "$FLEET_LOCK"
  return 0
}

fleet_lock_acquire(){   # $1 = label (e.g. daily-2026-08-21)
  local label="${1:-run}" waited=0 pid
  while [ -f "$FLEET_LOCK" ]; do
    pid=$(cut -d' ' -f1 "$FLEET_LOCK" 2>/dev/null)
    if [ -z "$pid" ] || [ "$pid" = "$$" ] || ! kill -0 "$pid" 2>/dev/null; then
      break   # empty, ours, or holder is dead -> stale, take it
    fi
    [ $((waited % 60)) -eq 0 ] && echo "[fleet-lock] $label waiting — held by $(cat "$FLEET_LOCK" 2>/dev/null)"
    sleep 10; waited=$((waited + 10))
    if [ "$waited" -ge 7200 ]; then
      echo "[fleet-lock] $label waited 2h — forcing (holder pid=$pid may be hung)"; break
    fi
  done
  echo "$$ $label $(date +%s)" > "$FLEET_LOCK"
  trap 'fleet_lock_release' EXIT
  echo "[fleet-lock] $label acquired (pid $$)"
}
