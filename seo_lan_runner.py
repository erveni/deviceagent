#!/usr/bin/env python3
"""Signal SEO — LAN-native engagement runner (ZERO runtime adb).

Drives the fleet entirely over LAN HTTP to each phone's agent (:8765):
  1. bring up a Mac gost + sni_relay chain -> Decodo, pinned to the client's ZIP
  2. POST /proxy/start  -> the phone's SocksDroid (per-app: Chrome only, from its
                           saved profile) dials MAC_IP:relay over Wi-Fi. Only Chrome
                           egresses the localized IP; the agent's control channel
                           stays on real Wi-Fi, so it survives the VPN.
  3. POST /session (seo + gps + engage) per keyword -> localized search -> click -> dwell
  4. POST /proxy/stop   -> drop the phone's VPN, tear down the Mac tunnel

No adb at runtime. One-time provisioning is assumed already done on each phone:
APK install, accessibility toggle, `appops set com.deviceagent android:mock_location
allow`, and the SocksDroid per-app profile (Per-app Proxy ON, Bypass OFF, App List =
com.android.chrome, server = Mac LAN IP:relay-port, anon/anon). See the
`lan-control-no-adb` session memory for the full setup.

  set -a; source .env.dev; set +a        # PROXY_* (gost auth)
  MAC_IP=<mac-lan-ip> python3 seo_lan_runner.py clients_lan.json
  DRY_RUN=1 python3 seo_lan_runner.py clients_lan.json    # plan only

Client config (SEO or AEO catalog shape) + a `phone_ip` per client:
  [{"biz_name":"Mae's Childcare","biz_url":"https://www.maeschildcare.com",
    "city":"San Francisco","state":"California",
    "proxy":{"zip":"94117","iproyal_city":"san_francisco","iproyal_state":"california",
             "latitude":37.77784,"longitude":-122.430147},
    "keywords":[{"keyword":"bilingual childcare San Francisco"}],
    "phone_ip":"192.168.254.101"}]
"""
import functools
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

import run_with_proxy as rwp
import seo_proxy_run as spr
from serp_fleet_worker import _build_geo_suffix
from signal_seo_daily import _normalize_client

HERE = os.path.dirname(os.path.abspath(__file__))
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
MAC_IP = os.environ.get("MAC_IP") or rwp.MAC_IP
PHONE_PORT = int(os.environ.get("SIGNAL_PHONE_PORT", "8765"))
COUNTRY = os.environ.get("SIGNAL_COUNTRY", "us")
# Persistent-VPN model (default): the phone's SocksDroid runs the per-app (Chrome-only)
# VPN continuously from its SAVED PROFILE (Per-app Proxy + Connect-on-Boot), dialing
# MAC_IP:relay over Wi-Fi. The runner only manages the Mac gost/relay on that fixed port.
# We do NOT POST /proxy/start: that fires SocksDroid's AdbStartActivity, which rebuilds the
# profile from intent extras WITHOUT per-app -> full-route -> black-holes LAN control.
VPN_PERSISTENT = os.environ.get("SIGNAL_VPN_PERSISTENT", "1") == "1"
# Where per-run result JSON is written (the dashboard reads these).
RUNS_DIR = os.environ.get("SIGNAL_RUNS_DIR", os.path.join(HERE, "seo_runs"))


def _slug(s):
    return "".join(c.lower() if c.isalnum() else "-" for c in (s or "")).strip("-")[:60] or "client"


def _persist_run(record: dict):
    """Write one client's run result to seo_runs/<date>/<slug>_<unixts>.json — the
    machine-readable record the dashboard surfaces. Best-effort; never breaks a run."""
    try:
        day = time.strftime("%Y-%m-%d", time.gmtime(record.get("started_at") or time.time()))
        d = os.path.join(RUNS_DIR, day)
        os.makedirs(d, exist_ok=True)
        ts = int(record.get("finished_at") or time.time())
        path = os.path.join(d, f"{_slug(record.get('client'))}_{ts}.json")
        with open(path, "w") as f:
            json.dump(record, f, indent=2)
        print(f"  run record → {path}", flush=True)
    except Exception as e:
        print(f"  [warn] persist failed: {type(e).__name__}: {e}", flush=True)
SESSION_TIMEOUT = int(os.environ.get("SIGNAL_SESSION_TIMEOUT", "220"))
# query-retries doubles as the captcha rotation budget (each rotation = fresh exit IP).
QUERY_RETRIES = int(os.environ.get("SIGNAL_QUERY_RETRIES", "3"))


def _http(phone_ip, path, body=None, method="GET", timeout=15):
    url = f"http://{phone_ip}:{PHONE_PORT}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _gost_spec(geo):
    host, port, up, pw = spr._gateway("residential")
    rwp.PROXY_HOST, rwp.PROXY_PORT, rwp.PROXY_PASS = host, int(port), pw
    sid = spr._sid()
    user = (f"{up}-country-{COUNTRY}{_build_geo_suffix(geo)}"
            f"-session-{sid}-sessionduration-{spr.SESSION_DURATION}")
    return {"port": spr.GOST_PORT, "sid": sid, "upstream_user": user}


def _bring_up_gost(geo):
    """Mac gost (SOCKS5 -> Decodo, ZIP-pinned) + sni_relay; both bind 0.0.0.0 so the
    phone reaches the relay over Wi-Fi. Returns handles + the LAN relay port + exit IP."""
    gp, gc = rwp.gost_start([_gost_spec(geo)])
    rp = spr._relay_start(spr.RELAY_PORT, spr.GOST_PORT)
    time.sleep(2)
    return {"gost_proc": gp, "gost_cfg": gc, "relay_proc": rp,
            "relay_port": spr.RELAY_PORT, "exit_ip": rwp.resolve_proxy_ip(spr.GOST_PORT)}


def _rotate_gost(h, geo):
    """Fresh Decodo exit IP on the SAME relay port — the phone keeps dialing the relay,
    so no /proxy/start re-fire is needed; only the Mac-side gost session changes."""
    try:
        rwp.gost_stop(h["gost_proc"], h["gost_cfg"])
    except Exception:
        pass
    gp, gc = rwp.gost_start([_gost_spec(geo)])
    time.sleep(2)
    h["gost_proc"], h["gost_cfg"] = gp, gc
    h["exit_ip"] = rwp.resolve_proxy_ip(spr.GOST_PORT)
    return h


def _teardown_gost(h):
    try:
        rwp.gost_stop(h["gost_proc"], h["gost_cfg"])
    except Exception:
        pass
    try:
        h["relay_proc"].terminate()
        h["relay_proc"].wait(timeout=5)
    except Exception:
        try:
            h["relay_proc"].kill()
        except Exception:
            pass


def _start_proxy(phone_ip, relay_port):
    """Bring up the phone's per-app VPN over LAN, resiliently.

    On a COLD start (no tun0 yet) establishing the VpnService resets the in-flight
    /proxy/start request — expected, not an error. So: fire it, tolerate the reset,
    poll /ping until per-app control returns (per-app keeps the agent off the tunnel),
    then re-fire (warm) to confirm tun0_up. Raises if control never returns."""
    body = {"proxy": {"host": MAC_IP, "port": relay_port, "uname": "anon",
                      "passwd": "anon", "per_app": True, "app_list": "com.android.chrome"}}
    try:
        ps = _http(phone_ip, "/proxy/start", body, method="POST", timeout=45)
        if ps.get("tun0_up") and _http(phone_ip, "/ping", timeout=8).get("pong"):
            return ps
    except (urllib.error.URLError, OSError):
        pass  # connection reset as the VPN came up — expected on cold start
    # poll for the control channel to return (proves per-app kept the agent untunneled)
    for _ in range(20):
        time.sleep(2)
        try:
            if _http(phone_ip, "/ping", timeout=5).get("pong"):
                break
        except (urllib.error.URLError, OSError):
            continue
    else:
        raise RuntimeError("LAN control never returned after /proxy/start — "
                           "per-app profile not applied? (would full-route and black-hole control)")
    # warm re-fire to confirm tun0 is actually up
    ps = _http(phone_ip, "/proxy/start", body, method="POST", timeout=20)
    if not ps.get("tun0_up"):
        raise RuntimeError("tunnel did not come up on the phone")
    return ps


@functools.lru_cache(maxsize=1)
def _our_real_ip():
    """The Mac's REAL public IP (direct, no proxy). The phone's Chrome must NEVER show this."""
    try:
        cp = subprocess.run(["curl", "-sS", "--max-time", "8", "-4", "https://api.ipify.org"],
                            capture_output=True, text=True, timeout=12)
        return cp.stdout.strip()
    except Exception:
        return ""


def _assert_chrome_egress_safe(phone_ip, h):
    """HARD SAFETY GATE — nothing runs until the phone's Chrome is PROVEN to egress the proxy,
    not our real IP. Drives Chrome to an IP echo (GET /egress_check) and aborts the client if:
      - Chrome's egress IP can't be read (refuse to run blind), or
      - it equals our real IP (a LEAK — proxy not active), or
      - it doesn't match the gost exit IP (Chrome not routed through our proxy; warn).
    """
    real = _our_real_ip()
    resp = _http(phone_ip, "/egress_check", timeout=45)
    chrome_ip = (resp.get("chrome_egress_ip") or "").strip()
    if not resp.get("readable") or not chrome_ip:
        raise RuntimeError("ABORT: could not read Chrome's egress IP — refusing to run blind")
    if real and chrome_ip == real:
        raise RuntimeError(f"ABORT: LEAK — Chrome is egressing our REAL IP {real}! "
                           f"Proxy is NOT active. No job will run.")
    exit_ip = h.get("exit_ip")
    if exit_ip and chrome_ip != exit_ip:
        print(f"  ⚠ Chrome egress {chrome_ip} != gost exit {exit_ip} (sticky-session drift?) — "
              f"continuing since it's not our real IP", flush=True)
    print(f"  ✓ PROXY VERIFIED: Chrome egress={chrome_ip} — NOT our real IP ({real or 'unknown'})",
          flush=True)
    return chrome_ip


def _exit_geo():
    """Geolocate the current gost exit IP (Mac -> gost -> Decodo), IPv4 only via ip-api."""
    try:
        cp = subprocess.run(
            ["curl", "-sS", "--max-time", "12", "-4", "--socks5-hostname",
             f"anon:anon@127.0.0.1:{spr.GOST_PORT}",
             "http://ip-api.com/json?fields=status,countryCode,regionName,city,zip,query"],
            capture_output=True, text=True, timeout=15)
        return json.loads(cp.stdout or "{}")
    except Exception:
        return {}


def _geo_ok(geo, info):
    """True if the exit IP landed in the client's expected state (localization worked,
    not a random in-country IP). Country must match; if a state is configured it must
    match the geolocated region."""
    if (info.get("countryCode") or "").upper() != COUNTRY.upper():
        return False
    exp_state = (geo.get("state") or "").replace("_", " ").strip().lower()
    got_region = (info.get("regionName") or "").strip().lower()
    if exp_state:
        return bool(got_region) and (exp_state in got_region or got_region in exp_state)
    return True


def _ensure_localized(h, geo, label, rotations=4):
    """Verify the gost exit is in the client's city/state; rotate to a fresh IP until it
    is (or give up). Returns the geo info dict. Guards against a job silently running
    from the wrong geo (random Decodo IP, stale session, etc.)."""
    for i in range(rotations + 1):
        info = _exit_geo()
        if _geo_ok(geo, info):
            print(f"  localized OK: exit {info.get('query')} {info.get('city')}, "
                  f"{info.get('regionName')} {info.get('zip')}", flush=True)
            h["exit_ip"] = info.get("query") or h.get("exit_ip")
            return info
        print(f"  exit geo MISMATCH for {label} (got {info.get('city')},"
              f"{info.get('regionName')} cc={info.get('countryCode')}) — rotating "
              f"{i + 1}/{rotations}", flush=True)
        if i < rotations:
            _rotate_gost(h, geo)
    raise RuntimeError(f"could not get an exit IP in the client's geo after {rotations} rotations")


def run_client(c: dict) -> dict:
    c = _normalize_client(c)
    name = c["business_name"]
    domain = c.get("business_domain")
    location = c.get("location", "")
    keywords = c["keywords"]
    geo = c.get("geo") or {}
    lat, lng = geo.get("lat"), geo.get("lng")
    phone_ip = c.get("phone_ip") or os.environ.get("SIGNAL_PHONE_IP")
    geo_desc = _build_geo_suffix(geo) or "(random in-country)"
    print(f"\n=== {name} — {location} ({len(keywords)} kw) @ {phone_ip} ===", flush=True)

    if not phone_ip:
        print("  [skip] no phone_ip"); return {"client": name, "skipped": "no_phone_ip"}
    if not domain:
        print("  [skip] no business_domain"); return {"client": name, "skipped": "no_domain"}
    if not keywords:
        print("  [skip] no keywords"); return {"client": name, "skipped": "no_keywords"}

    if DRY_RUN:
        print(f"  [dry] Mac gost+relay → Decodo {COUNTRY}{geo_desc} (exit IP in this city)")
        if VPN_PERSISTENT:
            print(f"  [dry] phone already runs per-app VPN (profile) dialing MAC:{spr.RELAY_PORT}; "
                  f"verify /ping")
        else:
            print(f"  [dry] POST /proxy/start host={MAC_IP} port={spr.RELAY_PORT} per-app=chrome")
        for kw in keywords:
            print(f"  [dry] POST http://{phone_ip}:{PHONE_PORT}/session seo engage "
                  f"kw={kw!r} loc={location!r} gps={lat},{lng}")
        print(f"  [dry] tear down Mac gost/relay" +
              ("" if VPN_PERSISTENT else " + POST /proxy/stop"))
        return {"client": name, "dry": True}

    print(f"  bringing up gost+relay (Decodo {COUNTRY}{geo_desc})…", flush=True)
    h = _bring_up_gost(geo)
    print(f"  relay_port={h['relay_port']}", flush=True)
    results = []
    started_at = time.time()
    verified_egress = None
    try:
        # UPDATE 1 — localization guard: confirm the exit IP is in the client's city/state,
        # rotating fresh IPs until it is. Never run a job from the wrong geo.
        _ensure_localized(h, geo, name)

        if VPN_PERSISTENT:
            # UPDATE 3 — VPN-drop detection: /ping proves the agent is reachable, but the
            # per-app VPN could be DOWN (Chrome would egress the real IP). /netstate reads
            # tun0 directly, so we abort instead of silently searching from the phone's real geo.
            if not _http(phone_ip, "/ping", timeout=8).get("pong"):
                raise RuntimeError("phone unreachable over LAN")
            net = _http(phone_ip, "/netstate", timeout=8)
            if not net.get("tun0_up"):
                raise RuntimeError("phone per-app VPN is DOWN (tun0 not up) — toggle SocksDroid "
                                   "on (profile + Connect-on-Boot); Chrome would egress the real IP")
            print(f"  per-app VPN up (tun0={net.get('tun0_addr')}); "
                  f"Chrome egresses via MAC:{h['relay_port']}", flush=True)
            # HARD SAFETY GATE — prove Chrome egresses the proxy, not our real IP, before any job.
            verified_egress = _assert_chrome_egress_safe(phone_ip, h)
        else:
            ps = _start_proxy(phone_ip, h["relay_port"])
            print(f"  /proxy/start ok={ps.get('ok')} tun0_up={ps.get('tun0_up')} "
                  f"per_app={ps.get('per_app')} — LAN control intact", flush=True)
            # HARD SAFETY GATE — prove Chrome egresses the proxy, not our real IP, before any job.
            verified_egress = _assert_chrome_egress_safe(phone_ip, h)

        for kw in keywords:
            body = {"type": "seo", "keyword": kw, "targetDomain": domain,
                    "targetName": name, "location": location, "engage": True}
            if lat is not None and lng is not None:
                body["gps"] = {"lat": lat, "lng": lng}
            clicked = False
            for attempt in range(QUERY_RETRIES + 1):
                try:
                    resp = _http(phone_ip, "/session", body, method="POST", timeout=SESSION_TIMEOUT)
                except urllib.error.URLError as e:
                    print(f"    {kw!r}: session error {e}; retry", flush=True)
                    continue
                clicked = bool(resp.get("engaged") or resp.get("backlink_clicked"))
                status = resp.get("status")
                # A flagged exit IP shows up as EITHER an explicit captcha (challenge=true)
                # OR a "blocked" SERP (sorry/unusual-traffic page, challenge=false). Both mean
                # this IP is burned — rotate to a fresh one and retry, don't accept the result.
                burned = bool(resp.get("challenge")) or status == "blocked"
                print(f"    {kw!r}: status={status} clicked={clicked} "
                      f"burned_ip={burned} (try {attempt + 1})", flush=True)
                if clicked or not burned or attempt == QUERY_RETRIES:
                    break
                # UPDATE 2 — captcha/blocked: rotate to a FRESH exit IP, then re-confirm it's
                # still in the client's geo before retrying (a rotated IP could land out-of-area).
                print("    blocked/captcha → rotating to a fresh localized exit IP…", flush=True)
                _rotate_gost(h, geo)
                _ensure_localized(h, geo, name)
            results.append({"keyword": kw, "clicked": clicked, "status": status,
                            "exit_ip": h.get("exit_ip"), "attempts": attempt + 1})
    finally:
        if not VPN_PERSISTENT:
            try:
                _http(phone_ip, "/proxy/stop", {}, method="POST", timeout=15)
            except Exception:
                pass
        _teardown_gost(h)
        print("  gost/relay down (persistent VPN left up)" if VPN_PERSISTENT
              else "  tunnel down", flush=True)
    record = {
        "client": name, "location": location, "domain": domain, "phone_ip": phone_ip,
        "geo_pin": _build_geo_suffix(geo) or "(random)",
        "verified_chrome_egress": verified_egress,   # the proxy-safety proof for this run
        "results": results,
        "clicks": sum(1 for r in results if r["clicked"]),
        "started_at": started_at, "finished_at": time.time(),
    }
    _persist_run(record)
    return record


def main():
    cfg = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "clients.json")
    clients = json.load(open(cfg))
    print(f"Signal SEO LAN runner — {len(clients)} client(s) | mac_ip={MAC_IP} | "
          f"dry={DRY_RUN}", flush=True)
    out = [run_client(c) for c in clients]
    ok = sum(1 for r in out if not r.get("dry") and not r.get("skipped"))
    clicks = sum(len([x for x in r.get("results", []) if x["clicked"]]) for r in out)
    print(f"\nDONE — {ok} client(s) engaged (LAN, no adb) · {clicks} keyword click(s)", flush=True)


if __name__ == "__main__":
    main()
