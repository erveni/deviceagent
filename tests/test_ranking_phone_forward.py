import unittest

from audit_dispatch_http import _assigned_proxy_zip, _http_port_for_serial
from device_dispatch import DEVICES


class RankingPhoneForwardTests(unittest.TestCase):
    def test_ranking_uses_the_ports_created_by_device_pool(self):
        for index, (_, serial) in enumerate(DEVICES):
            self.assertEqual(_http_port_for_serial(serial), 8765 + index)

    def test_unknown_phone_fails_closed(self):
        with self.assertRaises(ValueError):
            _http_port_for_serial('not-in-the-pool')

    def test_street_number_cannot_replace_terminal_postal_zip(self):
        entry={'biz_address':'14979 W Bell Rd #150, Surprise, AZ 85374',
               'proxy':{'zip':'14979'}}
        self.assertEqual(_assigned_proxy_zip(entry),'85374')


if __name__ == '__main__':
    unittest.main()
