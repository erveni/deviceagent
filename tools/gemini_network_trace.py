"""Opt-in passive CDP resource accounting for the exclusively owned test phone.

Explicit start() only; no import side effects. Never intercepts requests, changes
cache settings, navigates or pauses targets. The caller owns device-104. Old or
racing requests may precede Network.enable; receipts always disclose that gap.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
import re
import subprocess
import threading
import time
import urllib.parse
import urllib.request

RESOURCE_TYPES = {'Document', 'Stylesheet', 'Image', 'Media', 'Font', 'Script', 'TextTrack',
                  'XHR', 'Fetch', 'Prefetch', 'EventSource', 'WebSocket', 'Manifest',
                  'SignedExchange', 'Ping', 'CSPViolationReport', 'Preflight', 'Other'}


def _resource_type(value):
    return value if isinstance(value, str) and value in RESOURCE_TYPES else 'Other'


def _host(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        return parsed.hostname if parsed.scheme in ('http', 'https') else None
    except (TypeError, ValueError):
        return None


def _cache_control(headers):
    """Retain recognized cache directives only, never arbitrary header content."""
    allowed = []
    value = next((value for key, value in headers.items() if key.lower() == 'cache-control'), '')
    for directive in str(value).lower().split(','):
        directive = directive.strip()
        if re.fullmatch(r'(?:public|private|no-cache|no-store|must-revalidate|proxy-revalidate|immutable|'
                        r'(?:max-age|s-maxage|stale-while-revalidate|stale-if-error)=\d+)', directive):
            allowed.append(directive)
    return ','.join(allowed)


class ResourceEvents:
    """Bounded in-memory request join; every output field is explicitly selected."""
    def __init__(self):
        self.requests = {}

    def event(self, message):
        method = message.get('method', '')
        params = message.get('params', {})
        sid, rid = message.get('sessionId'), params.get('requestId')
        if not isinstance(sid, str) or not isinstance(rid, str):
            return None
        key = (sid, rid)
        if method == 'Network.requestWillBeSent':
            self.requests[key] = {'host': _host(params.get('request', {}).get('url', '')),
                                  'resource_type': _resource_type(params.get('type')), '_request_seen': True}
            if len(self.requests) > 2000:
                self.requests.pop(next(iter(self.requests)))
            return None
        if method == 'Network.requestServedFromCache':
            self.requests.setdefault(key, {})['served_from_cache'] = True
            return None
        if method == 'Network.responseReceived':
            response = params.get('response', {})
            record = self.requests.setdefault(key, {})
            record.update(host=_host(response.get('url', '')),
                          _response_seen=True,
                          resource_type=_resource_type(params.get('type')),
                          from_disk_cache=bool(response.get('fromDiskCache', False)),
                          from_service_worker=bool(response.get('fromServiceWorker', False)),
                          cache_control=_cache_control(response.get('headers', {})))
            return None
        if method not in ('Network.loadingFinished', 'Network.loadingFailed'):
            return None
        record = self.requests.pop(key, {})
        complete = record.pop('_request_seen', False) and record.get('_response_seen', False)
        record.pop('_response_seen', None)
        value = params.get('encodedDataLength')
        return {'event': 'resource_finished' if method.endswith('loadingFinished') else 'resource_failed',
                **record, 'encoded_bytes': value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None,
                'missing_request_or_response': not complete}


class NetworkTrace:
    def __init__(self, serial, path):
        self.serial = serial
        self.path = Path(path)
        self.stop_event = threading.Event()
        self.thread = None
        self.ws = None
        self.ports = []
        self.sequence = 0
        self.pending = {}
        self.sessions = set()
        self.resources = ResourceEvents()
        self.started = False
        self._closed = False
        # Exclusive new output prevents accidentally appending another trial.
        self.output = self.path.open('x')
        self._write('trace_start', missing_early_events_possible=True,
                    accounting='encoded_resource_bytes_not_provider_billing')

    def _write(self, event, **fields):
        self.output.write(json.dumps({'time': time.time(), 'event': event, **fields}) + '\n')
        self.output.flush()

    def _adb(self, *args):
        return subprocess.check_output(['adb', '-s', self.serial, *args],
                                       stderr=subprocess.DEVNULL, timeout=5).decode(errors='replace')

    def _send(self, method, params, sid=None):
        self.sequence += 1
        message = {'id': self.sequence, 'method': method, 'params': params}
        if sid:
            message['sessionId'] = sid
        self.pending[self.sequence] = (method, sid)
        self.ws.send(json.dumps(message))

    def _handle(self, message):
        if 'id' in message:
            method, sid = self.pending.pop(message['id'], ('unknown', None))
            if message.get('error'):
                self._write('protocol_error', method=method)
            elif method == 'Network.enable':
                self._write('network_enabled', missing_early_events_possible=True)
            return
        if message.get('method') == 'Target.attachedToTarget':
            params = message.get('params', {})
            sid = params.get('sessionId')
            if params.get('targetInfo', {}).get('type') == 'page' and isinstance(sid, str):
                self.sessions.add(sid)
                self._send('Network.enable', {}, sid)
            return
        record = self.resources.event(message)
        if record:
            event = record.pop('event')
            self._write(event, **record)

    def start(self):
        import websocket
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        unix = self._adb('shell', 'cat', '/proc/net/unix')
        sockets = sorted(set(re.findall(r'@(chrome_devtools_remote(?:_\d+)?)\b', unix)))
        if not sockets or len(sockets) > 4:
            raise RuntimeError('missing_or_excessive_debug_sockets')
        endpoints = []
        for name in sockets:
            port = int(self._adb('forward', 'tcp:0', 'localabstract:' + name).strip())
            self.ports.append(port)
            try:
                with opener.open(f'http://127.0.0.1:{port}/json/version', timeout=1) as response:
                    version = json.load(response)
                with opener.open(f'http://127.0.0.1:{port}/json/list', timeout=1) as response:
                    pages = [page for page in json.load(response) if page.get('type') == 'page']
                if not pages:
                    continue
                parsed = urllib.parse.urlsplit(version['webSocketDebuggerUrl'])
                if parsed.scheme != 'ws' or not (parsed.path == '/devtools/browser'
                                                or parsed.path.startswith('/devtools/browser/')):
                    continue
                endpoints.append(f'ws://127.0.0.1:{port}{parsed.path}')
            except (OSError, ValueError, KeyError):
                continue
        if len(endpoints) != 1:
            raise RuntimeError('ambiguous_or_missing_browser_endpoint')
        self.ws = websocket.create_connection(endpoints[0], suppress_origin=True, timeout=.5)
        self._send('Target.setAutoAttach', {'autoAttach': True, 'waitForDebuggerOnStart': False,
                                          'flatten': True, 'filter': [{'type': 'page'}, {'exclude': True}]})
        self.started = True

        def loop():
            try:
                while not self.stop_event.is_set():
                    try:
                        self._handle(json.loads(self.ws.recv()))
                    except websocket.WebSocketTimeoutException:
                        continue
            except Exception as error:
                if not self.stop_event.is_set():
                    self._write('trace_error', error_type=type(error).__name__)

        self.thread = threading.Thread(target=loop, daemon=True, name='gemini-network-trace')
        self.thread.start()
        return self

    def stop(self):
        if self._closed:
            return
        self._closed = True
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=1)
        if self.ws:
            try:
                self.ws.close(timeout=.2)
            except Exception:
                pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1)
        for port in self.ports:
            try:
                self._adb('forward', '--remove', f'tcp:{port}')
            except Exception:
                pass
        self._write('trace_stop', attached_page_count=len(self.sessions),
                    unfinished_requests=len(self.resources.requests),
                    missing_early_events_possible=True)
        self.output.close()


def start_gemini_network_trace(serial, path):
    """Start passive trace only by explicit caller request on test device-104.

    No proxy or page state is changed. Raises on failed startup after cleaning
    owned resources; caller may continue the job but must mark trace unavailable.
    """
    if '149145555W002883' not in serial:
        raise ValueError('network_trace_test_phone_only')
    trace = NetworkTrace(serial, path)
    try:
        return trace.start()
    except Exception:
        trace.stop()
        raise
