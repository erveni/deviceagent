#!/usr/bin/env python3
"""Recover validated ranks from already-saved text/screenshots without a paid rerun."""
import argparse,csv,glob,os,re,subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
import sys;sys.path.insert(0,str(ROOT))
from audit_dispatch_http import _OCR_BIN,_WALL_RE,_parse_rank_markers,_rank_inconsistent

_VETTED_PUBLIC_NAMES={
    '90054':'Leo Lapuerta, MD Plastic Surgery',
    '740366':'Auction Direct RV',
    '1120555':'Top Choice Roofing, LLC',
    '1350667':'Mend Chiropractic - Grapevine',
    '1350671':'Mend Chiropractic - Grapevine',
    '1351420':'Mend Chiropractic - Grapevine',
    '1351433':'Mend Chiropractic - Grapevine',
    '1351434':'Mend Chiropractic - Grapevine',
}


def _explicit_target_rank(text,name,position,total):
    """Require the generated prose to state this exact vetted target and rank."""
    flat=re.sub(r'\s+',' ',text or '')
    pattern=(rf'{re.escape(name)}\s+ranks\b.{{0,100}}?\bposition\s+'
             rf'(?:approximately\s+|around\s+|about\s+)*{int(position)}\b'
             rf'.{{0,80}}?\bof\s+(?:about\s+)?{int(total)}\b')
    return bool(re.search(pattern,flat,re.IGNORECASE))


def recover(row,ocr_text):
    if (row.get('status') or '').lower()!='ocr_no_answer' or _WALL_RE.search(ocr_text or ''):
        return None
    response=_parse_rank_markers(row.get('response_text') or '','response')
    pixels=_parse_rank_markers(ocr_text or '','ocr')
    if not response or not pixels or response[0]!='success' or pixels[0]!='success':return None
    campaign=(row.get('campaign_id') or '').strip()
    if response[1:3]!=pixels[1:3]:
        # Apple Vision occasionally reads the closing ']' as a trailing '1'
        # (visible [RANK: 2/8] -> OCR 2/81). Correct only an explicitly vetted
        # campaign, with the same position and this exact decimal shape.
        bracket_as_one=(campaign in _VETTED_PUBLIC_NAMES
                        and response[1]==pixels[1]
                        and int(pixels[2])==int(response[2])*10+1)
        if not bracket_as_one:return None
        pixels=response
    public_name=_VETTED_PUBLIC_NAMES.get(campaign)
    explicit=(public_name and _explicit_target_rank(
        ocr_text,public_name,pixels[1],pixels[2]))
    items=len(re.findall(r'(?m)(?:^|\s)[1-9]\d?[.)]\s+[A-Za-z]',ocr_text))
    total=int(pixels[2])
    if items<2 and not (total==1 and items>=1) and not explicit:return None
    if _rank_inconsistent(row.get('response_text') or '',row.get('biz_name') or '',row.get('platform') or ''):
        # Copilot's accessibility text can move the "3." marker below the
        # answer and campaign names can differ from the public listing name.
        # For manually reviewed pairs only, require the screenshot OCR
        # itself to show the vetted public name at the claimed rank.
        pixel_inconsistent=(not public_name or
                            _rank_inconsistent(ocr_text or '',public_name,row.get('platform') or ''))
        # Copilot may number placeholder lines even after being told not to.
        # For an explicitly vetted campaign, accept only when its generated
        # prose independently names the target and repeats the exact marker
        # position/total. Placeholder items are not treated as businesses.
        if pixel_inconsistent and not explicit:
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
