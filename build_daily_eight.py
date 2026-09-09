"""Build the canonical eight-type daily; no browser jobs are launched here."""
import csv
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
import glob,json,os,random,re,time,urllib.request,urllib.error
from collections import Counter,defaultdict
from pathlib import Path
from daily_geo import coordinates

from daily_prompt_plan import campaign_slots,cycle_day,validate_typed_jobs,validate_typed_plan,PROMPT_TYPES,reconcile_legacy_credits

EXCLUDED_BIZ_NAMES={'Caspian Painting Co, Inc.','Nez Perce Traditions Gift Shop',"Smith's Enterprise"}


def active(row):
    return row['isActive'] if isinstance(row.get('isActive'),bool) else row.get('status')=='active'


def eligible_groups(businesses,keywords,clients,free_trial_ids,top3):
    business={b['id']:b for b in businesses};client_ids={c['id'] for c in clients if active(c)}
    groups=defaultdict(list)
    for kw in keywords:
        biz=business.get(kw.get('businessId'))
        if not active(kw) or kw.get('archivedAt') or kw.get('status')=='locked' or not biz or not active(biz) or biz.get('clientId') not in client_ids:continue
        if kw.get('campaignStatus') not in (None,'active'):continue
        if (biz.get('name') or biz.get('businessName')) in EXCLUDED_BIZ_NAMES:continue
        key=((biz.get('name') or biz.get('businessName') or '').strip().lower(),kw.get('keywordText','').strip().lower())
        if kw.get('aeoPlanId') in free_trial_ids and key in top3:continue
        if not kw.get('aeoPlanId'):raise ValueError(f"Keyword {kw['id']} has no campaign ID")
        groups[(kw['aeoPlanId'],biz['id'])].append({'kw':kw,'biz':biz})
    return groups


def make_job(slot,session,run_date):
    kw,biz=slot['item']['kw'],slot['item']['biz']
    expected={'promptType':slot['prompt_type'],'dailySlotId':slot['daily_slot_id'],
              'promptCycleDay':slot['prompt_cycle_day'],'isDiscovery':slot['is_discovery'],
              'campaignId':kw['aeoPlanId'],'businessId':biz['id'],'keywordId':kw['id'],
              'platform':slot['platform']}
    if any(session.get(k)!=v for k,v in expected.items()):
        raise ValueError(f"Backend daily contract mismatch for {slot['daily_slot_id']}")
    addr=session.get('searchAddress') or biz.get('publishedAddress') or ''
    city,state=session.get('city') or '',session.get('state') or ''
    lat,lng,tz=coordinates(city,state)
    zips=re.findall(r'\b\d{5}\b',addr)
    return dict(client_id=session['clientId'],client_name='',campaign_id=kw['aeoPlanId'],
        campaign_name=kw.get('campaignName') or f"biz{biz['id']}",business_id=biz['id'],keyword_id=kw['id'],
        keyword_text=kw.get('keywordText') or '',keyword_variant=session.get('variantText') or kw.get('keywordText') or '',
        variant_id=None,platform=slot['platform'],biz_name=session.get('bizName') or biz.get('name') or '',
        biz_city=session.get('city') or biz.get('city') or '',biz_state=session.get('state') or biz.get('state') or '',
        biz_zip=session.get('zip') or (zips[-1] if zips else ''),biz_address=addr,
        biz_lat=lat,biz_lng=lng,
        biz_timezone=tz,
        gmb_url=biz.get('gmbUrl') or biz.get('websiteUrl'),backlinks=[],backlink_injected=False,backlink_url=None,
        prompt=session.get('prompt') or '',follow_up='',targetDate=run_date+'T12:00:00Z',
        daily_slot_id=slot['daily_slot_id'],prompt_type=slot['prompt_type'],
        prompt_cycle_day=slot['prompt_cycle_day'],is_discovery=slot['is_discovery'])


def pack_waves(jobs,seed):
    rest=list(jobs);random.Random(seed).shuffle(rest);waves=[]
    while rest:
        wave=[];clients=set();campaigns=set();left=[]
        for job in rest:
            if len(wave)<10 and job['client_id'] not in clients and job['campaign_id'] not in campaigns:
                wave.append(job);clients.add(job['client_id']);campaigns.add(job['campaign_id'])
            else:left.append(job)
        waves.append(wave);rest=left
    return waves


def main():
    os.environ.setdefault('SSL_CERT_FILE',__import__('certifi').where())
    run_date=os.environ.get('DATE',datetime.now(timezone.utc).date().isoformat());cycle_day(run_date)
    output=Path(os.environ.get('PLAN_PATH',f'daily_plan_{run_date}.json'))
    dry=os.environ.get('DRY_RUN')=='1'
    legacy_rows=[]
    legacy_plan=os.environ.get('DAILY_LEGACY_PLAN')
    credit=os.environ.get('DAILY_LEGACY_POLICY')=='credit-existing-toward-eight'
    if credit and not legacy_plan:raise SystemExit('Legacy credit requires DAILY_LEGACY_PLAN')
    if output.exists() and not dry:raise SystemExit(f'Refusing to overwrite existing plan: {output}; use a new PLAN_PATH')
    # Old successes have no type/slot identity. Never silently treat them as
    # failures and buy eight additional sessions for an already-started day.
    for file in glob.glob(f'daily_plan_{run_date}*results*.csv'):
        with open(file, newline='') as stream:
            historical=[r for r in csv.DictReader(stream) if r.get('status')=='success' and not r.get('daily_slot_id')]
            if historical:
                legacy_rows.extend(historical)
                if not dry and not credit:
                    raise SystemExit('Historical successes exist for this date. Reconcile the transition '
                                     'before building a new eight-type daily; nothing was overwritten.')
    admin=os.environ.get('ADMIN_BASE','https://jjm59vpn3y.us-east-1.awsapprunner.com')
    headers={'X-Executor-Token':os.environ.get('EXECUTOR_TOKEN','')}
    def request(path,body=None):
        req=urllib.request.Request(admin+path,headers={**headers,'Content-Type':'application/json'},
            data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(req,timeout=int(os.environ.get('BUILD_TIMEOUT_S','60'))) as response:
            return json.load(response)
    catalog=os.environ.get('DAILY_CATALOG_DIR')
    if catalog:
        data={name:json.loads((Path(catalog)/file).read_text()) for name,file in
              [('businesses','biz_admin.json'),('keywords','kw_admin.json'),('clients','clients_admin.json')]}
    else:
        data=request('/api/llm/daily-catalog')
        if data.get('version')!='daily-guide-v1':raise SystemExit('Backend daily catalog capability missing')
    trial_file=Path(os.environ.get('EXCLUDE_PLAN_IDS_FILE','/tmp/exclude_plan_ids.json'))
    trials=set(json.loads(trial_file.read_text())) if trial_file.exists() else set()
    top3=set()
    for file in glob.glob(os.environ.get('RANK_CSVS','rabbitmq_audit_results_2026-07-17_ranking_*.csv')):
        with open(file) as stream:
            for row in csv.DictReader(stream):
                try:rank=int(float(row.get('rank_position','')))
                except (TypeError,ValueError):continue
                if 1<=rank<=3:top3.add((row.get('biz_name','').strip().lower(),row.get('keyword','').strip().lower()))
    groups=eligible_groups(data['businesses'],data['keywords'],data['clients'],trials,top3)
    if not groups:raise SystemExit('No eligible campaigns; refusing empty daily')
    slots=[slot for key in sorted(groups) for slot in campaign_slots(groups[key],run_date)]
    transition=None
    if credit:
        slots,transition=reconcile_legacy_credits(slots,legacy_rows,json.loads(Path(legacy_plan).read_text()),run_date)
        print(json.dumps(dict(legacy_credits=len(transition['credits']),
            historical_outside_scope=len(transition['outside_current_scope']),new_jobs=len(slots))),flush=True)
    print(json.dumps(dict(date=run_date,campaigns=len(groups),total_slots=len(slots),
        sessions_per_campaign=8,platforms=dict(Counter(s['platform'] for s in slots))),indent=2),flush=True)
    if dry:return
    policy=request('/api/llm/daily-prompt-types')
    if (policy.get('version')!='daily-guide-v1' or policy.get('runsPerCampaign')!=8
            or [t.get('id') for t in policy.get('types',[])]!=list(PROMPT_TYPES)):
        raise SystemExit('Backend eight-run daily capability missing; no prompt calls made')
    def build(slot):
        body=dict(keyword_id=slot['item']['kw']['id'],platform=slot['platform'],
                  prompt_type=slot['prompt_type'],run_date=run_date)
        for attempt in range(3):
            try:return make_job(slot,request('/api/llm/build-session',body),run_date)
            except urllib.error.HTTPError as error:
                if error.code<500 or attempt==2:raise
            except (TimeoutError,urllib.error.URLError):
                if attempt==2:raise
            time.sleep(attempt+1)
        raise RuntimeError('Unreachable build failure')
    with ThreadPoolExecutor(max_workers=int(os.environ.get('BUILD_WORKERS','8'))) as workers:
        jobs=list(workers.map(build,slots)) # Never silently drop failed slots.
    validate_typed_jobs(jobs,run_date,require_complete=transition is None)
    plan=dict(daily_protocol='eight-v1',generated_at=datetime.now(timezone.utc).isoformat(),target_date=run_date,
        total_jobs=len(jobs),total_campaigns=len(groups),sessions_per_campaign=8,cycle_day=cycle_day(run_date),
        _source='build_daily_eight.py',waves=pack_waves(jobs,'daily-v1:'+run_date))
    if transition is not None:plan['legacy_transition']=transition
    validate_typed_plan(plan)
    with output.open('x') as stream:json.dump(plan,stream,indent=1)
    print(f'Wrote {output}: {len(jobs)} jobs; no browser jobs launched')


if __name__=='__main__':main()
