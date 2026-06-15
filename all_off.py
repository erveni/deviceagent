#!/usr/bin/env python3
"""all_off.py — the proxy/VPN KILL SWITCH. Turns EVERYTHING off so nothing is left stuck on.

For every phone on the LAN (auto-discovered, or --phones a,b,c):
  - POST /proxy/stop      → drop the SocksDroid/Decodo per-app proxy (if that build)
  - POST /vpn/disconnect  → drop NordVPN                            (if that build)
Then kills any gost / sni_relay process on this Mac, and prints the final tunnel state
of every phone so you can SEE it's clean.

Both phone calls are harmless if the endpoint isn't on that build (404/000 ignored), so this
works against the SEO (Decodo) build AND the CitedLogic (NordVPN) build. Idempotent — safe to
run anytime, especially "done testing, turn it all off".

  python3 all_off.py                 # discover phones on the LAN, turn everything off
  python3 all_off.py --phones 192.168.254.101,192.168.254.107
"""
from __future__ import annotations
import argparse
import json
import socket
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

PORT = 8765


def _local_subnet() -> str | None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80)); return s.getsockname()[0].rsplit(".", 1)[0]
    except OSError:
        return None
    finally:
        s.close()


def discover(subnet: str | None) -> list[str]:
    subnet = subnet or _local_subnet()
    if not subnet:
        return []
    def probe(ip):
        try:
            urllib.request.urlopen(f"http://{ip}:{PORT}/health", timeout=0.6).read(); return ip
        except Exception:
            return None
    with ThreadPoolExecutor(max_workers=64) as ex:
        return sorted([r for r in ex.map(probe, [f"{subnet}.{i}" for i in range(1, 255)]) if r],
                      key=lambda ip: int(ip.rsplit(".", 1)[1]))


def _post(ip: str, path: str) -> None:
    try:
        req = urllib.request.Request(f"http://{ip}:{PORT}{path}", data=b"{}",
                                     method="POST", headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=15).read()
    except Exception:
        pass  # endpoint absent on this build, or the proxy teardown reset the request — both fine


def _tun_up(ip: str):
    try:
        with urllib.request.urlopen(f"http://{ip}:{PORT}/health", timeout=5) as r:
            return (json.loads(r.read()).get("tun0") or {}).get("up")
    except Exception:
        return "unreachable"


def kill_mac_proxies() -> None:
    for pat in ("gost", "sni_relay", "superproxy"):
        subprocess.run(["pkill", "-f", pat], capture_output=True)
    print("  [mac] killed any gost/sni_relay/superproxy process")


def main() -> None:
    ap = argparse.ArgumentParser(description="Turn off ALL phone proxies/VPNs + Mac gost")
    ap.add_argument("--phones", help="comma-separated IPs (default: auto-discover the LAN)")
    args = ap.parse_args()

    phones = ([p.strip() for p in args.phones.split(",") if p.strip()]
              if args.phones else discover(None))
    if not phones:
        print("no phones found on the LAN"); sys.exit(0)

    print(f"turning OFF proxy + VPN on {len(phones)} phone(s): {', '.join(phones)}")
    for ip in phones:
        _post(ip, "/proxy/stop")        # Decodo / SocksDroid per-app
        _post(ip, "/vpn/disconnect")    # NordVPN
        print(f"  [{ip}] proxy/stop + vpn/disconnect sent")
    kill_mac_proxies()

    print("final tunnel state:")
    all_off = True
    for ip in phones:
        up = _tun_up(ip)
        if up is True:
            all_off = False
        print(f"  {ip}: tun0.up = {up}")
    print("✅ ALL OFF" if all_off else "⚠️  something still up — re-run or check the phone")
    sys.exit(0 if all_off else 1)


if __name__ == "__main__":
    main()
