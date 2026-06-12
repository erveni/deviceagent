#!/usr/bin/env python3
"""One-off: bring up ONE residential Decodo tunnel on ONE phone, then verify
the exit IP is residential. Leaves gost running so Chrome can be opened after.

Residential config (per handover 2026-06-02):
  PROXY_HOST=gate.decodo.com  PROXY_PORT=10001  PROXY_BASE_USER=user-spmqebjuzf
  USE_SNI_RELAY=0 (residential accepts IP-CONNECT, no relay needed)
"""
import os, sys, json, subprocess, time

# --- residential env (must be set BEFORE importing gost_manager) ---
# Secrets/targets come from the environment — NOTHING is hardcoded here.
# Required:  PROXY_PASSWORD  (the Decodo residential account password)
#            TEST_SERIAL     (adb serial of the phone to test — see `adb devices`)
# Optional:  PROXY_BASE_USER (default user-spmqebjuzf), PROXY_HOST, PROXY_PORT,
#            TEST_ZIP / TEST_STATE (geo target), MAC_IP (this Mac's LAN IP)
#
# Example:
#   export PROXY_PASSWORD='...'
#   TEST_SERIAL="$(adb devices | awk 'NR==2{print $1}')" \
#   TEST_ZIP=85395 TEST_STATE=AZ python3 test_residential_one.py
os.environ.setdefault("PROXY_HOST", "gate.decodo.com")
os.environ.setdefault("PROXY_PORT", "10001")          # 10001 = residential pool
os.environ.setdefault("PROXY_BASE_USER", "user-spmqebjuzf")
if not os.environ.get("PROXY_PASSWORD"):
    sys.exit("ERROR: set PROXY_PASSWORD (Decodo residential password) in the environment first.")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "aeo-appium"))
from gost_manager import GostManager  # noqa: E402

SER    = os.environ.get("TEST_SERIAL")
if not SER:
    sys.exit("ERROR: set TEST_SERIAL to the phone's adb serial (see `adb devices`).")
PORT   = int(os.environ.get("TEST_GOST_PORT", "11001"))
ZIP    = os.environ.get("TEST_ZIP", "85395")          # Goodyear AZ — validated
STATE  = os.environ.get("TEST_STATE", "AZ")
MAC_IP = os.environ.get("MAC_IP", "192.168.0.102")    # this Mac's LAN IP (phone dials it)


def run(cmd, t=30):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=t)
    except Exception as e:
        class _R: returncode = 1; stdout = ""; stderr = str(e)
        return _R()


def curl_through_gost(url, t=25):
    cp = run(f'curl -s --max-time {t} --proxy "socks5h://anon:anon@127.0.0.1:{PORT}" "{url}"', t + 5)
    return cp.stdout.strip()


# 1) start residential gost listener
gm = GostManager(
    [{"device_id": "device-101", "zip": ZIP, "state": STATE, "session_duration": 30}],
    base_port=PORT,
)
gm.start(wait_seconds=2.5)
print(f"[ok] gost up on :{PORT}  spec={gm.specs[0].tier} zip={gm.specs[0].zip_code}", flush=True)

# 2) confirm exit IP + that it's residential (ipinfo org/type)
ip = curl_through_gost("https://ifconfig.me")
print(f"[exit-ip] {ip}", flush=True)
info = curl_through_gost("https://ipinfo.io/json")
try:
    j = json.loads(info)
    print(f"[ipinfo] ip={j.get('ip')} city={j.get('city')} region={j.get('region')} "
          f"country={j.get('country')} org={j.get('org')}", flush=True)
except Exception:
    print(f"[ipinfo-raw] {info[:300]}", flush=True)

# 3) wire the phone's SocksDroid -> Mac gost listener
run(f'adb -s "{SER}" shell am force-stop net.typeblog.socks', 5)
time.sleep(0.5)
run(f'adb -s "{SER}" shell appops set net.typeblog.socks ACTIVATE_VPN allow', 5)
run(f'adb -s "{SER}" shell am start -n net.typeblog.socks/.AdbStartActivity '
    f'-a net.typeblog.socks.ACTION_START_VPN --es SOCKSSERV "{MAC_IP}" --ei SOCKSPORT {PORT} '
    f'--es SOCKSUNAME "anon" --es SOCKSPASSWD "anon" --es SOCKSDNS "8.8.8.8" --es SOCKSROUTE "all"', 10)
time.sleep(2)

# 4) wait for tunnel up (tun0 UP + TCP flows)
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
print(f"[done] gost left running on :{PORT}. Phone routed through residential exit {ip}.", flush=True)
