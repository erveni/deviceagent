"""One isolated Edge-cache measurement on104, with original APK restoration."""
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]


def main():
    os.chdir(ROOT)
    out=ROOT/'copilot_cache_one_20260910_v2_wrapper'
    out.mkdir(exist_ok=False)
    meter=ROOT/'copilot_cache_one_20260910_v2_metered'
    if meter.exists():raise RuntimeError('Measurement already exists')
    original=ROOT/'direct_ui_20260908_apk/device104-original-v79.apk'
    candidate=ROOT/'app/build/outputs/apk/debug/app-debug.apk'
    if not original.is_file() or not candidate.is_file():raise RuntimeError('Missing APK/rollback')
    names=subprocess.check_output(['ps','-axo','comm='],text=True)
    if any(Path(x.strip()).name=='gost' for x in names.splitlines()):raise RuntimeError('Proxy active')
    serials=[r.split('\t')[0] for r in subprocess.check_output(['adb','devices'],text=True).splitlines()
             if '149145555W002883' in r and r.endswith('\tdevice')]
    if len(serials)!=1:raise RuntimeError('Ambiguous104')
    serial=serials[0]
    def adb(*args):return subprocess.check_output(['adb','-s',serial,*args],timeout=60).decode()
    lock=Path('/tmp/fleet.lock')
    def acquire():
        with lock.open('x') as stream:stream.write(f'{os.getpid()} copilot-cache-trial\n')
    def owned():return lock.exists() and lock.read_text().split()[0]==str(os.getpid())
    acquire()
    report={'status':'starting','measurement_only':True,'device':'device-104'}
    changed=False
    port=int(adb('forward','tcp:0','tcp:8765').strip())
    def request(path):
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/{path}',timeout=5) as r:return json.load(r)
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
        time.sleep(3)
        return request('health')
    try:
        if request('result').get('running'):raise RuntimeError('Phone busy')
        if request('health').get('versionCode')!=79:raise RuntimeError('Expected original79')
        if re.search(r'^\d+: tun0(?:[@:])',adb('shell','ip','link'),re.M):raise RuntimeError('VPN active')
        changed=True
        adb('install','-r',str(candidate))
        report['candidate_health']=rebind()
        if report['candidate_health'].get('versionCode')!=85 or report['candidate_health'].get('accessibility') is not True:
            raise RuntimeError('Candidate85 unavailable')
        if not owned():raise RuntimeError('Lost preparation lock')
        lock.unlink()
        env=os.environ.copy()
        env.update(COST_DRIVER='reframe_single',COST_YOKL_COPILOT='1',COST_COPILOT_CACHE='1',
                   COST_COPILOT_ZIP_FIRST='1',COST_COPILOT_NOTIFICATION_DENY='1',COST_PHASE_TELEMETRY='1',
                   RANK_CATALOG_DIR=str(ROOT/'ranking_yokl_20260909/catalog'))
        env.pop('COST_SETTLED_BASELINE_REPORT',None)
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
        except Exception as error:report['restore_error']=str(error)
        (out/'report.json').write_text(json.dumps(report,indent=2))
        adb('forward','--remove',f'tcp:{port}')
        if owned():lock.unlink()
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
