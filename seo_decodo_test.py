#!/usr/bin/env python3
"""E2E: Decodo US tunnel (socksdroid + gost HTTP-connector) + the new type:seo
flow with `location` → uule. Verifies the SERP is city-accurate (local pack +
organic) on a real US residential IP. No NordVPN.

  set -a; source .env.dev; set +a
  python3 seo_decodo_test.py            # San Francisco
  LOC="Austin, Texas" python3 seo_decodo_test.py
"""
import base64
import json
import os
import sys
import urllib.request

os.environ.setdefault("MAC_IP", "192.168.0.102")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import run_with_proxy as rwp

# device-106 (HQWNyz) — fix DEVICES to the (2) serial adb actually has, before the
# spike module snapshots it at import.
ADB_SERIAL = "adb-1490455572007706-HQWNyz (2)._adb-tls-connect._tcp"
for i, (name, ser) in enumerate(rwp.DEVICES):
    if "HQWNyz" in ser:
        rwp.DEVICES[i] = (name, ADB_SERIAL)
        os.environ["SPIKE_IDX"] = str(i)
        print(f"[seo-decodo] {name} idx={i} serial={ADB_SERIAL}", flush=True)
        break

import spike_locale_captcha as sp   # imports tunnel helpers (bring_up/tear/adb)

LOC = os.environ.get("LOC", "San Francisco, California")
KW = os.environ.get("KW", "best med spa")

# Rotate fresh sticky US IPs until one returns a clean (non-blocked) SERP — this
# is what the bridge's bring_up_tunnel does. A flagged residential IP → reCAPTCHA;
# the flow reports `blocked` (never ingests a captcha'd SERP), and we try the next.
import time
resp = None
for attempt in range(1, 7):
    sid = 770000 + attempt * 137 + int(time.time()) % 1000
    print(f"\n[seo-decodo] attempt {attempt}: bring up Decodo US tunnel (sid={sid})…", flush=True)
    gp, gc, ip, ok = sp.bring_up(sid)
    print(f"[seo-decodo] tunnel: exit_ip={ip} up={ok}", flush=True)
    if not ok:
        sp.tear(gp, gc)
        continue
    try:
        sp.adb("forward", "tcp:18799", "tcp:8765")
        body = {"type": "seo", "keyword": KW, "location": LOC, "targetDomain": os.environ.get("TARGET","example.com")}
        print(f"[seo-decodo] POST type:seo kw={KW!r} location={LOC!r}", flush=True)
        req = urllib.request.Request(
            "http://localhost:18799/session",
            data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST",
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=300).read())
        resp["_exit_ip"] = ip
        status = resp.get("status")
        print(f"[seo-decodo] status={status} challenge={resp.get('challenge')}", flush=True)
        if status != "blocked" and not resp.get("challenge"):
            break  # clean IP — done
        print("[seo-decodo] flagged IP → rotating to a fresh one", flush=True)
        resp = None
    finally:
        sp.tear(gp, gc)
        print("[seo-decodo] tunnel torn down", flush=True)

if not resp:
    sys.exit("[seo-decodo] could not get a captcha-clean Decodo IP in 6 tries")

json.dump(resp, open("/tmp/seo_decodo.json", "w"))
serp = resp.get("serp") or {}
print(f"\n=== RESULT (exit_ip={resp.get('_exit_ip')}) ===")
print("status:", resp.get("status"), "| challenge:", resp.get("challenge"), "| err:", resp.get("error"))
print(f"organic: {len(serp.get('organic', []))} | local: {len(serp.get('local', []))}")
print("ORGANIC:")
for o in (serp.get("organic") or [])[:8]:
    print(f"  #{o.get('position')} {o.get('domain')}")
print("LOCAL PACK:")
for l in (serp.get("local") or [])[:6]:
    print(f"  {l.get('name')} | {l.get('rating')} | {l.get('address')}")
for k, fn in [("screenshot_local_b64", "decodo_local"), ("screenshotLocalB64", "decodo_local"),
              ("screenshot_organic_b64", "decodo_organic"), ("screenshotOrganicB64", "decodo_organic")]:
    b = resp.get(k)
    if b:
        open(f"/tmp/{fn}.png", "wb").write(base64.b64decode(b))
