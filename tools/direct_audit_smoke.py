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
    p.add_argument('--yokl-priority', action='store_true', help='Exact five YOKL keywords, three live platforms, isolated catalog')
    p.add_argument('--single-manifest', help='One explicit keyword for the combined cache evidence test')
    p.add_argument('--yokl-cache-followup', action='store_true', help='Four remaining Gemini keywords after the successful metered YOKL cache proof')
    p.add_argument('--pilot-manifest', help='Ten distinct Gemini keyword IDs; requires cache trial and UTC deadline')
    p.add_argument('--chatgpt-cache', action='store_true', help='Device104/v84 YOKL ChatGPT direct then one metered job')
    p.add_argument('--chatgpt-followup', action='store_true', help='Remaining four YOKL ChatGPT keywords after settled cheap first success')
    args=p.parse_args()
    if args.yokl_priority and (args.cache_trial or args.cache_evidence or args.pilot_manifest or args.rerun_manifest or not args.metered_output):
        p.error('YOKL priority requires metered output and forbids other trial modes')
    if args.cache_evidence and (not args.cache_trial or args.pilot_manifest or args.rerun_manifest):
        p.error('--cache-evidence requires --cache-trial and forbids multi-job modes')
    manifest=ROOT/'tools/ranking_one_reframe_0908.json'
    planned_jobs=1
    if args.chatgpt_followup and (not args.chatgpt_cache or not args.metered_output):
        p.error('ChatGPT follow-up requires ChatGPT cache and metered output')
    if args.chatgpt_cache:
        if any((args.cache_trial,args.cache_evidence,args.yokl_priority,args.yokl_cache_followup,args.single_manifest,args.rerun_manifest,args.pilot_manifest)):
            p.error('ChatGPT cache is a separate one-job mode')
        manifest=ROOT/'tools/yokl_one_cache_0909.json'
        if json.loads(manifest.read_text()) != [5221]:
            p.error('ChatGPT test requires YOKL keyword5221')
        if args.chatgpt_followup:
            from tools.yokl_delivery_gate import require_chatgpt_proof
            require_chatgpt_proof(ROOT)
            manifest=ROOT/'tools/yokl_remaining_cache_0909.json'
            if json.loads(manifest.read_text())!=[5222,5223,5224,5225]:
                p.error('ChatGPT follow-up manifest mismatch')
            planned_jobs=4
    if args.yokl_cache_followup:
        if not args.cache_trial or not args.cache_evidence or args.single_manifest or args.yokl_priority or args.rerun_manifest or args.pilot_manifest or not args.metered_output:
            p.error('YOKL cache follow-up requires combined cache mode only')
        prior=json.loads((ROOT/'yokl_cache_20260909_metered/report.json').read_text())
        rollback=json.loads((ROOT/'yokl_cache_20260909_direct_v2/report.json').read_text())
        leg=(prior.get('legs') or [{}])[0]
        if (prior.get('status')!='complete' or prior.get('keywords')!=[5221]
                or leg.get('successful_pairs')!=1 or not 0 < leg.get('used_mb',0) < 8
                or rollback.get('restored_health',{}).get('versionCode')!=79
                or rollback.get('restored_no_tun0') is not True or rollback.get('restore_error')):
            p.error('Successful cheap YOKL cache proof and rollback required')
        manifest=ROOT/'tools/yokl_remaining_cache_0909.json'
        if json.loads(manifest.read_text())!=[5222,5223,5224,5225]:
            p.error('YOKL remaining manifest mismatch')
        planned_jobs=4
    if args.single_manifest:
        if not args.cache_evidence or not args.cache_trial or args.yokl_priority or args.rerun_manifest or args.pilot_manifest:
            p.error('Single manifest requires combined cache evidence mode only')
        manifest=Path(args.single_manifest).resolve()
        ids=json.loads(manifest.read_text())
        if not isinstance(ids,list) or len(ids)!=1 or type(ids[0]) is not int or ids[0]<=0:
            p.error('Single manifest must contain one positive keyword ID')
    if args.yokl_priority:
        manifest=ROOT/'ranking_yokl_20260909/keywords.json'
        if json.loads(manifest.read_text()) != [5221,5222,5223,5224,5225]:
            p.error('YOKL manifest mismatch')
        planned_jobs=15
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
        if (args.rerun_manifest or args.yokl_priority) and report['candidate_health'].get('versionCode') != 83:
            raise RuntimeError('Four-row evidence repair requires verified candidate v83')
        print('Candidate installed on device104 only; direct network verified',flush=True)
        for cmd in [('keyevent','KEYCODE_WAKEUP'),('keyevent','KEYCODE_MENU'),('swipe','500','1600','500','400','300')]:adb('shell','input',*cmd)
        body={'type':'audit','platform':'gemini','bizName':'Carrot Software',
              'bizUrl':'https://maps.app.goo.gl/uvmmKU3ezTV1k9hP6','city':'Eugene','state':'OR',
              'searchAddress':'1310 Coburg Rd suite 10, Eugene, OR','keyword':'mobile app development',
              'genTimeoutSec':90,'async':True}
        if args.yokl_priority or args.chatgpt_cache:
            body.update(bizName='Yokl, Inc.',bizUrl='https://www.shopyokl.com/',city='Hershey',state='PA',
                        searchAddress='129 Cedar Avenue, Hershey, PA',keyword='food tours in Hershey PA')
        if args.chatgpt_cache:
            body['platform']='chatgpt'
            if args.chatgpt_followup:
                body['keyword']='Hershey trolley tours'
        if args.request_json:
            body=json.loads(Path(args.request_json).read_text())
            if body.get('type') != 'audit' or body.get('platform') != ('chatgpt' if args.chatgpt_cache else 'gemini') or body.get('geminiCachePrepared') or body.get('chatgptCachePrepared'):
                raise RuntimeError('Request must be a normal Gemini audit without cache overrides')
            body['async']=True
            body['genTimeoutSec']=min(int(body.get('genTimeoutSec',90)),150)
        if args.cache_trial or args.chatgpt_cache:
            from tools.cache_evidence_policy import cache_health_allowed
            health=report['candidate_health']
            allowed=(type(health.get('versionCode')) is int and health['versionCode']==84 and health.get('accessibility') is True) if args.chatgpt_cache else cache_health_allowed(health,args.cache_evidence)
            if not allowed:
                raise RuntimeError('Cache experiment requires matching accessible APK (82 legacy / 83 evidence)')
            from tools.gemini_cache_reset import prepare_gemini_cache, prepare_chatgpt_cache
            # Installing/rebinding the agent brings its UI forward. Chrome's
            # Android debugger exposes no page targets while it is backgrounded.
            # Bring the existing browser task forward; do not navigate a URL.
            adb('shell', 'am', 'start', '-n', 'com.android.chrome/com.google.android.apps.chrome.Main')
            time.sleep(1)
            flags = {'RANK_GEMINI_CACHE_TRIAL': '1', 'RANK_SINGLE_ATTEMPT': '1'}
            if args.chatgpt_cache:
                flags={'RANK_CHATGPT_CACHE_TRIAL':'1','RANK_SINGLE_ATTEMPT':'1'}
            previous = {key: os.environ.get(key) for key in flags}
            try:
                os.environ.update(flags)
                prepared = prepare_chatgpt_cache(serial) if args.chatgpt_cache else prepare_gemini_cache(serial)
            finally:
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
            (out/'cache_prepared.json').write_text(json.dumps(prepared, indent=2))
            if not prepared.get('ok'):
                raise RuntimeError('Direct cache preparation failed')
            body['chatgptCachePrepared' if args.chatgpt_cache else 'geminiCachePrepared'] = True
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
        pr=(result.get('platforms') or {}).get(body['platform'],{})
        if pr.get('screenshot_b64'):(out/'app.png').write_bytes(base64.b64decode(pr['screenshot_b64']))
        (out/'last_screen.png').write_bytes(adb('exec-out','screencap','-p'))
        report.update(status='complete',elapsed_s=round(time.monotonic()-started,2),
                      result_status=pr.get('status'),error=pr.get('error'),steps=result.get('step_log'))
        if args.cache_evidence or args.yokl_priority or args.chatgpt_cache:
            from tools.direct_evidence_gate import validate_direct_answer
            evidence = validate_direct_answer(serial, body['keyword'], pr, out, platform=body['platform'])
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
            if args.chatgpt_cache:
                env.update(COST_CHATGPT_CACHE='1', COST_PHASE_TELEMETRY='1',
                           RANK_CATALOG_DIR=str(ROOT/'ranking_yokl_20260909/catalog'))
                if args.chatgpt_followup:
                    env['COST_CHATGPT_FOLLOWUP']='1'
            if args.rerun_manifest:
                env.update(COST_DRIVER='rerun_four', COST_PROMPT_FREE='1', COST_PHASE_TELEMETRY='1')
            if args.cache_trial:
                env.update(COST_CACHE_TRIAL='1', COST_PHASE_TELEMETRY='1')
            if args.cache_evidence:
                env.update(COST_CACHE_EVIDENCE='1', COST_PROMPT_FREE='1')
            if args.yokl_cache_followup:
                env['COST_DRIVER']='yokl_cache_followup'
                env['RANK_CATALOG_DIR']=str(ROOT/'ranking_yokl_20260909/catalog')
            if args.yokl_priority:
                env.update(COST_DRIVER='yokl_priority', COST_PHASE_TELEMETRY='1',
                           RANK_CATALOG_DIR=str(ROOT/'ranking_yokl_20260909/catalog'))
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
