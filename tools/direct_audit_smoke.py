"""One device-104 direct-network audit smoke test, restoring its backed-up APK."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',required=True)
    p.add_argument('--request-json', help='Explicit direct Gemini audit request; never a paid ranking result')
    p.add_argument('--rerun-manifest', help='Exactly four Gemini IDs; requires --metered-output, no cache trial')
    p.add_argument('--metered-output', help='After direct success only, run one isolated paid job and restore APK')
    p.add_argument('--cache-trial', action='store_true', help='Verify host-prepared v82 cache reset on device104')
    p.add_argument('--cache-evidence', action='store_true', help='Opt-in v83 cache + prompt-free validation; one paid job maximum')
    p.add_argument('--pilot-manifest', help='Ten distinct Gemini keyword IDs; requires cache trial and UTC deadline')
    args=p.parse_args()
    if args.cache_evidence and (not args.cache_trial or args.pilot_manifest or args.rerun_manifest):
        p.error('--cache-evidence requires --cache-trial and forbids multi-job modes')
    manifest=ROOT/'tools/ranking_one_reframe_0908.json'
    planned_jobs=1
    if args.rerun_manifest:
        if not args.metered_output or args.cache_trial or args.pilot_manifest:
            p.error('Four-job rerun requires metered output and no cache/pilot mode')
        manifest=Path(args.rerun_manifest).resolve()
        ids=json.loads(manifest.read_text())
        if not isinstance(ids,list) or len(ids)!=4 or any(type(k) is not int or k<=0 for k in ids) or len(set(ids))!=4:
            p.error('Rerun requires exactly four distinct positive keyword IDs')
        planned_jobs=4
    if args.pilot_manifest:
        import datetime
        if not args.cache_trial or not args.metered_output:
            p.error('Pilot requires --cache-trial and --metered-output')
        manifest=Path(args.pilot_manifest).resolve()
        ids=json.loads(manifest.read_text())
        if not isinstance(ids,list) or len(ids)!=10 or any(type(k) is not int or k<=0 for k in ids) or len(set(ids))!=10:
            p.error('Pilot requires ten distinct positive integer IDs')
        deadline=datetime.datetime.fromisoformat(os.environ.get('COST_DEADLINE_UTC','').replace('Z','+00:00'))
        if deadline.utcoffset()!=datetime.timedelta(0) or deadline.timestamp()-time.time()<900:
            p.error('Pilot needs a UTC deadline at least 15 minutes away')
        planned_jobs=10
    out=Path(args.output).resolve(); out.mkdir(exist_ok=False)
    original=ROOT/'direct_ui_20260908_apk/device104-original-v79.apk'
    candidate=ROOT/'app/build/outputs/apk/debug/app-debug.apk'
    if not original.exists() or not candidate.exists(): raise RuntimeError('Missing rollback or candidate APK')
    names=subprocess.check_output(['ps','-axo','comm='],text=True)
    if any(Path(x.strip()).name=='gost' for x in names.splitlines()): raise RuntimeError('Proxy running')
    rows=subprocess.check_output(['adb','devices'],text=True).splitlines()
    serials=[x.split('\t')[0] for x in rows if '149145555W002883' in x and x.endswith('\tdevice')]
    if len(serials)!=1: raise RuntimeError('Ambiguous phone')
    serial=serials[0]
    def adb(*cmd):
        return subprocess.check_output(['adb','-s',serial,*cmd],timeout=60)
    lock=Path('/tmp/fleet.lock')
    with lock.open('x') as f:f.write(f'{os.getpid()} direct-audit-smoke\n')
    port=None; changed=False
    report={'status':'starting','device':'device-104','proxy_started':False,'jobs':0}
    def request(path,body=None):
        data=json.dumps(body).encode() if body is not None else None
        req=urllib.request.Request(f'http://127.0.0.1:{port}/{path}',data=data,
                                   headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
    def rebind():
        service='com.deviceagent/com.deviceagent.AgentAccessibilityService'
        old=adb('shell','settings','get','secure','enabled_accessibility_services').decode().strip()
        others=[x for x in old.split(':') if x and x not in ('null',service)]
        adb('shell','am','force-stop','com.deviceagent')
        adb('shell','am','start','-n','com.deviceagent/.MainActivity')
        for attempt in range(5):
            if others:
                adb('shell','settings','put','secure','enabled_accessibility_services',':'.join(others))
            else:
                adb('shell','settings','delete','secure','enabled_accessibility_services')
            time.sleep(.5)
            adb('shell','settings','put','secure','enabled_accessibility_services',':'.join(others+[service]))
            adb('shell','settings','put','secure','accessibility_enabled','1')
            time.sleep(2)
            try:return request('health')
            except Exception:pass
        raise RuntimeError('Accessibility/HTTP rebind failed')
    try:
        port=int(adb('forward','tcp:0','tcp:8765').strip())
        if request('result').get('running'): raise RuntimeError('Phone busy')
        adb('shell','pm','clear','net.typeblog.socks');time.sleep(2)
        if re.search(r'^\d+: tun0(?:[@:])',adb('shell','ip','addr').decode(),re.M):raise RuntimeError('VPN remains')
        if adb('shell','settings','get','global','http_proxy').decode().strip() not in ('null',':0',''):raise RuntimeError('HTTP proxy configured')
        report['before_health']=request('health')
        changed=True
        adb('install','-r',str(candidate))
        report['candidate_health']=rebind()
        if args.rerun_manifest and report['candidate_health'].get('versionCode') != 83:
            raise RuntimeError('Four-row evidence repair requires verified candidate v83')
        print('Candidate installed on device104 only; direct network verified',flush=True)
        for cmd in [('keyevent','KEYCODE_WAKEUP'),('keyevent','KEYCODE_MENU'),('swipe','500','1600','500','400','300')]:adb('shell','input',*cmd)
        body={'type':'audit','platform':'gemini','bizName':'Carrot Software',
              'bizUrl':'https://maps.app.goo.gl/uvmmKU3ezTV1k9hP6','city':'Eugene','state':'OR',
              'searchAddress':'1310 Coburg Rd suite 10, Eugene, OR','keyword':'mobile app development',
              'genTimeoutSec':90,'async':True}
        if args.request_json:
            body=json.loads(Path(args.request_json).read_text())
            if body.get('type') != 'audit' or body.get('platform') != 'gemini' or body.get('geminiCachePrepared'):
                raise RuntimeError('Request must be a normal Gemini audit without cache overrides')
            body['async']=True
            body['genTimeoutSec']=min(int(body.get('genTimeoutSec',90)),150)
        if args.cache_trial:
            from tools.cache_evidence_policy import cache_health_allowed
            if not cache_health_allowed(report['candidate_health'], args.cache_evidence):
                raise RuntimeError('Cache experiment requires matching accessible APK (82 legacy / 83 evidence)')
            from tools.gemini_cache_reset import prepare_gemini_cache
            # Installing/rebinding the agent brings its UI forward. Chrome's
            # Android debugger exposes no page targets while it is backgrounded.
            # Bring the existing browser task forward; do not navigate a URL.
            adb('shell', 'am', 'start', '-n', 'com.android.chrome/com.google.android.apps.chrome.Main')
            time.sleep(1)
            flags = {'RANK_GEMINI_CACHE_TRIAL': '1', 'RANK_SINGLE_ATTEMPT': '1'}
            previous = {key: os.environ.get(key) for key in flags}
            try:
                os.environ.update(flags)
                prepared = prepare_gemini_cache(serial)
            finally:
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
            (out/'cache_prepared.json').write_text(json.dumps(prepared, indent=2))
            if not prepared.get('ok'):
                raise RuntimeError('Direct cache preparation failed')
            body['geminiCachePrepared'] = True
        (out/'request.json').write_text(json.dumps(body,indent=2))
        started=time.monotonic();ack=request('session',body);report['jobs']=1
        result=ack
        if ack.get('async'):
            while time.monotonic()-started<300:
                time.sleep(5);result=request('result')
                print('Direct audit elapsed',round(time.monotonic()-started),'running',result.get('running'),flush=True)
                if not result.get('running'):break
            else:raise RuntimeError('Owned direct audit exceeded 300 seconds')
        (out/'response.json').write_text(json.dumps(result,indent=2))
        pr=(result.get('platforms') or {}).get('gemini',{})
        if pr.get('screenshot_b64'):(out/'app.png').write_bytes(base64.b64decode(pr['screenshot_b64']))
        (out/'last_screen.png').write_bytes(adb('exec-out','screencap','-p'))
        report.update(status='complete',elapsed_s=round(time.monotonic()-started,2),
                      result_status=pr.get('status'),error=pr.get('error'),steps=result.get('step_log'))
        if args.cache_evidence:
            from tools.direct_evidence_gate import validate_direct_answer
            evidence = validate_direct_answer(serial, body['keyword'], pr, out)
            report['direct_evidence'] = evidence
            if not evidence.get('ok'):
                raise RuntimeError('Direct answer/capture evidence failed; refusing paid job')
        if args.metered_output:
            if pr.get('status') not in ('success', 'completed') or pr.get('error'):
                raise RuntimeError('Direct smoke failed; refusing paid job')
            # The ranking launcher owns the same fleet mutex during its job.
            # Release our idle-phone lock before handing control to that launcher.
            if lock.read_text().split()[0] != str(os.getpid()):
                raise RuntimeError('Lost direct-test fleet lock')
            lock.unlink()
            env=os.environ.copy();env['COST_DRIVER']='cache_pilot' if args.pilot_manifest else 'reframe_single'
            if args.rerun_manifest:
                env.update(COST_DRIVER='rerun_four', COST_PROMPT_FREE='1', COST_PHASE_TELEMETRY='1')
            if args.cache_trial:
                env.update(COST_CACHE_TRIAL='1', COST_PHASE_TELEMETRY='1')
            if args.cache_evidence:
                env.update(COST_CACHE_EVIDENCE='1', COST_PROMPT_FREE='1')
            print(f'Direct passed; starting {planned_jobs} metered jobs, no retries',flush=True)
            completed=subprocess.run(['bash',str(ROOT/'tools/run_ranking_cost_pair.sh'),
                str(manifest),args.metered_output],
                cwd=ROOT,env=env)
            report['metered_exit_code']=completed.returncode
            report['metered_output']=args.metered_output
            report['proxy_started']=True
            report['planned_metered_jobs']=planned_jobs
            meter_report=Path(args.metered_output)/'report.json'
            if meter_report.exists():
                measured=json.loads(meter_report.read_text())
                report['metered_status']=measured.get('status')
                report['jobs']=1+sum(x.get('completed_rows',0) for x in measured.get('legs',[]))
                report['metered_successful_pairs']=sum(x.get('successful_pairs',0)
                    for x in measured.get('legs',[]))
            with lock.open('x') as f:f.write(f'{os.getpid()} direct-audit-restore\n')
            if completed.returncode:
                raise RuntimeError('Metered supervisor failed; inspect its report')
    except Exception as error:
        report.update(status='error',error=str(error))
        raise
    finally:
        try:
            if changed:
                if not lock.exists() or lock.read_text().split()[0] != str(os.getpid()):
                    raise RuntimeError('No owned fleet lock for safe APK restoration')
                # The ranking dispatcher rebuilds ADB forwards, invalidating our
                # pre-test HTTP port. Obtain a fresh owned forward for rollback.
                port=int(adb('forward','tcp:0','tcp:8765').strip())
                adb('shell','am','force-stop','net.typeblog.socks')
                adb('shell','pm','clear','net.typeblog.socks')
                adb('install','-r','-d',str(original))
                report['restored_health']=rebind()
                report['restored_no_tun0']=not bool(re.search(r'^\d+: tun0(?:[@:])',
                    adb('shell','ip','addr').decode(),re.M))
                print('Original APK restored on device104',flush=True)
        except Exception as error:
            report['restore_error']=str(error)
        finally:
            (out/'report.json').write_text(json.dumps(report,indent=2))
            if port:adb('forward','--remove',f'tcp:{port}')
            if lock.exists() and lock.read_text().split()[0]==str(os.getpid()):lock.unlink()
    print(json.dumps({k:report[k] for k in ('status','result_status','error') if k in report}),flush=True)

if __name__=='__main__':main()
