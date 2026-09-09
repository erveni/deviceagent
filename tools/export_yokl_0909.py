"""Local YOKL deliverable only; preserves actual timestamps, never uploads/backdates."""
import csv
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'ranking_yokl_20260909'


def main():
    sources = sorted((RUN/'metered/candidate').glob('results*.csv'))
    rows = [r for p in sources for r in csv.DictReader(p.open())]
    keys = {k['id']:k['keywordText'] for k in json.loads((RUN/'catalog/kw_admin.json').read_text())}
    allowed = {(k,p) for k in keys for p in ('chatgpt','gemini','copilot')}
    records = {}
    for row in rows:
        kid = int(row['campaign_id']) - 3630000
        pair = (kid,row['platform'].lower())
        if pair not in allowed or str(row['client_id']) != '329':
            raise RuntimeError('Unexpected business/keyword/platform in output')
        if pair in records:
            raise RuntimeError('Duplicate pair: choose evidence explicitly, do not silently replace')
        records[pair] = row
    if set(records) != allowed:
        raise RuntimeError('Priority pass not finished; no final export')
    out = Path('/Users/seolocalph/Desktop/Rankings/Yokl_initial_2026-09-09')
    out.mkdir(exist_ok=False)
    exported = []
    for (kid, platform), row in sorted(records.items()):
        source = row.get('screenshot_path') or row.get('screenshot') or ''
        image = ''
        if row.get('status') == 'success':
            if not source or not Path(source).is_file():
                raise RuntimeError(f'Missing accepted screenshot for {kid}/{platform}')
            image = f'kw{kid}_{platform}.png'
            shutil.copy2(source, out/image)
        exported.append({'business':'Yokl, Inc.','keyword_id':kid,'keyword':keys[kid],
            'platform':platform,'observed_at_utc':row.get('timestamp',''),
            'status':row.get('status',''), 'ranking_position':row.get('rank_position',''),
            'ranking_total':row.get('rank_total',''), 'screenshot':image,
            'error':row.get('error',''), 'response_text':row.get('response_text','')})
    with (out/'rankings.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(exported[0]))
        writer.writeheader();writer.writerows(exported)
    successes=sum(r['status']=='success' for r in exported)
    (out/'README.md').write_text(
        '# YOKL initial rankings\n\n'
        f'{successes}/15 automatically accepted captures across five keywords and three platforms.\n\n'
        'Read rankings.csv; screenshot filenames refer to the PNGs in this folder. '
        'Timestamps are the actual UTC observations, not reconstructed earlier dates. '
        'Rankings report what each AI platform answered; they are not independent verification '
        'of business facts. A failed row is not a measured position. '
        'Direct readiness-check results are excluded. No backend upload was performed.\n')
    print(json.dumps({'output':str(out),'accepted_captures':successes,'total_pairs':15}))


if __name__=='__main__':main()
