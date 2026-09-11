import unittest
from pathlib import Path
from unittest.mock import patch
from tools.cache_rollout_scope import device_allowed
from audit_dispatch_http import _cache_low_cost_enabled


class CacheRolloutScopeTests(unittest.TestCase):
    def test_explicit_allowlist_and_release_flags(self):
        env={'RANK_CACHE_LOW_COST_ROLLOUT':'1','RANK_CACHE_LOW_COST_DEVICES':'device-104',
             'RANK_CHATGPT_LOW_COST_RELEASED':'1','RANK_GEMINI_LOW_COST_RELEASED':'1'}
        with patch.dict('os.environ',env,clear=True):
            self.assertTrue(device_allowed('device-104'));self.assertFalse(device_allowed('device-106'))
            self.assertTrue(_cache_low_cost_enabled('chatgpt'));self.assertTrue(_cache_low_cost_enabled('gemini'))
        with patch.dict('os.environ',{**env,'RANK_CACHE_LOW_COST_DEVICES':'device-125'},clear=True):
            with self.assertRaises(ValueError):device_allowed('device-125')

    def test_paid_tunnel_starts_after_cache_preparation(self):
        source=(Path(__file__).resolve().parents[1]/'audit_dispatch_http.py').read_text()
        self.assertLess(source.index("phase('offline_cache_prepare_done')"),
                        source.index('phase("gost_start")'))


if __name__=='__main__':unittest.main()
