"""Test-only Gemini identity reset, retaining Chrome's HTTP resource cache.

Caller must exclusively own an authorized disposable Chrome test profile and call
this BEFORE native Gemini navigation. Global cookies are removed; do not use on
personal/logged-in profiles. No work runs on import. Failure must prevent dispatch.

CDP references:
https://chromedevtools.github.io/devtools-protocol/tot/Network/
https://chromedevtools.github.io/devtools-protocol/tot/Storage/
https://chromedevtools.github.io/devtools-protocol/tot/Target/
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request

ORIGIN = 'https://gemini.google.com'
CLEAR_ORIGINS = (ORIGIN, 'https://www.google.com')
STORAGE_TYPES = 'cookies,file_systems,indexeddb,local_storage,websql,service_workers,cache_storage,storage_buckets'
AUTH_COOKIE_NAMES = {'SID', 'HSID', 'SSID', 'APISID', 'SAPISID', '__Secure-1PSID', '__Secure-3PSID'}


class ResetRefused(RuntimeError):
    def __init__(self, reason, stage=None, evidence=None):
        super().__init__(reason)
        self.stage = stage
        self.evidence = evidence


def _call(client, method, params=None):
    reply = client.call(method, params or {})
    if not isinstance(reply, dict) or reply.get('error') or not isinstance(reply.get('result'), dict):
        raise ResetRefused('cdp_method_failed:' + method)
    return reply['result']


def _allowed_url(url):
    if url in ('about:blank', 'chrome://newtab/', 'chrome://newtab'):
        return True
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme == 'https' and parsed.hostname == 'www.google.com'
            and parsed.port in (None, 443) and not parsed.username and not parsed.password
            and parsed.path in ('', '/') and not parsed.query and not parsed.fragment):
        return True  # Known Chrome first-run homepage, never search/accounts.
    return (parsed.scheme == 'https' and parsed.hostname == 'gemini.google.com'
            and parsed.port in (None, 443) and not parsed.username and not parsed.password)


def _pages(client, deadline=None):
    def query(method):
        if deadline is not None:
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise ResetRefused('old_target_teardown_timeout', 'wait_old_targets_closed')
            client.ws.settimeout(min(.5, remaining))
        return _call(client, method)
    targets = query('Target.getTargets').get('targetInfos')
    if not isinstance(targets, list):
        raise ResetRefused('missing_target_list')
    pages = [target for target in targets if target.get('type') == 'page']
    if any(not _allowed_url(target.get('url', '')) for target in pages):
        raise ResetRefused('unexpected_page_or_browser_context')
    # Android supplies a nonempty context ID even for the ordinary profile.
    # getBrowserContexts lists created/nondefault contexts, not that default ID.
    contexts = query('Target.getBrowserContexts').get('browserContextIds')
    if not isinstance(contexts, list):
        raise ResetRefused('missing_browser_context_evidence')
    if any(target.get('browserContextId') in contexts for target in pages):
        raise ResetRefused('nondefault_browser_context')
    if len({target.get('browserContextId') for target in pages}) > 1:
        raise ResetRefused('mixed_browser_contexts')
    if any(not target.get('targetId') for target in pages):
        raise ResetRefused('missing_target_id')
    return pages


def _reset_clients(browser, page_factory):
    """Pure orchestration seam for mock tests; returns sanitized reset evidence."""
    old_pages = _pages(browser)
    # Refuse recognizable Google authentication before making any mutation.
    cookies = _call(browser, 'Storage.getCookies').get('cookies')
    if not isinstance(cookies, list):
        raise ResetRefused('missing_cookie_evidence')
    if any(cookie.get('name') in AUTH_COOKIE_NAMES for cookie in cookies):
        raise ResetRefused('authenticated_profile')
    fresh = _call(browser, 'Target.createTarget', {'url': 'about:blank'}).get('targetId')
    if not fresh or fresh in {page['targetId'] for page in old_pages}:
        raise ResetRefused('fresh_target_not_created')
    for old in old_pages:
        if not _call(browser, 'Target.closeTarget', {'targetId': old['targetId']}).get('success'):
            raise ResetRefused('old_target_not_closed')
    # A close acknowledgement precedes Android tab destruction. Only the exact
    # old targets authorized above may linger; wait before deleting identity so
    # their outstanding work cannot immediately repopulate cleared state.
    _wait_old_targets_closed(browser, {old['targetId'] for old in old_pages}, fresh)
    page = page_factory(fresh)
    stage = 'clear_cookies'
    try:
        _call(page, 'Network.clearBrowserCookies')
        stage = 'clear_origin_storage'
        for origin in CLEAR_ORIGINS:
            _call(page, 'Storage.clearDataForOrigin', {'origin': origin, 'storageTypes': STORAGE_TYPES})
        # Never invoke Network.clearBrowserCache or setCacheDisabled(true).
        stage = 'enable_http_cache'
        _call(page, 'Network.setCacheDisabled', {'cacheDisabled': False})
        stage = 'verify_stable_identity'
        verification = _verify_stable_identity(browser, page, fresh)
        # The new unrelated blank browsing context has no old sessionStorage or
        # conversation JS heap. The caller's native flow navigates this context.
        return {'ok': True, 'reason': 'gemini_identity_reset', 'closed_pages': len(old_pages),
                'fresh_target_id': fresh, 'cookies_remaining': 0, 'origin': ORIGIN,
                'origins_cleared': list(CLEAR_ORIGINS),
                'storage_types_cleared': STORAGE_TYPES.split(','),
                **verification,
                'http_cache_clear_requested': False,
                'cache_reuse_verified': False}
    except Exception as error:
        if isinstance(error, ResetRefused):
            if error.stage is None:
                error.stage = stage
            raise
        raise ResetRefused('reset_stage_failed:' + type(error).__name__, stage) from None
    finally:
        try:
            page.ws.close()
        except Exception:
            pass


def _wait_old_targets_closed(browser, old_ids, fresh):
    """Wait <=3 seconds for acknowledged old targets, never close new targets."""
    deadline = time.monotonic() + 3
    last_evidence = {}
    while time.monotonic() < deadline:
        browser.ws.settimeout(min(.5, max(.001, deadline-time.monotonic())))
        try:
            pages = _pages(browser, deadline=deadline)
        except Exception as error:
            if isinstance(error, ResetRefused):
                if error.stage is None:
                    error.stage = 'wait_old_targets_closed'
                raise
            raise ResetRefused('target_teardown_check_failed:' + type(error).__name__,
                               'wait_old_targets_closed') from None
        last_evidence = {'page_count': len(pages), 'pages': [
            {'is_fresh': target['targetId'] == fresh, 'is_old_target': target['targetId'] in old_ids,
             'url_class': 'blank' if target.get('url') == 'about:blank' else 'allowed_nonblank'}
            for target in pages]}
        fresh_pages = [target for target in pages if target['targetId'] == fresh]
        if len(fresh_pages) != 1 or fresh_pages[0].get('url') != 'about:blank':
            raise ResetRefused('fresh_target_missing_or_navigated', 'wait_old_targets_closed', last_evidence)
        if any(target['targetId'] not in old_ids | {fresh} for target in pages):
            raise ResetRefused('unknown_target_during_teardown', 'wait_old_targets_closed', last_evidence)
        if not any(target['targetId'] in old_ids for target in pages):
            return
        time.sleep(min(.1, max(0, deadline-time.monotonic())))
    raise ResetRefused('old_target_teardown_timeout', 'wait_old_targets_closed', last_evidence)


def _verify_stable_identity(browser, page, fresh):
    """Require two clean snapshots >=200ms apart, allowing <=3s settling.

    Old pages are already closed and service-worker storage already cleared.
    Cookies/quota written by an in-flight completion are cleared again; no dirty
    snapshot is accepted. Unexpected pages, malformed evidence and renewed auth
    are terminal failures rather than reasons to expand deletion scope.
    """
    began = time.monotonic()
    deadline = began + 3
    consecutive = attempts = reclears = 0
    last_dirty = 'stable_verification_timeout'

    def checked(client, method, params=None):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ResetRefused(last_dirty, 'verify_stable_identity')
        client.ws.settimeout(min(.5, remaining))
        return _call(client, method, params)

    while time.monotonic() < deadline:
        attempts += 1
        remaining = checked(browser, 'Storage.getCookies').get('cookies')
        if not isinstance(remaining, list):
            raise ResetRefused('missing_cookie_evidence', 'verify_cookies')
        if any(cookie.get('name') in AUTH_COOKIE_NAMES for cookie in remaining):
            raise ResetRefused('authenticated_profile_reappeared', 'verify_cookies')
        dirty_origins = []
        for origin in CLEAR_ORIGINS:
            breakdown = checked(page, 'Storage.getUsageAndQuota', {'origin': origin}).get('usageBreakdown')
            if not isinstance(breakdown, list) or any(not isinstance(item, dict)
                    or type(item.get('usage')) not in (int, float) or item['usage'] < 0
                    for item in breakdown):
                raise ResetRefused('missing_storage_usage_evidence', 'verify_origin_storage')
            if any(item.get('storageType') in STORAGE_TYPES.split(',') and item['usage'] != 0
                   for item in breakdown):
                dirty_origins.append(origin)
        targets = checked(browser, 'Target.getTargets').get('targetInfos')
        if not isinstance(targets, list):
            raise ResetRefused('missing_target_list', 'verify_fresh_page')
        pages = [target for target in targets if target.get('type') == 'page']
        if len(pages) != 1 or pages[0].get('targetId') != fresh or pages[0].get('url') != 'about:blank':
            raise ResetRefused('unexpected_page_after_reset', 'verify_fresh_page', {
                'page_count': len(pages),
                'pages': [{'is_fresh': target.get('targetId') == fresh,
                           'url_class': ('blank' if target.get('url') == 'about:blank'
                                         else 'allowed_nonblank' if _allowed_url(target.get('url','')) else 'unexpected')}
                          for target in pages]})
        if remaining or dirty_origins:
            consecutive = 0
            last_dirty = 'cookies_remain_after_reset' if remaining else 'origin_storage_remains'
            if reclears < 3:
                for origin in dirty_origins:
                    checked(page, 'Storage.clearDataForOrigin', {'origin': origin, 'storageTypes': STORAGE_TYPES})
                if remaining:
                    checked(page, 'Network.clearBrowserCookies')
                reclears += 1
        else:
            consecutive += 1
            if consecutive >= 2:
                return {'clean_snapshots': 2, 'verification_attempts': attempts,
                        'verification_reclears': reclears,
                        'verification_elapsed_s': round(time.monotonic()-began, 3)}
        time.sleep(min(.2, max(0, deadline-time.monotonic())))
    raise ResetRefused(last_dirty, 'verify_stable_identity')


def reset_gemini_preserving_http_cache(serial: str, *, authorized_test_phone: bool = False) -> dict:
    """Return ok only after verified local identity reset; never navigate Gemini.

    Requires explicit test-profile authorization AND RANK_GEMINI_CACHE_TRIAL=1.
    Unknown page origins and recognizable signed-in Google profiles are refused.
    Clearing browser cookies is profile-wide; HTTP-cache reuse still needs actual
    measurement (cache partitioning/revalidation can limit savings).
    """
    if not authorized_test_phone or os.environ.get('RANK_GEMINI_CACHE_TRIAL') != '1':
        return {'ok': False, 'reason': 'test_only_disabled'}
    from gemini_cdp_capture import CDP
    ports = []
    browsers = []

    def adb(*args):
        return subprocess.check_output(['adb', '-s', serial, *args], timeout=10,
                                       stderr=subprocess.DEVNULL).decode(errors='replace')

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get(port, path):
        with opener.open(f'http://127.0.0.1:{port}{path}', timeout=3) as response:
            return json.load(response)

    def websocket_url(port, supplied):
        parsed = urllib.parse.urlsplit(supplied)
        if parsed.scheme != 'ws' or not parsed.path.startswith('/devtools/') or parsed.query or parsed.fragment:
            raise ResetRefused('unexpected_debugger_endpoint')
        return f'ws://127.0.0.1:{port}{parsed.path}'

    try:
        unix = adb('shell', 'cat', '/proc/net/unix')
        names = sorted(set(re.findall(r'@((?:chrome_devtools_remote)(?:_\d+)?)\b', unix)))
        if not names:
            raise ResetRefused('no_chrome_debug_socket')
        candidates = []
        for name in names:
            port = int(adb('forward', 'tcp:0', 'localabstract:' + name).strip())
            ports.append(port)
            try:
                version = get(port, '/json/version')
                browser = CDP(websocket_url(port, version['webSocketDebuggerUrl']))
            except (OSError, ValueError, KeyError):
                # Android can advertise a dead unsuffixed socket alongside its
                # working PID-suffixed socket. Only transport/protocol discovery
                # failures are skipped; page/profile safety refusals below are
                # deliberately outside this handler.
                continue
            browsers.append(browser)
            pages = _pages(browser)  # Refuse unrelated work on any exposed socket.
            candidates.append((port, browser, pages))
        with_pages = [candidate for candidate in candidates if candidate[2]]
        if len(with_pages) != 1:
            raise ResetRefused('ambiguous_or_empty_chrome_profile')
        port, browser, _ = with_pages[0]

        def page_factory(target_id):
            for _ in range(5):
                blanks = [page for page in get(port, '/json/list')
                          if page.get('type') == 'page' and page.get('url') == 'about:blank']
                if len(blanks) > 1:
                    raise ResetRefused('ambiguous_blank_page')
                if blanks:
                    candidate = CDP(websocket_url(port, blanks[0]['webSocketDebuggerUrl']))
                    try:
                        # Android's HTTP /json IDs can be '0'/'1', unlike the
                        # protocol's hexadecimal target IDs. Verify identity on
                        # the page connection rather than equating those IDs.
                        info = _call(candidate, 'Target.getTargetInfo').get('targetInfo', {})
                        if info.get('targetId') != target_id or info.get('url') != 'about:blank':
                            raise ResetRefused('fresh_page_target_mismatch')
                        return candidate
                    except Exception:
                        candidate.ws.close()
                        raise
                time.sleep(.2)
            raise ResetRefused('fresh_page_debugger_missing')

        return _reset_clients(browser, page_factory)
    except Exception as error:
        return {'ok': False, 'reason': str(error) if isinstance(error, ResetRefused)
                else 'reset_failed:' + type(error).__name__,
                'failure_stage': (getattr(error, 'stage', None) or 'discovery_or_target_setup'),
                'evidence': getattr(error, 'evidence', None)}
    finally:
        for browser in browsers:
            try:
                browser.ws.close()
            except Exception:
                pass
        for port in ports:
            try:
                adb('forward', '--remove', f'tcp:{port}')
            except Exception:
                pass


def prepare_gemini_cache(serial: str) -> dict:
    """Dispatcher entry point; additionally restrict trial to device-104.

    Caller verifies exclusive phone ownership, Gemini, native v82 and single-
    attempt mode. A failed preparation MUST NOT set geminiCachePrepared=true.
    Rollback: disable RANK_GEMINI_CACHE_TRIAL; normal native full reset resumes.
    """
    if ('149145555W002883' not in serial or os.environ.get('RANK_SINGLE_ATTEMPT') != '1'
            or os.environ.get('RANK_GEMINI_CACHE_TRIAL') != '1'):
        return {'ok': False, 'reason': 'trial_scope_not_enabled'}
    return reset_gemini_preserving_http_cache(serial, authorized_test_phone=True)
