"""Static safety contracts for the paid test launcher (no proxy/device work)."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CostRunnerContractTests(unittest.TestCase):
    def test_shell_launchers_parse(self):
        for filename in ('run_ranking_auto.sh', 'run_daily_auto.sh',
                         'daily_full_auto.sh', 'tools/run_ranking_cost_pair.sh'):
            subprocess.run(['bash', '-n', str(ROOT / filename)], check=True)

    def test_meter_harness_uses_syntax_checked_snapshot(self):
        source = (ROOT / 'tools/run_ranking_cost_pair.sh').read_text()
        self.assertIn("launcher.write_bytes((root / 'run_ranking_auto.sh').read_bytes())", source)
        self.assertLess(source.index("['bash', '-n', str(launcher)]"),
                        source.index("['bash', str(launcher), date, 'stale']"))

    def test_launcher_failure_is_reported_after_meter_settlement(self):
        source = (ROOT / 'tools/run_ranking_cost_pair.sh').read_text()
        self.assertLess(source.index("after = settled(name + '-after'"),
                        source.index("if leg['launcher_exit_code']:"))
        self.assertIn("if report.get('status') != 'complete':\n        raise SystemExit(1)",
                      (ROOT / 'tools/copilot_cache_trial.py').read_text())


if __name__ == '__main__':
    unittest.main()
