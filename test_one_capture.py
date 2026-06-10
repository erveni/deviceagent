#!/usr/bin/env python3
"""One-off: run a single CitedLogic capture job through the FULL proxied dispatch
path (gost + SocksDroid + residential exit) on ONE pinned phone.

Usage:
  set -a; source .env.dev; set +a
  export PROXY_HOST=gate.decodo.com PROXY_PORT=10001 PROXY_PASSWORD="$PROXY_PASS" USE_SNI_RELAY=0
  python3 test_one_capture.py <engine> "<prompt>" <metro> <lat> <lng> [serial]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

engine = sys.argv[1] if len(sys.argv) > 1 else "gemini"
prompt = sys.argv[2] if len(sys.argv) > 2 else "best med spa near me"
metro = sys.argv[3] if len(sys.argv) > 3 else "atlanta-ga"
lat = float(sys.argv[4]) if len(sys.argv) > 4 else 33.749
lng = float(sys.argv[5]) if len(sys.argv) > 5 else -84.388
serial = sys.argv[6] if len(sys.argv) > 6 else \
    "adb-1490455572007706-HQWNyz (2)._adb-tls-connect._tcp"

import run_with_proxy
# Pin the pool to the one test phone BEFORE device_dispatch snapshots DEVICES.
run_with_proxy.DEVICES[:] = [("device-114", serial)]

# Import audit_dispatch_http FIRST so sys.modules holds the worktree copy before
# citedlogic_capture's sys.path.insert can shadow it with another checkout's copy.
import audit_dispatch_http
print("[test] audit_dispatch_http =", audit_dispatch_http.__file__, flush=True)
assert "device-agent-citedlogic" in audit_dispatch_http.__file__, "wrong audit_dispatch_http imported!"
dispatch_audit_job = audit_dispatch_http.dispatch_audit_job

from citedlogic_capture import metro_state, _STATE_GOOD_ZIP, _FALLBACK_GOOD_ZIP, SYNTH_ID_BASE

st = metro_state(metro)
job = {
    "client_id": 0, "keyword_id": SYNTH_ID_BASE + 1, "campaign_id": str(SYNTH_ID_BASE + 1),
    "biz_name": "", "biz_url": "", "city": metro, "state": st,
    "zip": _STATE_GOOD_ZIP.get(st, _FALLBACK_GOOD_ZIP),
    "keyword": prompt,
    "mock_lat": lat, "mock_lng": lng,
    "mode": "citedlogic_capture",
    "targetDate": "2026-06-10T18:00:00-07:00",
}
print(f"[test] engine={engine} metro={metro} zip={job['zip']} serial={serial}", flush=True)
row = dispatch_audit_job(job, platform=engine, csv_path=None, capture_prompt=prompt)
out = {k: (v[:300] + "..." if isinstance(v, str) and len(v) > 300 else v) for k, v in row.items()}
print(json.dumps(out, indent=2, default=str))
