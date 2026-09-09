import tempfile
from pathlib import Path
import unittest
from daily_budget import DailyBudget

class DailyBudgetTests(unittest.TestCase):
    def test_budget_persists_across_retry_rounds(self):
        with tempfile.TemporaryDirectory() as temp:
            env=dict(DAILY_BUDGET_MB='100',DAILY_BALANCE_FLOOR_MB='500',PROXY_PROVIDER='evomi',
                     DAILY_METER_LEDGER=str(Path(temp)/'meter.jsonl'))
            guard=DailyBudget(env=env,read=lambda:1000)
            self.assertTrue(guard.admit())
            resumed=DailyBudget(env=env,read=lambda:899)
            self.assertFalse(resumed.admit())
            self.assertEqual(resumed.before,1000)

    def test_meter_failure_stops_new_jobs(self):
        with tempfile.TemporaryDirectory() as temp:
            env=dict(DAILY_BUDGET_MB='100',DAILY_BALANCE_FLOOR_MB='500',PROXY_PROVIDER='evomi',
                     DAILY_METER_LEDGER=str(Path(temp)/'meter.jsonl'))
            guard=DailyBudget(env=env,read=lambda:1000)
            def failed():raise TimeoutError('meter unavailable')
            guard.read=failed
            self.assertFalse(guard.admit())

if __name__=='__main__':unittest.main()
