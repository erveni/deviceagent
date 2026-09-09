"""Read-only prerequisites for bounded YOKL delivery continuations."""
import json
from pathlib import Path


def require_chatgpt_proof(root):
    root=Path(root)
    meter=json.loads((root/'yokl_chatgpt_one_20260909_metered/report.json').read_text())
    wrapper=json.loads((root/'yokl_chatgpt_one_20260909_direct/report.json').read_text())
    legs=meter.get('legs',[])
    if (meter.get('status')!='complete' or meter.get('keywords')!=[5221] or len(legs)!=1
            or legs[0].get('status')!='valid' or legs[0].get('successful_pairs')!=1
            or legs[0].get('actual_pairs')!=[['3635221','chatgpt']]
            or not 0 < legs[0].get('used_mb',0) < 15
            or wrapper.get('status')!='complete' or wrapper.get('restore_error')
            or wrapper.get('restored_health',{}).get('versionCode')!=79
            or wrapper.get('restored_health',{}).get('accessibility') is not True
            or wrapper.get('restored_no_tun0') is not True):
        raise ValueError('Complete ChatGPT success below15MB and verified original79 rollback required')
    return legs[0]
