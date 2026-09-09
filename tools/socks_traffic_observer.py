"""Passive local SOCKS byte accounting. No TLS interception or routing changes.

Only hostname/port and cumulative byte counts are written. Never persist the
SOCKS credentials, TLS handshake, URL, answer, or payload. Missing SNI is explicit.
"""
import json
import re
import socket
import socketserver
import struct
import threading
import time

from sni_relay import parse_sni


class Destination:
    def __init__(self):
        self.buffer = b''
        self.stage = 'greeting'
        self.host = 'unknown'
        self.port = 0

    def feed(self, data):
        if self.stage == 'done':
            return
        self.buffer += data
        if len(self.buffer) > 65536:
            self.stage, self.buffer = 'done', b''
            return
        while True:
            b = self.buffer
            if self.stage in ('greeting', 'auth'):
                if len(b) < 2:
                    return
                n = 2 + b[1]
                if self.stage == 'auth':
                    if len(b) < n + 1:
                        return
                    n += 1 + b[n]
                if len(b) < n:
                    return
                next_stage = 'auth' if self.stage == 'greeting' and 2 in b[2:n] else 'request'
                self.stage = next_stage
            elif self.stage == 'request':
                if len(b) < 5:
                    return
                atyp = b[3]
                n = {1: 10, 4: 22}.get(atyp, 7 + b[4] if atyp == 3 else 0)
                if not n:
                    self.stage, self.buffer = 'done', b''
                    return
                if len(b) < n:
                    return
                self.port = struct.unpack('!H', b[n-2:n])[0]
                if atyp == 3:
                    host = b[5:n-2].decode('ascii', errors='replace')
                    if re.fullmatch(r'[A-Za-z0-9._-]{1,253}', host):
                        self.host = host.lower()
                else:
                    # Do not persist destination IPs; TLS SNI gives useful host labels.
                    self.host = 'ip_without_sni'
                self.stage = 'tls' if self.port == 443 else 'done'
            elif self.stage == 'tls':
                if len(b) < 5:
                    return
                if b[0] == 22 and len(b) < 5 + int.from_bytes(b[3:5], 'big'):
                    return
                host = parse_sni(b)
                if host and re.fullmatch(r'[A-Za-z0-9._-]{1,253}', host):
                    self.host = host.lower()
                self.stage, self.buffer = 'done', b''
                return
            else:
                self.buffer = b''
                return
            self.buffer = b[n:]


class TrafficObserver:
    def __init__(self, listen_port, upstream_port, path):
        self.path = path
        self.upstream_port = upstream_port
        self.lock = threading.Lock()
        self.rows = []
        self.sockets = set()
        self.halt = threading.Event()
        owner = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                row = {'id': 0, 'input_bytes': 0, 'output_bytes': 0, 'closed': False,
                       'destination': Destination()}
                upstream = None
                with owner.lock:
                    row['id'] = len(owner.rows)
                    owner.rows.append(row)
                    owner.sockets.add(self.request)
                def pipe(source, target, direction):
                    try:
                        while not owner.halt.is_set():
                            data = source.recv(65536)
                            if not data:
                                break
                            with owner.lock:
                                row[direction] += len(data)
                                if direction == 'input_bytes':
                                    row['destination'].feed(data)
                            target.sendall(data)
                    except OSError:
                        pass
                    finally:
                        for conn in (source, target):
                            try:
                                conn.shutdown(socket.SHUT_RDWR)
                            except OSError:
                                pass
                try:
                    upstream = socket.create_connection(('127.0.0.1', owner.upstream_port), timeout=10)
                    upstream.settimeout(None)
                    with owner.lock:
                        owner.sockets.add(upstream)
                    worker = threading.Thread(target=pipe, args=(self.request, upstream, 'input_bytes'), daemon=True)
                    worker.start()
                    pipe(upstream, self.request, 'output_bytes')
                    worker.join(timeout=2)
                except OSError:
                    pass
                finally:
                    with owner.lock:
                        row['closed'] = True
                        owner.sockets.discard(self.request)
                        owner.sockets.discard(upstream)
                    if upstream:
                        upstream.close()

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self.server = Server(('0.0.0.0', listen_port), Handler)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.sampler = threading.Thread(target=self._sample, daemon=True)

    def start(self):
        # Exclusive creation prevents accidental evidence overwrite.
        with open(self.path, 'x'):
            pass
        self.worker.start()
        self.sampler.start()
        return self

    def snapshot(self):
        with self.lock:
            rows = [dict(id=r['id'], host=r['destination'].host, port=r['destination'].port,
                         input_bytes=r['input_bytes'], output_bytes=r['output_bytes'], closed=r['closed'])
                    for r in self.rows]
        with open(self.path, 'a') as out:
            out.write(json.dumps(dict(time=time.time(), source='passive_socks_cumulative', connections=rows))+'\n')

    def _sample(self):
        while not self.halt.wait(1):
            self.snapshot()

    def stop(self):
        self.halt.set()
        self.server.shutdown()
        with self.lock:
            sockets = list(self.sockets)
        for conn in sockets:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self.sampler.join(timeout=2)
        self.snapshot()
        self.server.server_close()
