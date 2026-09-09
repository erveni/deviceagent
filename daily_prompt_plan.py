"""Eight-run daily identity/rotation; pure functions, no network or device work."""
from collections import Counter
from datetime import date

PROMPT_TYPES = ('direct_service','best_provider','local_intent','problem_based',
                'conversational','trust_based','comparison','brand_verification')
PLATFORM_BASE = ('chatgpt','gemini','gemini','gemini','chatgpt','chatgpt','copilot','copilot')
EPOCH = date(2026,9,9)
DAILY_FIELDS = ['business_id','keyword_id','daily_slot_id','prompt_type','prompt_cycle_day','is_discovery']


def cycle_day(run_date):
    parsed=date.fromisoformat(run_date)
    if parsed.isoformat()!=run_date:raise ValueError('Expected YYYY-MM-DD')
    return (parsed-EPOCH).days % 14


def platform_for(prompt_type,run_date):
    return PLATFORM_BASE[(PROMPT_TYPES.index(prompt_type)+cycle_day(run_date))%8]


def slot_id(run_date,campaign_id,business_id,prompt_type):
    cycle_day(run_date)
    if prompt_type not in PROMPT_TYPES:raise ValueError('Unknown prompt type')
    if any(type(n) is not int or n<=0 for n in (campaign_id,business_id)):
        raise ValueError('Daily requires real campaign and business IDs')
    return f'daily:v1:{run_date}:c{campaign_id}:b{business_id}:{prompt_type}'


def campaign_slots(items,run_date):
    """items contain kw/biz; each campaign/location gets eight distinct slots."""
    if not items:raise ValueError('Campaign has no eligible keywords')
    identities={(i['kw'].get('aeoPlanId'),i['biz']['id']) for i in items}
    if len(identities)!=1:raise ValueError('Mixed campaigns/locations')
    campaign,business=next(iter(identities))
    ordered=sorted(items,key=lambda i:i['kw']['id'])
    day=cycle_day(run_date)
    result=[]
    for index,kind in enumerate(PROMPT_TYPES):
        # Seven discovery slots rotate across the approved keyword set. The
        # brand slot is business-level but retains a keyword FK for existing API.
        item=ordered[(day*7+index)%len(ordered)] if index<7 else ordered[0]
        result.append(dict(item=item,platform=platform_for(kind,run_date),prompt_type=kind,
            daily_slot_id=slot_id(run_date,campaign,business,kind),prompt_cycle_day=day,
            is_discovery=kind!='brand_verification'))
    return result


def metadata(job):
    return {field:job.get(field,'') if job.get(field) is not None else '' for field in DAILY_FIELDS}


def norm(value):
    value='' if value is None else str(value).strip()
    return '' if value.lower() in ('null','none') else value


def result_key(row):
    if norm(row.get('daily_slot_id')):
        return ('daily',norm(row['daily_slot_id']),norm(row.get('client_id')),norm(row.get('platform')).lower())
    return ('legacy',norm(row.get('platform')).lower(),norm(row.get('client_id')),
            norm(row.get('campaign_id')),norm(row.get('biz_name')).lower(),
            norm(row.get('keyword_text') or row.get('keyword')).lower())


def remaining_jobs(plan,rows):
    done={result_key(r) for r in rows if r.get('status')=='success'}
    return [j for wave in plan['waves'] for j in wave if result_key(j) not in done]


def validate_typed_jobs(jobs,run_date,require_complete=True):
    seen=set();groups={}
    for job in jobs:
        expected=slot_id(run_date,job['campaign_id'],job['business_id'],job['prompt_type'])
        if job.get('daily_slot_id')!=expected or expected in seen:raise ValueError('Invalid/duplicate daily slot')
        if norm(job.get('platform')).lower()!=platform_for(job['prompt_type'],run_date):raise ValueError('Wrong platform rotation')
        if job.get('prompt_cycle_day')!=cycle_day(run_date):raise ValueError('Wrong cycle day')
        if job.get('is_discovery')!=(job['prompt_type']!='brand_verification'):raise ValueError('Wrong discovery classification')
        if not norm(job.get('prompt')) or job.get('follow_up') or job.get('backlink_injected'):
            raise ValueError('Typed daily requires one nonempty prompt and no injected follow-up/backlink')
        seen.add(expected)
        groups.setdefault((job['campaign_id'],job['business_id']),[]).append(job)
    for rows in groups.values() if require_complete else []:
        if len(rows)!=8 or {r['prompt_type'] for r in rows}!=set(PROMPT_TYPES):raise ValueError('Campaign must have all eight types')
        if Counter(norm(r['platform']).lower() for r in rows)!=Counter(chatgpt=3,gemini=3,copilot=2):raise ValueError('Wrong platform split')
    return len(groups)
