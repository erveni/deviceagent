"""One isolated Edge-cache measurement on104, with original APK restoration."""
import json
import hashlib
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.copilot_bootstrap_scope import selected_device


def main():
    os.chdir(ROOT)
    bootstrap=os.environ.get('COPILOT_BOOTSTRAP_TRIAL')=='1'
    confirm=os.environ.get('COPILOT_BOOTSTRAP_CONFIRM')=='1'
    observe=os.environ.get('COPILOT_TRAFFIC_CONFIRM')=='1'
    wifi_settle=os.environ.get('COPILOT_BOOTSTRAP_SETTLE')=='1'
    wifi_confirm=os.environ.get('COPILOT_WIFI_CONFIRM')=='1'
    device,hardware=selected_device()
    rollout=device!='device-104'
    if rollout and not (bootstrap and confirm and observe and wifi_settle):
        raise RuntimeError('Second-phone rollout requires the measured WiFi-settled bootstrap')
    if wifi_confirm and not wifi_settle:raise RuntimeError('WiFi confirmation requires settlement mode')
    if wifi_settle and not observe:raise RuntimeError('WiFi settlement requires traced confirmation')
    if observe and not confirm:raise RuntimeError('Traffic confirmation requires automatic bootstrap')
    if confirm and not bootstrap:raise RuntimeError('Confirmation requires bootstrap mode')
    prefix=('copilot_bootstrap_auto_20260910' if confirm else 'copilot_bootstrap_one_20260910') if bootstrap else 'copilot_cache_one_20260910_v5'
    if observe:prefix='copilot_bootstrap_trace_20260910'
    if wifi_settle:prefix='copilot_bootstrap_wifi_20260910'
    if wifi_confirm:prefix='copilot_bootstrap_wifi_confirm_20260910'
    if rollout:
        attempt=os.environ.get('COPILOT_ROLLOUT_ATTEMPT','1')
        if not re.fullmatch(r'[1-9][0-9]*',attempt):raise ValueError('Invalid rollout attempt')
        prefix='copilot_bootstrap_wifi_20260910_'+device+('_attempt'+attempt if attempt!='1' else '')
    out=ROOT/(prefix+'_wrapper')
    out.mkdir(exist_ok=False)
    meter=ROOT/(prefix+'_metered')
    if meter.exists():raise RuntimeError('Measurement already exists')
    original=ROOT/'direct_ui_20260908_apk/device104-original-v79.apk'
    if rollout:original=out/'original-v79.apk'
    candidate=ROOT/'app/build/outputs/apk/debug/app-debug.apk'
    if (not rollout and not original.is_file()) or not candidate.is_file():raise RuntimeError('Missing APK/rollback')
    names=subprocess.check_output(['ps','-axo','comm='],text=True)
    if any(Path(x.strip()).name=='gost' for x in names.splitlines()):raise RuntimeError('Proxy active')
    serials=[r.split('\t')[0] for r in subprocess.check_output(['adb','devices'],text=True).splitlines()
             if hardware in r and r.endswith('\tdevice')]
    if len(serials)!=1:raise RuntimeError('Ambiguous104')
    serial=serials[0]
    def adb(*args):return subprocess.check_output(['adb','-s',serial,*args],timeout=60).decode()
    lock=Path('/tmp/fleet.lock')
    def acquire():
        with lock.open('x') as stream:stream.write(f'{os.getpid()} copilot-cache-trial\n')
    def owned():return lock.exists() and lock.read_text().split()[0]==str(os.getpid())
    acquire()
    report={'status':'starting','measurement_only':True,'device':device,
            'candidate_sha256':hashlib.sha256(candidate.read_bytes()).hexdigest()}
    changed=False
    port=int(adb('forward','tcp:0','tcp:8765').strip())
    def request(path,body=None):
        req=urllib.request.Request(f'http://127.0.0.1:{port}/{path}',
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=10) as r:return json.load(r)
    def rebind():
        service='com.deviceagent/com.deviceagent.AgentAccessibilityService'
        old=adb('shell','settings','get','secure','enabled_accessibility_services').strip()
        others=[x for x in old.split(':') if x and x not in ('null',service)]
        adb('shell','am','force-stop','com.deviceagent')
        adb('shell','am','start','-n','com.deviceagent/.MainActivity')
        if others:adb('shell','settings','put','secure','enabled_accessibility_services',':'.join(others))
        else:adb('shell','settings','delete','secure','enabled_accessibility_services')
        time.sleep(.5)
        adb('shell','settings','put','secure','enabled_accessibility_services',':'.join(others+[service]))
        adb('shell','settings','put','secure','accessibility_enabled','1')
        last_error=None
        for attempt in range(5):
            time.sleep(3)
            try:
                health=request('health')
                if health.get('accessibility') is True:return health
            except Exception as error:last_error=error
            adb('shell','settings','put','secure','enabled_accessibility_services',':'.join(others+[service]))
            adb('shell','settings','put','secure','accessibility_enabled','1')
        raise RuntimeError('Agent/accessibility did not become ready after five polls') from last_error
    try:
        if request('result').get('running'):raise RuntimeError('Phone busy')
        if request('health').get('versionCode')!=79:raise RuntimeError('Expected original79')
        if rollout:
            # Exclusive fleet lock + no gost + native idle were checked above.
            # Disconnect only stale SocksDroid, never another VPN app.
            adb('shell','am','force-stop','net.typeblog.socks')
            time.sleep(1)
        if re.search(r'^\d+: tun0(?:[@:])',adb('shell','ip','link'),re.M):raise RuntimeError('VPN active')
        for command in [('keyevent','KEYCODE_WAKEUP'),('keyevent','KEYCODE_MENU'),
                        ('swipe','500','1600','500','400','300')]:
            adb('shell','input',*command)
        if rollout:
            apk_paths=[line.removeprefix('package:').strip() for line in adb('shell','pm','path','com.deviceagent').splitlines() if line.startswith('package:')]
            if len(apk_paths)!=1:raise RuntimeError('Ambiguous original APK backup')
            adb('pull',apk_paths[0],str(original))
            if not original.is_file() or original.stat().st_size<100000:raise RuntimeError('Original APK backup missing')
        changed=True
        adb('install','-r',str(candidate))
        report['candidate_health']=rebind()
        expected_version=(87 if os.environ.get('COPILOT_NETWORK_GUARD_TRIAL')=='1' else 86) if bootstrap else 85
        if report['candidate_health'].get('versionCode')!=expected_version or report['candidate_health'].get('accessibility') is not True:
            raise RuntimeError('Matching candidate unavailable')
        if bootstrap:
            if adb('shell','pm','clear','com.microsoft.emmx').strip()!='Success':
                raise RuntimeError('Offline full Edge data clear failed')
        adb('shell','am','force-stop','com.microsoft.emmx')
        adb('shell','am','start','-n','com.microsoft.emmx/com.microsoft.ruby.Main')
        time.sleep(3)
        request('session',dict(type='audit',platform='copilot',bizName='Yokl, Inc.',
            bizUrl='https://www.shopyokl.com/',city='Hershey',state='PA',keyword='private group tours in Hershey PA',
            copilotCacheTrial=not bootstrap,copilotCacheResetOnly=True,**{'async':True}))
        print('Offline reset-only readiness running; no AI prompt or proxy',flush=True)
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            time.sleep(2)
            readiness=request('result')
            if not readiness.get('running'):break
        else:raise RuntimeError('Offline reset readiness timed out')
        report['offline_reset_steps']=readiness.get('step_log',[])
        if (not any('[copilot] reset_edge OK' in s for s in report['offline_reset_steps'])
                or any('[copilot] submit' in s or '[copilot] input' in s for s in report['offline_reset_steps'])):
            raise RuntimeError('Offline reset readiness failed; refusing paid test')
        print('Offline reset-only readiness PASSED',flush=True)
        if bootstrap:
            receipt=out/'edge_ready.json'
            receipt.write_text(json.dumps(dict(status='full_reset_ready',at=time.time(),serial=serial,
                keyword_id=5225,proxy_connected=False,prompts_submitted=0,steps=report['offline_reset_steps']),indent=2))
        if not owned():raise RuntimeError('Lost preparation lock')
        lock.unlink()
        env=os.environ.copy()
        env.update(COST_DRIVER='reframe_single',COST_YOKL_COPILOT='1',COST_COPILOT_CACHE='1',
                   COST_COPILOT_ZIP_FIRST='1',COST_COPILOT_NOTIFICATION_DENY='1',COST_PHASE_TELEMETRY='1',
                   RANK_CATALOG_DIR=str(ROOT/'ranking_yokl_20260909/catalog'))
        env['COST_SETTLED_BASELINE_REPORT']=str(ROOT/'copilot_cache_one_20260910_v4_metered/report.json')
        if bootstrap:
            env.update(COST_COPILOT_CACHE='0',COST_COPILOT_BOOTSTRAP='1',COST_COPILOT_EDGE_RECEIPT=str(receipt),
                COST_SETTLED_BASELINE_REPORT=str(ROOT/('copilot_bootstrap_one_20260910_metered/report.json' if confirm else 'copilot_cache_one_20260910_v5_metered/report.json')))
            if confirm:env['COST_COPILOT_INLINE']='1'
            if observe:
                env.update(RANK_COPILOT_TRAFFIC_OBSERVER='1',USE_SNI_RELAY='0')
                # Fresh settlement; the previous run may no longer be within15min.
                env.pop('COST_SETTLED_BASELINE_REPORT',None)
            if wifi_settle:
                env.update(RANK_COPILOT_WIFI_SETTLE='1',
                    COST_SETTLED_BASELINE_REPORT=str(ROOT/'copilot_bootstrap_trace_20260910_metered/report.json'))
            if wifi_confirm:
                env['COST_SETTLED_BASELINE_REPORT']=str(ROOT/'copilot_bootstrap_wifi_20260910_metered/report.json')
            if rollout:
                # Other-phone trials establish a fresh baseline; the old104
                # comparison is documentation, not a reusable live meter read.
                env.pop('COST_SETTLED_BASELINE_REPORT',None)
                if os.environ.get('COPILOT_NETWORK_GUARD_TRIAL')=='1':
                    env['COST_SETTLED_BASELINE_REPORT']=str(ROOT/'copilot_bootstrap_wifi_20260910_device-106_attempt4_metered/report.json')
        print('Starting ONE cache measurement; not a YOKL report replacement',flush=True)
        completed=subprocess.run(['bash',str(ROOT/'tools/run_ranking_cost_pair.sh'),
            str(ROOT/'tools/yokl_copilot_final_retry_0910.json'),str(meter)],env=env)
        acquire()
        report['meter_exit_code']=completed.returncode
        report['status']='complete' if completed.returncode==0 else 'error'
    except Exception as error:
        report.update(status='error',error=str(error))
        raise
    finally:
        try:
            if changed:
                if not owned():raise RuntimeError('No owned lock for rollback')
                port=int(adb('forward','tcp:0','tcp:8765').strip())
                adb('shell','am','force-stop','net.typeblog.socks')
                adb('shell','pm','clear-permission-flags','com.microsoft.emmx','android.permission.POST_NOTIFICATIONS','user-fixed')
                adb('install','-r','-d',str(original))
                report['restored_health']=rebind()
                report['restored_no_tun0']=not bool(re.search(r'^\d+: tun0(?:[@:])',adb('shell','ip','link'),re.M))
        except Exception as error:
            report['restore_error']=str(error)
            report['status']='restore_failed'
        (out/'report.json').write_text(json.dumps(report,indent=2))
        adb('forward','--remove',f'tcp:{port}')
        if owned():lock.unlink()
    print(json.dumps(report),flush=True)
    if report.get('status') != 'complete':
        raise SystemExit(1)


if __name__=='__main__':main()
