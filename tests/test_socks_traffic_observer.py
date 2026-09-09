import json
import socket
import struct
import tempfile
import threading
import unittest
from pathlib import Path

from tools.socks_traffic_observer import Destination, TrafficObserver


class TrafficTests(unittest.TestCase):
    def test_fragmented_tls_sni_is_label_only(self):
        host=b'assets.example.com'
        name=b'\x00'+struct.pack('!H',len(host))+host
        names=struct.pack('!H',len(name))+name
        extension=b'\x00\x00'+struct.pack('!H',len(names))+names
        body=b'\x03\x03'+b'x'*32+b'\x00\x00\x02\x13\x01\x01\x00'+struct.pack('!H',len(extension))+extension
        hello=b'\x01'+len(body).to_bytes(3,'big')+body
        tls=b'\x16\x03\x01'+struct.pack('!H',len(hello))+hello
        parser=Destination()
        request=b'\x05\x01\x00\x05\x01\x00\x01\x7f\x00\x00\x01\x01\xbb'
        for byte in request+tls:parser.feed(bytes([byte]))
        self.assertEqual((parser.host,parser.port),('assets.example.com',443))
        self.assertEqual(parser.buffer,b'')

    def test_http_host_only_no_url_cookie_retained(self):
        parser=Destination()
        parser.feed(b'\x05\x01\x00\x05\x01\x00\x01\x7f\x00\x00\x01\x00\x50')
        parser.feed(b'GET /private?token=secret HTTP/1.1\r\nHost: downloads.example.com\r\nCookie: secret\r\n\r\n')
        self.assertEqual(parser.host,'downloads.example.com')
        self.assertEqual(parser.buffer,b'')
        self.assertEqual(parser.stage,'done')
        parser.feed(b'encrypted payload must not be retained')
        self.assertEqual(parser.buffer,b'')

    def test_fragmented_auth_not_persisted(self):
        parser=Destination()
        request=b'\x05\x01\x02\x01\x04anon\x06secret\x05\x01\x00\x03\x0bexample.com\x00\x50'
        for value in request:parser.feed(bytes([value]))
        self.assertEqual((parser.host,parser.port),('example.com',80))
        self.assertEqual(parser.buffer,b'')

    def test_passthrough_and_open_socket_counts(self):
        upstream=socket.socket()
        upstream.bind(('127.0.0.1',0));upstream.listen()
        def echo():
            conn,_=upstream.accept()
            with conn:
                while True:
                    data=conn.recv(65536)
                    if not data:break
                    conn.sendall(data)
        worker=threading.Thread(target=echo,daemon=True);worker.start()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'trace.jsonl'
            observer=TrafficObserver(0,upstream.getsockname()[1],path).start()
            client=socket.create_connection(('127.0.0.1',observer.server.server_address[1]))
            payload=b'\x05\x01\x00\x05\x01\x00\x03\x0bexample.com\x00\x50'+b'x'*10000
            client.sendall(payload)
            received=b''
            while len(received)<len(payload):received+=client.recv(65536)
            self.assertEqual(received,payload)
            observer.snapshot()
            row=json.loads(path.read_text().splitlines()[-1])['connections'][0]
            self.assertEqual(row['input_bytes'],len(payload))
            self.assertEqual(row['output_bytes'],len(payload))
            self.assertFalse(row['closed'])
            self.assertEqual(row['host'],'example.com')
            self.assertNotIn('xxxxx',path.read_text())
            client.close();observer.stop()
        upstream.close();worker.join(timeout=2)


if __name__=='__main__':unittest.main()
