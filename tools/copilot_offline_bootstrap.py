"""Prepare a fresh Edge profile before a ranking job starts its proxy.

Host-only opt-in pilot; no generation/open-Copilot occurs in this function.
"""
import json
import os
import re
import time
import urllib.request
from tools.copilot_bootstrap_scope import selected_device


def settle_wifi(serial,adb,*,minimum_s=150,quiet_s=30,deadline_s=300,
                now=time.monotonic,sleep=time.sleep):
    """Let fresh-profile background downloads finish on WiFi, not Evomi.

    Observes all wlan0 RX/TX, not just Edge. Busy phones fail closed instead of
    opening the paid tunnel. No AI page is opened and no prompt is submitted.
    """
    def count():
        reply=adb(serial,'shell','cat','/proc/net/dev',timeout=10)
        for line in reply.stdout.splitlines():
            if line.strip().startswith('wlan0:'):
                fields=line.split(':',1)[1].split()
                if reply.returncode==0 and len(fields)>=16:
                    return int(fields[0])+int(fields[8])
        raise ValueError('WiFi byte counters unavailable')
    start=now();previous=count();initial=previous;quiet_since=start;samples=[]
    while now()-start<deadline_s:
        sleep(5)
        current=count();at=now()
        if current<previous:raise ValueError('WiFi counters reset during bootstrap')
        delta=current-previous
        samples.append(dict(elapsed_s=round(at-start,1),bytes=delta))
        # A small amount of DNS/telemetry is normal; sustained bulk transfer is not.
        if delta>16384:quiet_since=at
        previous=current
        if at-start>=minimum_s and at-quiet_since>=quiet_s:
            links=adb(serial,'shell','ip','link',timeout=10)
            if links.returncode or re.search(r'^\d+: tun0(?:[@:])',links.stdout,re.M):
                raise ValueError('VPN appeared during offline bootstrap')
            return dict(elapsed_s=round(at-start,1),wifi_bytes=current-initial,
                        quiet_s=round(at-quiet_since,1),samples=samples)
    raise ValueError('Fresh Edge WiFi downloads did not settle; refusing paid job')


def prepare(serial,port,body,adb,post):
    if selected_device()[1] not in serial or body.get('platform')!='copilot':
        raise ValueError('Offline bootstrap outside selected Copilot measurement scope')
    adb(serial,'forward',f'tcp:{port}','tcp:8765',timeout=10)
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=5) as r:health=json.load(r)
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/result',timeout=5) as r:old=json.load(r)
        expected_version=87 if os.environ.get('COPILOT_NETWORK_GUARD_TRIAL')=='1' else 86
        if health.get('versionCode')!=expected_version or health.get('accessibility') is not True or old.get('running'):
            raise ValueError(f'Idle v{expected_version}/accessibility required')
        # Check ownership/idleness BEFORE touching the existing VPN.
        adb(serial,'shell','am','force-stop','net.typeblog.socks',timeout=10)
        links=adb(serial,'shell','ip','link',timeout=10)
        proxy=adb(serial,'shell','settings','get','global','http_proxy',timeout=10)
        if links.returncode or proxy.returncode or re.search(r'^\d+: tun0(?:[@:])',links.stdout,re.M) or proxy.stdout.strip() not in ('null',':0',''):
            raise ValueError('Phone is not verified off-proxy')
        cleared=adb(serial,'shell','pm','clear','com.microsoft.emmx',timeout=60)
        if cleared.returncode or cleared.stdout.strip()!='Success':raise ValueError('Full Edge clear failed')
        launched=adb(serial,'shell','am','start','-n','com.microsoft.emmx/com.microsoft.ruby.Main',timeout=10)
        if launched.returncode:raise ValueError('Edge launch failed')
        time.sleep(3)
        result=post(port,dict(body,type='audit',copilotCacheTrial=False,copilotCacheResetOnly=True))
        steps=result.get('step_log',[])
        if (not any('[copilot] reset_edge OK' in s for s in steps)
                or any('[copilot] open_copilot' in s or '[copilot] input' in s or '[copilot] submit' in s for s in steps)):
            raise ValueError('Offline full-reset-only proof failed')
        proof=dict(status='full_reset_ready',at=time.time(),serial=serial,proxy_connected=False,
                   prompts_submitted=0,steps=steps,versionCode=expected_version)
        if os.environ.get('RANK_COPILOT_WIFI_SETTLE')=='1':
            print('  [copilot-offline] waiting for fresh-profile WiFi downloads; no Evomi or AI prompt',flush=True)
            proof['wifi_settlement']=settle_wifi(serial,adb)
            proof['at']=time.time()
            print('  [copilot-offline] WiFi downloads settled',flush=True)
        return proof
    finally:
        adb(serial,'forward','--remove',f'tcp:{port}',timeout=10)
