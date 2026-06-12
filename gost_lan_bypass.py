#!/usr/bin/env python3
"""
Launch a gost v3 SOCKS5 listener that chains to Decodo residential BUT bypasses
the LAN (private ranges) so the phone can reach the Mac directly through the same
tunnel. This is the proxy half of the INVERTED control plane:

  phone SocksDroid (route=all) ─▶ this gost ─┬─ public dst ─▶ Decodo residential
                                             └─ 192.168/10/172 ─▶ direct (the Mac)

Without the LAN bypass, the phone's poll/post to the Mac (a private IP) would be
handed to Decodo, which can't route to the Mac → the persistent-tunnel control
loop would break. The bypass is attached to the Decodo *node*, so matching
destinations skip the node and gost dials them directly.

Usage:
  set -a; source .env.dev; set +a
  export PROXY_PASSWORD="$PROXY_PASS"        # if not already set
  python3 gost_lan_bypass.py --port 11001 --zip 78701 [--session S]
Leaves gost running in the foreground (Ctrl-C to stop); writes config+log to /tmp.
"""
import argparse
import os
import socket
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "aeo-appium"))
import gost_manager as g  # build_upstream_username + PROXY_* + GOST_BINARY

LAN_MATCHERS = ["192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12", "127.0.0.0/8"]


def pick_healthy_gateway(host: str, port: int, timeout: float = 4.0) -> str:
    """gate.decodo.com round-robins across several gateway IPs and some have an
    unreachable SOCKS port (seen: 95.177.122.2 — ping OK but :10001 refused),
    which makes gost intermittently time out. Resolve all A records, TCP-probe
    :port, and return the first IP that actually accepts a connection. Falls back
    to the hostname if none probe OK (let gost try)."""
    try:
        ips = sorted({ai[4][0] for ai in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)})
    except Exception:
        return host
    for ip in ips:
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                print(f"[gost] healthy Decodo gateway: {ip}:{port} (of {ips})")
                return ip
        except Exception:
            print(f"[gost] gateway {ip}:{port} unreachable — skipping")
    print(f"[gost] no healthy gateway probed; falling back to {host}")
    return host


def build_config(port: int, zip_code: str, session_id: str) -> str:
    user = g.build_upstream_username(zip_code=zip_code, country="us", session_id=session_id)
    pw = g.PROXY_PASSWORD
    gw = pick_healthy_gateway(g.PROXY_HOST, g.PROXY_PORT)
    bypass = "\n".join(f"      - {m}" for m in LAN_MATCHERS)
    return f"""bypasses:
  - name: bypass-lan
    matchers:
{bypass}
services:
  - name: service-0
    addr: ":{port}"
    handler:
      type: socks5
      chain: chain-0
    listener:
      type: tcp
chains:
  - name: chain-0
    hops:
      - name: hop-0
        nodes:
          - name: decodo-0
            addr: {gw}:{g.PROXY_PORT}
            bypass: bypass-lan
            connector:
              type: socks5
              auth:
                username: "{user}"
                password: "{pw}"
            dialer:
              type: tcp
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=11001)
    ap.add_argument("--zip", default="78701")
    ap.add_argument("--session", default="inv1")
    ap.add_argument("--print-only", action="store_true", help="print config and exit")
    args = ap.parse_args()

    if not g.PROXY_PASSWORD:
        sys.exit("PROXY_PASSWORD not set — `set -a; source .env.dev; set +a` first")

    cfg = build_config(args.port, args.zip, args.session)
    if args.print_only:
        print(cfg)
        return
    f = tempfile.NamedTemporaryFile("w", suffix=".yaml", prefix="gost_lanbypass_", delete=False)
    f.write(cfg)
    f.close()
    log = f.name.replace(".yaml", ".log")
    print(f"[gost] :{args.port} -> Decodo zip={args.zip} (LAN bypassed direct) | cfg={f.name} log={log}")
    with open(log, "w") as lf:
        proc = subprocess.Popen([g.GOST_BINARY, "-C", f.name, "-D"], stdout=lf, stderr=subprocess.STDOUT)
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()


if __name__ == "__main__":
    main()
