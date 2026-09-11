#!/usr/bin/env python3
"""Prepare Chrome and warm static AI-site assets on Wi-Fi, never paid proxy."""
import argparse,json,os,re,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.copilot_offline_bootstrap import settle_wifi


def center_for_resource(xml,resource):
    match=next((m.group(0) for m in re.finditer(r'<node[^>]+',xml)
                if f'resource-id="{resource}"' in m.group(0)),None)
    if not match:return None
    bounds=re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',match)
    if not bounds:return None
    x1,y1,x2,y2=map(int,bounds.groups());return ((x1+x2)//2,(y1+y2)//2)


def main():
    p=argparse.ArgumentParser();p.add_argument('label');p.add_argument('serial');p.add_argument('output',type=Path);a=p.parse_args()
    def adb(serial,*args,timeout=15):
        return subprocess.run(['adb','-s',serial,*args],capture_output=True,text=True,timeout=timeout)
    proof={'label':a.label,'serial':a.serial,'proxy_connected':False,'prompts_submitted':0,'clicks':[]}
    adb(a.serial,'shell','am','force-stop','net.typeblog.socks')
    links=adb(a.serial,'shell','ip','link');proxy=adb(a.serial,'shell','settings','get','global','http_proxy')
    if links.returncode or proxy.returncode or re.search(r'^\d+: tun0(?:[@:])',links.stdout,re.M) or proxy.stdout.strip() not in ('null',':0',''):
        raise SystemExit('phone is not verified off-proxy')
    for key in ('KEYCODE_WAKEUP','KEYCODE_MENU'):adb(a.serial,'shell','input','keyevent',key)
    adb(a.serial,'shell','input','swipe','360','1300','360','300','500')
    adb(a.serial,'shell','am','start','-n','com.android.chrome/com.google.android.apps.chrome.Main')
    for _ in range(6):
        time.sleep(2);adb(a.serial,'shell','uiautomator','dump','/sdcard/chrome_low_cost.xml',timeout=20)
        xml=adb(a.serial,'shell','cat','/sdcard/chrome_low_cost.xml').stdout
        target=None
        for resource in ('com.android.chrome:id/signin_fre_dismiss_button',
                         'com.android.chrome:id/negative_button','android:id/button1'):
            target=center_for_resource(xml,resource)
            if target:
                adb(a.serial,'shell','input','tap',str(target[0]),str(target[1]));proof['clicks'].append(resource);break
        if not target:break
    activity=adb(a.serial,'shell','dumpsys','activity','activities').stdout
    top=next((line for line in activity.splitlines() if 'topResumedActivity' in line),'')
    if 'FirstRunActivity' in top:
        raise SystemExit('Chrome first-run UI did not complete')
    for url in ('https://gemini.google.com/app','https://chatgpt.com/'):
        adb(a.serial,'shell','am','start','-n','com.android.chrome/com.google.android.apps.chrome.Main',
            '-a','android.intent.action.VIEW','-d',url);time.sleep(20)
    proof['wifi_settlement']=settle_wifi(a.serial,adb,minimum_s=45,quiet_s=20,deadline_s=180)
    os.environ.update(RANK_SINGLE_ATTEMPT='1',RANK_CACHE_LOW_COST_ROLLOUT='1',
                      RANK_GEMINI_LOW_COST_RELEASED='1')
    from tools.gemini_cache_reset import prepare_gemini_cache
    proof['identity_reset']=prepare_gemini_cache(a.serial,authorized_production=True)
    if not proof['identity_reset'].get('ok'):raise SystemExit('identity reset failed: '+str(proof['identity_reset']))
    a.output.write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({'label':a.label,'status':'ready','wifi_bytes':proof['wifi_settlement']['wifi_bytes']}))


if __name__=='__main__':main()
