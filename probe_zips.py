#!/usr/bin/env python3
"""Probe every unique zip from clients_audit_targets.json against Decodo.

For each zip, attempt a zip-tier upstream probe (single TCP connect via SOCKS5).
Cache result to /tmp/decodo_zip_cache.json:

  {
    "11211": {
      "supported": true,
      "fallback_region": "new_york",
      "probed_at": "2026-05-13T21:00:00Z"
    },
    "37402": {
      "supported": false,
      "fallback_region": "tennessee",
      "probed_at": "2026-05-13T21:00:00Z"
    }
  }

Run before a batch to know which zips will use zip-tier vs region-tier.
The dispatcher will short-circuit to region-tier for "supported: false" zips
(skips the per-job probe + ensures correct tier from the start).
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/Users/seolocalph/projects/aeo-appium")
from gost_manager import (  # type: ignore
    _probe_decodo_upstream,
    _random_session_id,
    build_upstream_username,
    resolve_region,
)

CLIENTS_JSON = os.environ.get(
    "AUDIT_CLIENTS_JSON_PATH",
    "/Users/seolocalph/projects/aeo-appium/clients_audit_targets.json",
)
CACHE_PATH = Path("/tmp/decodo_zip_cache.json")
PROBE_DURATION = 30  # match the session duration audits use

# Load existing cache if present (so re-runs only re-probe stale entries)
cache: dict[str, dict] = {}
if CACHE_PATH.exists():
    cache = json.loads(CACHE_PATH.read_text())

with open(CLIENTS_JSON) as f:
    clients = json.load(f)

# Build unique (zip, state) set
unique = {}
for c in clients:
    z = (c.get("proxy") or {}).get("zip", "") or ""
    st = (c.get("state") or "").upper()
    if z and z not in unique:
        unique[z] = st

print(f"Found {len(unique)} unique zips across {len(clients)} clients")
print()

now = datetime.now(timezone.utc).isoformat()
probed = 0
supported_count = 0
skipped_count = 0

for zip_code, state in sorted(unique.items()):
    # Skip if cache entry is fresh (<24h old)
    existing = cache.get(zip_code)
    if existing and (datetime.now(timezone.utc) - datetime.fromisoformat(existing["probed_at"])).total_seconds() < 86400:
        skipped_count += 1
        continue

    region = resolve_region(state)
    probe_sid = _random_session_id()
    zip_user = build_upstream_username(
        zip_code=zip_code, country="us",
        session_duration=PROBE_DURATION, session_id=probe_sid,
    )
    ok = _probe_decodo_upstream(zip_user)
    cache[zip_code] = {
        "supported": ok,
        "state": state,
        "fallback_region": region,
        "probed_at": now,
    }
    if ok:
        supported_count += 1
        status = "✓ zip"
    else:
        status = f"✗ → region={region}"
    print(f"  {zip_code} ({state:2}): {status}")
    probed += 1
    time.sleep(0.4)  # space out probes to avoid Decodo rate-limit

# Persist cache
CACHE_PATH.write_text(json.dumps(cache, indent=2))

print()
print(f"Probed: {probed} new ({supported_count} zip-supported)")
print(f"Skipped (cached <24h): {skipped_count}")
print(f"Total cached: {len(cache)}")
print(f"Saved to: {CACHE_PATH}")
