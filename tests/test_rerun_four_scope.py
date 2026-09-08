"""Static guards for the four replacement captures; no phones or proxy traffic."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'tools/run_ranking_cost_pair.sh').read_text().split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]


class RerunFourScopeTests(unittest.TestCase):
    def test_four_job_mode_is_bounded_and_not_cache_deployment(self):
        ast.parse(SOURCE)
        self.assertIn("job_count = 4 if rerun_four else (1 if single else 10)", SOURCE)
        self.assertIn('budget_mb, leg_timeout = 150, 40 * 60', SOURCE)
        self.assertIn("if rerun_four:\n            city_first = '0'", SOURCE)
        self.assertIn("if rerun_four:\n            env['RANK_GEMINI_CACHE_TRIAL'] = '0'", SOURCE)

    def test_exact_manifest(self):
        import json
        self.assertEqual(json.loads((ROOT / 'tools/prompt_leak_top3_rerun_20260909.json').read_text()),
                         [345, 143, 4711, 4680])

    def test_actual_environment_disables_retries_and_cache(self):
        import textwrap
        from types import SimpleNamespace
        block = SOURCE[SOURCE.index('        env = os.environ.copy()'):SOURCE.index("        (legdir / 'settings.json')")]
        ns = {'os': SimpleNamespace(environ={'COST_CACHE_TRIAL': '1'}),
              'fixed': Path('/mock/four.json'), 'legdir': Path('/mock/candidate'),
              'job_count': 4, 'city_first': '0', 'pilot': False, 'single': False,
              'one_phone': True, 'rerun_four': True, 'driver': 'rerun_four', 'name': 'candidate'}
        exec(compile(textwrap.dedent(block), '<settings>', 'exec'), ns)
        env = ns['env']
        for key, value in {'MAX_JOBS': '4', 'PLATFORMS': 'gemini', 'WORKERS_CAP': '1',
                           'RANK_SINGLE_ATTEMPT': '1', 'RANK_RETRY_ROUNDS': '0',
                           'RANK_GEMINI_CACHE_TRIAL': '0', 'RANK_CACHE_PILOT': '0',
                           'EVOMI_CITY_FIRST': '0', 'RANK_GEMINI_SAME_ANSWER_REFRAME': '1'}.items():
            self.assertEqual(env[key], value, key)
        self.assertNotIn('device-104', env['DEVICE_EXCLUDE'].split(','))
        self.assertIn('device-125', env['DEVICE_EXCLUDE'].split(','))
