"""Eight-run daily identity/rotation; pure functions, no network or device work."""
from collections import Counter
from datetime import date

PROMPT_TYPES = ('direct_service','best_provider','local_intent','problem_based',
                'conversational','trust_based','comparison','brand_verification')
PLATFORM_BASE = ('chatgpt','gemini','gemini','gemini','chatgpt','chatgpt','copilot','copilot')
# Deterministic first mixed-mode policy.  The three conversational/local
# prompt types are voice; the remaining five stay typed.  This is deliberately
# not random so rebuilding a plan cannot change its mode assignment.
VOICE_PROMPT_TYPES = frozenset(('local_intent','problem_based','conversational'))
MODE_BY_PROMPT = {kind: ('voice' if kind in VOICE_PROMPT_TYPES else 'type') for kind in PROMPT_TYPES}
EPOCH = date(2026,9,9)
DAILY_FIELDS = ['business_id','keyword_id','daily_slot_id','prompt_type','prompt_cycle_day','is_discovery',
                'backfill_slot_id','backfill_prompt_type']


def cycle_day(run_date):
    parsed=date.fromisoformat(run_date)
    if parsed.isoformat()!=run_date:raise ValueError('Expected YYYY-MM-DD')
    return (parsed-EPOCH).days % 14


def platform_for(prompt_type,run_date):
    return PLATFORM_BASE[(PROMPT_TYPES.index(prompt_type)+cycle_day(run_date))%8]


def mode_for(prompt_type):
    if prompt_type not in MODE_BY_PROMPT: raise ValueError('Unknown prompt type')
    return MODE_BY_PROMPT[prompt_type]


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
        result.append(dict(item=item,platform=platform_for(kind,run_date),mode=mode_for(kind),prompt_type=kind,
            daily_slot_id=slot_id(run_date,campaign,business,kind),prompt_cycle_day=day,
            is_discovery=kind!='brand_verification'))
    return result


def metadata(job):
    return {field:job.get(field,'') if job.get(field) is not None else '' for field in DAILY_FIELDS}


def norm(value):
    value='' if value is None else str(value).strip()
    return '' if value.lower() in ('null','none') else value


def result_key(row):
    if norm(row.get('backfill_slot_id')):
        return ('backfill',norm(row['backfill_slot_id']),norm(row.get('client_id')),
                norm(row.get('platform')).lower())
    if norm(row.get('daily_slot_id')):
        return ('daily',norm(row['daily_slot_id']),norm(row.get('client_id')),norm(row.get('platform')).lower())
    return ('legacy',norm(row.get('platform')).lower(),norm(row.get('client_id')),
            norm(row.get('campaign_id')),norm(row.get('biz_name')).lower(),
            norm(row.get('keyword_text') or row.get('keyword')).lower())


def remaining_jobs(plan,rows):
    done={result_key(r) for r in rows if r.get('status')=='success'}
    return [j for wave in plan['waves'] for j in wave if result_key(j) not in done]


def reconcile_legacy_credits(slots,rows,old_plan,run_date):
    """Credit old successes toward eight without assigning historical types.

    Return runnable slots and an audit manifest. Match old rows to their actual
    old-plan identity, not a guessed business name. A credited slot is omitted
    from this transition day's new work, NOT claimed as a completed prompt type.
    """
    old={}
    for wave in old_plan['waves']:
        for job in wave:
            key=result_key(job)
            identity=(int(job['campaign_id']),int(job['business_id']))
            if key in old and old[key]!=identity:raise ValueError('Ambiguous historical job identity')
            old[key]=identity
    groups={}
    for slot in slots:
        identity=(slot['item']['kw']['aeoPlanId'],slot['item']['biz']['id'])
        groups.setdefault(identity,[]).append(slot)
    credits=[];seen=set();outside=[]
    for row in rows:
        if row.get('status')!='success' or norm(row.get('daily_slot_id')):continue
        if row.get('date')!=run_date:raise ValueError('Historical result date mismatch')
        key=result_key(row)
        if key in seen:continue
        seen.add(key)
        if key not in old:raise ValueError('Historical success absent from original plan')
        identity=old[key]
        if identity not in groups:
            outside.append(dict(campaign_id=identity[0],business_id=identity[1],legacy_key=key))
            continue
        available=groups[identity]
        if not available:raise ValueError('More than eight historical successes for campaign/location')
        # Preserve the daily platform quota when possible; all remaining new
        # prompts keep their authentic type and rotation assignment.
        selected=next((s for s in available if s['platform']==norm(row.get('platform')).lower()),available[0])
        available.remove(selected)
        credits.append(dict(campaign_id=identity[0],business_id=identity[1],legacy_key=key,
                            omitted_slot_id=selected['daily_slot_id'],historical_prompt_type=None))
    return [s for group in groups.values() for s in group],dict(
        policy='credit-existing-toward-eight',credits=credits,outside_current_scope=outside,
        unique_historical_successes=len(seen))


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


def validate_mixed_modes(jobs, require_complete=True):
    """Validate the eight-job mixed planner contract (5 type + 3 voice)."""
    groups={}
    for job in jobs:
        kind=job.get('prompt_type')
        if job.get('mode') not in ('type','voice') or mode_for(kind)!=job.get('mode'):
            raise ValueError('Mode does not match prompt type')
        groups.setdefault((job.get('campaign_id'),job.get('business_id')),[]).append(job)
    if require_complete:
        for rows in groups.values():
            if len(rows)!=8 or Counter(r['mode'] for r in rows)!=Counter(type=5,voice=3):
                raise ValueError('Campaign must have exactly 5 type and 3 voice jobs')
    return len(groups)


def validate_typed_plan(plan):
    if plan.get('daily_protocol')!='eight-v1':return
    jobs=[j for wave in plan['waves'] for j in wave]
    if plan.get('total_jobs')!=len(jobs):raise ValueError('Daily job count mismatch')
    run_date=plan['target_date'];transition=plan.get('legacy_transition')
    validate_typed_jobs(jobs,run_date,require_complete=not (plan.get('is_remaining') or transition))
    if plan.get('is_remaining'):return
    groups={}
    for job in jobs:groups.setdefault((job['campaign_id'],job['business_id']),set()).add(job['daily_slot_id'])
    if transition:
        if transition.get('policy')!='credit-existing-toward-eight':raise ValueError('Unknown transition policy')
        seen_credits=set()
        for credit in transition['credits']:
            key=(credit['campaign_id'],credit['business_id']);slot=credit['omitted_slot_id']
            legacy_key=tuple(credit['legacy_key'])
            expected={slot_id(run_date,*key,kind) for kind in PROMPT_TYPES}
            if slot not in expected or slot in groups.get(key,set()) or legacy_key in seen_credits:
                raise ValueError('Duplicate/invalid historical quota credit')
            if credit.get('historical_prompt_type') is not None:raise ValueError('Historical type must stay null')
            groups.setdefault(key,set()).add(slot);seen_credits.add(legacy_key)
    for key,slots in groups.items():
        if slots!={slot_id(run_date,*key,kind) for kind in PROMPT_TYPES}:
            raise ValueError('New jobs plus historical credits must total eight per campaign/location')
    if len(groups)!=plan.get('total_campaigns'):raise ValueError('Daily campaign count mismatch')
