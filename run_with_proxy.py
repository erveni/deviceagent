#!/usr/bin/env python3
"""Daily plan runner — wave-based. Fresh proxy per wave. CSV after every session."""

import json, sys, time, csv, os, subprocess, random, string, threading, math, re
from datetime import datetime, timezone
from urllib.parse import urlparse

PLAN_PATH = sys.argv[1] if len(sys.argv) > 1 else "/Users/seolocalph/projects/aeo-appium/daily_plan_2026-05-04.json"

GOST_BIN = os.environ.get("GOST_BIN", "/opt/homebrew/bin/gost")
PROXY_HOST = os.environ.get("PROXY_HOST", "gate.decodo.com")
PROXY_PORT = int(os.environ.get("PROXY_PORT", "7000"))   # Decodo mobile gateway (was 10001 for residential)
PROXY_USER = os.environ.get("PROXY_USER", "")
PROXY_PASS = os.environ.get("PROXY_PASS", "")
DURATION = int(os.environ.get("PROXY_DURATION", "60"))
PROXY_TARGET = os.environ.get("PROXY_TARGET", "country-us")  # e.g. asn-21928 (T-Mobile), asn-20057 (AT&T)
# Which residential provider's username format to build. "decodo" (default) uses
# the -session-<sid>-sessionduration-<dur>-country-us[-zip-X] scheme; "dataimpulse"
# uses the __cr.us[__city.X] suffix scheme. Both go through the same SOCKS5 gost
# connector — only the upstream username differs (host/port/pass come from env).
PROXY_PROVIDER = os.environ.get("PROXY_PROVIDER", "decodo").lower()


def build_upstream_user(sid, zip_=None, state=None, country=None):
    """Build the upstream proxy username for the active provider.

    sid    — per-listener session id (rotation key on Decodo; cosmetic on
             DataImpulse, which pins one sticky exit IP per source).
    zip_   — optional retry geo: Decodo appends -zip-<zip>; DataImpulse has no
             zip targeting, so US country is kept (city-level would be __city.X).
    """
    if PROXY_PROVIDER == "rayobyte":
        # Rayobyte targets via the PASSWORD (see gost_start), so the username is the
        # plain account; geo/session live in the password string.
        return PROXY_USER
    if PROXY_PROVIDER == "dataimpulse":
        return f"{PROXY_USER}__cr.us__sid.{sid}"
    if (country or "us").lower() == "ca":
        # Canada: country-level only — Decodo city/postal CA targeting is unreliable
        # (probed 2026-06-24: -country-ca works, -country-ca-city-* returns empty).
        return f"{PROXY_USER}-session-{sid}-sessionduration-{DURATION}-country-ca"
    if zip_:
        return f"{PROXY_USER}-session-{sid}-sessionduration-{DURATION}-country-us-zip-{zip_}"
    return f"{PROXY_USER}-session-{sid}-sessionduration-{DURATION}-country-us"

_CA_PROVINCES = {"ON","QC","BC","AB","MB","SK","NS","NB","NL","PE","NT","YT","NU"}

def geo_target(job):
    """Derive (zip_or_None, country) for proxy geo-targeting from a job/target.

    biz_zip is unreliable — it is sometimes the street number (e.g. "21312
    Provincial Blvd, Katy, TX 77450" stored biz_zip=21312), so prefer the LAST
    5-digit group parsed from biz_address (the real zip sits at the address tail).
    Canada is detected by province or 'Canada' in the address and targeted at
    country level (Decodo has no reliable CA zip targeting)."""
    addr = job.get("biz_address") or ""
    state = (job.get("biz_state") or "").upper()
    if state in _CA_PROVINCES or "canada" in addr.lower():
        return None, "ca"
    zips = re.findall(r"\b(\d{5})\b", addr)
    z = zips[-1] if zips else (str(job.get("biz_zip") or "").strip() or None)
    return z, "us"
WAVE_STAGGER_S = int(os.environ.get("WAVE_STAGGER_S", "0"))  # seconds between starting each phone's session; 0 = fire all at once (residential)
# Auto-retry transient errors with a fresh Decodo session — mirrors
# audit_dispatch_http.py:587-643 + device_dispatch.py:217. Most 'input failed'
# bursts clear on a second IP per the audit author's empirical claim.
RETRY_TRIGGERS = ("input failed", "navigate", "proxy_unreachable", "generation timeout")
RETRY_MAX_ROUNDS = int(os.environ.get("RETRY_MAX_ROUNDS", "1"))
BASE_GOST = 11001
def _detect_mac_lan_ip():
    """Auto-detect the Mac's LAN IP so SocksDroid always dials the live gost host.
    Hardcoding broke when DHCP moved the Mac .102 -> .105 (2026-06-10) — every phone
    routed to a dead IP -> 'site can't be reached'. Env MAC_IP overrides; .102 fallback."""
    for _if in ("en0", "en1"):
        _ip = subprocess.run(["ipconfig", "getifaddr", _if],
                             capture_output=True, text=True).stdout.strip()
        if _ip:
            return _ip
    return "192.168.0.102"


MAC_IP = os.environ.get("MAC_IP") or _detect_mac_lan_ip()
# SNI-rewriting relay (sni_relay.py). SocksDroid (tun2socks) can only IP-CONNECT,
# which mobile Decodo rejects. The relay sits in front of gost, recovers the
# hostname from the TLS SNI, and re-dials gost->Decodo by hostname. The phone
# still connects to BASE_GOST+i (now the RELAY); gost is shifted up by
# GOST_PORT_OFFSET and only the relay talks to it. See sni_relay.py.
USE_SNI_RELAY = os.environ.get("USE_SNI_RELAY", "1") == "1"
GOST_PORT_OFFSET = int(os.environ.get("GOST_PORT_OFFSET", "100"))
RELAY_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sni_relay.py")
RELAY_PY = os.environ.get("RELAY_PY", sys.executable)
_relays_by_cfg = {}              # gost cfg path -> [relay Popen, ...]
_relays_lock = threading.Lock()

DEVICES = [
    ("device-101", "adb-R83L112EVWK-PydBnX (2)._adb-tls-connect._tcp"),
    ("device-102", "adb-10HFBBFEBZ000RA-dvvJ3y (2)._adb-tls-connect._tcp"),
    ("device-103", "adb-149145555W001028-XsQtPA (2)._adb-tls-connect._tcp"),
    ("device-104", "adb-149145555W002883-aGtZ5h (2)._adb-tls-connect._tcp"),
    ("device-105", "adb-149145555W005208-27c1FH._adb-tls-connect._tcp"),
    ("device-106", "adb-149145555W006477-JjonPV._adb-tls-connect._tcp"),
    ("device-107", "adb-149145555W006788-Vb9M0e (2)._adb-tls-connect._tcp"),
    ("device-108", "adb-1490455613010287-g9bnc8 (2)._adb-tls-connect._tcp"),
    ("device-109", "adb-149145555W002563-yWaJau._adb-tls-connect._tcp"),
    ("device-110", "adb-149145555W006589-2W7yzb (2)._adb-tls-connect._tcp"),
    ("device-111", "adb-129143748T010173-6zhzYl._adb-tls-connect._tcp"),
    ("device-112", "adb-129143748T079638-YjN1XH._adb-tls-connect._tcp"),
    ("device-113", "adb-129143749A011759-fEoBDp._adb-tls-connect._tcp"),
    ("device-114", "adb-1490455572007706-HQWNyz._adb-tls-connect._tcp"),
    ("device-115", "adb-R83L103VCVH-uvv2pp._adb-tls-connect._tcp"),
    ("device-116", "adb-1490455615007763-aoRAJa (2)._adb-tls-connect._tcp"),
    ("device-117", "adb-1490455613010774-txpX1j (2)._adb-tls-connect._tcp"),
    # Added 2026-07-17: 8 new Infinix X6725 / Android 15 phones. They shipped with a
    # differently-signed agent 0.6.3 (install -r fails INSTALL_FAILED_UPDATE_INCOMPATIBLE),
    # so each was uninstalled and reinstalled with the fleet build 0.9.52 (versionCode 71).
    ("device-118", "adb-149045556L013514-Lp5Qe9._adb-tls-connect._tcp"),
    ("device-119", "adb-149045556R004735-xZmsMI._adb-tls-connect._tcp"),
    ("device-120", "adb-149045556R006310-ke8PPl._adb-tls-connect._tcp"),
    ("device-121", "adb-149045556R021680-y2ttdr._adb-tls-connect._tcp"),
    ("device-122", "adb-149045556S003287-TPRJ3x._adb-tls-connect._tcp"),
    ("device-123", "adb-1490455571033550-R2yFec._adb-tls-connect._tcp"),
    ("device-124", "adb-1490455572006390-9vebFC._adb-tls-connect._tcp"),
    ("device-125", "adb-1490455572008742-O0MeAp._adb-tls-connect._tcp"),
]

# ONLY_ONLINE=1 prunes DEVICES to phones currently reporting `device` in
# `adb devices`, so a run skips offline phones instead of failing their jobs
# with device_pool_timeout. Runs at import time, before DevicePool sizes itself.
def _hw_core(_s):
    """Stable hardware id from an mDNS adb serial. The mDNS wrapper rotates the
    trailing hash and a " (N)" duplicate-counter on every reconnect, but the
    hardware id (token right after "adb-") never changes — match on that so a
    DEVICES entry still resolves to its phone after the serial flaps."""
    return _s.split("-")[1] if _s.startswith("adb-") else _s.strip()

if os.environ.get("ONLY_ONLINE") == "1":
    _out = subprocess.run("adb devices", shell=True, capture_output=True, text=True).stdout
    # adb devices is TAB-separated (serial<TAB>state). mDNS serials can contain a
    # space (the "(2)" variant), so split on TAB — never whitespace, or those
    # serials get truncated and the phone is wrongly treated as offline.
    _online = {}  # hw-core -> ACTUAL connected serial (use this for adb -s)
    for _l in _out.splitlines()[1:]:
        if "\t" not in _l:
            continue
        _ser, _, _state = _l.partition("\t")
        if _state.strip() == "device":
            _online[_hw_core(_ser.strip())] = _ser.strip()
    _before = len(DEVICES)
    # Resolve each DEVICES serial to the serial that is ACTUALLY connected right
    # now (by hardware core), and keep only phones that are online.
    DEVICES = [(n, _online[_hw_core(s)]) for n, s in DEVICES if _hw_core(s) in _online]
    print(f"[ONLY_ONLINE] {len(DEVICES)}/{_before} phones online: "
          f"{', '.join(n for n, _ in DEVICES)}", flush=True)

def run(cmd, timeout=30):
    """Subprocess wrapper that NEVER raises — a hung adb call must not kill the
    whole wave. Returns a CompletedProcess-like object with returncode=124 on
    timeout (matches GNU timeout's convention) so callers can detect failure."""
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        print(f"  [run-timeout {timeout}s] {cmd[:120]}", flush=True)
        class _R:
            returncode = 124
            stdout = e.stdout.decode("utf-8", "replace") if e.stdout else ""
            stderr = e.stderr.decode("utf-8", "replace") if e.stderr else ""
        return _R()
    except Exception as e:
        print(f"  [run-error] {type(e).__name__}: {e} cmd={cmd[:120]}", flush=True)
        class _R:
            returncode = 1; stdout = ""; stderr = str(e)
        return _R()

def get_online_serials():
    """Return set of currently-adb-reachable serials (state == 'device').

    Used to skip offline phones before each wave so we don't waste 60s in
    wait_tunnel on a phone that's no longer connected. The slot's job is
    deferred to a later wave instead of being failed with tunnel_failed.
    """
    try:
        r = run("adb devices", 5)
        out = set()
        for ln in r.stdout.strip().split("\n")[1:]:
            ln = ln.rstrip()
            if ln.endswith("\tdevice"):
                out.add(ln[:-len("\tdevice")])
        return out
    except Exception:
        return set()

def rsid(n=10):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

def extract_domain(url):
    try: return urlparse(url).netloc
    except: return url

def randomize_location(lat, lng, r=5.0):
    rd_lat = r / 69.0
    rd_lng = r / (69.0 * math.cos(math.radians(lat)))
    a = random.uniform(0, 2*math.pi)
    d = random.uniform(0, 1)**0.5
    return (round(lat+d*rd_lat*math.sin(a),6), round(lng+d*rd_lng*math.cos(a),6))

def _gost_listen_port(phone_port):
    """gost's own listener port. With the relay on, gost is shifted up so the
    phone-facing port (phone_port) belongs to the relay instead."""
    return phone_port + GOST_PORT_OFFSET if USE_SNI_RELAY else phone_port

def _relay_start(listen_port, gost_port):
    log = f"/tmp/sni_relay_{listen_port}.log"
    return subprocess.Popen([RELAY_PY, "-u", RELAY_SCRIPT, str(listen_port), str(gost_port)],
                            stdout=open(log, "a"), stderr=subprocess.STDOUT)

def gost_start(specs):
    lines = ["services:"]
    for i, s in enumerate(specs):
        lines += [f'  - name: s{i}', f'    addr: ":{_gost_listen_port(s["port"])}"',
                  f'    handler: {{type: socks5, chain: c{i}, auth: {{username: anon, password: anon}}}}',
                  f'    listener: {{type: tcp}}']
    lines.append("chains:")
    for i, s in enumerate(specs):
        # Rayobyte uses an HTTP upstream endpoint (:8000) and targets via the password
        # (country + sticky session); everyone else is socks5 with the global password.
        if PROXY_PROVIDER == "rayobyte":
            ctype = "http"; upw = f"{PROXY_PASS}-country-US-session-{s['sid']}"
        else:
            ctype = "socks5"; upw = PROXY_PASS
        lines += [f'  - name: c{i}', f'    hops:', f'      - name: h{i}', f'        nodes:',
                  f'          - name: d{i}', f'            addr: {PROXY_HOST}:{PROXY_PORT}',
                  f'            connector: {{type: {ctype}, auth: {{username: "{s["upstream_user"]}", password: "{upw}"}}}}',
                  f'            dialer: {{type: tcp}}']
    cfg = f"/tmp/gost_{os.getpid()}_{specs[0]['port']}.yaml"
    with open(cfg, "w") as f: f.write("\n".join(lines)+"\n")
    proc = subprocess.Popen([GOST_BIN, "-C", cfg, "-D"], stdout=open(cfg+".log","w"), stderr=subprocess.STDOUT)
    # Start one relay per slot (phone_port -> gost listener). Both warm up
    # during the same 2s window gost needs to bind + chain to Decodo.
    relays = []
    if USE_SNI_RELAY:
        relays = [_relay_start(s["port"], _gost_listen_port(s["port"])) for s in specs]
    time.sleep(2)
    if proc.poll() is not None: raise RuntimeError(f"gost died: {cfg}.log")
    for r in relays:
        if r.poll() is not None:
            raise RuntimeError("sni_relay died — see /tmp/sni_relay_*.log")
    if relays:
        with _relays_lock:
            _relays_by_cfg[cfg] = relays
    return proc, cfg

def gost_stop(proc, cfg):
    if proc and proc.poll() is None: proc.terminate(); proc.wait(timeout=5)
    with _relays_lock:
        relays = _relays_by_cfg.pop(cfg, [])
    for r in relays:
        if r and r.poll() is None:
            r.terminate()
            try: r.wait(timeout=5)
            except Exception: pass
    for p in (cfg, cfg+".log"):
        try: os.unlink(p)
        except: pass

def resolve_proxy_ip(port):
    """Capture the Decodo exit IP for this gost listener.

    Goes Mac -> gost -> Decodo -> ifconfig.me, so it does NOT depend on the
    phone tunnel being up. Listener requires anon:anon SOCKS5 auth (gost
    YAML), which the historical preflight in audit_dispatch_http.py omitted —
    that's why proxy_ip was "none" on every audit row. 15s budget covers
    cold-tunnel handshakes. Probes gost directly (not the relay) — it's a
    Mac-side hostname-CONNECT check that doesn't depend on the phone path."""
    probe_port = _gost_listen_port(port)
    try:
        cp = subprocess.run(
            ["curl", "-sS", "--max-time", "15", "--socks5-hostname",
             f"anon:anon@127.0.0.1:{probe_port}", "https://ifconfig.me"],
            capture_output=True, text=True, timeout=18,
        )
        ip = cp.stdout.strip()
        if ip and len(ip) < 64 and ip.count(".") == 3:
            return ip
        print(f"  [preflight-ip] port={port} rc={cp.returncode} "
              f"stderr={cp.stderr.strip()[:120]!r} stdout={ip[:120]!r}", flush=True)
    except Exception as e:
        print(f"  [preflight-ip] port={port} curl raised {type(e).__name__}: {e}", flush=True)
    return ""

def socksdroid_connect(serial, port):
    run(f"adb -s \"{serial}\" shell am force-stop net.typeblog.socks", 5)
    time.sleep(0.5)
    run(f"adb -s \"{serial}\" shell appops set net.typeblog.socks ACTIVATE_VPN allow", 5)
    run(f"adb -s \"{serial}\" shell am start -n net.typeblog.socks/.AdbStartActivity "
        f"-a net.typeblog.socks.ACTION_START_VPN --es SOCKSSERV \"{MAC_IP}\" --ei SOCKSPORT {port} "
        f"--es SOCKSUNAME \"anon\" --es SOCKSPASSWD \"anon\" --es SOCKSDNS \"8.8.8.8\" --es SOCKSROUTE \"all\"", 10)
    time.sleep(2)

def socksdroid_disconnect(serial):
    try:
        run(f"adb -s \"{serial}\" shell pm clear net.typeblog.socks", 30)
    except Exception as e:
        print(f"  [cleanup] pm clear net.typeblog.socks slow/failed on {serial}: {e} — continuing")
    time.sleep(1)

def wait_tunnel(serial):
    # Phase 1: tun0 must be UP locally (fast sanity check).
    # Phase 2: TCP must actually flow through it (proves the full chain
    # socksdroid → gost → Decodo → upstream is carrying traffic — not just
    # that tun0 has an IP). The old local-only check missed cases where
    # gost was still handshaking with Decodo. Probes 1.1.1.1:53 via `nc`
    # because curl is not installed on these Android builds.
    for _ in range(20):
        r = run(f"adb -s \"{serial}\" shell ifconfig tun0", 5)
        if "UP" in r.stdout and "inet" in r.stdout:
            # `-z` rejected by BusyBox nc (TECNO KL4 ships BusyBox; Infinix/Samsung ship toybox).
            # `</dev/null >/dev/null` mirrors open-and-close semantics on both BusyBox AND toybox —
            # strictly more compatible than the original `-z`.
            # Probe a HOSTNAME, not a raw IP: this forces real DNS resolution
            # through the tunnel. The old `nc 1.1.1.1 53` only proved TCP-to-an-IP
            # worked, so it passed even when DNS was dead — the phone then hit
            # DNS_PROBE_FINISHED_NO_INTERNET on every real page (no input field /
            # no capture). Two hosts so a single blocked domain doesn't false-fail.
            r2 = run(f"adb -s \"{serial}\" shell \"(nc -w 4 www.google.com 443 </dev/null >/dev/null 2>&1 || nc -w 4 chatgpt.com 443 </dev/null >/dev/null 2>&1) && echo OK\"", 12)
            if "OK" in r2.stdout:
                return True
        time.sleep(3)
    return False

def mock_location(serial, lat, lng):
    if lat and lng:
        run(f"adb -s \"{serial}\" shell am start-foreground-service "
            f"-a com.blogspot.newapphorizons.fakegps.START "
            f"-e latitude {lat} -e longitude {lng}", 5)

def set_timezone(serial, tz):
    if tz:
        run(f"adb -s \"{serial}\" shell service call alarm 3 s16 \"{tz}\"", 5)

def http_post(port, path, body=None):
    import urllib.request
    url = f"http://localhost:{port}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data,
        headers={"Content-Type":"application/json"} if data else {}, method="POST" if body else "GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r: return json.loads(r.read())
    except: return {"status":"error","error":"http fail"}

# ── Inline Gemini (CDP StreamGenerate capture) ───────────────────────────────
# When GEMINI_INLINE=1, gemini jobs run in the SAME mixed wave as ChatGPT/
# Perplexity but route to the CDP save-capture instead of the app /session flow
# (logged-out Gemini wipes its answer from the UI; we read it off the wire). The
# wave's gost for a gemini-assigned device is zip-targeted so Gemini's IP-geo is
# correct. Success = the answer was SAVED (captured); rank is a bonus parse.
GEMINI_INLINE = os.environ.get("GEMINI_INLINE") == "1"
GEMINI_PROMPT_T = os.environ.get("GEMINI_PROMPT_T") or (
    "Top 3 businesses for {kw} in {city}, {state} {zip}. Numbered list, each with "
    "a one-sentence reason. After the list, rank {biz} ({url}) among all businesses "
    "in this space. You MUST include this exact line on its own: [RANK: X/Y] where "
    "X is the position and Y is total businesses. Keep entire response under 160 words."
)

def _gemini_cdp_session(device_idx, job, gost_spec, proxy_ip):
    serial = DEVICES[device_idx][1]
    cdp = 9222 + device_idx
    rfile, afile = f"/tmp/gem_result_{device_idx}.json", f"/tmp/gem_answer_{device_idx}.txt"
    t0 = time.time()
    url = re.sub(r"[^a-z0-9]", "", (job.get("biz_name") or "biz").lower())[:18] + ".com"
    prompt = GEMINI_PROMPT_T.format(kw=job.get("keyword_text",""), city=job.get("biz_city",""),
                                    state=job.get("biz_state",""), zip=job.get("biz_zip",""),
                                    biz=job.get("biz_name",""), url=url)
    res = {}
    try:
        run(f'adb -s "{serial}" shell "am start -n com.android.chrome/com.google.android.apps.chrome.Main '
            f"-a android.intent.action.VIEW -d 'https://gemini.google.com/app'\"", 12)
        time.sleep(9)
        for f in (rfile, afile):
            try: os.remove(f)
            except OSError: pass
        env = {**os.environ, "CDP_PORT": str(cdp),
               "GEMINI_RESULT_FILE": rfile, "GEMINI_ANSWER_FILE": afile}
        subprocess.run(["python3", "gemini_cdp_capture.py", serial, prompt],
                       capture_output=True, timeout=130, env=env)
        if os.path.exists(rfile):
            res = json.load(open(rfile))
    except Exception as e:
        res = {"error": str(e)[:90]}
    dur = round(time.time() - t0, 1)
    captured = bool(res.get("captured"))
    err = "" if captured else (res.get("error") or "not_captured")
    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "wave_index": 0,
        "client_id": job.get("client_id",""), "client_name": job.get("client_name",""),
        "biz_name": job.get("biz_name",""), "search_address": job.get("biz_address",""),
        "campaign_id": job.get("campaign_id",""), "campaign_name": job.get("campaign_name",""),
        "keyword": job.get("keyword_text",""), "keyword_variant": job.get("keyword_variant", job.get("keyword_text","")),
        "prompt": prompt, "follow_up": "", "has_follow_up": False,
        "device_id": DEVICES[device_idx][0], "platform": "gemini",
        "status": "success" if captured else "error", "duration_s": dur,
        "proxy_status": "CONNECTED", "proxy_username": gost_spec.get("upstream_user",""),
        "proxy_host": MAC_IP, "proxy_port": gost_spec["port"], "proxy_ip": proxy_ip or "none",
        "base_latitude": job.get("biz_lat",0) or 0, "base_longitude": job.get("biz_lng",0) or 0,
        "mocked_latitude": 0, "mocked_longitude": 0, "mocked_timezone": job.get("biz_timezone",""),
        "backlinks_expected": 0, "backlink_injected": False,
        "backlink_found": False, "backlink_url": "",
        "failure_step": err, "error": err,
        "response_text": (res.get("answer") or "")[:4000],
        "rank_position": res.get("rank_position") or "",
        "rank_total": res.get("rank_total") or "",
        "has_rank": bool(res.get("rank_position")),
    }

def session(device_idx, job, gost_spec, proxy_ip):
    port = 8765 + device_idx
    platform = job.get("platform","chatgpt").lower()
    if GEMINI_INLINE and platform == "gemini":
        return _gemini_cdp_session(device_idx, job, gost_spec, proxy_ip)
    prompt = job.get("prompt","")
    follow_up = job.get("follow_up","") or None
    backlinks = job.get("backlinks",[])
    bk_domain = extract_domain(backlinks[0]["url"]) if backlinks else ""
    t0 = time.time()

    http_post(port, "/session", {"platform":platform,"prompt":prompt,"followUp":follow_up,"backlinkDomain":bk_domain})

    for _ in range(50):
        time.sleep(8)
        r = http_post(port, "/status")
        if r.get("status") in ("completed","error"): break

    dur = round(time.time()-t0, 1)
    base_lat = job.get("biz_lat",0) or 0
    base_lng = job.get("biz_lng",0) or 0
    mlat, mlng = randomize_location(base_lat, base_lng) if (base_lat and base_lng) else (0,0)
    tz = job.get("biz_timezone","")
    bk_url = backlinks[0]["url"] if (r.get("backlink_clicked") and backlinks) else ""

    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "wave_index": 0,
        "client_id": job.get("client_id",""), "client_name": job.get("client_name",""),
        "biz_name": job.get("biz_name",""), "search_address": job.get("biz_address",""),
        "campaign_id": job.get("campaign_id",""), "campaign_name": job.get("campaign_name",""),
        "keyword": job.get("keyword_text",""), "keyword_variant": job.get("keyword_variant", job.get("keyword_text","")),
        "prompt": prompt,
        "follow_up": follow_up or "", "has_follow_up": bool(follow_up),
        "device_id": DEVICES[device_idx][0], "platform": platform,
        "status": "success" if r.get("status")=="completed" and not r.get("error") else "error",
        "duration_s": dur, "proxy_status": "CONNECTED",
        "proxy_username": gost_spec.get("upstream_user", ""),
        "proxy_host": MAC_IP, "proxy_port": gost_spec["port"], "proxy_ip": proxy_ip or "none",
        "base_latitude": base_lat, "base_longitude": base_lng,
        "mocked_latitude": mlat, "mocked_longitude": mlng, "mocked_timezone": tz,
        "backlinks_expected": len(backlinks),
        "backlink_injected": job.get("backlink_injected",False),
        "backlink_found": r.get("backlink_clicked",False), "backlink_url": bk_url,
        "failure_step": r.get("error",""), "error": r.get("error",""),
    }

def main():
    plan = json.load(open(PLAN_PATH))
    waves = plan["waves"]
    nd = len(DEVICES)
    # PLATFORMS env restricts which platforms run (e.g. "chatgpt,perplexity" to skip
    # Gemini while its proxy-flagging issue is unresolved). Flatten → filter → repack
    # into fleet-sized waves so job/device slot alignment stays correct.
    _plat_filter = {p.strip().lower() for p in os.environ.get("PLATFORMS", "").split(",") if p.strip()}
    if _plat_filter:
        flat = [j for w in waves for j in w if j.get("platform", "chatgpt").lower() in _plat_filter]
        waves = [flat[i:i + nd] for i in range(0, len(flat), nd)] or [[]]
        plan["waves"] = waves
        print(f"  [PLATFORMS filter] {sorted(_plat_filter)} -> {len(flat)} jobs, {len(waves)} waves of {nd}", flush=True)
    total = sum(len(w) for w in waves)
    out = os.path.splitext(PLAN_PATH)[0] + "_results.csv"
    start_wave = plan.get("start_wave", 1)

    # Startup banner — what's actually being run. Makes the log auditable.
    print("=" * 70, flush=True)
    print(f"  plan:           {PLAN_PATH}", flush=True)
    print(f"  total jobs:     {total}  ({len(waves)} waves, {nd} devices)", flush=True)
    print(f"  proxy host:     {PROXY_HOST}:{PROXY_PORT}", flush=True)
    print(f"  proxy user:     {PROXY_USER}", flush=True)
    print(f"  proxy target:   {PROXY_TARGET}", flush=True)
    print(f"  session dur:    {DURATION} min", flush=True)
    print(f"  wave stagger:   {WAVE_STAGGER_S}s between phones", flush=True)
    print(f"  retry rounds:   {RETRY_MAX_ROUNDS}  (triggers: {', '.join(RETRY_TRIGGERS)})", flush=True)
    print(f"  output csv:     {out}", flush=True)
    print("=" * 70, flush=True)

    # Port forwards once
    run("adb forward --remove-all")
    for i, (_, ser) in enumerate(DEVICES):
        run(f"adb -s \"{ser}\" forward tcp:{8765+i} tcp:8765")

    # Load existing results if resuming
    results = []
    if os.path.exists(out):
        with open(out, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                results.append(row)
        print(f"Loaded {len(results)} existing results from {out}")

    grand_total = len(results) + total
    ok_cnt = sum(1 for r in results if r.get("status") == "success")
    bk_cnt = sum(1 for r in results if r.get("backlink_found") in ("True", True))
    t0 = time.time()
    csv_lock = threading.Lock()

    fns = ["timestamp","date","wave_index","client_id","client_name","biz_name",
           "search_address","campaign_id","campaign_name","keyword","keyword_variant","prompt",
           "follow_up","has_follow_up","device_id","platform","status","duration_s",
           "proxy_status","proxy_username","proxy_host","proxy_port","proxy_ip",
           "base_latitude","base_longitude","mocked_latitude","mocked_longitude",
           "mocked_timezone","backlinks_expected","backlink_injected",
           "backlink_found","backlink_url","failure_step","error"]
    if GEMINI_INLINE:
        fns = fns + ["response_text","rank_position","rank_total","has_rank"]

    def save_csv():
        with csv_lock:
            with open(out, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fns); w.writeheader(); w.writerows(results)

    done = 0
    wave_queue = list(waves)
    deferred = []
    deferred_rounds = 0
    MAX_DEFERRED_ROUNDS = 3
    retry_jobs = []        # transient errors queued for retry with fresh Decodo session
    retry_rounds = 0
    WAVE_SLOTS = nd
    wi = 0
    while wi < len(wave_queue):
        wave = wave_queue[wi]
        wn = wi + start_wave; n = len(wave)
        used = min(n, nd)

        # Live phone check: skip offline slots, defer their jobs
        online_set = get_online_serials()
        slot_online = [DEVICES[i][1] in online_set for i in range(used)]
        offline_slots = [i for i in range(used) if not slot_online[i]]
        if offline_slots:
            names = [DEVICES[i][0] for i in offline_slots]
            for i in offline_slots:
                if i < n:
                    deferred.append(wave[i])
            print(f"[wave {wn}] OFFLINE phones: {names} — deferring {len(offline_slots)} jobs to extra wave")

        # If ALL phones offline, skip wave entirely
        if all(not s for s in slot_online):
            print(f"Wave {wn}: all phones offline, skipping (jobs deferred)")
            wi += 1
            continue

        # One gost with N ports for this wave (allocate for all slots; unused ports are harmless)
        specs = []
        for i in range(used):
            sid = f"phone{i:02d}"
            job_i = wave[i] if i < n else None
            if GEMINI_INLINE and job_i and job_i.get("platform","").lower() == "gemini":
                gz, gc = geo_target(job_i)
                uu = build_upstream_user(sid, zip_=gz, country=gc)
            else:
                uu = f"{PROXY_USER}-session-{sid}-sessionduration-{DURATION}-{PROXY_TARGET}"
            specs.append({"port": BASE_GOST + i, "upstream_user": uu, "sid": sid})
        gost_proc, gost_cfg = gost_start(specs)

        # Resolve per-port Decodo exit IPs via Mac-side curl through the gost
        # SOCKS5 listener. One curl per port; ~1-2s each. Cheap, parallel with
        # zero phone involvement. Stored for session() / tunnel_failed rows.
        proxy_ips = [resolve_proxy_ip(BASE_GOST + i) for i in range(used)]

        # Connect proxy + mock location PER DEVICE IN PARALLEL.
        # Sequential 10x ~5-8s = 50-80s of dead time per wave; parallel is ~10s.
        # All ADB calls are wrapped by run() so timeouts never escape this loop.
        tunnel_ok = [False] * used

        def _setup_one(i):
            if not slot_online[i]:
                return  # skip offline phone
            _, ser = DEVICES[i]
            try:
                socksdroid_connect(ser, BASE_GOST + i)
            except Exception as e:
                print(f"  [setup-err i={i}] socksdroid_connect: {e}", flush=True)
                return
            time.sleep(3)  # let VPN stabilize before checking
            try:
                tunnel_ok[i] = wait_tunnel(ser)
            except Exception as e:
                print(f"  [setup-err i={i}] wait_tunnel: {e}", flush=True)
                tunnel_ok[i] = False
                return
            if tunnel_ok[i] and i < n:
                job = wave[i]
                bl, bln = job.get("biz_lat", 0) or 0, job.get("biz_lng", 0) or 0
                if bl and bln:
                    ml, mln = randomize_location(bl, bln)
                    try: mock_location(ser, ml, mln)
                    except Exception as e: print(f"  [setup-warn i={i}] mock_location: {e}", flush=True)
                tz = job.get("biz_timezone", "")
                if tz:
                    try: set_timezone(ser, tz)
                    except Exception as e: print(f"  [setup-warn i={i}] set_timezone: {e}", flush=True)

        setup_threads = [threading.Thread(target=_setup_one, args=(i,)) for i in range(used)]
        for t in setup_threads: t.start()
        for t in setup_threads: t.join()

        # IP warmup. Parallelization saves ~45s of setup time per wave but also
        # eliminates the implicit IP-warmup window the sequential setup gave (the
        # first phone got 50s of idle time while other phones set up; with parallel
        # setup, the first phone fires its job ~5s after socksdroid_connect, which
        # is too early — Decodo IP isn't fully stabilised, page load is slow, and
        # input automation fires before the page is ready → "input failed" race).
        # 45s replicates the original sequential timing within ~10s.
        time.sleep(45)

        # Run jobs in parallel (only for ONLINE devices with working tunnel)
        threads = [None] * used
        wr = [None] * used
        print_lock = threading.Lock()
        def run_one(di, job):
            wr[di] = session(di, job, specs[di], proxy_ips[di])
            # Live per-thread print so we see results IN ORDER OF COMPLETION,
            # not blocked behind a slow earlier-indexed thread.
            r = wr[di]
            if r:
                ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
                fail = r.get("failure_step") or ""
                with print_lock:
                    print(f"  [{ts}] wave={wn} {r['device_id']} {r['platform']:11s} {r['status']:8s} dur={r['duration_s']}s ip={r.get('proxy_ip','-')[:18]:18s} step={fail[:25]}", flush=True)
        first_started = False
        for i in range(used):
            if i < n:
                if not slot_online[i]:
                    continue  # already deferred above
                if tunnel_ok[i]:
                    if first_started and WAVE_STAGGER_S > 0:
                        time.sleep(WAVE_STAGGER_S)
                    t = threading.Thread(target=run_one, args=(i, wave[i]))
                    t.start(); threads[i] = t
                    first_started = True
                else:
                    # Tunnel failed even though phone is online — create error result
                    j = wave[i]
                    wr[i] = {
                        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        "wave_index": wn,
                        "client_id": j.get("client_id",""), "client_name": j.get("client_name",""),
                        "biz_name": j.get("biz_name",""), "search_address": j.get("biz_address",""),
                        "campaign_id": j.get("campaign_id",""), "campaign_name": j.get("campaign_name",""),
                        "keyword": j.get("keyword_text",""), "keyword_variant": j.get("keyword_variant", j.get("keyword_text","")),
                        "prompt": j.get("prompt",""), "follow_up": j.get("follow_up","") or "", "has_follow_up": bool(j.get("follow_up","")),
                        "device_id": DEVICES[i][0], "platform": j.get("platform","chatgpt").lower(),
                        "status": "error", "duration_s": 0, "proxy_status": "FAILED",
                        "proxy_username": "", "proxy_host": MAC_IP, "proxy_port": BASE_GOST + i,
                        "proxy_ip": proxy_ips[i] or "none",
                        "base_latitude": j.get("biz_lat",0) or 0, "base_longitude": j.get("biz_lng",0) or 0,
                        "mocked_latitude": 0, "mocked_longitude": 0, "mocked_timezone": j.get("biz_timezone",""),
                        "backlinks_expected": len(j.get("backlinks",[])),
                        "backlink_injected": j.get("backlink_injected", False),
                        "backlink_found": False, "backlink_url": "",
                        "failure_step": "tunnel_failed", "error": "tunnel failed",
                    }

        # Wait and save per session
        for i, t in enumerate(threads):
            if t:
                t.join()
            r = wr[i]
            if r:
                r["wave_index"] = wn
                results.append(r)
                is_ok = 1 if r["status"] == "success" else 0
                is_bk = 1 if r.get("backlink_found") else 0
                ok_cnt += is_ok; bk_cnt += is_bk
                save_csv()
                elapsed = time.time() - t0
                rate = len(results) / elapsed if elapsed > 0 else 0
                eta = int((grand_total - len(results)) / rate / 60) if rate > 0 else 0
                print(f"[{len(results)}/{grand_total}] {r['device_id']} {r['platform']} {r['status']} bk={r['backlink_found']} | ok={ok_cnt} fail={len(results)-ok_cnt} bk_total={bk_cnt} | {r['duration_s']}s | ETA ~{eta}min", flush=True)
                # Queue transient errors for retry with a fresh Decodo session
                # (mirrors device_dispatch.py:217 retry trigger logic).
                if r.get("status") == "error":
                    err = (r.get("failure_step") or r.get("error") or "").lower()
                    j = wave[i]
                    cur_round = int(j.get("_retry_round", 0))
                    if cur_round < RETRY_MAX_ROUNDS and any(t in err for t in RETRY_TRIGGERS):
                        retry_j = dict(j); retry_j["_retry_round"] = cur_round + 1
                        retry_jobs.append(retry_j)
                        print(f"  [retry-queue] {r['device_id']} {r['platform']} err='{err[:40]}' → retry round {cur_round+1}", flush=True)

        # done counts only slots we actually attempted (online slots);
        # deferred jobs will be counted when their repack-wave runs
        attempted = sum(1 for s in slot_online if s)
        done += attempted

        # Disconnect proxies (only for slots we touched)
        for i in range(used):
            if slot_online[i]:
                socksdroid_disconnect(DEVICES[i][1])
        gost_stop(gost_proc, gost_cfg)

        wave_ok = sum(1 for r in wr if r and r['status'] == 'success')
        print(f"Wave {wn}: {wave_ok}/{attempted} ok | {done}/{total} done"
              + (f" | {len(deferred)} deferred" if deferred else ""))

        wi += 1

        # After preplanned waves done, if any deferred jobs, repack into extra waves
        if wi >= len(wave_queue) and deferred:
            deferred_rounds += 1
            if deferred_rounds > MAX_DEFERRED_ROUNDS:
                print(f"\n[deferred] {len(deferred)} jobs still pending after {MAX_DEFERRED_ROUNDS} retry rounds — giving up")
                for j in deferred:
                    results.append({
                        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        "wave_index": 0,
                        "client_id": j.get("client_id",""), "client_name": j.get("client_name",""),
                        "biz_name": j.get("biz_name",""), "search_address": j.get("biz_address",""),
                        "campaign_id": j.get("campaign_id",""), "campaign_name": j.get("campaign_name",""),
                        "keyword": j.get("keyword_text",""), "keyword_variant": j.get("keyword_variant", j.get("keyword_text","")),
                        "prompt": j.get("prompt",""), "follow_up": j.get("follow_up","") or "", "has_follow_up": bool(j.get("follow_up","")),
                        "device_id": "", "platform": j.get("platform","chatgpt").lower(),
                        "status": "error", "duration_s": 0, "proxy_status": "SKIPPED",
                        "proxy_username": "", "proxy_host": "", "proxy_port": 0,
                        "base_latitude": j.get("biz_lat",0) or 0, "base_longitude": j.get("biz_lng",0) or 0,
                        "mocked_latitude": 0, "mocked_longitude": 0, "mocked_timezone": j.get("biz_timezone",""),
                        "backlinks_expected": len(j.get("backlinks",[])),
                        "backlink_injected": j.get("backlink_injected", False),
                        "backlink_found": False, "backlink_url": "",
                        "failure_step": "phone_offline_persistent",
                        "error": "phone offline for all retry rounds",
                    })
                save_csv()
                deferred = []
            else:
                print(f"\n[deferred round {deferred_rounds}/{MAX_DEFERRED_ROUNDS}] {len(deferred)} jobs from offline phones — repacking into extra waves")
                random.shuffle(deferred)
                extra_waves = []
                rem = list(deferred)
                deferred = []
                while rem:
                    w_pack = []
                    used_c, used_camp = set(), set()
                    leftover = []
                    for j in rem:
                        if len(w_pack) >= WAVE_SLOTS: leftover.append(j); continue
                        if j["client_id"] in used_c or j["campaign_id"] in used_camp:
                            leftover.append(j); continue
                        w_pack.append(j); used_c.add(j["client_id"]); used_camp.add(j["campaign_id"])
                    if not w_pack:
                        w_pack = leftover[:WAVE_SLOTS]; leftover = leftover[WAVE_SLOTS:]
                    extra_waves.append(w_pack); rem = leftover
                wave_queue.extend(extra_waves)
                total += sum(len(w) for w in extra_waves)
                grand_total += sum(len(w) for w in extra_waves)
                print(f"[deferred] appended {len(extra_waves)} extra waves ({sum(len(w) for w in extra_waves)} jobs)")

        # Retry repack — same shape as deferred. Triggers only after preplanned
        # + deferred waves are exhausted, and only up to RETRY_MAX_ROUNDS times.
        if wi >= len(wave_queue) and retry_jobs and retry_rounds < RETRY_MAX_ROUNDS:
            retry_rounds += 1
            print(f"\n[retry round {retry_rounds}/{RETRY_MAX_ROUNDS}] {len(retry_jobs)} jobs from transient errors — repacking into extra waves", flush=True)
            random.shuffle(retry_jobs)
            extra_waves = []
            rem = list(retry_jobs)
            retry_jobs = []
            while rem:
                w_pack = []
                used_c, used_camp = set(), set()
                leftover = []
                for j in rem:
                    if len(w_pack) >= WAVE_SLOTS: leftover.append(j); continue
                    if j["client_id"] in used_c or j["campaign_id"] in used_camp:
                        leftover.append(j); continue
                    w_pack.append(j); used_c.add(j["client_id"]); used_camp.add(j["campaign_id"])
                if not w_pack:
                    w_pack = leftover[:WAVE_SLOTS]; leftover = leftover[WAVE_SLOTS:]
                extra_waves.append(w_pack); rem = leftover
            wave_queue.extend(extra_waves)
            total += sum(len(w) for w in extra_waves)
            grand_total += sum(len(w) for w in extra_waves)
            print(f"[retry] appended {len(extra_waves)} retry waves ({sum(len(w) for w in extra_waves)} jobs)", flush=True)

    elapsed = time.time() - t0
    print(f"\nDone. {len(results)} jobs | OK:{ok_cnt} Fail:{len(results)-ok_cnt} Bk:{bk_cnt} | {elapsed/60:.0f}min | {out}")

if __name__ == "__main__":
    main()
