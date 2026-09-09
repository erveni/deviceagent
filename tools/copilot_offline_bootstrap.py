"""Prepare a fresh Edge profile before a ranking job starts its proxy.

Host-only opt-in pilot; no generation/open-Copilot occurs in this function.
"""
import json
import re
import time
import urllib.request


def prepare(serial,port,body,adb,post):
    if '149145555W002883' not in serial or body.get('platform')!='copilot':
        raise ValueError('Offline bootstrap pilot restricted to104/Copilot')
    adb(serial,'shell','am','force-stop','net.typeblog.socks',timeout=10)
    links=adb(serial,'shell','ip','link',timeout=10)
    proxy=adb(serial,'shell','settings','get','global','http_proxy',timeout=10)
    if links.returncode or re.search(r'^\d+: tun0(?:[@:])',links.stdout,re.M) or proxy.stdout.strip() not in ('null',':0',''):
        raise ValueError('Phone is not verified off-proxy')
    adb(serial,'forward',f'tcp:{port}','tcp:8765',timeout=10)
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=5) as r:health=json.load(r)
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/result',timeout=5) as r:old=json.load(r)
        if health.get('versionCode')!=86 or health.get('accessibility') is not True or old.get('running'):
            raise ValueError('Idle86/accessibility required')
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
        return dict(status='full_reset_ready',at=time.time(),serial=serial,proxy_connected=False,
                    prompts_submitted=0,steps=steps,versionCode=86)
    finally:
        adb(serial,'forward','--remove',f'tcp:{port}',timeout=10)
