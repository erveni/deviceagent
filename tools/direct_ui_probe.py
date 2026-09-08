"""Inspect one idle phone on its normal connection; never starts a proxy/job."""
import argparse
import base64
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', required=True)
    p.add_argument('--frame', action='store_true')
    p.add_argument('--validated-frame', action='store_true')
    p.add_argument('--expected-rank', nargs=2, type=int, default=[4,4])
    p.add_argument('--page-scale', type=float, help='Direct-only browser zoom probe; reset on exit')
    p.add_argument('--answer-zoom', type=float, help='Direct-only answer layout zoom; restored on exit')
    p.add_argument('--dispatch-replay', help='Replay early capture block against a saved response, never dispatch')
    p.add_argument('--no-front', action='store_true', help='Do not wake or bring Chrome foreground')
    args = p.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(exist_ok=False)
    processes = subprocess.check_output(['ps', '-axo', 'comm='], text=True)
    if any(Path(x.strip()).name == 'gost' for x in processes.splitlines()):
        raise RuntimeError('A proxy is running; refusing phone actions')
    online = subprocess.check_output(['adb', 'devices'], text=True)
    serials = [s.split('\t')[0] for s in online.splitlines()
               if '149145555W002883' in s and s.endswith('\tdevice')]
    if len(serials) != 1:
        raise RuntimeError('device-104 must resolve to exactly one online serial')
    serial = serials[0]
    def adb(*cmd):
        return subprocess.check_output(['adb', '-s', serial, *cmd], timeout=20)
    lock = Path('/tmp/fleet.lock')
    with lock.open('x') as f:
        f.write(f'{os.getpid()} direct-ui-device104\n')
    port = None
    try:
        port = int(adb('forward', 'tcp:0', 'tcp:8765').strip())
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/result', timeout=5) as r:
            result = json.load(r)
        if result.get('running'):
            raise RuntimeError('Phone has an in-flight session')
        (out/'last_result.json').write_text(json.dumps(result,indent=2))
        adb('shell', 'am', 'force-stop', 'net.typeblog.socks')
        adb('shell', 'pm', 'clear', 'net.typeblog.socks')
        time.sleep(2)
        interfaces = adb('shell', 'ip', 'addr').decode()
        if re.search(r'^\d+: tun0(?:[@:])', interfaces, re.M):
            raise RuntimeError('VPN tunnel remains; refusing direct test')
        proxy = adb('shell', 'settings', 'get', 'global', 'http_proxy').decode().strip()
        if proxy not in ('null', ':0', ''):
            raise RuntimeError('System HTTP proxy is configured')
        if not args.no_front:
            for cmd in [('keyevent', 'KEYCODE_WAKEUP'), ('keyevent', 'KEYCODE_MENU'),
                        ('swipe', '500', '1600', '500', '400', '300')]:
                adb('shell', 'input', *cmd)
            adb('shell', 'am', 'start', '-n', 'com.android.chrome/com.google.android.apps.chrome.Main')
        time.sleep(2)
        os.environ['CDP_PORT'] = '19991'
        from gemini_cdp_capture import CDP
        sockets = re.findall(r'@(chrome_devtools_remote[^\s]*)', adb('shell', 'cat', '/proc/net/unix').decode())
        tabs = []
        for socket in sorted(set(sockets), reverse=True):
            adb('forward', 'tcp:19991', 'localabstract:' + socket)
            try:
                with urllib.request.urlopen('http://127.0.0.1:19991/json', timeout=3) as r:
                    tabs = json.load(r)
                if tabs:
                    break
            except Exception:
                continue
        pages = [t for t in tabs if t.get('type') == 'page' and 'gemini.google.com' in t.get('url', '')]
        if not pages:
            raise RuntimeError('No existing Gemini tab; no navigation performed')
        c = CDP(pages[0]['webSocketDebuggerUrl'])
        old_answer_zoom = None
        try:
            if args.page_scale is not None:
                if not .5 <= args.page_scale <= 1:
                    raise ValueError('Direct page scale must be .5..1')
                zoom=c.call('Emulation.setPageScaleFactor', {'pageScaleFactor':args.page_scale})
                (out/'zoom.json').write_text(json.dumps(zoom,indent=2))
            if args.answer_zoom is not None:
                if not .5 <= args.answer_zoom <= 1:
                    raise ValueError('Answer zoom must be .5..1')
                zexpr="""(()=>{const es=[...document.querySelectorAll('model-response message-content')];
                  if(es.length!==1)throw Error('ambiguous answer');const e=es[0];
                  const old=e.style.zoom;e.style.zoom=%s;return old;})()""" % json.dumps(str(args.answer_zoom))
                old_answer_zoom=c.call('Runtime.evaluate', {'expression':zexpr,'returnByValue':True})['result']['result']['value']
            expression = """JSON.stringify({title:document.title,text:document.body.innerText,
              rank_markup:[...document.querySelectorAll('model-response message-content p')].filter(e=>/\\[RANK:/i.test(e.textContent)).map(e=>e.outerHTML),
              overlays:[...document.querySelectorAll('*')].filter(e=>e.childElementCount===0 && (e.textContent||'').includes('Sign in to connect to Google apps')).map(e=>{const a=[];for(let i=0;e&&i<6;i++,e=e.parentElement)a.push({tag:e.tagName,cls:e.className,pos:getComputedStyle(e).position,rect:e.getBoundingClientRect().toJSON()});return a}),
              elements:[...document.querySelectorAll('model-response,message-content,.markdown,ol,[role=dialog]')].map(e=>({tag:e.tagName,cls:e.className,text:e.innerText,rect:e.getBoundingClientRect().toJSON()}))})"""
            response = c.call('Runtime.evaluate', {'expression':expression, 'returnByValue':True})
            (out/'dom.json').write_text(response['result']['result']['value'])
            (out/'before.png').write_bytes(adb('exec-out', 'screencap', '-p'))
            if args.validated_frame:
                import ast
                from tools.gemini_same_answer_reframe import reframe_same_answer
                tree=ast.parse((ROOT/'audit_dispatch_http.py').read_text())
                fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_screenshot_has_answer')
                ns={'os':os,'re':re,'subprocess':subprocess,'_OCR_WARNED':False,
                    '_OCR_BIN':str(ROOT/'tools/ocr_vision'),
                    '_WALL_RE':re.compile(r'verify you are human|not a robot|captcha|just a moment|press & hold',re.I),
                    '_ANSWER_RE':re.compile(r'rank:\s*\d+\s*/\s*\d+|\[rank|google maps|maps:\s*(yes|no)',re.I)}
                exec(compile(ast.Module(body=[fn],type_ignores=[]),'production-ocr-gate','exec'),ns)
                if args.dispatch_replay:
                    from datetime import datetime, timezone
                    defs={'_classify','_write_b64_screenshot','_parse_rank_markers','_rank_inconsistent','_keyword_text',
                          '_recover_rank_via_ocr','_screenshot_has_expected_rank'}
                    ns.update(base64=base64,Path=Path,datetime=datetime,timezone=timezone,time=time,
                        AUDIT_RESULTS_DIR=str(out),_OCR_RANK_RE=re.compile(r'\[?rank:\s*(\d+)\s*/\s*(\d+\+?)\]?',re.I),
                        _OCR_EG_RE=re.compile(r'(?:e\s*\.\s*g\s*\.?|->|\u2192)\s*[\(\[]?\s*$',re.I),_OCR_EG_LOOKBACK=24)
                    exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in defs],type_ignores=[]),'capture-functions','exec'),ns)
                    saved=json.loads(Path(args.dispatch_replay).read_text())
                    status,_,_,_,_,b64=ns['_classify'](saved,'gemini')
                    ns.update(response=saved,status=status,ss_b64=b64,ss_local='',capture_prompt=None,
                        serial=serial,keyword_id=64,platform='gemini',started=datetime.now(timezone.utc),
                        entry={'biz_name':'Carrot Software','keywords':[{'keyword_id':64,'keyword':'mobile app development'}]},
                        _answer_ok=ns['_screenshot_has_answer'])
                    dispatch=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='dispatch_audit_job')
                    early=next(n for n in ast.walk(dispatch) if isinstance(n,ast.If) and any(
                        isinstance(x,ast.Name) and x.id=='_early_text' for s in n.body for x in ast.walk(s)))
                    prior=os.environ.get('RANK_GEMINI_SAME_ANSWER_REFRAME')
                    os.environ['RANK_GEMINI_SAME_ANSWER_REFRAME']='1'
                    try:exec(compile(ast.Module(body=[early],type_ignores=[]),'production-early-reframe','exec'),ns)
                    finally:
                        if prior is None:os.environ.pop('RANK_GEMINI_SAME_ANSWER_REFRAME',None)
                        else:os.environ['RANK_GEMINI_SAME_ANSWER_REFRAME']=prior
                    evidence=ns.get('_early_result',{'ok':False,'reason':'early_reframe_not_invoked'})
                    evidence['production_early_block_replayed']=True
                else:
                    evidence=reframe_same_answer(serial,'mobile app development',tuple(args.expected_rank),out/'validated_rank.png',
                                                 ocr_validator=lambda path: ns['_screenshot_has_answer'](path, strict=True))
                (out/'validated_frame.json').write_text(json.dumps(evidence,indent=2))
                print('Validated frame:',evidence,flush=True)
            if args.frame:
                expr = """(()=>{const e=[...document.querySelectorAll('model-response message-content')].pop();
                  if(!e || !/\\[RANK:\\s*\\d+\\/\\d+\\]/i.test(e.innerText)) return null;
                  const r=e.getBoundingClientRect();return {text:e.innerText,x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height};})()"""
                original = c.call('Runtime.evaluate', {'expression':expr,'returnByValue':True})['result']['result'].get('value')
                if not original:
                    raise RuntimeError('No answer-scoped numeric rank; refusing capture')
                shot = c.call('Page.captureScreenshot', {'format':'png','captureBeyondViewport':True,
                    'clip':{k:original[k] for k in ('x','y','width','height')} | {'scale':1}})
                (out/'answer_full.png').write_bytes(base64.b64decode(shot['result']['data']))
                c.call('Page.bringToFront')
                scroll_rank = """(()=>{const e=[...document.querySelectorAll('model-response message-content')].pop();
                  const n=e && [...e.querySelectorAll('*')].find(x=>x.childElementCount===0 && /\\[RANK:\\s*\\d+\\/\\d+\\]/i.test(x.textContent));
                  if(!n)return false;n.scrollIntoView({block:'center',behavior:'instant'});return true;})()"""
                positioned = c.call('Runtime.evaluate', {'expression':scroll_rank,'returnByValue':True})['result']['result'].get('value')
                time.sleep(1)
                (out/'rank_visible.png').write_bytes(adb('exec-out','screencap','-p'))
                after = c.call('Runtime.evaluate', {'expression':expr,'returnByValue':True})['result']['result'].get('value')
                (out/'frame.json').write_text(json.dumps({'before':original,'after':after,
                    'response_unchanged':bool(after and after['text']==original['text']),
                    'new_prompts':0,'reloads':0,'rank_node_found':positioned},indent=2))
            (out/'report.json').write_text(json.dumps({'device':'device-104', 'serial':serial,
                'no_tun0':True,'system_http_proxy':proxy,'new_jobs':0,'proxy_started':False},indent=2))
            print('Saved direct idle UI evidence:',out)
        finally:
            if old_answer_zoom is not None:
                c.call('Runtime.evaluate', {'expression':
                    "document.querySelector('model-response message-content').style.zoom="+json.dumps(old_answer_zoom)})
            if args.page_scale is not None:
                c.call('Emulation.resetPageScaleFactor')
            c.close()
    finally:
        if port:
            adb('forward', '--remove', f'tcp:{port}')
        try:
            adb('forward', '--remove', 'tcp:19991')
        except subprocess.CalledProcessError:
            pass
        if lock.exists() and lock.read_text().split()[0] == str(os.getpid()):
            lock.unlink()

if __name__ == '__main__':
    main()
