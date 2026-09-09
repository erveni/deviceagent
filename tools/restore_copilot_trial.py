"""Recover one recorded106 trial after ADB interrupted automatic rollback."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]


def main():
    folder=Path(sys.argv[1]).resolve()
    if folder.parent!=ROOT or not folder.name.startswith('copilot_bootstrap_wifi_20260910_device-106_'):
        raise ValueError('Recovery is restricted to a recorded106 wrapper')
    report=json.loads((folder/'report.json').read_text())
    original=folder/'original-v79.apk'
    if report.get('device')!='device-106' or not original.is_file():raise ValueError('Original106 backup required')
    serials=[r.split('\t')[0] for r in subprocess.check_output(['adb','devices'],text=True).splitlines()
             if '149145555W006477' in r and r.endswith('\tdevice')]
    if len(serials)!=1:raise ValueError('Ambiguous106 transport')
    serial=serials[0];lock=Path('/tmp/fleet.lock')
    with lock.open('x') as stream:stream.write(f'{os.getpid()} copilot106-rollback\n')
    out={'device':'device-106','status':'restoring','original_apk':str(original)};port=None
    def adb(*args,timeout=15):
        for attempt in range(3):
            try:return subprocess.check_output(['adb','-s',serial,*args],timeout=timeout).decode()
            except subprocess.TimeoutExpired:
                if attempt==2:raise
                subprocess.run(['adb','-s',serial,'reconnect'],timeout=10,capture_output=True)
                time.sleep(2)
    try:
        adb('shell','am','force-stop','net.typeblog.socks')
        adb('shell','pm','clear-permission-flags','com.microsoft.emmx','android.permission.POST_NOTIFICATIONS','user-fixed')
        adb('install','-r','-d',str(original),timeout=60)
        service='com.deviceagent/com.deviceagent.AgentAccessibilityService'
        previous=adb('shell','settings','get','secure','enabled_accessibility_services').strip()
        others=[s for s in previous.split(':') if s and s not in ('null',service)]
        adb('shell','am','force-stop','com.deviceagent')
        adb('shell','am','start','-n','com.deviceagent/.MainActivity')
        port=int(adb('forward','tcp:0','tcp:8765').strip())
        for attempt in range(5):
            if others:adb('shell','settings','put','secure','enabled_accessibility_services',':'.join(others))
            else:adb('shell','settings','delete','secure','enabled_accessibility_services')
            time.sleep(.5)
            adb('shell','settings','put','secure','enabled_accessibility_services',':'.join(others+[service]))
            adb('shell','settings','put','secure','accessibility_enabled','1');time.sleep(3)
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=5) as response:health=json.load(response)
                if health.get('versionCode')==79 and health.get('accessibility') is True:break
            except Exception:pass
        else:raise RuntimeError('Original79/accessibility not verified')
        if re.search(r'^\d+: tun0(?:[@:])',adb('shell','ip','link'),re.M):raise RuntimeError('VPN still active')
        out.update(status='restored',health=health,no_tun0=True)
    except Exception as error:out.update(status='restore_failed',error=str(error));raise
    finally:
        with (folder/'recovery.json').open('w') as stream:json.dump(out,stream,indent=2)
        if port:subprocess.run(['adb','-s',serial,'forward','--remove',f'tcp:{port}'],timeout=10,capture_output=True)
        if lock.exists() and lock.read_text().split()[0]==str(os.getpid()):lock.unlink()
    print(json.dumps(out))


if __name__=='__main__':main()
