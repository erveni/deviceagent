import unittest
from tools.ranking_cost_release import check
from tools.copilot_bootstrap_scope import selected_device
from unittest.mock import patch


class RankingReleaseTests(unittest.TestCase):
    def test_normal_queue_cannot_fall_back_to_expensive_path(self):
        with self.assertRaises(ValueError):check({})

    def test_only_bounded_meter_harness_is_permitted_before_release(self):
        check(dict(RANK_COST_MEASUREMENT='1',RANK_RETRY_ROUNDS='0',GOST_COST_LEDGER='/tmp/test-ledger',MAX_JOBS='1'))
        with self.assertRaises(ValueError):check(dict(RANK_COST_MEASUREMENT='1',RANK_RETRY_ROUNDS='40'))

    def test_meter_flag_cannot_unlock_unbounded_queue(self):
        for maximum in ('', '0', '21', 'all'):
            with self.assertRaises(ValueError):
                check(dict(RANK_COST_MEASUREMENT='1', RANK_RETRY_ROUNDS='0',
                           GOST_COST_LEDGER='/tmp/test-ledger', MAX_JOBS=maximum))

    def test_production_release_requires_complete_wifi_controls_and_allowlist(self):
        released=dict(RANK_COST_ROLLOUT='copilot-wifi-v1',
            RANK_COPILOT_OFFLINE_BOOTSTRAP='1',RANK_COPILOT_WIFI_SETTLE='1',
            RANK_COPILOT_WIFI_ROLLOUT='1',
            RANK_COPILOT_WIFI_ROLLOUT_DEVICES='device-104,device-106',PLATFORMS='copilot')
        check(released)
        for missing in ('RANK_COPILOT_OFFLINE_BOOTSTRAP','RANK_COPILOT_WIFI_SETTLE',
                        'RANK_COPILOT_WIFI_ROLLOUT','RANK_COPILOT_WIFI_ROLLOUT_DEVICES'):
            broken=released.copy();broken.pop(missing)
            with self.assertRaises(ValueError):check(broken)
        broken=released.copy();broken['RANK_COPILOT_WIFI_ROLLOUT_DEVICES']='device-125'
        with self.assertRaises(ValueError):check(broken)
        broken=released.copy();broken['RANK_COPILOT_WIFI_ROLLOUT_DEVICES']='device-108'
        with self.assertRaises(ValueError):check(broken)
        broken['RANK_ALLOW_QUARANTINED_DEVICE_108']='1';check(broken)

    def test_unreleased_chatgpt_and_gemini_are_blocked(self):
        base=dict(RANK_COST_ROLLOUT='copilot-wifi-v1',
            RANK_COPILOT_OFFLINE_BOOTSTRAP='1',RANK_COPILOT_WIFI_SETTLE='1',
            RANK_COPILOT_WIFI_ROLLOUT='1',RANK_COPILOT_WIFI_ROLLOUT_DEVICES='device-104')
        for platform in ('chatgpt','gemini','chatgpt,gemini,copilot'):
            with self.assertRaises(ValueError):check({**base,'PLATFORMS':platform})
        released={**base,'PLATFORMS':'chatgpt,gemini,copilot',
                  'RANK_CHATGPT_LOW_COST_RELEASED':'1','RANK_GEMINI_LOW_COST_RELEASED':'1',
                  'RANK_CACHE_LOW_COST_ROLLOUT':'1','RANK_CACHE_LOW_COST_DEVICES':'device-104'}
        check(released)
        for missing in ('RANK_CACHE_LOW_COST_ROLLOUT','RANK_CACHE_LOW_COST_DEVICES'):
            broken=released.copy();broken.pop(missing)
            with self.assertRaises(ValueError):check(broken)

    def test_second_phone_scope_cannot_expand_to_test_or_failed_phones(self):
        with patch.dict('os.environ',COPILOT_ROLLOUT_DEVICE='device-106'):
            self.assertEqual(selected_device()[1],'149145555W006477')
        for label in ('device-108','device-125','all'):
            with patch.dict('os.environ',COPILOT_ROLLOUT_DEVICE=label):
                with self.assertRaises(ValueError):selected_device()
