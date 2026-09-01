#!/usr/bin/env python3
"""Measure how tightly Copilot's answers follow the proxy's location.

Copilot-via-Edge is only proven to follow an Evomi exit at STATE level: a Denver
target answered "Aurora, CO" once and "Colorado Springs" another time. The daily
ranks businesses by METRO, so a Denver client answered from Colorado Springs is a
wrong result that still looks like a successful one. This runs the same target
several times and reports which city Copilot actually names each time.

Secrets come from the environment; nothing is hardcoded.

  cd ~/projects/device-agent
  set -a; source .env.dev; set +a
  PROXY_PROVIDER=evomi TEST_SERIAL='<adb serial>' \\
    TEST_ZIP=80202 TEST_CITY=Denver TEST_STATE=CO RUNS=3 \\
    python3 copilot_geo_test.py
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

os.environ.setdefault("PROXY_PROVIDER", "evomi")
# .env.dev still points PROXY_HOST at Decodo, which is dead — sourcing it and setting
# only PROXY_PROVIDER builds a Decodo tunnel with no exit, and the platform then reports
# a network error that looks like a Copilot fault. Mirror run_daily_auto.sh's evomi block.
if os.environ["PROXY_PROVIDER"] == "evomi":
    os.environ["PROXY_HOST"] = "core-residential.evomi.com"
    os.environ["PROXY_PORT"] = "1000"
    # gost_manager reads the username from PROXY_BASE_USER, not PROXY_USER; setting only
    # the latter leaves it on the stale Decodo default and every request 407s.
    for dst, src in (("PROXY_BASE_USER", "EVOMI_USER"), ("PROXY_USER", "EVOMI_USER"),
                     ("PROXY_PASS", "EVOMI_PASS"), ("PROXY_PASSWORD", "EVOMI_PASS")):
        if os.environ.get(src):
            os.environ[dst] = os.environ[src]
    os.environ["USE_SNI_RELAY"] = "0"
    if not os.environ.get("PROXY_BASE_USER"):
        sys.exit("set EVOMI_USER / EVOMI_PASS (they live in .env.dev): "
                 "set -a; source .env.dev; set +a")
elif os.environ["PROXY_PROVIDER"] == "decodo":
    # Mirrors run_ranking_auto.sh's decodo branch: residential :10001, zip geo in the
    # username. .env.dev's own PROXY_HOST/PORT point at a different provider.
    os.environ["PROXY_HOST"] = "gate.decodo.com"
    os.environ["PROXY_PORT"] = "10001"
    os.environ["PROXY_BASE_USER"] = "user-" + os.environ.get("DECODO_USER", "spmqebjuzf")
    if os.environ.get("DECODO_PASS"):
        os.environ["PROXY_PASSWORD"] = os.environ["DECODO_PASS"]
    os.environ["USE_SNI_RELAY"] = "0"
    if not os.environ.get("PROXY_PASSWORD"):
        sys.exit("set DECODO_PASS (it lives in .env.dev): set -a; source .env.dev; set +a")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "aeo-appium"))
from gost_manager import GostManager  # noqa: E402

SER = os.environ.get("TEST_SERIAL") or sys.exit("set TEST_SERIAL (see `adb devices`)")
ZIP = os.environ.get("TEST_ZIP", "80202")
CITY = os.environ.get("TEST_CITY", "Denver")
STATE = os.environ.get("TEST_STATE", "CO")
PORT = int(os.environ.get("TEST_GOST_PORT", "11901"))
HTTP_PORT = int(os.environ.get("TEST_HTTP_PORT", "18765"))
MAC_IP = os.environ.get("MAC_IP", "192.168.0.102")
RUNS = int(os.environ.get("RUNS", "3"))
KEYWORD = os.environ.get("TEST_KEYWORD", "emergency plumber")
BIZ = os.environ.get("TEST_BIZ", "Bell Plumbing and Heating")
BIZ_URL = os.environ.get("TEST_BIZ_URL", "bellplumbing.com")


def run(cmd, t=30):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=t)
    except Exception as e:
        class _R:
            returncode, stdout, stderr = 1, "", str(e)
        return _R()


def curl_through_gost(url, t=25):
    return run(f'curl -s --max-time {t} --proxy "socks5h://anon:anon@127.0.0.1:{PORT}" "{url}"',
               t + 5).stdout.strip()


def start_tunnel(port):
    """Same spec the ranking dispatcher builds in audit_dispatch_http.py."""
    gm = GostManager(
        [{"device_id": "device-101", "zip": ZIP, "city": CITY, "state": STATE,
          "country": "us", "session_duration": 30}],
        base_port=port,
    )
    gm.start(wait_seconds=2.5)
    return gm


# Providers can hand back an exit outside the requested geo while looking healthy, so
# rotate the session until the exit really is in the target state — the dispatcher does
# the same on a bad tunnel rather than accepting the first one it gets.
ROTATE = int(os.environ.get("ROTATE_UNTIL_GEO", "6"))
gm = None
exit_city = "?"
for attempt in range(1, ROTATE + 1):
    port = PORT + (attempt - 1) * 2
    gm = start_tunnel(port)
    PORT = port
    info = curl_through_gost("https://ipinfo.io/json")
    try:
        j = json.loads(info)
        exit_city = f"{j.get('city')}, {j.get('region')}"
        ok_geo = (j.get("region") or "").lower().startswith(STATE.lower()) or \
                 (j.get("region") or "") in (STATE,) or \
                 (j.get("city") or "").lower() == CITY.lower()
        print(f"[exit try{attempt}] ip={j.get('ip')} city={exit_city} org={j.get('org')} "
              f"in_target={'yes' if ok_geo else 'NO — rotating session'}", flush=True)
        if ok_geo:
            break
    except Exception:
        print(f"[exit try{attempt}] no exit (raw={info[:80]!r}) — rotating session", flush=True)
    gm.stop() if hasattr(gm, "stop") else None

spec = gm.specs[0]
print(f"[gost] up on :{PORT} tier={spec.tier} zip={spec.zip_code} city={spec.city}", flush=True)

run(f'adb -s "{SER}" shell am force-stop net.typeblog.socks', 5)
time.sleep(0.5)
run(f'adb -s "{SER}" shell appops set net.typeblog.socks ACTIVATE_VPN allow', 5)
run(f'adb -s "{SER}" shell am start -n net.typeblog.socks/.AdbStartActivity '
    f'-a net.typeblog.socks.ACTION_START_VPN --es SOCKSSERV "{MAC_IP}" --ei SOCKSPORT {PORT} '
    f'--es SOCKSUNAME "anon" --es SOCKSPASSWD "anon" --es SOCKSDNS "8.8.8.8" --es SOCKSROUTE "all"', 10)

up = False
for _ in range(20):
    r = run(f'adb -s "{SER}" shell ifconfig tun0', 5)
    if "UP" in r.stdout and "inet" in r.stdout:
        r2 = run(f'adb -s "{SER}" shell "nc -w 3 1.1.1.1 53 </dev/null >/dev/null && echo OK"', 6)
        if "OK" in r2.stdout:
            up = True
            break
    time.sleep(3)
print(f"[tunnel] {'UP' if up else 'FAILED'}", flush=True)
if not up:
    sys.exit("tunnel never came up — not measuring geo through a leaking phone")

run(f'adb -s "{SER}" forward tcp:{HTTP_PORT} tcp:8765', 10)
body = json.dumps({
    "type": "audit", "platform": "copilot", "bizName": BIZ, "bizUrl": BIZ_URL,
    "city": CITY, "state": STATE, "keyword": KEYWORD, "genTimeoutSec": 240,
}).encode()

# Cities named in the answer tell us where Copilot thinks the user is. Compare each
# against the target rather than trusting the exit IP: the two can disagree.
CITY_RE = re.compile(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+)?),\s*(?:%s|%s)\b" % (STATE, CITY))
for i in range(1, RUNS + 1):
    req = urllib.request.Request(f"http://127.0.0.1:{HTTP_PORT}/session", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            d = json.loads(r.read())
    except Exception as e:
        print(f"[run {i}] request failed: {e}", flush=True)
        continue
    p = d.get("platforms", {}).get("copilot", {})
    text = p.get("response_text") or ""
    cities = sorted(set(CITY_RE.findall(text)))
    print(f"[run {i}] status={p.get('status')} rank={p.get('ranking_position')}/"
          f"{p.get('ranking_total')} cities_named={cities or '-'}", flush=True)
    print(f"        {' '.join(text.split())[:220]}", flush=True)

print(f"[done] target={CITY} {ZIP} exit={exit_city} tier={spec.tier}", flush=True)
