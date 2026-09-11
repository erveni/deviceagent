#!/usr/bin/env python3
"""Recover validated ranks from already-saved text/screenshots without a paid rerun."""
import argparse,csv,glob,os,subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
import sys;sys.path.insert(0,str(ROOT))
from audit_dispatch_http import _OCR_BIN,_WALL_RE,_parse_rank_markers,_rank_inconsistent


def recover(row,ocr_text):
    if (row.get('status') or '').lower()!='ocr_no_answer' or _WALL_RE.search(ocr_text or ''):
        return None
    response=_parse_rank_markers(row.get('response_text') or '','response')
    pixels=_parse_rank_markers(ocr_text or '','ocr')
    if not response or not pixels or response[0]!='success' or pixels[0]!='success':return None
    if response[1:3]!=pixels[1:3]:return None
    items=len(__import__('re').findall(r'(?m)(?:^|\s)[1-9]\d?[.)]\s+[A-Za-z]',ocr_text))
    total=int(pixels[2])
    if items<2 and not (total==1 and items>=1):return None
    if _rank_inconsistent(row.get('response_text') or '',row.get('biz_name') or '',row.get('platform') or ''):
        return None
    fixed=dict(row);fixed.update(status='success',rank_position=pixels[1],rank_total=pixels[2],rank_context=pixels[3])
    fixed['error']='offline OCR recovery from preserved response + screenshot; no new generation'
    return fixed


def main():
    p=argparse.ArgumentParser();p.add_argument('source_glob');p.add_argument('output',type=Path);a=p.parse_args()
    paths=glob.glob(a.source_glob);rows=[r for path in paths for r in csv.DictReader(open(path))]
    succeeded={((r.get('campaign_id') or '').strip(),(r.get('platform') or '').lower().strip())
               for r in rows if (r.get('status') or '').lower() in {'success','no_rank'}}
    candidates={}
    for row in rows:
        key=((row.get('campaign_id') or '').strip(),(row.get('platform') or '').lower().strip())
        if key not in succeeded and (row.get('status') or '').lower()=='ocr_no_answer':candidates[key]=row
    def inspect(item):
        key,row=item;shot=row.get('screenshot') or ''
        if not os.path.isfile(shot):return key,None
        try:ocr=subprocess.run([_OCR_BIN,shot],capture_output=True,text=True,timeout=40,check=True).stdout
        except Exception:return key,None
        return key,recover(row,ocr)
    recovered={key:fixed for key,fixed in ThreadPoolExecutor(max_workers=8).map(inspect,candidates.items()) if fixed}
    if recovered:
        fields=list(next(iter(recovered.values())))
        with a.output.open('x',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(recovered.values())
    print(f'offline recovered {len(recovered)} unique validated pairs -> {a.output}')


if __name__=='__main__':main()
