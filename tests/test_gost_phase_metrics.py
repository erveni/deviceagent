"""Telemetry tests. Integration traffic is entirely localhost; no proxy provider."""
import contextlib
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from device_agent_proxy import gost_manager as g


class PhaseMetricsTests(unittest.TestCase):
    def test_parser_dedup_components_and_sanitization(self):
        text = '''
# comment
gost_service_transfer_input_bytes_total{service="service-0",host="SECRET",client="phone1"} 100
gost_service_transfer_input_bytes_total{client="phone1",host="SECRET",service="service-0"} 100
gost_service_transfer_input_bytes_total{service="service-0",host="SECRET",client="phone2"} 50
gost_service_transfer_input_bytes_total{service="service-0",host="SECRET"} 150
gost_service_transfer_output_bytes_total{service="service-0",host="SECRET"} 2e3
gost_service_transfer_output_bytes_total{service="service-1"} NaN
gost_service_transfer_output_bytes_total{service="service-1"} -1
gost_service_transfer_output_bytes_total{service="service-1"} +Inf
gost_service_transfer_output_bytes_total{service="SECRET"} 400
gost_service_requests_total{service="service-0"} 600
garbage
'''
        result = g._parse_gost_metrics(text)
        self.assertEqual(result, {'service-0': {'input_bytes': 150, 'output_bytes': 2000}})
        self.assertNotIn('SECRET', json.dumps(result))

    def test_disabled_no_io(self):
        manager = g.GostManager.__new__(g.GostManager)
        with patch('builtins.open', side_effect=AssertionError('unexpected IO')):
            manager.sample_phase_metrics('test')

    def test_broken_ledger_does_not_raise(self):
        manager = g.GostManager.__new__(g.GostManager)
        manager._phase_ledger = '/nonexistent/ledger'
        manager._phase_sample_lock = threading.Lock()
        manager.process = None
        manager._cost_started_at = time.time()
        # Missing opener is recorded as unavailable, then a filesystem error
        # cannot escape the best-effort telemetry method.
        manager.sample_phase_metrics('test')

    @unittest.skipUnless(os.environ.get("RUN_LOCAL_GOST_INTEGRATION") == "1",
                         "explicit opt-in required; do not launch gost during fleet work")
    def test_live_open_socket_is_counted_before_close(self):
        if not Path(g.GOST_BINARY).exists():
            self.skipTest('gost binary unavailable')
        stop_server = threading.Event()
        server = socket.socket()
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        server.settimeout(5)
        target_port = server.getsockname()[1]

        def serve():
            try:
                connection, _ = server.accept()
                with connection:
                    connection.sendall(b'x' * 32768)
                    stop_server.wait(8)
            except OSError:
                pass

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            proxy_port = reservation.getsockname()[1]
        manager = None
        client = None
        with tempfile.TemporaryDirectory(prefix='gost-phase-local-test-') as directory:
            ledger = Path(directory) / 'phase.jsonl'
            env = {'GOST_PHASE_LEDGER': str(ledger), 'GOST_COST_LEDGER': ''}
            yaml = (f'services:\n  - name: service-0\n    addr: "127.0.0.1:{proxy_port}"\n'
                    '    handler:\n      type: socks5\n    listener:\n      type: tcp\n')
            try:
                with patch.dict(os.environ, env), patch.object(g, 'PROXY_PASSWORD', 'local-only'), \
                     patch.object(g.GostManager, '_preflight_upstreams'), \
                     patch.object(g.GostManager, '_warm_upstreams'), \
                     patch.object(g.GostManager, '_build_yaml_config', return_value=yaml), \
                     contextlib.redirect_stdout(io.StringIO()):
                    manager = g.GostManager([{'device_id': 'local-test'}], base_port=proxy_port)
                    manager.start(wait_seconds=.3)
                    client = socket.create_connection(('127.0.0.1', proxy_port), timeout=3)
                    client.sendall(b'\x05\x01\x00')
                    self.assertEqual(client.recv(2), b'\x05\x00')
                    client.sendall(b'\x05\x01\x00\x01' + socket.inet_aton('127.0.0.1')
                                   + target_port.to_bytes(2, 'big'))
                    reply = b''
                    while len(reply) < 10:
                        reply += client.recv(10 - len(reply))
                    self.assertEqual(reply[:2], b'\x05\x00')
                    received = b''
                    while len(received) < 32768:
                        received += client.recv(32768 - len(received))
                    manager.sample_phase_metrics('socket_still_open')
                    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
                    record = next(row for row in rows if row['phase'] == 'socket_still_open')
                    self.assertEqual(record['status'], 'ok', record)
                    self.assertGreaterEqual(record['services'][0]['output_bytes'], 32768)
                    # Deliberately stop while the accepted socket remains open;
                    # the final snapshot must retain bytes before termination.
                    manager.stop()
                    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
                    self.assertEqual(rows[-1]['phase'], 'before_stop')
                    self.assertGreaterEqual(rows[-1]['services'][0]['output_bytes'], 32768)
                    self.assertNotIn('local-only', ledger.read_text())
                    self.assertFalse(manager._phase_thread.is_alive())
            finally:
                if client:
                    client.close()
                stop_server.set()
                server.close()
                thread.join(timeout=2)
                if manager:
                    with contextlib.redirect_stdout(io.StringIO()):
                        manager.stop()


if __name__ == '__main__':
    unittest.main()
