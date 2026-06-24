#!/usr/bin/env python3
"""Probe an expanded set of US zips against Decodo and cache results.

Includes:
1. All zips from clients_audit_targets.json (current client set)
2. Top US metro zips (for future client onboarding)
3. Nearby zips for any unsupported zip in (1) — found via api.zippopotam.us

Output: /tmp/decodo_zip_cache.json with structure:
  {
    "11211": {
      "supported": true,
      "state": "NY",
      "fallback_region": "new_york",
      "nearest_supported_zip": "11211",   # self when supported
      "probed_at": "2026-05-13T22:00:00Z"
    },
    "37402": {
      "supported": false,
      "state": "TN",
      "fallback_region": "tennessee",
      "nearest_supported_zip": "37411",   # found via nearby probe
      "probed_at": "..."
    }
  }
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
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
PROBE_DURATION = 30

# Top US metro zips — covers NYC, LA, Chicago, Houston, Dallas, Phoenix, Philly, etc.
# These are common audit-client locations so caching them upfront avoids the per-job probe.
TOP_METROS = {
    # NY
    "NY": ["10001","10002","10003","10010","10011","10019","10022","10025","10036","11201","11211","11215","11217","11217"],
    # CA
    "CA": ["90001","90012","90024","90025","90028","90035","90210","90211","90402","90403","92101","92103","92122","94102","94103","94110","94111","94117","95101","95110"],
    # IL
    "IL": ["60601","60606","60610","60611","60614","60622","60654","60657","60661"],
    # TX
    "TX": ["75201","75204","75206","75219","75225","75240","77002","77004","77019","77024","77027","77056","78201","78215","78216","78230","78701","78703","78704"],
    # AZ
    "AZ": ["85001","85006","85012","85016","85020","85308","85331"],
    # PA
    "PA": ["19102","19103","19106","19107","19130","19146","15201","15217","15222"],
    # FL
    "FL": ["33101","33125","33130","33145","33178","32801","32803","32806","33602","33606","33609"],
    # OH
    "OH": ["43215","44113","44114","45202"],
    # GA
    "GA": ["30303","30305","30309","30318","30327","30339","30342","30350","30326"],
    # NC
    "NC": ["27601","27604","27607","28202","28204","28209"],
    # MA
    "MA": ["02108","02114","02116","02118","02134","02139","02144"],
    # WA
    "WA": ["98101","98103","98105","98109","98115","98121","98144"],
    # CO
    "CO": ["80202","80203","80205","80209","80216"],
    # MD
    "MD": ["21201","21210","21218","21230","20815","20817"],
    # VA
    "VA": ["22101","22102","22201","22203","22301"],
    # MI
    "MI": ["48201","48202","48207","48226"],
    # MO
    "MO": ["63101","63103","63105","64101","64108"],
    # MN
    "MN": ["55101","55102","55401","55403","55410"],
    # IN
    "IN": ["46202","46204","46208","46220","46278"],
    # TN
    "TN": ["37203","37204","37205","37206","37211","37402","37411","37416","37421","38103","38104","38117"],
    # KY
    "KY": ["40202","40204","40207","40217","40299"],
    # NJ
    "NJ": ["07102","07306","07310","08540","08901"],
    # WI
    "WI": ["53202","53204","53211","53217"],
    # OR
    "OR": ["97201","97205","97209","97214","97232"],
    # NV
    "NV": ["89101","89109","89117","89123"],
    # UT
    "UT": ["84101","84102","84109","84111"],
    # SC
    "SC": ["29201","29401","29403","29407"],
}


def get_nearby_zips_in_state(zip_code: str, state: str, n: int = 5) -> list[str]:
    """Get up to n nearby zips in the same state via api.zippopotam.us.
    Crude approach: increment/decrement the zip number by ±5 and see which are valid."""
    try:
        z = int(zip_code)
    except Exception:
        return []
    candidates = []
    for delta in (-5, -4, -3, -2, -1, 1, 2, 3, 4, 5):
        cand = f"{z + delta:05d}"
        if cand == zip_code:
            continue
        try:
            with urllib.request.urlopen(f"https://api.zippopotam.us/us/{cand}", timeout=3) as r:
                data = json.loads(r.read())
                place = data.get("places", [{}])[0]
                if (place.get("state abbreviation") or "").upper() == state.upper():
                    candidates.append(cand)
                    if len(candidates) >= n:
                        break
        except Exception:
            continue
        time.sleep(0.2)
    return candidates


# Load existing cache
cache: dict[str, dict] = {}
if CACHE_PATH.exists():
    cache = json.loads(CACHE_PATH.read_text())

# 1. Collect every zip we want to probe
target_zips: dict[str, str] = {}  # zip → state

# from clients
with open(CLIENTS_JSON) as f:
    for c in json.load(f):
        z = (c.get("proxy") or {}).get("zip", "") or ""
        st = (c.get("state") or "").upper()
        if z:
            target_zips[z] = st

# from top metros
for st, zips in TOP_METROS.items():
    for z in zips:
        if z not in target_zips:
            target_zips[z] = st

print(f"Target set: {len(target_zips)} zips before nearby expansion")

# 2. Probe everything not already cached fresh (<24h)
def is_stale(entry: dict) -> bool:
    try:
        ts = datetime.fromisoformat(entry["probed_at"])
        return (datetime.now(timezone.utc) - ts).total_seconds() > 86400
    except Exception:
        return True


def probe_one(z: str, st: str) -> bool:
    """Probe a zip; updates cache; returns whether it's supported."""
    region = resolve_region(st)
    probe_sid = _random_session_id()
    user = build_upstream_username(
        zip_code=z, country="us",
        session_duration=PROBE_DURATION, session_id=probe_sid,
    )
    ok = _probe_decodo_upstream(user)
    cache[z] = {
        "supported": ok,
        "state": st,
        "fallback_region": region,
        "nearest_supported_zip": z if ok else cache.get(z, {}).get("nearest_supported_zip", ""),
        "probed_at": datetime.now(timezone.utc).isoformat(),
    }
    return ok


probed = 0
new_supported = 0
for z, st in sorted(target_zips.items()):
    if z in cache and not is_stale(cache[z]):
        continue
    ok = probe_one(z, st)
    probed += 1
    if ok:
        new_supported += 1
        sym = "✓"
    else:
        sym = "✗"
    print(f"  {z} ({st}): {sym}")
    time.sleep(0.3)

# 3. For each unsupported zip with valid US format, probe nearby zips and pick nearest supported
print()
print("=== Nearby-zip fallback for unsupported zips ===")
unsupported = [(z, info["state"]) for z, info in cache.items()
               if not info.get("supported") and z.isdigit() and len(z) == 5]

# Filter: only do this for unsupported zips that are in our actual client set
client_zips = set()
with open(CLIENTS_JSON) as f:
    for c in json.load(f):
        z = (c.get("proxy") or {}).get("zip", "") or ""
        if z:
            client_zips.add(z)

unsupported_clients = [(z, st) for z, st in unsupported if z in client_zips]

for z, st in unsupported_clients:
    if cache[z].get("nearest_supported_zip"):
        continue
    nearby = get_nearby_zips_in_state(z, st, n=5)
    print(f"  {z} ({st}): probing {len(nearby)} nearby zips ({nearby})")
    found = ""
    for cand in nearby:
        if cand in cache and cache[cand].get("supported"):
            found = cand
            break
        if cand not in cache:
            ok = probe_one(cand, st)
            probed += 1
            time.sleep(0.3)
            if ok:
                new_supported += 1
                found = cand
                break
    if found:
        cache[z]["nearest_supported_zip"] = found
        print(f"     → nearest_supported_zip = {found}")
    else:
        print(f"     → no nearby supported zip found; will use region fallback")

# Persist
CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True))

# Summary
print()
print(f"Probed this run: {probed} (newly supported: {new_supported})")
print(f"Total in cache:  {len(cache)}")
supported_total = sum(1 for v in cache.values() if v.get("supported"))
print(f"  supported:     {supported_total}")
print(f"  unsupported:   {len(cache) - supported_total}")
print(f"Saved to: {CACHE_PATH}")
