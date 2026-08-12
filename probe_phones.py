#!/usr/bin/env python3
"""Probe every phone's on-device app server and report which are usable.

For each device in device_dispatch.DEVICES, ensure the adb port-forward exists
and GET http://127.0.0.1:{8765+idx}/health. A phone is "good" if adb-reachable
AND health==200. Prints two shell-eval'able lines:

    DOWN=device-114,device-107      # comma list of unusable phones (DEVICE_EXCLUDE)
    GOOD=13                          # count of usable phones (MAX_PARALLEL)

Used by run_daily_auto.sh so a run automatically excludes dead phones and sizes
parallelism to whatever is actually up — no hardcoded exclude list to rot.

Serial-flap resilience: adb-over-wifi drops leave a phone advertising under a
different serial than the one hardcoded in DEVICES — the mDNS " (2)" duplicate
suffix, a rotated trailing hash, or an ephemeral ip:port after `adb connect`.
Probing the stale DEVICES serial then fails with get-state != device and the
(healthy) phone is falsely marked DOWN, which under-counts GOOD and starves the
run. So resolve each DEVICES entry to its CURRENTLY-ONLINE serial by hardware
core (the token after "adb-", stable across flaps) before probing — matching
run_with_proxy.py's _hw_core so probe and the runner agree on what is up.
"""
import subprocess, sys, urllib.request
from device_dispatch import DEVICES


def _hw_core(s):
    """Stable hardware id from an mDNS adb serial (token after "adb-"). The mDNS
    wrapper rotates the trailing hash and a " (N)" duplicate counter on every
    reconnect, but this id never changes. ip:port serials carry no id, so their
    hardware id is resolved separately via getprop."""
    return s.split("-")[1] if s.startswith("adb-") else s.strip()


def _online_by_core():
    """Map hardware-core -> currently-online adb serial. mDNS-name serials map
    directly by _hw_core; ip:port serials are resolved by querying the device's
    ro.serialno so a phone reconnected via `adb connect ip:port` still matches."""
    out = subprocess.run(["adb", "devices"], capture_output=True, text=True).stdout
    online = [l.split("\t")[0] for l in out.splitlines() if "\tdevice" in l]
    by_core = {}
    for s in online:
        if s.startswith("adb-"):
            by_core.setdefault(_hw_core(s), s)
    # resolve ip:port serials (no embedded hw id) via getprop
    dev_cores = {_hw_core(ser) for _, ser in DEVICES}
    for s in online:
        if s.startswith("adb-"):
            continue
        hwid = subprocess.run(["adb", "-s", s, "shell", "getprop", "ro.serialno"],
                              stdin=subprocess.DEVNULL, capture_output=True, text=True).stdout.strip()
        core = next((c for c in dev_cores if hwid and hwid in c), None)
        if core and core not in by_core:
            by_core[core] = s
    return by_core


def probe(ser, port):
    subprocess.run(["adb", "-s", ser, "forward", f"tcp:{port}", "tcp:8765"],
                   capture_output=True)
    st = subprocess.run(["adb", "-s", ser, "get-state"],
                        capture_output=True, text=True).stdout.strip()
    if st != "device":
        return False
    try:
        return urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=4).status == 200
    except urllib.error.HTTPError as e:
        return e.code == 200
    except Exception:
        return False


online_by_core = _online_by_core()
down, good = [], 0
for i, (label, ser) in enumerate(DEVICES):
    # probe the phone's LIVE serial (resolved by hw-core), not the stale DEVICES one
    live = online_by_core.get(_hw_core(ser), ser)
    if probe(live, 8765 + i):
        good += 1
    else:
        down.append(label)
    print(f"  {label}: {'GOOD' if label not in down else 'DOWN'}", file=sys.stderr)

print(f"DOWN={','.join(down)}")
print(f"GOOD={good}")
