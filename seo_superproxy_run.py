#!/usr/bin/env python3
"""Run one SEO (Google SERP) job through the REAL device-agent mobile-proxy path:
the farm agent (com.farm…) drives the SuperProxy app (com.scheler.superproxy),
which opens a single VPN tunnel straight from the phone to Decodo Mobile — a stable
US cellular egress IP, no Mac/gost in the data path (which is why gost got
ERR_CONNECTION_RESET but this won't).

Lifecycle (mirrors superproxy_dispatch.dispatch_audit_job_superproxy):
    POOL.setup_forwards()  -> sp.setup(serial, idx)  [mobile tunnel up, tun0 verified]
    -> POST /session type=seo to com.deviceagent (8765)  [Chrome egresses via tun0]
    -> sp.teardown(serial)  [pm clear com.scheler.superproxy]

Dummy test data only. Env: source .env.dev (carries SUPERPROXY_USER/PASS).

Usage:
    set -a; source .env.dev; set +a
    SEO_HTTP_TIMEOUT_S=420 python3 seo_superproxy_run.py --device-idx 0 \
        --keyword "best coffee shop austin" --target epoch.coffee
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import superproxy_proxy as sp
import superproxy_dispatch as spd
import seo_dispatch as sd
from run_with_proxy import DEVICES


def main() -> int:
    ap = argparse.ArgumentParser(description="SEO job via the SuperProxy (Decodo Mobile) path.")
    ap.add_argument("--device-idx", type=int, default=0, help="0 = device-101 (Samsung)")
    ap.add_argument("--keyword", default="best coffee shop austin")
    ap.add_argument("--target", default="epoch.coffee")
    ap.add_argument("--out", default="/tmp/seo_superproxy")
    args = ap.parse_args()

    if not os.environ.get("SUPERPROXY_PASS"):
        print("ERROR: SUPERPROXY_PASS not set — run `set -a; source .env.dev; set +a`")
        return 2

    device_id, serial = DEVICES[args.device_idx]
    print(f"[seo-sp] {device_id} ({serial}) — bringing up Decodo Mobile tunnel via SuperProxy app")

    spd.POOL.setup_forwards()
    ok, info = sp.setup(serial, args.device_idx)
    if not ok:
        print(f"[seo-sp] superproxy setup FAILED: {info.get('reason')}")
        return 1
    print(f"[seo-sp] mobile tunnel UP — tun0={info.get('tun0_ip')} user={info.get('username')} "
          f"attempts={info.get('attempts')}")

    try:
        port = spd._old_agent_local_port(args.device_idx)  # com.deviceagent /session
        summary = sd.dispatch_one(serial, args.keyword, args.target, Path(args.out),
                                  local_port=port, retries=0)
        summary["tun0_ip"] = info.get("tun0_ip")
        sd._print_summary(summary)
        print(f"[seo-sp] egress tun0={info.get('tun0_ip')}")
        return 0 if summary.get("status") == "completed" else 1
    finally:
        try:
            sp.teardown(serial)
            print("[seo-sp] teardown done (SuperProxy cleared)")
        except Exception as e:
            print(f"[seo-sp] teardown warn: {e}")


if __name__ == "__main__":
    raise SystemExit(main())
