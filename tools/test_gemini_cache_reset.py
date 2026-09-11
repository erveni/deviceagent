import os
import io
import json
import types
import unittest
from unittest.mock import Mock, patch

from tools import gemini_cache_reset as reset


class FakeBrowser:
    def __init__(self, url='https://gemini.google.com/app/old', cookies=None):
        self.targets = [{'type': 'page', 'url': url, 'targetId': 'old'}]
        self.cookies = cookies if cookies is not None else [{'name': 'anonymous', 'value': 'SECRET'}]
        self.calls = []
        self.ws = Mock()

    def call(self, method, params):
        self.calls.append((method, params))
        if method == 'Target.getTargets':
            result = {'targetInfos': self.targets.copy()}
        elif method == 'Target.getBrowserContexts':
            result = {'browserContextIds': []}
        elif method == 'Storage.getCookies':
            result = {'cookies': self.cookies.copy()}
        elif method == 'Target.createTarget':
            self.targets.append({'type': 'page', 'url': 'about:blank', 'targetId': 'fresh'})
            result = {'targetId': 'fresh'}
        elif method == 'Target.closeTarget':
            self.targets = [t for t in self.targets if t['targetId'] != params['targetId']]
            result = {'success': True}
        else:
            raise AssertionError(method)
        return {'result': result}


class FakePage:
    def __init__(self, browser, clear=True, quota=0):
        self.browser, self.clear, self.quota = browser, clear, quota
        self.calls = []
        self.ws = Mock()

    def call(self, method, params):
        self.calls.append((method, params))
        if method == 'Network.clearBrowserCookies' and self.clear:
            self.browser.cookies = []
        if method == 'Storage.getUsageAndQuota':
            result = {'usageBreakdown': [{'storageType': 'cache_storage', 'usage': self.quota}]}
        elif method == 'Target.getTargetInfo':
            result = {'targetInfo': {'targetId': 'fresh', 'url': 'about:blank'}}
        else:
            result = {}
        return {'result': result}


class ResetTests(unittest.TestCase):
    def test_happy_path_clears_identity_not_http_cache(self):
        browser = FakeBrowser()
        page = FakePage(browser)
        result = reset._reset_clients(browser, lambda target: page)
        self.assertTrue(result['ok'])
        self.assertEqual(result['clean_snapshots'], 2)
        self.assertFalse(result['http_cache_clear_requested'])
        self.assertFalse(result['cache_reuse_verified'])
        self.assertNotIn('SECRET', str(result))
        self.assertEqual(browser.targets[0]['targetId'], 'fresh')
        methods = [method for method, _ in page.calls]
        self.assertNotIn('Network.clearBrowserCache', methods)
        self.assertIn(('Network.setCacheDisabled', {'cacheDisabled': False}), page.calls)
        clear = next(params for method, params in page.calls if method == 'Storage.clearDataForOrigin')
        self.assertEqual(clear['origin'], 'https://gemini.google.com')
        self.assertEqual({params['origin'] for method, params in page.calls
                          if method == 'Storage.clearDataForOrigin'}, set(reset.CLEAR_ORIGINS))
        self.assertEqual({params['origin'] for method, params in page.calls
                          if method == 'Storage.getUsageAndQuota'}, set(reset.CLEAR_ORIGINS))
        self.assertIn('service_workers', clear['storageTypes'])
        self.assertIn('cache_storage', clear['storageTypes'])
        self.assertNotIn('all', clear['storageTypes'].split(','))
        page.ws.close.assert_called_once()

    def test_unrelated_page_refused_before_mutation(self):
        for url in ['https://chatgpt.com/', 'https://gemini.google.com.evil/',
                    'http://gemini.google.com/', 'https://gemini.google.com:444/',
                    'https://someone@gemini.google.com/', 'https://www.google.com/search?q=private',
                    'https://www.google.com/?q=private', 'https://accounts.google.com/',
                    'https://www.google.com/account', 'https://www.google.com/#private']:
            browser = FakeBrowser(url)
            with self.assertRaises(reset.ResetRefused):
                reset._reset_clients(browser, Mock())
            self.assertEqual([c[0] for c in browser.calls], ['Target.getTargets'])

    def test_only_google_homepage_allowed(self):
        for url in ['https://www.google.com/', 'https://www.google.com']:
            browser = FakeBrowser(url)
            page = FakePage(browser)
            self.assertTrue(reset._reset_clients(browser, lambda target: page)['ok'])

    def test_normal_android_context_id_accepted(self):
        browser = FakeBrowser()
        browser.targets[0]['browserContextId'] = 'normal-nonempty-id'
        page = FakePage(browser)
        self.assertTrue(reset._reset_clients(browser, lambda target: page)['ok'])

    def test_incognito_context_refused(self):
        browser = FakeBrowser()
        browser.targets[0]['browserContextId'] = 'incognito-id'
        original = browser.call
        browser.call = lambda method, params: ({'result': {'browserContextIds': ['incognito-id']}}
                                               if method == 'Target.getBrowserContexts'
                                               else original(method, params))
        with self.assertRaisesRegex(reset.ResetRefused, 'nondefault_browser_context'):
            reset._reset_clients(browser, Mock())
        self.assertNotIn('Target.createTarget', [c[0] for c in browser.calls])

    def test_signed_in_profile_refused_before_mutation(self):
        browser = FakeBrowser(cookies=[{'name': 'SID', 'value': 'SECRET'}])
        with self.assertRaisesRegex(reset.ResetRefused, 'authenticated_profile'):
            reset._reset_clients(browser, Mock())
        self.assertNotIn('Target.createTarget', [c[0] for c in browser.calls])

    def test_residual_identity_fails_closed(self):
        for clear, quota in [(False, 0), (True, 500)]:
            browser = FakeBrowser()
            page = FakePage(browser, clear, quota)
            with self.assertRaises(reset.ResetRefused):
                reset._reset_clients(browser, lambda target: page)
            page.ws.close.assert_called_once()

    def test_transient_cookie_completion_recleared_then_twice_clean(self):
        browser = FakeBrowser()
        page = FakePage(browser)
        original = page.call
        clears = 0
        def delayed(method, params):
            nonlocal clears
            if method == 'Network.clearBrowserCookies':
                clears += 1
                if clears == 1:
                    return {'result': {}}  # late completion leaves a cookie
            return original(method, params)
        page.call = delayed
        result = reset._reset_clients(browser, lambda target: page)
        self.assertTrue(result['ok'])
        self.assertEqual(result['verification_attempts'], 3)
        self.assertEqual(result['verification_reclears'], 1)
        self.assertEqual(result['clean_snapshots'], 2)
        self.assertEqual(clears, 2)

    def test_transient_quota_recleared_then_both_origins_twice_clean(self):
        browser = FakeBrowser()
        page = FakePage(browser)
        original = page.call
        reads = 0
        def delayed(method, params):
            nonlocal reads
            if method == 'Storage.getUsageAndQuota':
                reads += 1
                if reads == 1:
                    return {'result': {'usageBreakdown': [{'storageType': 'cache_storage', 'usage': 99}]}}
            return original(method, params)
        page.call = delayed
        result = reset._reset_clients(browser, lambda target: page)
        self.assertTrue(result['ok'])
        self.assertEqual(reads, 6)  # both origins, one dirty + two clean snapshots
        self.assertEqual(result['verification_reclears'], 1)

    def test_failure_carries_diagnostic_stage(self):
        browser = FakeBrowser()
        page = FakePage(browser)
        original = page.call
        page.call = lambda method, params: ({'error': {'message': 'SECRET'}}
                                             if method == 'Storage.clearDataForOrigin'
                                             else original(method, params))
        with self.assertRaises(reset.ResetRefused) as caught:
            reset._reset_clients(browser, lambda target: page)
        self.assertEqual(caught.exception.stage, 'clear_origin_storage')
        self.assertNotIn('SECRET', str(caught.exception))

    def test_old_target_teardown_waits_before_identity_clear(self):
        browser = FakeBrowser()
        page = FakePage(browser)
        original = browser.call
        polls = 0
        close_ack = False
        def delayed(method, params):
            nonlocal polls, close_ack
            if method == 'Target.closeTarget':
                close_ack = True
                return {'result': {'success': True}}  # acknowledged, not destroyed
            if method == 'Target.getTargets' and close_ack:
                polls += 1
                if polls <= 2:
                    self.assertEqual(page.calls, [])
                else:
                    browser.targets = [t for t in browser.targets if t['targetId'] != 'old']
            return original(method, params)
        browser.call = delayed
        self.assertTrue(reset._reset_clients(browser, lambda target: page)['ok'])
        self.assertGreaterEqual(polls, 3)

    def test_old_target_never_disappears_times_out(self):
        browser = FakeBrowser()
        browser.targets.append({'type': 'page', 'url': 'about:blank', 'targetId': 'fresh'})
        # Simulated monotonic progression avoids a three-second wall wait.
        clock = [0.0]
        def advance(_):
            clock[0] = 4.0
        with patch.object(reset.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(reset.time, 'sleep', side_effect=advance):
            with self.assertRaisesRegex(reset.ResetRefused, 'old_target_teardown_timeout') as caught:
                reset._wait_old_targets_closed(browser, {'old'}, 'fresh')
        self.assertEqual(caught.exception.stage, 'wait_old_targets_closed')
        self.assertTrue(any(p['is_old_target'] for p in caught.exception.evidence['pages']))

    def test_unknown_target_teardown_refuses_even_allowed_origin(self):
        browser = FakeBrowser()
        browser.targets.extend([{'type': 'page', 'url': 'about:blank', 'targetId': 'fresh'},
                                {'type': 'page', 'url': 'https://www.google.com/', 'targetId': 'new'}])
        with self.assertRaisesRegex(reset.ResetRefused, 'unknown_target_during_teardown'):
            reset._wait_old_targets_closed(browser, {'old'}, 'fresh')
        self.assertNotIn('Target.closeTarget', [method for method, _ in browser.calls])

    def test_fresh_navigation_or_absence_during_teardown_refused(self):
        for url in [None, 'https://gemini.google.com/app']:
            browser = FakeBrowser()
            if url:
                browser.targets.append({'type': 'page', 'url': url, 'targetId': 'fresh'})
            with self.assertRaisesRegex(reset.ResetRefused, 'fresh_target_missing_or_navigated'):
                reset._wait_old_targets_closed(browser, {'old'}, 'fresh')

    def test_default_off_no_adb(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(reset.subprocess, 'check_output') as adb:
            self.assertFalse(reset.prepare_gemini_cache('adb-149145555W002883-hash')['ok'])
            self.assertFalse(reset.reset_gemini_preserving_http_cache('any')['ok'])
            adb.assert_not_called()

    def test_wrong_phone_scope_refused(self):
        with patch.dict(os.environ, {'RANK_SINGLE_ATTEMPT': '1', 'RANK_GEMINI_CACHE_TRIAL': '1'}), \
             patch.object(reset.subprocess, 'check_output') as adb:
            self.assertFalse(reset.prepare_gemini_cache('device-125')['ok'])
            adb.assert_not_called()

    def test_suffixed_socket_dynamic_owned_forward_cleanup(self):
        browser = FakeBrowser()
        page = FakePage(browser)
        cdp = Mock(side_effect=[browser, page])
        opener = Mock()
        opener.open.side_effect = [
            io.StringIO(json.dumps({'webSocketDebuggerUrl': 'ws://localhost/devtools/browser/b'})),
            io.StringIO(json.dumps([{'id': '0', 'type': 'page', 'url': 'about:blank',
                                    'webSocketDebuggerUrl': 'ws://localhost/devtools/page/fresh'}]))]
        serial = 'adb-149145555W002883-hash (2)._adb-tls-connect._tcp'
        with patch.dict(os.environ, {'RANK_SINGLE_ATTEMPT': '1', 'RANK_GEMINI_CACHE_TRIAL': '1'}), \
             patch.dict('sys.modules', {'gemini_cdp_capture': types.SimpleNamespace(CDP=cdp)}), \
             patch.object(reset.urllib.request, 'build_opener', return_value=opener), \
             patch.object(reset.subprocess, 'check_output',
                          side_effect=[b'000 @chrome_devtools_remote_777\n', b'45678\n', b'']) as adb:
            self.assertTrue(reset.prepare_gemini_cache(serial)['ok'])
        commands = [call.args[0] for call in adb.call_args_list]
        self.assertEqual(commands[1], ['adb', '-s', serial, 'forward', 'tcp:0',
                                       'localabstract:chrome_devtools_remote_777'])
        self.assertEqual(commands[-1], ['adb', '-s', serial, 'forward', '--remove', 'tcp:45678'])
        self.assertEqual(cdp.call_args_list[0].args[0], 'ws://127.0.0.1:45678/devtools/browser/b')
        browser.ws.close.assert_called_once()

    def test_unreachable_default_socket_does_not_hide_suffixed(self):
        browser = FakeBrowser()
        page = FakePage(browser)
        cdp = Mock(side_effect=[browser, page])
        opener = Mock()
        opener.open.side_effect = [
            io.StringIO(json.dumps({'webSocketDebuggerUrl': 'ws://localhost/devtools/browser/b'})),
            io.StringIO(json.dumps([{'id': '1', 'type': 'page', 'url': 'about:blank',
                                    'webSocketDebuggerUrl': 'ws://localhost/devtools/page/fresh'}]))]
        serial = 'adb-149145555W002883-hash (2)._adb-tls-connect._tcp'
        with patch.dict(os.environ, {'RANK_SINGLE_ATTEMPT': '1', 'RANK_GEMINI_CACHE_TRIAL': '1'}), \
             patch.dict('sys.modules', {'gemini_cdp_capture': types.SimpleNamespace(CDP=cdp)}), \
             patch.object(reset.urllib.request, 'build_opener', return_value=opener), \
             patch.object(reset.subprocess, 'check_output', side_effect=[
                 b'000 @chrome_devtools_remote\n000 @chrome_devtools_remote_777\n',
                 b'45678\n', b'']) as adb:
            self.assertTrue(reset.prepare_gemini_cache(serial)['ok'])
        commands = [call.args[0] for call in adb.call_args_list]
        self.assertNotIn('localabstract:chrome_devtools_remote', [part for cmd in commands for part in cmd])
        self.assertEqual(commands[-1][-1], 'tcp:45678')
        self.assertEqual(cdp.call_args_list[0].args[0], 'ws://127.0.0.1:45678/devtools/browser/b')

    def test_multiple_pid_sockets_fail_closed_before_forward(self):
        serial = 'adb-149145555W002883-hash (2)._adb-tls-connect._tcp'
        with patch.dict(os.environ, {'RANK_SINGLE_ATTEMPT': '1', 'RANK_GEMINI_CACHE_TRIAL': '1'}), \
             patch.object(reset.subprocess, 'check_output', return_value=(
                 b'000 @chrome_devtools_remote_777\n000 @chrome_devtools_remote_888\n')) as adb:
            result = reset.prepare_gemini_cache(serial)
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'multiple_pid_chrome_debug_sockets')
        self.assertEqual(adb.call_count, 1)


if __name__ == '__main__':
    unittest.main()
