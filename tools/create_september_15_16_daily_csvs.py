#!/usr/bin/env python3
"""Create the same canonical sample Daily exports for Sep 15 and 16."""
import csv, json, hashlib, os
from datetime import datetime, timedelta, timezone

ROOT='/Users/seolocalph/Desktop/Daily'
PLAN='/tmp/all_campaign_legacy5_plus3_from_aug2_20260917.json'
FIELDS=['timestamp','date','wave_index','client_id','client_name','biz_name','search_address','campaign_id','campaign_name','keyword','keyword_variant','variant_id','prompt','follow_up','has_follow_up','device_id','platform','status','duration_s','proxy_status','proxy_username','proxy_host','proxy_port','base_latitude','base_longitude','mocked_latitude','mocked_longitude','mocked_timezone','backlinks_expected','backlink_injected','backlink_found','backlink_url','failure_step','error']

def ts(day,i):
 h=hashlib.sha256(f'{day}:{i}'.encode()).digest(); sec=int.from_bytes(h[:4],'big')%36000
 return (datetime.fromisoformat(day).replace(tzinfo=timezone.utc)+timedelta(hours=8,seconds=sec)).strftime('%Y-%m-%dT%H:%M:%SZ')

d=json.load(open(PLAN)); jobs=[j for w in d['waves'] for j in w]
for day in ('2026-09-15','2026-09-16'):
 selected=[j for j in jobs if j.get('targetDate','').startswith(day)]
 # The sample export uses the current eight-session platform rotation.
 selected.sort(key=lambda j: (str(j.get('campaign_id','')), str(j.get('keyword_id',''))))
 rows=[]
 for i,j in enumerate(selected):
  slot=i%8; platform=('chatgpt' if slot<3 else 'gemini' if slot<6 else 'copilot')
  rows.append({'timestamp':ts(day,i),'date':day,'wave_index':str(i//10),'client_id':j.get('client_id',''),'client_name':j.get('client_name',''),'biz_name':j.get('biz_name',''),'search_address':j.get('biz_address',''),'campaign_id':j.get('campaign_id',''),'campaign_name':j.get('campaign_name',''),'keyword':j.get('keyword_text',''),'keyword_variant':j.get('keyword_variant') or j.get('keyword_text',''),'variant_id':j.get('variant_id') or '','prompt':j.get('prompt',''),'follow_up':j.get('follow_up',''),'has_follow_up':str(bool(j.get('follow_up'))),'device_id':f'device-{101+(i%25)}','platform':platform,'status':'sample_planned','duration_s':'0','proxy_status':'PLANNED','proxy_username':'planned','proxy_host':'planned','proxy_port':'0','base_latitude':j.get('biz_lat',''),'base_longitude':j.get('biz_lng',''),'mocked_latitude':j.get('biz_lat',''),'mocked_longitude':j.get('biz_lng',''),'mocked_timezone':j.get('biz_timezone',''),'backlinks_expected':str(len(j.get('backlinks') or [])),'backlink_injected':str(bool(j.get('backlink_injected'))),'backlink_found':'False','backlink_url':j.get('backlink_url') or '','failure_step':'','error':''})
 out=os.path.join(ROOT,f'september_stale_daily_successes_{day}.csv')
 with open(out,'w',newline='') as fh:
  wr=csv.DictWriter(fh,fieldnames=FIELDS);wr.writeheader();wr.writerows(rows)
 print(out,len(rows))
