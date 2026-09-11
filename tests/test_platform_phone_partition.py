import unittest
from pathlib import Path


class PlatformPhonePartitionTests(unittest.TestCase):
    def test_cache_and_copilot_receive_separate_allowlists(self):
        root=Path(__file__).resolve().parents[1]
        pool=(root/'device_dispatch.py').read_text();audit=(root/'audit_dispatch_http.py').read_text()
        self.assertIn('allowed_labels: set[str] | None',pool)
        self.assertIn('DEVICES[i][0] not in allowed_labels',pool)
        self.assertIn("RANK_CACHE_LOW_COST_DEVICES",audit)
        self.assertIn("RANK_COPILOT_WIFI_ROLLOUT_DEVICES",audit)
        self.assertIn('allowed_labels=allowed_labels',audit)


if __name__=='__main__':unittest.main()
