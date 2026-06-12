#!/usr/bin/env python3
"""
Mac job-server for the INVERTED control plane (CONTROL_MODE=http, phone-pull).

Why inverted: a full-device SocksDroid VPN captures the Mac<->phone Wi-Fi link, so
the Mac cannot *reach into* a phone whose proxy is up (and SocksDroid exposes no
app-driven stop without root). Instead the PHONE initiates everything: it registers,
pulls a job, runs it (bringing its own proxy up), and pushes the result back. All
phone-initiated, so it works even while the VPN is up (phone -> gost-on-Mac -> Mac)
and a transient Wi-Fi flap just means the phone's next poll retries -- no long-lived
inbound socket to drop. This is the flap-resilient replacement for the per-job ADB path.

Endpoints (all phone-initiated):
  POST /register     {serial, ip, version}            -> register / heartbeat
  GET  /next-job?serial=S                             -> 200 job JSON | 204 no work
  POST /result       {serial, job_id, ...}            -> store result
Operator endpoints (Mac-side, for driving/observing):
  GET  /status                                        -> registry + queue + results summary
  POST /seed         {job}  (or {jobs:[...]})         -> enqueue job(s)

Stdlib only. In-memory queue (this is the dummy-data harness; RabbitMQ wiring comes later).
"""
import base64
import json
import os
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HOST = "0.0.0.0"
PORT = 8870
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inverted_results")


def _save_screenshots(job_id: str, serial: str, data: dict) -> list:
    """Decode any screenshot_*_b64 fields in a result and write them as PNGs."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    saved = []
    for key, val in data.items():
        if key.startswith("screenshot") and key.endswith("_b64") and val:
            tag = key[len("screenshot"):-len("_b64")].strip("_") or "main"
            path = os.path.join(RESULTS_DIR, f"{job_id}_{serial}_{tag}.png")
            try:
                with open(path, "wb") as f:
                    f.write(base64.b64decode(val))
                saved.append(path)
            except Exception as e:
                print(f"  [screenshot] {key} decode failed: {e}")
    return saved

_lock = threading.Lock()
_jobs = deque()                 # pending jobs (dicts with at least job_id)
_inflight = {}                  # job_id -> {job, serial, sent_at}
_results = []                   # completed result dicts
_registry = {}                  # serial -> {ip, version, last_seen, jobs_done}
_seq = {"n": 0}


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _next_job_id():
    _seq["n"] += 1
    return f"job-{_seq['n']:04d}"


def _enqueue(job):
    if "job_id" not in job:
        job["job_id"] = _next_job_id()
    job.setdefault("type", "noop")
    _jobs.append(job)
    return job["job_id"]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # we do our own concise logging

    def _send(self, code, obj=None):
        body = b"" if obj is None else json.dumps(obj).encode()
        self.send_response(code)
        if body:
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _read_json(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode())
        except Exception:
            return {}

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/next-job":
            q = parse_qs(u.query)
            serial = (q.get("serial", [""])[0]) or "?"
            with _lock:
                if _registry.get(serial):
                    _registry[serial]["last_seen"] = _now()
                if _jobs:
                    job = _jobs.popleft()
                    _inflight[job["job_id"]] = {"job": job, "serial": serial, "sent_at": _now()}
                    print(f"[{_now()}] -> DISPATCH {job['job_id']} ({job.get('type')}) to {serial}")
                    self._send(200, job)
                else:
                    self._send(204)
            return
        if u.path == "/status":
            with _lock:
                self._send(200, {
                    "now": _now(),
                    "queue_depth": len(_jobs),
                    "inflight": list(_inflight.keys()),
                    "results": len(_results),
                    "registry": _registry,
                    "last_results": _results[-5:],
                })
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        data = self._read_json()
        if u.path == "/register":
            serial = data.get("serial", "?")
            with _lock:
                r = _registry.setdefault(serial, {"jobs_done": 0})
                r.update({"ip": data.get("ip", ""), "version": data.get("version", ""),
                          "last_seen": _now()})
            print(f"[{_now()}] REGISTER {serial} ip={data.get('ip')} v={data.get('version')}")
            self._send(200, {"ok": True})
            return
        if u.path == "/result":
            jid = data.get("job_id", "?")
            serial = data.get("serial", "?")
            shots = _save_screenshots(jid, serial, data)
            with _lock:
                _inflight.pop(jid, None)
                # don't keep the big base64 blobs in memory; record the saved paths
                slim = {k: v for k, v in data.items() if not k.startswith("screenshot_") or not k.endswith("_b64")}
                slim["screenshots"] = shots
                _results.append({"received_at": _now(), **slim})
                if _registry.get(serial):
                    _registry[serial]["jobs_done"] = _registry[serial].get("jobs_done", 0) + 1
            print(f"[{_now()}] <- RESULT  {jid} from {serial}: status={data.get('status')} "
                  f"egress={data.get('egress_ip','')} gps_set={data.get('gps_set')} shots={shots}")
            self._send(200, {"ok": True})
            return
        if u.path == "/seed":
            with _lock:
                jobs = data.get("jobs") or [data.get("job") or data]
                ids = [_enqueue(dict(j)) for j in jobs if j]
            print(f"[{_now()}] SEED {ids}")
            self._send(200, {"ok": True, "job_ids": ids})
            return
        self._send(404, {"error": "not found"})


def main():
    # Seed one dummy job so a freshly-pointed phone has something to pull.
    with _lock:
        _enqueue({
            "type": "noop",
            "platform": "gemini",
            "keyword": "INVERTED dummy job",
            "proxy": {"host": "192.168.0.164", "port": 11001, "route": "all"},
            "gps": {"lat": 37.7749, "lng": -122.4194},
        })
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[{_now()}] mac_job_server on {HOST}:{PORT} (queue seeded with 1 dummy job)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
