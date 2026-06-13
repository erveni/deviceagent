#!/usr/bin/env python3
"""Probe every phone's on-device app server and report which are usable.

For each device in device_dispatch.DEVICES, ensure the adb port-forward exists
and GET http://127.0.0.1:{8765+idx}/health. A phone is "good" if adb-reachable
AND health==200. Prints two shell-eval'able lines:

    DOWN=device-114,device-107      # comma list of unusable phones (DEVICE_EXCLUDE)
    GOOD=13                          # count of usable phones (MAX_PARALLEL)

Used by run_daily_auto.sh so a run automatically excludes dead phones and sizes
parallelism to whatever is actually up — no hardcoded exclude list to rot.
"""
import subprocess, sys, urllib.request
from device_dispatch import DEVICES


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


down, good = [], 0
for i, (label, ser) in enumerate(DEVICES):
    if probe(ser, 8765 + i):
        good += 1
    else:
        down.append(label)
    print(f"  {label}: {'GOOD' if label not in down else 'DOWN'}", file=sys.stderr)

print(f"DOWN={','.join(down)}")
print(f"GOOD={good}")
