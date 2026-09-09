"""Single-use proof gate for the one-phone offline Edge bootstrap experiment."""
import json
from pathlib import Path
import time


def consume_receipt(path,serial,keyword_id,health):
    path=Path(path).resolve()
    root=Path(__file__).resolve().parents[1]
    expected={root/f'{prefix}_wrapper/edge_ready.json' for prefix in
              ('copilot_bootstrap_one_20260910','copilot_bootstrap_auto_20260910')}
    if path not in expected or '149145555W002883' not in serial or int(keyword_id)!=5225:
        raise ValueError('Unexpected bootstrap receipt/phone/keyword')
    proof=json.loads(path.read_text())
    steps=proof.get('steps',[])
    if (proof.get('status')!='full_reset_ready' or proof.get('serial')!=serial
            or proof.get('keyword_id')!=5225 or proof.get('proxy_connected') is not False
            or proof.get('prompts_submitted')!=0 or not 0<=time.time()-proof.get('at',0)<=900
            or health.get('versionCode')!=86 or health.get('accessibility') is not True
            or not any('[copilot] reset_edge OK' in s for s in steps)
            or any('[copilot] input' in s or '[copilot] submit' in s or '[copilot] open_copilot' in s for s in steps)):
        raise ValueError('Offline full-reset receipt failed validation')
    with path.with_suffix('.consumed').open('x') as stream:
        stream.write(str(time.time()))
    return proof
