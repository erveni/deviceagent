#!/usr/bin/env python3
"""One-off SPIKE (not committed long-term): measure two things over a live US tunnel.

Spike 1 — direct ?q= captcha rate: K fresh US IPs x M sequential direct-nav loads
          each, classify clean / captcha / unknown from the a11y dump. Answers
          "if we ship the direct-?q= fix, what captcha rate do we get?" (target <10%).
Spike 2 — uule effect (self-validating): on one clean IP, load the SAME keyword with
          uule=New York vs uule=Los Angeles (if their local packs differ, the uule
          encoder works), then gl=us-only vs gl=us+uule=SF to see if pinning a city
          changes the SERP. Screenshots saved for eyeball comparison.

Direct-nav only (am start VIEW url) — bypasses the broken typed-input step, so this
needs no APK change. Residential gost-direct (fast). Dummy/own measurement only.
"""
import base64, os, subprocess, sys, time
import run_with_proxy as rwp
import seo_proxy_run as spr

def _detect_mac_ip():
    try:
        rt = subprocess.run(["route", "get", "default"], capture_output=True, text=True).stdout
        ifn = next((l.split(":")[1].strip() for l in rt.splitlines() if "interface:" in l), "en0")
        return subprocess.run(["ipconfig", "getifaddr", ifn], capture_output=True, text=True).stdout.strip() or None
    except Exception:
        return None


_macip = os.environ.get("MAC_IP") or _detect_mac_ip()
if _macip and _macip != rwp.MAC_IP:
    print(f"[spike] MAC_IP {rwp.MAC_IP} -> {_macip} (DHCP changed; socksdroid dials this)")
    rwp.MAC_IP = _macip

IDX = int(os.environ.get("SPIKE_IDX", "4"))      # device-105 (SEO-capable, but only Chrome needed)
SERIAL = rwp.DEVICES[IDX][1]
OUT = "/tmp/spike"; os.makedirs(OUT, exist_ok=True)
host, port, user_prefix, password = spr._gateway("residential")
rwp.PROXY_HOST, rwp.PROXY_PORT, rwp.PROXY_PASS = host, int(port), password

CAPTCHA = ["sorry/index", "not a robot", "unusual traffic", "detected unusual",
           "recaptcha", "verifying you are human", "/sorry/"]
SERPISH = ["places", "web results", "sponsored", "more results", "people also ask",
           "image results", "shopping results", "related searches"]


def adb(*a, t=20):
    return subprocess.run(["adb", "-s", SERIAL, *a], capture_output=True, text=True, timeout=t)


def _gost_http_config(sid):
    """gost: local SOCKS5 listener -> Decodo via HTTP CONNECT (not SOCKS5).
    On this network SOCKS5->Decodo:10001 is flaky/timing out, but HTTP CONNECT
    to :10001 works cleanly (verified by curl). Sticky US session via username."""
    user = f"{user_prefix}-country-us-session-{sid}-sessionduration-30"
    cfg = f"/tmp/gost_http_{os.getpid()}_{sid}.yaml"
    open(cfg, "w").write(
        "services:\n"
        f"  - name: s0\n    addr: \":{spr.GOST_PORT}\"\n"
        "    handler: {type: socks5, chain: c0, auth: {username: anon, password: anon}}\n"
        "    listener: {type: tcp}\n"
        "chains:\n  - name: c0\n    hops:\n      - name: h0\n        nodes:\n"
        f"          - name: d0\n            addr: {host}:{int(port)}\n"
        f"            connector: {{type: http, auth: {{username: \"{user}\", password: \"{password}\"}}}}\n"
        "            dialer: {type: tcp}\n")
    proc = subprocess.Popen([rwp.GOST_BIN, "-C", cfg, "-D"],
                            stdout=open(cfg + ".log", "w"), stderr=subprocess.STDOUT)
    time.sleep(2)
    if proc.poll() is not None:
        raise RuntimeError(f"gost died: {cfg}.log")
    return proc, cfg


def bring_up(sid):
    gp, gc = _gost_http_config(sid)
    ip = rwp.resolve_proxy_ip(spr.GOST_PORT)
    rwp.socksdroid_connect(SERIAL, spr.GOST_PORT)
    ok = rwp.wait_tunnel(SERIAL)
    return gp, gc, ip, ok


def tear(gp, gc):
    try: rwp.socksdroid_disconnect(SERIAL)
    except Exception: pass
    try: rwp.gost_stop(gp, gc)
    except Exception: pass


def load(url, tag, settle=15):
    adb("shell", "pm", "clear", "com.android.chrome", t=30); time.sleep(1)
    adb("shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url,
        "com.android.chrome", t=15)
    time.sleep(settle)
    adb("shell", "uiautomator", "dump", "/sdcard/sp.xml", t=20)
    xml = adb("shell", "cat", "/sdcard/sp.xml", t=15).stdout
    low = xml.lower()
    png = f"{OUT}/{tag}.png"
    try:
        raw = subprocess.run(["adb", "-s", SERIAL, "exec-out", "screencap", "-p"],
                             capture_output=True, timeout=20).stdout
        open(png, "wb").write(raw)
    except Exception:
        png = ""
    if any(k in low for k in CAPTCHA):
        cls = "captcha"
    elif any(k in low for k in SERPISH):
        cls = "clean"
    else:
        cls = "unknown"
    return cls, png, low


def uule(loc):
    key = "w+CAIQICI"
    secret = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    enc = base64.b64encode(loc.encode()).decode()
    return key + secret[len(loc) % 64] + enc


def main():
    print(f"[spike] device={rwp.DEVICES[IDX][0]} serial={SERIAL}", flush=True)

    # ── Spike 1: direct ?q= captcha rate ──────────────────────────────────
    print("\n===== SPIKE 1: direct ?q= captcha rate (US residential) =====", flush=True)
    KW = "coffee shop near me"
    K, M = 4, 3
    s1 = []
    for g in range(K):
        sid = spr._sid()
        gp, gc, ip, ok = bring_up(sid)
        if not ok:
            print(f"[s1] group {g} sid={sid} ip={ip} TUNNEL_FAIL", flush=True)
            tear(gp, gc); continue
        for m in range(M):
            url = f"https://www.google.com/search?q={KW.replace(' ', '+')}&hl=en&gl=us"
            cls, png, _ = load(url, tag=f"s1_g{g}_m{m}")
            s1.append((ip, m, cls))
            print(f"[s1] ip={ip} load#{m+1} -> {cls}  ({png})", flush=True)
        tear(gp, gc)

    n = len(s1)
    cap = sum(1 for _, _, c in s1 if c == "captcha")
    clean = sum(1 for _, _, c in s1 if c == "clean")
    unk = sum(1 for _, _, c in s1 if c == "unknown")
    print(f"\n[S1 RESULT] n={n}  clean={clean}  captcha={cap}  unknown={unk}", flush=True)
    if n:
        print(f"[S1 RESULT] captcha_rate={cap/n*100:.0f}%  clean_rate={clean/n*100:.0f}%", flush=True)
        cold = [c for _, m, c in s1 if m == 0]
        warm = [c for _, m, c in s1 if m > 0]
        print(f"[S1 RESULT] cold(1st/IP) captcha={sum(1 for c in cold if c=='captcha')}/{len(cold)}"
              f"  warm(2nd+) captcha={sum(1 for c in warm if c=='captcha')}/{len(warm)}", flush=True)

    # ── Spike 2: uule effect (self-validating) ────────────────────────────
    print("\n===== SPIKE 2: uule effect (self-validating) =====", flush=True)
    sid = spr._sid()
    gp, gc, ip, ok = bring_up(sid)
    if not ok:
        print(f"[s2] tunnel fail ip={ip}", flush=True); tear(gp, gc); return
    print(f"[s2] on IP {ip}", flush=True)
    KW2 = "coffee shop"
    locs = {
        "none": None,
        "NY":   "New York,New York,United States",
        "LA":   "Los Angeles,California,United States",
        "SF":   "San Francisco,California,United States",
    }
    for tag, loc in locs.items():
        u = f"&uule={uule(loc)}" if loc else ""
        url = f"https://www.google.com/search?q={KW2.replace(' ', '+')}&hl=en&gl=us{u}"
        cls, png, low = load(url, tag=f"s2_{tag}")
        # crude "results for <place>" sniff
        marker = ""
        for kw in ["results for", "near ", "results near"]:
            i = low.find(kw)
            if i >= 0:
                marker = low[i:i+60].replace("\n", " "); break
        print(f"[s2] {tag:5} loc={loc} -> {cls}  marker={marker!r}  ({png})", flush=True)
    tear(gp, gc)
    print("\n[spike] DONE — compare screenshots in /tmp/spike/ (s2_NY vs s2_LA validates uule; "
          "s2_none vs s2_SF shows the city-pin effect).", flush=True)


if __name__ == "__main__":
    try:
        main()
    finally:
        try: rwp.socksdroid_disconnect(SERIAL)
        except Exception: pass
