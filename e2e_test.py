#!/usr/bin/env python3
"""E2E test of the FULL CitedLogic capture pipeline on ONE pinned phone.

Exercises the real production path: CSV -> load_jobs -> run_one -> capture_ai
(dispatch through proxy for AI / uule no-proxy for google-maps) -> single-screen
screenshot + cleaned text -> upload. Defaults to LOCAL_ONLY (writes citedlogic_local/,
no S3) so the output can be eyeballed before anything is uploaded.

Usage:
  set -a; source .env.dev; set +a
  export PROXY_HOST=gate.decodo.com PROXY_PORT=10001 PROXY_PASSWORD="$PROXY_PASS" USE_SNI_RELAY=0
  python3 e2e_test.py                 # LOCAL_ONLY, /tmp/cl_e2e.csv, device-114
  CL_LOCAL_ONLY=0 python3 e2e_test.py # real S3 upload
"""
import os
import sys

os.environ.setdefault("CL_CSV", "/tmp/cl_e2e.csv")
os.environ.setdefault("CL_LOCAL_ONLY", "1")
os.environ.setdefault("WORKERS", "1")          # one phone → sequential
os.environ.setdefault("CL_AWS_PROFILE", "aeo-admin")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SERIAL = os.environ.get(
    "E2E_SERIAL", "adb-1490455572007706-HQWNyz (2)._adb-tls-connect._tcp"
)

# Pin the device pool to the single test phone BEFORE device_dispatch snapshots it.
import run_with_proxy
run_with_proxy.DEVICES[:] = [("device-114", SERIAL)]

# Import the worktree's audit_dispatch_http first so its capture-mode copy wins
# over the stale one on the main checkout's sys.path.
import audit_dispatch_http
assert "device-agent-citedlogic" in audit_dispatch_http.__file__, audit_dispatch_http.__file__

import citedlogic_capture
citedlogic_capture.main()
