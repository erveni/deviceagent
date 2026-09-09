"""Offline tests for the explicit ChatGPT extension; no phones or paid traffic."""
import os
from pathlib import Path
import re
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools import gemini_cache_reset as reset
from tools.test_gemini_cache_reset import FakeBrowser, FakePage
from tools.gemini_same_answer_reframe import _expression, _same_clip_with_subpixel_rounding
from tools.direct_evidence_gate import validate_direct_answer


class ChatGPTCacheTests(unittest.TestCase):
    def test_compositor_rounding_is_not_real_scrolling(self):
        before=dict(x=0,y=102.13449,width=300,height=527.42859,scale=1)
        self.assertTrue(_same_clip_with_subpixel_rounding(before,dict(before,y=102.14286)))
        for after in (None,dict(before,y=103.13449),dict(before,width=301),dict(before,scale=2),dict(before,y=float('nan'))):
            self.assertFalse(_same_clip_with_subpixel_rounding(before,after))

    def test_native_health_matches_apk_version(self):
        root=Path(__file__).resolve().parents[1]
        gradle=(root/'app/build.gradle.kts').read_text()
        native=(root/'app/src/main/java/com/deviceagent/AgentHttpServer.kt').read_text()
        self.assertEqual(re.search(r'versionCode = (\d+)',gradle)[1],
                         re.search(r'APP_VERSION_CODE = (\d+)',native)[1])

    def test_disabled_and_wrong_device(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(reset.prepare_chatgpt_cache('149145555W002883')['ok'])
        with patch.dict(os.environ, {'RANK_CHATGPT_CACHE_TRIAL':'1','RANK_SINGLE_ATTEMPT':'1'}):
            self.assertFalse(reset.prepare_chatgpt_cache('other')['ok'])

    def test_policy_is_scoped_and_restored(self):
        with patch.dict(os.environ, {'RANK_CHATGPT_CACHE_TRIAL':'1','RANK_SINGLE_ATTEMPT':'1'}):
            def inspect(*args, **kwargs):
                self.assertTrue(reset._allowed_url('https://chatgpt.com/uc/test'))
                self.assertFalse(reset._allowed_url('https://chatgpt.com.evil.test/'))
                self.assertFalse(reset._allowed_url('https://accounts.google.com/'))
                return {'ok':True}
            with patch.object(reset, 'reset_gemini_preserving_http_cache', side_effect=inspect):
                self.assertTrue(reset.prepare_chatgpt_cache('149145555W002883')['ok'])
        self.assertFalse(reset._allowed_url('https://chatgpt.com/'))

    def test_chatgpt_reset_clears_identity_not_http_assets(self):
        token = reset._CHATGPT_POLICY.set(True)
        try:
            browser = FakeBrowser(url='https://chatgpt.com/uc/test')
            page = FakePage(browser)
            result = reset._reset_clients(browser, lambda target: page)
            self.assertTrue(result['ok'])
            self.assertIn('https://chatgpt.com', result['origins_cleared'])
            self.assertEqual(result['cookies_remaining'], 0)
            self.assertFalse(result['http_cache_clear_requested'])
            self.assertNotIn('Network.clearBrowserCache', [m for m,p in page.calls])
        finally:
            reset._CHATGPT_POLICY.reset(token)

    def test_authentication_is_refused(self):
        browser = FakeBrowser(cookies=[{'name':'__Secure-next-auth.session-token.0'}])
        with self.assertRaises(reset.ResetRefused):
            reset._reset_clients(browser, lambda target: FakePage(browser))
        self.assertNotIn('Target.createTarget', [m for m,p in browser.calls])

    def test_selectors_never_take_user_prompt_as_answer(self):
        expression = _expression('tour', (4,4), platform='chatgpt', prompt_free=True)
        self.assertIn('chatgpt.com', expression)
        self.assertIn('[data-message-author-role="assistant"]', expression)
        self.assertNotIn('model-response message-content', expression)
        self.assertIn('model-response message-content', _expression('tour',(4,4)))

    def test_chatgpt_boundary_and_summary_need_independent_dom_proof(self):
        result={'status':'completed','error':'','response_text':
                'You said:\nExample [RANK: 19/19]\nChatGPT said:\n1. A\n2. B\n3. C\n[RANK: 1/3]\nA ranks first.'}
        with tempfile.TemporaryDirectory() as directory:
            with patch('tools.gemini_same_answer_reframe.reframe_same_answer',return_value={'ok':True}) as frame:
                self.assertTrue(validate_direct_answer('test','tour',result,Path(directory),platform='chatgpt')['ok'])
                self.assertEqual(frame.call_args.args[2],(1,3))
                self.assertEqual(frame.call_args.kwargs['platform'],'chatgpt')
            result['response_text']='You said:\n1. A\n2. B\n3. C\n[RANK: 1/3]'
            self.assertFalse(validate_direct_answer('test','tour',result,Path(directory),platform='chatgpt')['ok'])

    def test_platform_settings_are_isolated(self):
        source=(Path(__file__).resolve().parents[1]/'tools/run_ranking_cost_pair.sh').read_text()
        block=source[source.index('        env = os.environ.copy()'):source.index("        (legdir / 'settings.json')")]
        for platform in ('chatgpt','copilot'):
            namespace=dict(os=SimpleNamespace(environ={'COST_PHASE_TELEMETRY':'1'}),
                fixed=Path('/one'),legdir=Path('/output'),job_count=1,city_first='1',
                pilot=False,single=True,rerun_four=False,one_phone=True,driver='reframe_single',
                name='candidate',chatgpt_cache=platform=='chatgpt',copilot_yokl=platform=='copilot',report={})
            exec(textwrap.dedent(block),namespace)
            env=namespace['env']
            self.assertEqual(env['PLATFORMS'],platform)
            self.assertEqual(env['RANK_GEMINI_CACHE_TRIAL'],'0')
            self.assertEqual(env['RANK_SINGLE_ATTEMPT'],'1')
            self.assertEqual(env['MAX_JOBS'],'1')
            self.assertEqual(env['WORKERS_CAP'],'1')
            self.assertEqual(env['RANK_RETRY_ROUNDS'],'0')
            self.assertEqual(len(env['DEVICE_EXCLUDE'].split(',')),24)
            if platform=='copilot':self.assertEqual(env['COPILOT_PM_CLEAR'],'1')


if __name__ == '__main__':
    unittest.main()
