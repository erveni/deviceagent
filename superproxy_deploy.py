#!/usr/bin/env python3
"""Deploy + validate the SuperProxy/Decodo Mobile stack across the fleet.

For each target phone (online phones in run_with_proxy.DEVICES):
  1. install the device-agent APK (com.farm…, patched build) if missing
  2. install SuperProxy (com.scheler.superproxy, multi-APK bundle) if missing
  3. enable BOTH accessibility services (old com.deviceagent + new agent)
  4. superproxy_proxy.setup() — bring the Decodo Mobile tunnel up
  5. record tun0 + result, then teardown (pm clear) to leave a clean state

VALIDATE-ONLY: it does not run daily/audit jobs. Model-specific UI issues
(TECNO/Samsung VPN-dialog tap, ad-dismiss) surface as per-phone failures in the
report rather than as damage. Re-runnable; installs are skipped where present.

Usage:
    SUPERPROXY_PASS=… python3.13 superproxy_deploy.py            # all online phones
    SUPERPROXY_PASS=… python3.13 superproxy_deploy.py --only 0 7 # DEVICES indices
    SUPERPROXY_PASS=… python3.13 superproxy_deploy.py --workers 1
"""
from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import superproxy_proxy as sp
from run_with_proxy import DEVICES, run, get_online_serials

NEW_AGENT_APK = os.environ.get("NEW_AGENT_APK", "/tmp/device-agent-superproxy-5237491-debug.apk")
SUPERPROXY_DIR = os.path.expanduser(os.environ.get("SUPERPROXY_DIR", "~/Downloads/split_config.arm64_v8a"))
SUPERPROXY_SPLITS = ["base.apk", "split_config.arm64_v8a.apk", "split_config.en.apk", "split_config.xhdpi.apk"]
OLD_ACCESSIBILITY = "com.deviceagent/com.deviceagent.AgentAccessibilityService"


def _installed(serial: str, pkg: str) -> bool:
    r = run(f'adb -s "{serial}" shell pm list packages', 15)
    return pkg in r.stdout


def deploy_one(device_idx: int, *, teardown: bool = True) -> dict:
    try:
        return _deploy_one(device_idx, teardown=teardown)
    except Exception as e:
        # Never let one phone's failure (e.g. an adb install timeout on a slow
        # wireless TECNO) abort the whole batch.
        device_id, serial = DEVICES[device_idx]
        return {"device": device_id, "serial": serial, "ok": False,
                "steps": [f"exception={type(e).__name__}: {str(e)[:80]}"]}


def _deploy_one(device_idx: int, *, teardown: bool = True) -> dict:
    device_id, serial = DEVICES[device_idx]
    res = {"device": device_id, "serial": serial, "steps": [], "ok": False}

    def step(name, cond, detail=""):
        res["steps"].append(f"{name}={'ok' if cond else 'FAIL'}{(' ' + detail) if detail else ''}")
        return cond

    # 1. install device-agent (new) if missing
    if _installed(serial, sp.AGENT_PKG):
        step("new_agent", True, "present")
    else:
        r = run(f'adb -s "{serial}" install -r -g "{NEW_AGENT_APK}"', 300)  # slow wireless TECNOs
        if not step("new_agent", "Success" in r.stdout, r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[:80]):
            return res

    # 2. install SuperProxy (multi-APK) if missing
    if _installed(serial, sp.SUPERPROXY_PKG):
        step("superproxy", True, "present")
    else:
        splits = " ".join(f'"{os.path.join(SUPERPROXY_DIR, s)}"' for s in SUPERPROXY_SPLITS)
        r = run(f'adb -s "{serial}" install-multiple -r {splits}', 300)
        if not step("superproxy", "Success" in r.stdout, r.stderr[:80]):
            return res

    # 3. enable BOTH accessibility services
    both = f"{OLD_ACCESSIBILITY}:{sp.ACCESSIBILITY_SERVICE}"
    run(f'adb -s "{serial}" shell settings put secure enabled_accessibility_services "{both}"', 8)
    run(f'adb -s "{serial}" shell settings put secure accessibility_enabled 1', 8)
    run(f'adb -s "{serial}" shell am start -n {sp.AGENT_PKG}/.MainActivity', 10)
    time.sleep(4)
    up, detail = sp.ensure_agent_up(serial, device_idx)
    step("agent_health", up, detail)

    # 4. bring up the proxy
    ok, info = sp.setup(serial, device_idx)
    step("proxy_setup", ok, info.get("reason", "") if not ok else
         f"tun0={info.get('tun0_ip')} user={info.get('username')} attempts={info.get('attempts')}")
    res["info"] = info
    res["ok"] = ok

    # 5. leave clean
    if teardown:
        try:
            sp.teardown(serial)
        except Exception:
            pass
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=int, nargs="*", help="DEVICES indices to target (default: all online)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--keep-up", action="store_true", help="don't teardown after validation (leave proxy connected)")
    args = ap.parse_args()

    if not os.environ.get("SUPERPROXY_PASS"):
        print("ERROR: SUPERPROXY_PASS not set"); return 2
    if not os.path.exists(NEW_AGENT_APK):
        print(f"ERROR: agent APK not found: {NEW_AGENT_APK}"); return 2

    online = get_online_serials()
    targets = args.only if args.only is not None else [
        i for i, (_, ser) in enumerate(DEVICES) if ser in online
    ]
    targets = [i for i in targets if DEVICES[i][1] in online]
    print(f"[deploy] targets: {[DEVICES[i][0] for i in targets]} (workers={args.workers}, teardown={not args.keep_up})", flush=True)

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(deploy_one, i, teardown=not args.keep_up): i for i in targets}
        for f in as_completed(futs):
            r = f.result()
            results.append(r)
            mark = "PASS" if r["ok"] else "FAIL"
            print(f"  [{mark}] {r['device']}: {' | '.join(r['steps'])}", flush=True)

    print("\n=== DEPLOY REPORT ===")
    results.sort(key=lambda r: r["device"])
    npass = sum(1 for r in results if r["ok"])
    for r in results:
        print(f"  {'PASS' if r['ok'] else 'FAIL'}  {r['device']:11} {' | '.join(r['steps'])}")
    print(f"\n{npass}/{len(results)} phones brought the SuperProxy tunnel up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
