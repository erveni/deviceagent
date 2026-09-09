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

    def test_second_phone_scope_cannot_expand_to_test_or_failed_phones(self):
        with patch.dict('os.environ',COPILOT_ROLLOUT_DEVICE='device-106'):
            self.assertEqual(selected_device()[1],'149145555W006477')
        for label in ('device-108','device-125','all'):
            with patch.dict('os.environ',COPILOT_ROLLOUT_DEVICE=label):
                with self.assertRaises(ValueError):selected_device()
