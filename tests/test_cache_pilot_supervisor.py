"""Offline supervisor configuration/deadline checks; never run its main loop."""
import ast
from pathlib import Path
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

SOURCE = (Path(__file__).resolve().parents[1] / 'tools/run_ranking_cost_pair.sh').read_text()
PYTHON = SOURCE.split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
TREE = ast.parse(PYTHON)


class CachePilotSupervisorTests(unittest.TestCase):
    def test_pilot_environment_has_ten_single_attempt_jobs_on_only_104(self):
        block = PYTHON[PYTHON.index('        env = os.environ.copy()'):PYTHON.index("        (legdir / 'settings.json')")]
        namespace = {'os': SimpleNamespace(environ={}), 'fixed': Path('/mock/ten.json'),
                     'legdir': Path('/mock/candidate'), 'job_count': 10, 'city_first': '1',
                     'pilot': True, 'single': False, 'rerun_four': False, 'one_phone': True, 'driver': 'cache_pilot',
                     'name': 'candidate'}
        exec(compile(textwrap.dedent(block), '<settings-only>', 'exec'), namespace)
        env = namespace['env']
        self.assertEqual(env['MAX_JOBS'], '10')
        self.assertEqual(env['RANK_RETRY_ROUNDS'], '0')
        self.assertEqual(env['WORKERS_CAP'], '1')
        self.assertEqual(env['RANK_SINGLE_ATTEMPT'], '1')
        self.assertEqual(env['RANK_GEMINI_CACHE_TRIAL'], '1')
        self.assertEqual(env['RANK_CACHE_PILOT'], '1')
        self.assertEqual(env['EVOMI_CITY_FIRST'], '1')
        self.assertEqual(env['GOST_PHASE_LEDGER'], '/mock/candidate/gost_phases.jsonl')
        self.assertNotIn('device-104', env['DEVICE_EXCLUDE'].split(','))
        self.assertEqual(len(env['DEVICE_EXCLUDE'].split(',')), 24)

    def test_deadline_rejects_late_start_but_allows_cleanup_settling(self):
        function = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == 'check_deadline')
        ns = {'pilot': True, 'finishing_partial': False, 'hard_deadline': 100,
              'time': SimpleNamespace(time=lambda: 100)}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<deadline-only>', 'exec'), ns)
        with self.assertRaises(RuntimeError):
            ns['check_deadline']()
        ns['finishing_partial'] = True
        ns['check_deadline']()
        ns.update(pilot=False, finishing_partial=False)
        ns['check_deadline']()

    def test_watchdog_only_calls_owned_process_cleanup(self):
        function = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == 'deadline_stop')
        stop = Mock()
        ns = {'active': None, 'stop_owned': stop, 'stop_pilot_phone': Mock()}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<watchdog-only>', 'exec'), ns)
        ns['deadline_stop']()
        stop.assert_not_called()
        ns['active'] = object()
        ns['deadline_stop']()
        stop.assert_called_once_with()
        ns['stop_pilot_phone'].assert_called_once_with()

    def test_partial_report_and_settlement_are_bounded(self):
        self.assertIn("report['status'] = 'partial'", PYTHON)
        self.assertIn('remaining_keyword_ids=', PYTHON)
        self.assertIn('completed_keyword_ids=', PYTHON)
        self.assertIn('max_seconds=330', PYTHON)
        self.assertIn('budget_mb, leg_timeout = 150, 30 * 60', PYTHON)
        self.assertIn('hard_deadline+330-time.time()', PYTHON)
        self.assertIn("legs = [('candidate', '1')] if one_phone", PYTHON)


if __name__ == '__main__':
    unittest.main()
