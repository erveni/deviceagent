"""Opt-in same-answer repair: scroll and temporary layout zoom, never regenerate.

The caller must own the phone until this function returns and provide its existing
OCR validator. `ok` is true only after that validator accepts the actual screenshot.
No function runs on import. Run --self-test for offline synthetic selector checks.
"""
from __future__ import annotations

import json
import base64
import math
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Callable
import urllib.parse
import urllib.request


# Snapshot guards and selection are deliberately shared with the synthetic tests.
# innerText is read ONLY from model-response message-content for rank extraction.
_SELECTOR_JS = r"""(function(expectedKeyword, expectedRank, scroll, expectedText, action, promptFree) {
  const fail = reason => ({ok:false, reason});
  const norm = s => String(s || '').normalize('NFKC').replace(/\s+/g,' ').trim().toLowerCase();
  if (location.hostname !== 'gemini.google.com' || location.protocol !== 'https:') return fail('wrong_origin');
  if (document.visibilityState !== 'visible') return fail('hidden_page');
  if (!norm(document.body && document.body.innerText).includes(norm(expectedKeyword))) return fail('keyword_mismatch');
  const displayed = e => {
    const style = getComputedStyle(e);
    return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0'
      && e.getClientRects().length > 0;
  };
  const answers = [...document.querySelectorAll('model-response message-content')].filter(displayed);
  if (answers.length !== 1) return fail('ambiguous_answer_count');
  const answer = answers[0], text = answer.innerText;
  const marker = /\[RANK:\s*(\d+)\s*\/\s*(\d+)\s*\]/gi;
  const ranks = [...text.matchAll(marker)];
  if (ranks.length !== 1 || Number(ranks[0][1]) !== expectedRank[0]
      || Number(ranks[0][2]) !== expectedRank[1]) return fail('rank_mismatch_or_ambiguity');
  if (expectedText !== null && text !== expectedText) return fail('answer_changed');
  const matching = [answer, ...answer.querySelectorAll('*')].filter(e => {
    if (!displayed(e)) return false;
    const hits = [...String(e.textContent || '').matchAll(marker)];
    return hits.length === 1 && Number(hits[0][1]) === expectedRank[0]
      && Number(hits[0][2]) === expectedRank[1];
  });
  // A rank paragraph may also contain an inline business link, or split the
  // marker over spans. Choose its smallest matching container, not a leaf.
  const containers = matching.filter(e => ![...e.querySelectorAll('*')].some(d => matching.includes(d)));
  if (containers.length !== 1) return fail('ambiguous_rank_container');
  if (action === 'retain') return answer;
  const safeTop = 160;
  let safeBottom = innerHeight - 130;
  for (const nudge of document.querySelectorAll('sign-in-nudge')) {
    if (nudge === answer || [...answer.querySelectorAll('*')].includes(nudge) || !displayed(nudge)) continue;
    const obstruction = nudge.getBoundingClientRect();
    if (obstruction.bottom > 0 && obstruction.top < innerHeight)
      safeBottom = Math.min(safeBottom, obstruction.top - 8);
  }
  let alignment_adjustments = 0;
  if (scroll) {
    answer.scrollIntoView({block:'center', inline:'nearest', behavior:'instant'});
    // Browser centering ignores our header/composer exclusion band. Align only
    // when the whole answer fits that band; never try to hide an oversized one.
    let box = answer.getBoundingClientRect();
    const bandHeight = safeBottom - safeTop;
    if (box.bottom - box.top <= bandHeight && bandHeight > 0
        && (promptFree || box.top < safeTop || box.bottom > safeBottom)) {
      let ancestor = answer.parentElement, scroller = null;
      for (let depth=0; ancestor && depth<32; depth++, ancestor=ancestor.parentElement) {
        const overflow = getComputedStyle(ancestor).overflowY;
        if (/^(auto|scroll|overlay)$/.test(overflow) && ancestor.scrollHeight > ancestor.clientHeight + 1) {
          scroller = ancestor; break;
        }
      }
      if (!scroller && document.scrollingElement
          && document.scrollingElement.scrollHeight > document.scrollingElement.clientHeight + 1)
        scroller = document.scrollingElement;
      for (let attempt=0; scroller && attempt<2; attempt++) {
        box = answer.getBoundingClientRect();
        if (promptFree ? Math.abs(box.top-safeTop) < 1 : (box.top >= safeTop && box.bottom <= safeBottom)) break;
        const targetTop = promptFree ? safeTop : safeTop + (bandHeight - (box.bottom-box.top)) / 2;
        const delta = Math.max(-innerHeight, Math.min(innerHeight, box.top-targetTop));
        const previous = scroller.scrollTop;
        scroller.scrollTop = previous + delta;
        alignment_adjustments++;
        if (Math.abs(scroller.scrollTop-previous) < 0.5) break;
      }
    }
  }
  const rect = containers[0].getBoundingClientRect();
  const full = answer.getBoundingClientRect();
  const prompts = [...document.querySelectorAll('user-query')].filter(displayed);
  const promptClear = !promptFree || (prompts.length === 1 && prompts[0].getBoundingClientRect().bottom <= safeTop);
  return {ok:true, text, rank:expectedRank, rank_in_view:rect.top >= 0 && rect.bottom <= innerHeight,
    full_answer_in_view:full.top >= safeTop && full.bottom <= safeBottom && promptClear,
    answer_fits:full.top >= safeTop && full.bottom <= safeBottom,
    answer_clip:{x:full.left+(globalThis.scrollX||0),y:full.top+(globalThis.scrollY||0),width:full.width,height:full.height,scale:1},
    prompt_clear:promptClear,
    safe_band:{top:safeTop,bottom:safeBottom},
    answer_rect:{top:full.top,bottom:full.bottom}, alignment_adjustments,
    rank_container_tag:containers[0].tagName || containers[0].tag || null};
})"""


def _expression(keyword: str, rank: tuple[int, int], *, scroll=False, text=None, action=None, prompt_free=False, platform='gemini') -> str:
    if platform not in ('gemini', 'chatgpt'):
        raise ValueError('Unsupported answer platform')
    selector = _SELECTOR_JS
    if platform == 'chatgpt':
        selector = selector.replace('gemini.google.com', 'chatgpt.com').replace(
            "const answers = [...document.querySelectorAll('model-response message-content')].filter(displayed);",
            "const modern = [...document.querySelectorAll('[data-assistant-markdown]')].filter(displayed); "
            "const answers = modern.length ? modern : [...document.querySelectorAll('[data-message-author-role=\"assistant\"]')].filter(displayed);").replace(
            'user-query', '[data-message-author-role="user"]').replace(
            'text = answer.innerText', 'text = answer.textContent').replace(
            'const safeTop = 160;', 'const safeTop = 100;')
    return selector + '(' + ','.join(json.dumps(v) for v in
                                       (keyword, rank, scroll, text, action, prompt_free)) + ')'


def _on_answer(client, object_id, function, arguments=()):
    reply = client.call('Runtime.callFunctionOn', {
        'objectId': object_id, 'functionDeclaration': function,
        'arguments': [{'value': value} for value in arguments], 'returnByValue': True})
    result = reply.get('result', {})
    if reply.get('error') or result.get('exceptionDetails'):
        raise RuntimeError('Answer layout operation failed')
    value = result.get('result', {}).get('value')
    if not isinstance(value, dict):
        raise RuntimeError('Answer layout operation returned no evidence')
    return value


_ZOOM_SAVE = """function(){return {value:this.style.getPropertyValue('zoom'),
 priority:this.style.getPropertyPriority('zoom')}}"""
_ZOOM_RESTORE = """function(value,priority){
 if(value==='')this.style.removeProperty('zoom');else this.style.setProperty('zoom',value,priority);
 return {ok:this.style.getPropertyValue('zoom')===value && this.style.getPropertyPriority('zoom')===priority};} """

# Never reduce the rendered answer below a readable half-size.  Google local-result
# cards can make a valid three-result answer too tall for the unobstructed Gemini
# viewport; these are whole-answer layout zooms, not DOM/content edits.
_READABLE_ZOOM_LEVELS = (0.65, 0.55, 0.50)


def _frame_diagnostics(snapshot: dict) -> dict:
    """Return layout-only rejection evidence; never return answer/prompt text."""
    return {key: snapshot.get(key) for key in (
        'ok', 'reason', 'rank_in_view', 'full_answer_in_view', 'safe_band',
        'answer_rect', 'alignment_adjustments', 'rank_container_tag')}


def _evaluate(client, expression):
    reply = client.call('Runtime.evaluate', {'expression': expression, 'returnByValue': True})
    result = reply.get('result', {})
    if reply.get('error') or result.get('exceptionDetails'):
        raise RuntimeError('CDP evaluation failed')
    value = result.get('result', {}).get('value')
    if not isinstance(value, dict):
        raise RuntimeError('CDP evaluation returned no snapshot')
    return value


def reframe_same_answer(serial: str, expected_keyword: str, expected_rank: tuple[int, int],
                       outputpath: str | Path, *,
                       ocr_validator: Callable[[str], bool] | None = None,
                       prompt_free: bool = False, platform: str = 'gemini') -> dict:
    """Return evidence. Success requires the full answer in a safe band and OCR.

    Only attaches to an already-visible, unambiguous Gemini answer. All discovered
    Chrome sockets are tried (including suffixed sockets); unreachable discovery
    endpoints are skipped. A reachable Gemini target that cannot be inspected
    fails closed. If scrolling alone clips the answer, temporarily use CSS zoom
    0.65 and restore the exact original inline value/priority in finally. Text and
    nodes are never deleted. No caller/global ADB forward is replaced or removed.
    """
    result = {'ok': False, 'response_unchanged': False, 'ocr_verified': False,
              'new_prompts': 0, 'reloads': 0, 'navigations': 0, 'screenshot': None,
              'layout_zoom': 1.0, 'full_answer_in_view': False}
    if not serial or not isinstance(expected_keyword, str) or not expected_keyword.strip():
        return result | {'reason': 'invalid_expected_identity'}
    if (not isinstance(expected_rank, (tuple, list)) or len(expected_rank) != 2
            or any(type(n) is not int for n in expected_rank)
            or not 0 < expected_rank[0] <= expected_rank[1]):
        return result | {'reason': 'invalid_expected_rank'}
    if not callable(ocr_validator):
        return result | {'reason': 'caller_ocr_validator_required'}
    output = Path(outputpath).resolve()
    from functools import partial
    if platform not in ('gemini', 'chatgpt'):
        return result | {'reason': 'unsupported_platform'}
    hostname = 'chatgpt.com' if platform == 'chatgpt' else 'gemini.google.com'
    expression = partial(_expression, prompt_free=prompt_free, platform=platform)
    if output.exists() or not output.parent.is_dir():
        return result | {'reason': 'output_must_be_new_file_in_existing_directory'}
    # Import only the websocket client class, never the old module's fixed forward.
    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from gemini_cdp_capture import CDP
    except ImportError:
        return result | {'reason': 'cdp_dependency_unavailable'}

    def adb(*args):
        return subprocess.check_output(['adb', '-s', serial, *args], timeout=10,
                                       stderr=subprocess.DEVNULL)

    forwards, clients, candidates, seen_targets = [], [], [], set()
    rejected = []
    restore = None
    try:
        unix = adb('shell', 'cat', '/proc/net/unix').decode(errors='replace')
        sockets = sorted(set(re.findall(r'@(chrome_devtools_remote[\w.-]*)(?=\s|$)', unix)),
                         key=lambda s: (s == 'chrome_devtools_remote', s))
        if not sockets or len(sockets) > 8:
            return result | {'reason': 'missing_or_excessive_chrome_sockets'}
        for socket_name in sockets:
            port = int(adb('forward', 'tcp:0', 'localabstract:' + socket_name).strip())
            forwards.append(port)
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list', timeout=3) as stream:
                    tabs = json.load(stream)
            except Exception:
                continue
            if not isinstance(tabs, list):
                return result | {'reason': 'invalid_target_list'}
            for tab in tabs:
                url = urllib.parse.urlparse(tab.get('url', ''))
                if tab.get('type') != 'page' or url.scheme != 'https' or url.hostname != hostname:
                    continue
                target = tab.get('id')
                if not target:
                    return result | {'reason': 'missing_target_identity'}
                if target in seen_targets:
                    continue  # Default and suffixed sockets can expose the same target.
                seen_targets.add(target)
                ws = urllib.parse.urlparse(tab.get('webSocketDebuggerUrl', ''))
                if ws.scheme != 'ws' or not ws.path.startswith('/devtools/page/'):
                    return result | {'reason': 'invalid_debugger_endpoint'}
                client = CDP(urllib.parse.urlunparse(ws._replace(netloc=f'127.0.0.1:{port}')))
                clients.append(client)
                snapshot = _evaluate(client, expression(expected_keyword, expected_rank))
                if snapshot.get('ok'):
                    candidates.append((client, snapshot))
                else:
                    rejected.append(snapshot.get('reason', 'unknown_snapshot_rejection'))
        if len(candidates) != 1:
            return result | {'reason': 'no_unique_visible_matching_answer',
                             'matching_targets': len(candidates), 'rejections': rejected}
        client, before = candidates[0]
        def chatgpt_wheel_align(snapshot):
            # This ChatGPT scroller ignores scrollTop but honors wheel input.
            # Every movement is derived from the guarded answer rectangle.
            if platform != 'chatgpt':
                return snapshot
            for _ in range(5):
                if not snapshot.get('ok'):
                    break
                rect, band = snapshot['answer_rect'], snapshot['safe_band']
                if rect['bottom']-rect['top'] > band['bottom']-band['top']:
                    break
                delta = rect['top']-(band['top']+2)
                if abs(delta) < .5:
                    break
                reply = client.call('Input.dispatchMouseEvent', {'type':'mouseWheel',
                    'x':180,'y':380,'deltaX':0,'deltaY':delta})
                if reply.get('error'):
                    break
                time.sleep(.15)
                snapshot = _evaluate(client, expression(expected_keyword, expected_rank, text=before['text']))
            return snapshot
        moved = _evaluate(client, expression(expected_keyword, expected_rank, scroll=True,
                                              text=before['text']))
        if not moved.get('ok'):
            return result | {'reason': moved.get('reason', 'reframe_failed')}
        time.sleep(0.5)
        framed = _evaluate(client, expression(expected_keyword, expected_rank, text=before['text']))
        framed = chatgpt_wheel_align(framed)
        if not framed.get('ok'):
            return result | {'reason': 'rank_not_visible_or_answer_changed'}
        if not framed.get('full_answer_in_view') and not (prompt_free and framed.get('answer_fits')):
            # Retain the exact guarded node as a remote object: restoration must
            # still reach that node if the UI changes or detaches it afterwards.
            retained = client.call('Runtime.evaluate', {
                'expression': expression(expected_keyword, expected_rank,
                                          text=before['text'], action='retain'),
                'returnByValue': False})
            node = retained.get('result', {}).get('result', {})
            if retained.get('error') or node.get('subtype') != 'node' or not node.get('objectId'):
                return result | {'reason': 'cannot_retain_guarded_answer'}
            object_id = node['objectId']
            original = _on_answer(client, object_id, _ZOOM_SAVE)
            restore = (client, object_id, original['value'], original['priority'])
            guard = expression(expected_keyword, expected_rank, text=before['text'], action='retain')
            # Try only readable, whole-answer zoom levels.  Each level repeats the
            # exact identity/rank guard after positioning; a partial card list or a
            # changed response therefore cannot become an accepted screenshot.
            for zoom in _READABLE_ZOOM_LEVELS:
                changed = _on_answer(client, object_id, 'function(){if((' + guard +
                                     ")!==this)return {ok:false};this.style.setProperty('zoom','" + str(zoom) + "');return {ok:true};}")
                if not changed.get('ok'):
                    return result | {'reason': 'answer_changed_before_zoom'}
                result['layout_zoom'] = zoom
                _evaluate(client, expression(expected_keyword, expected_rank, scroll=True, text=before['text']))
                time.sleep(0.5)
                framed = _evaluate(client, expression(expected_keyword, expected_rank, text=before['text']))
                framed = chatgpt_wheel_align(framed)
                if (framed.get('ok') and framed.get('rank_in_view')
                        and (framed.get('full_answer_in_view') or
                             (platform == 'chatgpt' and prompt_free and framed.get('answer_fits')))):
                    break
        # A short answer can fit while the page has no scroll range to hide the
        # prompt. Capture only that rendered answer rectangle, never synthesize or
        # edit its pixels. Oversized/clipped answers are still rejected.
        if platform == 'chatgpt':
            # Wheel input animates. Do not capture at the first passing frame:
            # require an unchanged answer rectangle for three observations.
            stable = 0
            for _ in range(15):
                time.sleep(.2)
                snapshot = _evaluate(client, expression(expected_keyword, expected_rank, text=before['text']))
                if not snapshot.get('ok'):
                    return result | {'reason':'answer_changed_while_settling'}
                stable = stable+1 if snapshot.get('answer_clip') == framed.get('answer_clip') else 0
                framed = snapshot
                if stable >= 2:
                    break
            else:
                return result | {'reason':'answer_layout_did_not_settle'}
        answer_clip = _safe_answer_clip(framed) if prompt_free else None
        cropped = bool(answer_clip and not framed.get('full_answer_in_view'))
        if not framed.get('ok') or not framed.get('rank_in_view') or not (framed.get('full_answer_in_view') or cropped):
            return result | {'reason': 'full_answer_clipped_or_changed',
                'frame_diagnostics': _frame_diagnostics(framed)}
        if cropped:
            capture = client.call('Page.captureScreenshot', {'format':'png',
                'captureBeyondViewport':platform != 'chatgpt', 'clip':answer_clip})
            screenshot = base64.b64decode(capture.get('result', {}).get('data', ''), validate=True)
        else:
            screenshot = adb('exec-out', 'screencap', '-p')
        after = _evaluate(client, expression(expected_keyword, expected_rank, text=before['text']))
        geometry_valid = (_safe_answer_clip(after) == answer_clip) if cropped else after.get('full_answer_in_view')
        if cropped and platform == 'chatgpt':
            geometry_valid = _same_clip_with_subpixel_rounding(answer_clip, _safe_answer_clip(after))
        if not after.get('ok') or not after.get('rank_in_view') or not geometry_valid:
            return result | {'reason': 'answer_changed_during_screenshot',
                'before_frame': _frame_diagnostics(framed), 'after_frame': _frame_diagnostics(after)}
        if not screenshot.startswith(b'\x89PNG\r\n\x1a\n'):
            return result | {'reason': 'invalid_actual_screenshot'}
        with output.open('xb') as stream:
            stream.write(screenshot)
        result.update(screenshot=str(output), response_unchanged=True,
                      capture_method='browser_answer_clip' if cropped else 'device_viewport',
                      expected_rank=list(expected_rank), full_answer_in_view=True,
                      safe_band=after.get('safe_band'))
        # A screenshot is evidence only when the existing production guard accepts it.
        if not ocr_validator(str(output)):
            return result | {'reason': 'caller_ocr_rejected'}
        result.update(ok=True, ocr_verified=True, reason='same_answer_reframed')
        return result  # finally can demote success if exact layout restoration fails.
    except Exception as error:
        return result | {'reason': 'reframe_failed', 'error_type': type(error).__name__}
    finally:
        restore_failed = False
        if restore is not None:
            try:
                restore_failed = not _on_answer(restore[0], restore[1], _ZOOM_RESTORE, restore[2:]).get('ok')
            except Exception:
                restore_failed = True
        for client in clients:
            try:
                client.close()
            except Exception:
                pass
        if restore_failed:
            result.update(ok=False, reason='original_layout_restore_failed')
        for port in forwards:
            try:
                adb('forward', '--remove', f'tcp:{port}')
            except Exception:
                pass


def _same_clip_with_subpixel_rounding(before, after):
    """Allow compositor rounding below 1/16 CSS pixel, never actual scrolling.

    Text identity and complete answer/rank visibility are checked separately.
    Measured ChatGPT drift was0.0084 CSS px; exact float equality rejected it.
    """
    return (isinstance(before,dict) and isinstance(after,dict)
            and set(before)==set(after)=={'x','y','width','height','scale'}
            and before['scale']==after['scale']==1
            and all(type(before[k]) in (int,float) and type(after[k]) in (int,float)
                    and math.isfinite(before[k]) and math.isfinite(after[k])
                    and abs(before[k]-after[k])<=1/16 for k in ('x','y','width','height')))


def _safe_answer_clip(snapshot):
    """Only an already complete, fully visible answer may use browser clipping."""
    if not snapshot.get('ok') or not snapshot.get('rank_in_view') or not snapshot.get('answer_fits'):
        return None
    clip = snapshot.get('answer_clip') or {}
    if set(clip) != {'x','y','width','height','scale'}:
        return None
    if any(type(v) not in (float,int) or not math.isfinite(v) for v in clip.values()):
        return None
    if clip['x'] < 0 or clip['y'] < 0 or not 0 < clip['width'] <= 4096 or not 0 < clip['height'] <= 4096 or clip['scale'] != 1:
        return None
    return clip


def _self_test():
    """Execute the real JavaScript against synthetic DOM objects, offline."""
    script = r"""
const select = SELECTOR;
let scrolled = 0;
global.location = {hostname:'gemini.google.com', protocol:'https:'};
global.innerHeight = 1000;
global.getComputedStyle = e => ({display:'block',visibility:'visible',opacity:'1'});
const node = text => ({innerText:text,textContent:text,childElementCount:0,
  getClientRects:()=>[{}],getBoundingClientRect:()=>({top:100,bottom:130}),
  scrollIntoView:()=>{scrolled++},querySelectorAll:()=>[]});
const good = node('Answer [RANK: 2/5]');
global.document = {visibilityState:'visible',body:{innerText:'Best plumbers city'},
  querySelectorAll:s=>s==='model-response message-content'?[good]:[]};
const check = (test, label) => {if(!test)throw Error(label)};
check(select('plumbers',[2,5],false,null).ok,'valid');
check(!select('dentists',[2,5],false,null).ok,'keyword mismatch');
check(!select('plumbers',[3,5],false,null).ok,'wrong expected rank');
check(!select('plumbers',[2,5],false,'changed').ok,'changed answer');
document.visibilityState='hidden';check(!select('plumbers',[2,5],false,null).ok,'hidden');
document.visibilityState='visible';
document.querySelectorAll=s=>s==='model-response message-content'?[good,node('Other [RANK: 2/5]')]:[];
check(!select('plumbers',[2,5],false,null).ok,'multiple answers');
document.querySelectorAll=s=>s==='model-response message-content'?[node('No answer rank')]:[];
document.body.innerText='plumbers prompt EXAMPLE [RANK: 2/5]';
check(!select('plumbers',[2,5],false,null).ok,'prompt marker excluded');
document.querySelectorAll=s=>s==='model-response message-content'?[node('[RANK: 2/5] [RANK: 2/5]')]:[];
check(!select('plumbers',[2,5],false,null).ok,'duplicate markers');
document.querySelectorAll=s=>s==='model-response message-content'?[good]:[];
check(select('plumbers',[2,5],true,good.innerText).ok && scrolled===1,'only scroll');
location.hostname='gemini.google.com.evil.test';
check(!select('plumbers',[2,5],false,null).ok,'origin');
location.hostname='gemini.google.com';
good.getBoundingClientRect=()=>({top:159,bottom:800});
check(!select('plumbers',[2,5],false,null).full_answer_in_view,'top clipped');
good.getBoundingClientRect=()=>({top:160,bottom:871});
check(!select('plumbers',[2,5],false,null).full_answer_in_view,'bottom clipped');
good.getBoundingClientRect=()=>({top:160,bottom:870});
check(select('plumbers',[2,5],false,null).full_answer_in_view,'safe boundary');
check(select('plumbers',[2,5],false,good.innerText,'retain')===good,'retain exact node');
check(select('plumbers',[2,5],false,'changed','retain')!==good,'retain changed forbidden');
let value='0.8', priority='important';
good.style={getPropertyValue:()=>value,getPropertyPriority:()=>priority,
 setProperty:(key,v,p='')=>{value=v;priority=p},removeProperty:()=>{value='';priority=''}};
const save=SAVE, restore=RESTORE;
const original=save.call(good);good.style.setProperty('zoom','0.65');
check(restore.call(good,original.value,original.priority).ok && value==='0.8' && priority==='important','restore priority');
check(restore.call(good,'','').ok && value==='' && priority==='','restore absent');
global.getComputedStyle=e=>({display:'block',visibility:'visible',opacity:'1',overflowY:e.overflowY || 'visible'});
let scrollPosition=500, baseTop=134.5625, height=397.69644;
const scroller={overflowY:'auto',scrollHeight:2000,clientHeight:1000,parentElement:null,
 get scrollTop(){return scrollPosition},set scrollTop(v){scrollPosition=Math.max(0,Math.min(1000,v))}};
good.parentElement=scroller;
good.getBoundingClientRect=()=>({top:baseTop-(scrollPosition-500),bottom:baseTop-(scrollPosition-500)+height});
let aligned=select('plumbers',[2,5],true,good.innerText);
check(aligned.full_answer_in_view && aligned.alignment_adjustments===1,'real clipped-top geometry aligned');
baseTop=600;scrollPosition=500;height=400;
aligned=select('plumbers',[2,5],true,good.innerText);
check(aligned.full_answer_in_view && aligned.alignment_adjustments===1,'bottom aligned');
baseTop=100;scrollPosition=500;height=900;
aligned=select('plumbers',[2,5],true,good.innerText);
check(!aligned.full_answer_in_view && aligned.alignment_adjustments===0,'oversize not concealed');
height=400;scrollPosition=0;baseTop=-400;
aligned=select('plumbers',[2,5],true,good.innerText);
check(!aligned.full_answer_in_view && aligned.alignment_adjustments===1,'clamped scroll fails bounded');
const unchanged=scrollPosition;
check(!select('wrong keyword',[2,5],true,good.innerText).ok && scrollPosition===unchanged,'alignment retains identity guard');
const nudge=node('Sign in');nudge.getBoundingClientRect=()=>({top:583,bottom:671});
document.querySelectorAll=s=>s==='model-response message-content'?[good]:s==='sign-in-nudge'?[nudge]:[];
baseTop=134.5625;height=397.69644;scrollPosition=500;
aligned=select('plumbers',[2,5],true,good.innerText);
check(aligned.full_answer_in_view && aligned.safe_band.bottom===575,'actual sign-in overlay band');
nudge.getClientRects=()=>[];
aligned=select('plumbers',[2,5],false,good.innerText);
check(aligned.safe_band.bottom===870,'hidden sign-in nudge ignored');
console.log('PASS 24 offline selector/layout guards; overlay band, alignment and exact style restoration');
""".replace('SELECTOR', _SELECTOR_JS).replace('SAVE', _ZOOM_SAVE).replace('RESTORE', _ZOOM_RESTORE)
    subprocess.run(['node', '-e', script], check=True, timeout=10)


if __name__ == '__main__':
    if sys.argv[1:] == ['--self-test']:
        _self_test()
    else:
        raise SystemExit('Import reframe_same_answer with a caller OCR validator; --self-test is offline')
