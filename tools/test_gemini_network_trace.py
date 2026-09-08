import json
import threading
import unittest
from unittest.mock import Mock, patch

from tools.gemini_network_trace import ResourceEvents, NetworkTrace, _cache_control, start_gemini_network_trace


class TraceTests(unittest.TestCase):
    def event(self, method, **params):
        return {'sessionId': 'session', 'method': method, 'params': {'requestId': 'request', **params}}

    def test_sanitized_finished_resource(self):
        tracker = ResourceEvents()
        tracker.event(self.event('Network.requestWillBeSent', type='Script',
                                 request={'url': 'https://cdn.example/js?q=SECRET',
                                          'headers': {'Cookie': 'SECRET'}, 'postData': 'SECRET'}))
        tracker.event(self.event('Network.responseReceived', type='Script', response={
            'url': 'https://cdn.example/js?q=SECRET', 'fromDiskCache': True,
            'headers': {'Set-Cookie': 'SECRET', 'Cache-Control': 'max-age=3600, public, secret=SECRET'}}))
        record = tracker.event(self.event('Network.loadingFinished', encodedDataLength=12345))
        self.assertEqual(record['host'], 'cdn.example')
        self.assertEqual(record['encoded_bytes'], 12345)
        self.assertTrue(record['from_disk_cache'])
        self.assertEqual(record['cache_control'], 'max-age=3600,public')
        self.assertNotIn('SECRET', json.dumps(record))
        self.assertEqual(tracker.requests, {})

    def test_missing_start_and_failed_requests(self):
        tracker = ResourceEvents()
        record = tracker.event(self.event('Network.loadingFinished', encodedDataLength=float('nan')))
        self.assertTrue(record['missing_request_or_response'])
        self.assertIsNone(record['encoded_bytes'])
        self.assertEqual(tracker.event(self.event('Network.loadingFailed', errorText='SECRET'))['event'],
                         'resource_failed')

    def test_untrusted_resource_type_not_retained(self):
        tracker = ResourceEvents()
        tracker.event(self.event('Network.requestWillBeSent', type='SECRET', request={'url': 'data:SECRET'}))
        record = tracker.event(self.event('Network.loadingFinished', encodedDataLength=0))
        self.assertEqual(record['resource_type'], 'Other')
        self.assertNotIn('SECRET', json.dumps(record))

    def test_attachment_enables_only_passive_network(self):
        trace = NetworkTrace.__new__(NetworkTrace)
        trace.sessions = set()
        trace._send = Mock()
        trace._handle({'method': 'Target.attachedToTarget', 'params': {
            'sessionId': 'new', 'targetInfo': {'type': 'page', 'url': 'https://gemini.google.com/?secret=SECRET'}}})
        trace._send.assert_called_once_with('Network.enable', {}, 'new')
        self.assertEqual(trace.sessions, {'new'})

    def test_bounded_stop_removes_only_owned_forward(self):
        trace = NetworkTrace.__new__(NetworkTrace)
        trace._closed = False
        trace.stop_event = threading.Event()
        trace.thread = None
        trace.ws = Mock()
        trace.ports = [12345]
        trace._adb = Mock()
        trace._write = Mock()
        trace.output = Mock()
        trace.sessions = {'s'}
        trace.resources = ResourceEvents()
        trace.stop()
        trace.stop()
        trace._adb.assert_called_once_with('forward', '--remove', 'tcp:12345')
        trace.output.close.assert_called_once()

    def test_wrong_phone_no_start(self):
        with patch('tools.gemini_network_trace.NetworkTrace') as constructor:
            with self.assertRaises(ValueError):
                start_gemini_network_trace('device-125', 'unused')
            constructor.assert_not_called()


if __name__ == '__main__':
    unittest.main()
