#!/usr/bin/env python3
"""Fleet smoke test over SuperProxy: one DAILY + one RANKING (dummy Mae's
Childcare data) per phone, phones run in parallel.

Each phone, sequentially: daily session, then ranking audit — both self-contained
(setup() -> /session -> teardown()) so they exercise the full per-job proxy
lifecycle. Across phones it fans out with a thread pool. Writes CSV rows and
prints a per-phone summary.

Usage:
    SUPERPROXY_PASS=… python3.13 superproxy_fleet_test.py                 # all online
    SUPERPROXY_PASS=… python3.13 superproxy_fleet_test.py --only 5 7 --workers 2
    SUPERPROXY_PASS=… python3.13 superproxy_fleet_test.py --platform chatgpt
"""
from __future__ import annotations

import argparse
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from run_with_proxy import DEVICES, get_online_serials
import superproxy_dispatch as sd

DAILY_CSV = "/tmp/fleet_daily.csv"
AUDIT_CSV = "/tmp/fleet_audit.csv"


def run_phone(device_idx: int, platform: str) -> dict:
    device_id = DEVICES[device_idx][0]
    out = {"device": device_id, "daily": "?", "daily_dur": 0, "audit": "?", "rank": "", "audit_dur": 0}
    try:
        d = sd.dispatch_one_job_superproxy(
            {**sd._dummy_daily_job(), "platform": platform}, csv_path=DAILY_CSV, device_idx=device_idx)
        out["daily"] = d.get("status"); out["daily_dur"] = d.get("duration_s")
        if d.get("status") != "success":
            out["daily"] += f" ({d.get('failure_step') or d.get('error')})"
    except Exception as e:
        out["daily"] = f"exc:{type(e).__name__}"
    try:
        a = sd.dispatch_audit_job_superproxy(
            sd._dummy_audit_job(), platform, csv_path=AUDIT_CSV, device_idx=device_idx)
        out["audit"] = a.get("status"); out["audit_dur"] = a.get("duration_s")
        fs = a.get("failure_step", "")
        if "rank=" in fs:
            out["rank"] = fs.split("rank=")[1].split()[0]
        if a.get("status") != "success":
            out["audit"] += f" ({fs or a.get('error')})"
    except Exception as e:
        out["audit"] = f"exc:{type(e).__name__}"
    print(f"  [{device_id}] daily={out['daily']} ({out['daily_dur']}s) | "
          f"audit={out['audit']} rank={out['rank']} ({out['audit_dur']}s)", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=int, nargs="*")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--platform", default="chatgpt", choices=["chatgpt", "gemini", "perplexity"])
    args = ap.parse_args()
    if not os.environ.get("SUPERPROXY_PASS"):
        print("ERROR: SUPERPROXY_PASS not set"); return 2

    online = get_online_serials()
    targets = args.only if args.only is not None else list(range(len(DEVICES)))
    targets = [i for i in targets if DEVICES[i][1] in online]
    print(f"[fleet-test] {[DEVICES[i][0] for i in targets]} platform={args.platform} workers={args.workers}", flush=True)

    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(run_phone, i, args.platform) for i in targets]
        for f in as_completed(futs):
            rows.append(f.result())

    rows.sort(key=lambda r: r["device"])
    dn = sum(1 for r in rows if r["daily"] == "success")
    an = sum(1 for r in rows if r["audit"] == "success")
    print("\n=== FLEET TEST REPORT ===")
    for r in rows:
        print(f"  {r['device']:11} daily={r['daily']:<28} audit={r['audit']:<28} rank={r['rank']}")
    print(f"\nDAILY  {dn}/{len(rows)} success    RANKING  {an}/{len(rows)} success")
    print(f"CSVs: {DAILY_CSV}* {AUDIT_CSV}*")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
