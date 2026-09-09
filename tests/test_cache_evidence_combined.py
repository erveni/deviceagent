"""Offline checks only: no phones, APK installs or provider requests."""
import json
import os
from pathlib import Path
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.cache_evidence_policy import cache_health_allowed
from tools.direct_evidence_gate import production_ocr_namespace, validate_direct_answer
from tools.after_daily_cache_evidence import workload_parser

ROOT = Path(__file__).resolve().parents[1]


class CombinedCacheTests(unittest.TestCase):
    def test_exact_health_versions_and_accessibility(self):
        for code in (79, 81, 82, 83, 84, '83', None, True):
            for evidence in (False, True):
                self.assertEqual(cache_health_allowed({'versionCode': code, 'accessibility': True}, evidence),
                                 type(code) is int and code == (83 if evidence else 82))
        self.assertFalse(cache_health_allowed({'versionCode': 83, 'accessibility': False}, True))

    def test_combined_single_job_settings(self):
        source = (ROOT/'tools/run_ranking_cost_pair.sh').read_text()
        block = source[source.index('        env = os.environ.copy()'):source.index("        (legdir / 'settings.json')")]
        ns = dict(os=SimpleNamespace(environ={'COST_CACHE_TRIAL':'1','COST_CACHE_EVIDENCE':'1'}),
                  fixed=Path('/mock/one.json'), legdir=Path('/mock/candidate'), job_count=1,
                  city_first='1', pilot=False, single=True, rerun_four=False, one_phone=True,
                  driver='reframe_single', name='candidate')
        exec(textwrap.dedent(block), ns)
        env = ns['env']
        for key in ('RANK_GEMINI_CACHE_TRIAL','RANK_GEMINI_CACHE_EVIDENCE','RANK_GEMINI_PROMPT_FREE',
                    'RANK_SINGLE_ATTEMPT','MAX_JOBS','WORKERS_CAP'):
            self.assertEqual(env[key], '1', key)
        self.assertEqual(env['RANK_RETRY_ROUNDS'], '0')
        self.assertEqual(env['COPILOT_MAX_PARALLEL'], '4')
        self.assertEqual(len(env['DEVICE_EXCLUDE'].split(',')),24)
        ns['single'] = False
        with self.assertRaises(RuntimeError):
            exec(textwrap.dedent(block), ns)

    def test_no_inherited_combined_flags_in_old_modes(self):
        source = (ROOT/'tools/run_ranking_cost_pair.sh').read_text()
        self.assertIn("RANK_GEMINI_CACHE_EVIDENCE='0', RANK_GEMINI_PROMPT_FREE='0'", source)
        wrapper = (ROOT/'tools/direct_audit_smoke.py').read_text()
        self.assertLess(wrapper.index('validate_direct_answer(serial'), wrapper.index("lock.unlink()"))
        self.assertIn('not args.cache_trial or args.pilot_manifest or args.rerun_manifest', wrapper)

    def test_answer_rejects_prompt_partial_and_failed_job_without_browser(self):
        with tempfile.TemporaryDirectory() as folder:
            for text in ('[RANK: 4/4]', 'You said\n1. A\n2. B\n3. C\n[RANK: 4/4]',
                         '1. A\n2. B\n3. C\n[RANK: 4/4] trailing',
                         '1. A\n2. B\n3. C\n[RANK: 5/4]'):
                result = validate_direct_answer('unused','keyword',{'status':'completed','response_text':text},Path(folder))
                self.assertFalse(result['ok'])

    def test_production_ocr_exact_rank_and_fail_closed(self):
        ns = production_ocr_namespace()
        with tempfile.NamedTemporaryFile() as image, patch('os.path.exists', return_value=True), \
                patch.dict(os.environ, {'OCR_VALIDATE_SCREENSHOT':'1'}), \
                patch('subprocess.run', return_value=SimpleNamespace(returncode=0,stdout='1. A\n2. B\n3. C\n[RANK: 2/3]')):
            self.assertTrue(ns['_screenshot_has_expected_rank'](image.name,(2,3)))
            self.assertFalse(ns['_screenshot_has_expected_rank'](image.name,(4,4)))

    def test_complete_answer_requires_prompt_free_reframe(self):
        with tempfile.TemporaryDirectory() as folder, patch(
                'tools.gemini_same_answer_reframe.reframe_same_answer', return_value={'ok': True}) as frame:
            result = validate_direct_answer('test-serial', 'test keyword',
                {'status':'completed','response_text':'1.\nA\n2.\nB\n3.\nC\n[RANK: 2/3]'}, Path(folder))
            self.assertTrue(result['ok'])
            self.assertTrue(frame.call_args.kwargs['prompt_free'])
            self.assertEqual(frame.call_args.args[2], (2, 3))
            self.assertTrue(callable(frame.call_args.kwargs['ocr_validator']))

    def test_waiter_recognizes_build_and_dispatch_without_shell_false_positives(self):
        recognize = workload_parser()
        for row in ('/bin/bash /repo/daily_full_auto.sh', '/usr/bin/python3 -u build_daily_plan.py',
                    '/usr/bin/python3 run_rolling_plan.py /plan', '/opt/homebrew/bin/gost -C /config'):
            self.assertIsNotNone(recognize(row))
        self.assertIsNone(recognize("/bin/zsh -c 'rg daily_full_auto.sh'"))
        self.assertIsNone(recognize('/usr/bin/python3 -u tools/after_daily_cache_evidence.py'))


if __name__ == '__main__':
    unittest.main()
