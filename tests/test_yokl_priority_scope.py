"""Exact YOKL priority scope, without running phones or touching the daily."""
import ast
from pathlib import Path
import textwrap
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]


class YoklPriorityTests(unittest.TestCase):
    def test_exact_five_keywords_and_three_platforms(self):
        s=(ROOT/'tools/run_ranking_cost_pair.sh').read_text()
        self.assertIn('keywords != [5221,5222,5223,5224,5225]',s)
        self.assertIn("catalog[k]['businessId'] != 363 or catalog[k]['clientId'] != 329",s)
        self.assertIn('budget_mb, leg_timeout = 750, 75 * 60',s)
        block=s[s.index('        env = os.environ.copy()'):s.index("        (legdir / 'settings.json')")]
        ns=dict(os=SimpleNamespace(environ={}),fixed=Path('/five'),legdir=Path('/out'),
                job_count=15,city_first='0',pilot=False,single=False,rerun_four=False,
                one_phone=True,driver='yokl_priority',name='candidate',chatgpt_cache=False,copilot_yokl=False)
        exec(textwrap.dedent(block),ns)
        e=ns['env']
        for k,v in {'PLATFORMS':'chatgpt,gemini,copilot','MAX_JOBS':'15','WORKERS_CAP':'1',
                    'RANK_SINGLE_ATTEMPT':'1','RANK_RETRY_ROUNDS':'0','RANK_GEMINI_CACHE_TRIAL':'0',
                    'RANK_GEMINI_PROMPT_FREE':'1','COPILOT_MAX_PARALLEL':'4','EVOMI_CITY_FIRST':'0'}.items():
            self.assertEqual(e[k],v,k)
        self.assertNotIn('device-104',e['DEVICE_EXCLUDE'])
        self.assertIn('device-125',e['DEVICE_EXCLUDE'])

    def test_isolated_catalog_and_safe_daily_resume(self):
        s=(ROOT/'run_ranking.py').read_text()
        self.assertIn('CATALOG_DIR = os.environ.get("RANK_CATALOG_DIR", "/tmp")',s)
        resume=(ROOT/'tools/run_yokl_priority_0909.sh').read_text()
        self.assertIn('SKIP_BASE=1 PROXY_PROVIDER=evomi bash daily_full_auto.sh 2026-09-09',resume)
        self.assertLess(resume.index("r.get('restored_no_tun0')"),resume.index('SKIP_BASE=1 PROXY_PROVIDER='))
        self.assertNotIn('kickstart',resume)


if __name__=='__main__':unittest.main()
