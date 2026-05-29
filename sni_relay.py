"""SNI-rewriting SOCKS5 relay for mobile Decodo.

SocksDroid (tun2socks) on the phones can only IP-CONNECT: it resolves DNS
locally (PH side) and asks the upstream SOCKS proxy to connect to a raw IP.
Mobile Decodo rejects IP-CONNECT to non-anycast destinations (error 0x02
"not allowed by ruleset") and cannot route to geo-specific Google edge IPs
(0x03 "host unreachable"). Result on the phone: "site can't be reached".

This relay sits between SocksDroid and the existing gost->Decodo chain. It
accepts the phone's IP-CONNECT, peeks the TLS ClientHello to recover the real
hostname (SNI), then re-dials the upstream by HOSTNAME (remote DNS at the
Decodo US exit). Decodo resolves + connects from the US, reaching the correct
regional edge. Empirically, hostname-CONNECT to gemini.google.com returns 200
where IP-CONNECT fails.

Flow:  SocksDroid (IP-CONNECT) -> sni_relay (extract SNI) -> gost (hostname) -> Decodo

Usage:
    python3 sni_relay.py <listen_port> <gost_port>

The relay accepts SOCKS5 with optional username/password auth (any creds, to
match SocksDroid's anon/anon) and forwards upstream to 127.0.0.1:<gost_port>
using gost's anon/anon. Non-TLS / no-SNI connections fall back to the original
IP-CONNECT so behaviour is unchanged for those.
"""

import socket
import socketserver
import struct
import sys
import threading

import socks  # PySocks

GOST_HOST = "127.0.0.1"
GOST_USER = "anon"
GOST_PASS = "anon"
GOST_PORT = 0  # set from argv in __main__

SNI_PEEK_TIMEOUT = 5.0
UPSTREAM_TIMEOUT = 30.0
BUF = 65536


def parse_sni(data: bytes) -> str | None:
    """Extract the SNI host from a TLS ClientHello. Returns None if absent."""
    try:
        if len(data) < 5 or data[0] != 0x16:  # not a TLS handshake record
            return None
        # TLS record header: type(1) version(2) length(2)
        pos = 5
        if len(data) < pos + 4:
            return None
        if data[pos] != 0x01:  # not ClientHello
            return None
        # handshake: type(1) length(3) version(2) random(32)
        pos += 4 + 2 + 32
        if pos >= len(data):
            return None
        # session_id
        sid_len = data[pos]
        pos += 1 + sid_len
        # cipher suites
        if pos + 2 > len(data):
            return None
        cs_len = struct.unpack(">H", data[pos:pos + 2])[0]
        pos += 2 + cs_len
        # compression methods
        if pos + 1 > len(data):
            return None
        comp_len = data[pos]
        pos += 1 + comp_len
        # extensions
        if pos + 2 > len(data):
            return None
        ext_total = struct.unpack(">H", data[pos:pos + 2])[0]
        pos += 2
        end = pos + ext_total
        while pos + 4 <= end and pos + 4 <= len(data):
            ext_type, ext_len = struct.unpack(">HH", data[pos:pos + 4])
            pos += 4
            if ext_type == 0x0000:  # server_name
                # server_name_list: list_len(2) name_type(1) name_len(2) name
                if pos + 5 > len(data):
                    return None
                name_type = data[pos + 2]
                name_len = struct.unpack(">H", data[pos + 3:pos + 5])[0]
                if name_type != 0:
                    return None
                host = data[pos + 5:pos + 5 + name_len]
                return host.decode("idna") if host else None
            pos += ext_len
    except Exception:
        return None
    return None


def recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("peer closed during read")
        buf += chunk
    return buf


def socks5_handshake(client: socket.socket) -> tuple[str, int]:
    """Complete SOCKS5 greeting + CONNECT request. Returns (dst_host, dst_port)."""
    ver, nmethods = struct.unpack("!BB", recv_exact(client, 2))
    if ver != 0x05:
        raise ConnectionError(f"bad socks version {ver}")
    methods = recv_exact(client, nmethods)
    if 0x02 in methods:
        # username/password auth — accept any credentials
        client.sendall(b"\x05\x02")
        v = recv_exact(client, 1)[0]
        ulen = recv_exact(client, 1)[0]
        recv_exact(client, ulen)
        plen = recv_exact(client, 1)[0]
        recv_exact(client, plen)
        client.sendall(b"\x01\x00")  # auth success
    else:
        client.sendall(b"\x05\x00")  # no auth

    ver, cmd, _rsv, atyp = struct.unpack("!BBBB", recv_exact(client, 4))
    if cmd != 0x01:  # only CONNECT
        client.sendall(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
        raise ConnectionError(f"unsupported cmd {cmd}")
    if atyp == 0x01:
        host = socket.inet_ntoa(recv_exact(client, 4))
    elif atyp == 0x03:
        dlen = recv_exact(client, 1)[0]
        host = recv_exact(client, dlen).decode("idna")
    elif atyp == 0x04:
        host = socket.inet_ntop(socket.AF_INET6, recv_exact(client, 16))
    else:
        raise ConnectionError(f"bad atyp {atyp}")
    port = struct.unpack(">H", recv_exact(client, 2))[0]
    # reply success, bound addr 0.0.0.0:0
    client.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
    return host, port


def open_upstream(host: str, port: int) -> socket.socket:
    s = socks.socksocket()
    s.set_proxy(socks.SOCKS5, GOST_HOST, GOST_PORT,
                username=GOST_USER, password=GOST_PASS, rdns=True)
    s.settimeout(UPSTREAM_TIMEOUT)
    s.connect((host, port))
    return s


def dial_direct(host: str, port: int) -> socket.socket:
    """Open a plain socket from the Mac (bypassing gost/Decodo). Used for DNS:
    mobile Decodo rejects IP-CONNECT to a resolver, so the phone can't resolve
    any hostname. The A-record returned here is irrelevant — the phone's next
    :443 connect is SNI-rewritten to the hostname, overriding the resolved IP."""
    return socket.create_connection((host, port), timeout=UPSTREAM_TIMEOUT)


def pipe(a: socket.socket, b: socket.socket) -> None:
    try:
        while True:
            data = a.recv(BUF)
            if not data:
                break
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


class Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        client = self.request
        upstream = None
        try:
            dst_ip, dst_port = socks5_handshake(client)

            head = b""
            if dst_port == 53:
                # DNS must bypass Decodo (it rejects IP-CONNECT to a resolver).
                upstream = dial_direct(dst_ip, dst_port)
            else:
                target_host = dst_ip
                if dst_port == 443:
                    client.settimeout(SNI_PEEK_TIMEOUT)
                    try:
                        head = client.recv(BUF)
                        sni = parse_sni(head)
                        if sni:
                            target_host = sni
                    except (OSError, socket.timeout):
                        pass
                    finally:
                        client.settimeout(None)
                upstream = open_upstream(target_host, dst_port)
                if head:
                    upstream.sendall(head)

            t = threading.Thread(target=pipe, args=(client, upstream), daemon=True)
            t.start()
            pipe(upstream, client)
            t.join(timeout=1)
        except Exception as e:
            print(f"[relay] {type(e).__name__}: {e}", flush=True)
        finally:
            if upstream is not None:
                try:
                    upstream.close()
                except OSError:
                    pass


class ThreadingServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    global GOST_PORT
    if len(sys.argv) != 3:
        print("usage: python3 sni_relay.py <listen_port> <gost_port>", file=sys.stderr)
        sys.exit(2)
    listen_port = int(sys.argv[1])
    GOST_PORT = int(sys.argv[2])
    srv = ThreadingServer(("0.0.0.0", listen_port), Handler)
    print(f"[relay] listening :{listen_port} -> gost 127.0.0.1:{GOST_PORT} "
          f"(SNI rewrite, IP-CONNECT fallback)", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
