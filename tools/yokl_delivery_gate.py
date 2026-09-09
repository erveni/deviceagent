"""Read-only prerequisites for bounded YOKL delivery continuations."""
import json
import csv
import hashlib
from pathlib import Path


def chatgpt_recovery(root):
    path=Path(root)/'yokl_chatgpt_one_20260909_metered'
    if not (path/'recovery.json').exists():return None
    proof=json.loads((path/'recovery.json').read_text())
    if (proof.get('status')!='recovered_same_paid_answer' or proof.get('keyword_id')!=5221
            or proof.get('platform')!='chatgpt' or proof.get('screenshot')!='candidate/recovered_kw5221.png'
            or any(proof.get(k) is not True for k in ('response_unchanged','ocr_verified','visual_review_passed'))
            or any(proof.get(k)!=0 for k in ('new_prompts','reloads','navigations'))
            or proof.get('proxy_connected') is not False or not (path/proof['screenshot']).is_file()):
        raise ValueError('Invalid local ChatGPT recovery proof')
    if hashlib.sha256((path/proof['screenshot']).read_bytes()).hexdigest()!=proof.get('screenshot_sha256'):
        raise ValueError('Recovered screenshot changed after review')
    rows=[r for p in (path/'candidate').glob('results*.csv') for r in csv.DictReader(p.open())]
    if (len(rows)!=1 or rows[0]['campaign_id']!='3635221' or rows[0]['client_id']!='329' or rows[0]['platform']!='chatgpt'
            or rows[0]['status']!='ocr_no_answer'
            or proof.get('rank')!=[int(rows[0]['rank_position']),int(rows[0]['rank_total'])]):
        raise ValueError('Recovery does not match the original paid row')
    return dict(rows[0],status='success',screenshot=str(path/proof['screenshot']),
                evidence_status='same_answer_recovery',source_run='yokl_chatgpt_one_20260909_metered')


def require_chatgpt_proof(root):
    root=Path(root)
    meter=json.loads((root/'yokl_chatgpt_one_20260909_metered/report.json').read_text())
    wrapper=json.loads((root/'yokl_chatgpt_one_20260909_direct/report.json').read_text())
    legs=meter.get('legs',[])
    recovered=chatgpt_recovery(root)
    if (meter.get('status')!='complete' or meter.get('keywords')!=[5221] or len(legs)!=1
            or legs[0].get('status')!='valid' or not (legs[0].get('successful_pairs')==1 or
                (legs[0].get('successful_pairs')==0 and recovered is not None))
            or legs[0].get('actual_pairs')!=[['3635221','chatgpt']]
            or not 0 < legs[0].get('used_mb',0) < 15
            or wrapper.get('status')!='complete' or wrapper.get('restore_error')
            or wrapper.get('restored_health',{}).get('versionCode')!=79
            or wrapper.get('restored_health',{}).get('accessibility') is not True
            or wrapper.get('restored_no_tun0') is not True):
        raise ValueError('Complete ChatGPT success below15MB and verified original79 rollback required')
    return legs[0]


def require_copilot_proof(root):
    retry=Path(root)/'yokl_copilot_retry_20260910_metered/report.json'
    path=retry if retry.exists() else Path(root)/'yokl_copilot_one_20260909_metered/report.json'
    meter=json.loads(path.read_text())
    legs=meter.get('legs',[])
    if (meter.get('status')!='complete' or meter.get('keywords')!=[5222] or len(legs)!=1
            or legs[0].get('status')!='valid' or legs[0].get('successful_pairs')!=1
            or legs[0].get('actual_pairs')!=[['3635222','copilot']]
            or not 0 < legs[0].get('used_mb',0) < 30):
        raise ValueError('Copilot continuation requires exact first success below30MB')
    return legs[0]


def require_copilot_retry(root):
    meter=json.loads((Path(root)/'yokl_copilot_one_20260909_metered/report.json').read_text())
    legs=meter.get('legs',[])
    if (meter.get('status')!='complete' or meter.get('keywords')!=[5222] or len(legs)!=1
            or legs[0].get('status')!='valid' or legs[0].get('successful_pairs')!=0
            or legs[0].get('actual_pairs')!=[['3635222','copilot']]
            or not 0 < legs[0].get('used_mb',0) < 30):
        raise ValueError('One Copilot retry requires settled failed first attempt below30MB')


def reviewed_chatgpt_followup(root):
    path=Path(root)/'yokl_chatgpt_four_20260909_metered'
    if not (path/'reviewed_captures.json').exists():return []
    proofs=json.loads((path/'reviewed_captures.json').read_text())
    rows=[r for p in (path/'candidate').glob('results*.csv') for r in csv.DictReader(p.open())]
    result=[]
    seen=set()
    for proof in proofs:
        kid=proof.get('keyword_id')
        if (kid not in (5222,5223,5224,5225) or kid in seen or proof.get('platform')!='chatgpt'
                or proof.get('status')!='visual_review_of_saved_capture'
                or any(proof.get(k) is not True for k in ('visual_review_passed','ocr_verified','full_ranked_list_and_summary_visible'))
                or proof.get('prompt_visible') is not False or proof.get('new_paid_attempts')!=0):
            raise ValueError('Invalid saved-capture review')
        matches=[r for r in rows if r['campaign_id']==str(3630000+kid) and r['platform']=='chatgpt']
        if (len(matches)!=1 or matches[0]['client_id']!='329' or matches[0]['status']!='ocr_no_answer'
                or matches[0]['screenshot']!=proof.get('screenshot')
                or proof.get('rank')!=[int(matches[0]['rank_position']),int(matches[0]['rank_total'])]):
            raise ValueError('Saved review does not match paid row')
        if hashlib.sha256(Path(proof['screenshot']).read_bytes()).hexdigest()!=proof.get('screenshot_sha256'):
            raise ValueError('Reviewed screenshot changed')
        seen.add(kid)
        result.append(dict(matches[0],status='success',evidence_status='visual_review_of_saved_capture',
                           source_run='yokl_chatgpt_four_20260909_metered'))
    return result
