"""Merge accepted YOKL paid captures without reranking, uploading or backdating."""
import argparse
import csv
import html
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
RUNS=(
    'ranking_yokl_20260909/metered',
    'yokl_cache_20260909_metered',
    'yokl_cache_four_20260909_metered',
    'yokl_chatgpt_one_20260909_metered',
    'yokl_chatgpt_four_20260909_metered',
    'yokl_copilot_one_20260909_metered',
    'yokl_copilot_retry_20260910_metered',
    'yokl_copilot_three_20260909_metered',
    'yokl_copilot_final_retry_20260910_metered',
)
PLATFORMS=('chatgpt','gemini','copilot')
RUN_LABELS={
    'yokl_cache_20260909_metered':'Gemini — first cached keyword',
    'yokl_cache_four_20260909_metered':'Gemini — remaining four keywords',
    'yokl_chatgpt_one_20260909_metered':'ChatGPT — first keyword, screenshot recovered locally',
    'yokl_chatgpt_four_20260909_metered':'ChatGPT — remaining four keywords, including two reviewed captures',
    'yokl_copilot_one_20260909_metered':'Copilot — first attempt failed',
    'yokl_copilot_retry_20260910_metered':'Copilot — successful retry of the first missing keyword',
    'yokl_copilot_three_20260909_metered':'Copilot — final three keywords',
    'yokl_copilot_final_retry_20260910_metered':'Copilot — retry of private group tours after connection failure',
}
ALLOWED={(k,p) for k in range(5221,5226) for p in PLATFORMS}


def select_records(rows):
    accepted={}
    for row in rows:
        pair=(int(row['campaign_id'])-3630000,row['platform'].lower())
        if pair not in ALLOWED or str(row['client_id'])!='329':
            raise ValueError('Unexpected business/keyword/platform in source')
        if row['status']!='success':
            continue
        position,total=int(row['rank_position']),int(row['rank_total'])
        if not 0 < position <= total:
            raise ValueError('Invalid ranking')
        if pair in accepted:
            raise ValueError('Duplicate accepted pair; review evidence explicitly')
        accepted[pair]=row
    return accepted


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    parser.add_argument('--allow-partial',action='store_true')
    args=parser.parse_args()
    rows=[]
    costs=[]
    for run in RUNS:
        path=ROOT/run
        for csv_path in sorted((path/'candidate').glob('results*.csv')):
            with csv_path.open() as stream:
                rows.extend(dict(row,source_run=run) for row in csv.DictReader(stream))
        if (path/'report.json').exists():
            report=json.loads((path/'report.json').read_text())
            if (run!='ranking_yokl_20260909/metered' and report.get('status')!='complete'
                    and not args.allow_partial):
                raise RuntimeError(f'Meter not complete for {run}; refusing understated final cost')
            if report.get('status')=='complete':
                for leg in report.get('legs',[]):
                    if leg.get('status')=='valid':
                        costs.append({'run':run,'mb':leg['used_mb'],'successes':leg['successful_pairs']})
    from tools.yokl_delivery_gate import chatgpt_recovery, reviewed_chatgpt_followup
    recovered=chatgpt_recovery(ROOT)
    reviewed=reviewed_chatgpt_followup(ROOT)
    accepted=select_records(rows+([recovered] if recovered else [])+reviewed)
    if set(accepted)!=ALLOWED and not args.allow_partial:
        raise RuntimeError(f'Only {len(accepted)}/15 accepted; refusing complete export')
    keys={k['id']:k['keywordText'] for k in json.loads((ROOT/'ranking_yokl_20260909/catalog/kw_admin.json').read_text())}
    for row in accepted.values():
        if not Path(row.get('screenshot','')).is_file():
            raise RuntimeError('Missing accepted screenshot')
    out=Path(args.output).resolve();out.mkdir(exist_ok=False)
    records=[]
    for pair in sorted(ALLOWED):
        kid,platform=pair
        row=accepted.get(pair,{})
        shot=f'kw{kid}_{platform}.png' if row else ''
        if row:shutil.copy2(row['screenshot'],out/shot)
        records.append(dict(keyword_id=kid,keyword=keys[kid],platform=platform,
            status='success' if row else 'pending',rank_position=row.get('rank_position',''),
            rank_total=row.get('rank_total',''),observed_at_utc=row.get('timestamp',''),
            screenshot=shot,response_text=row.get('response_text',''),source_run=row.get('source_run',''),
            evidence_status=row.get('evidence_status','automatic' if row else 'pending')))
    with (out/'rankings.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    (out/'attempts.json').write_text(json.dumps(rows,indent=2))
    # The canceled initial pass lacks a final meter leg. Its final settled boundary
    # is the following isolated Gemini test's baseline, not an unfinished reading.
    old=ROOT/'ranking_yokl_20260909/metered/report.json'
    following=ROOT/'yokl_cache_20260909_metered/report.json'
    if old.exists() and following.exists():
        previous=json.loads(old.read_text());nxt=json.loads(following.read_text())
        if nxt.get('status')=='complete' and previous.get('legs') and nxt.get('legs'):
            amount=previous['legs'][0]['before_mb']-nxt['legs'][0]['before_mb']
            if amount>=0:costs.insert(0,{'run':'Initial interrupted mixed-platform run (settled boundary difference)','mb':amount,'successes':1})
    (out/'bandwidth.json').write_text(json.dumps(costs,indent=2))
    esc=html.escape
    cells=[]
    for kid in sorted(keys):
        columns=[]
        for platform in PLATFORMS:
            row=accepted.get((kid,platform))
            columns.append(f'<td><a href="kw{kid}_{platform}.png">{esc(row["rank_position"])}/{esc(row["rank_total"])}</a></td>' if row else '<td>Pending</td>')
        cells.append('<tr><th>'+esc(keys[kid])+'</th>'+''.join(columns)+'</tr>')
    cost_rows=''.join(f'<tr><td>{esc(RUN_LABELS.get(c["run"],c["run"]))}</td><td>{c["mb"]:.2f}</td><td>{c["successes"]}</td></tr>' for c in costs)
    total=sum(c['mb'] for c in costs)
    document=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>YOKL ranking results</title><style>body{{font:17px/1.55 system-ui;max-width:1100px;margin:40px auto;padding:0 20px;color:#17212b}}table{{border-collapse:collapse;width:100%;margin:20px 0}}th,td{{border-bottom:1px solid #dce1e5;padding:12px;text-align:left}}a{{color:#0759b6}}small{{color:#536170}}</style>
<h1>YOKL ranking results</h1><p>{len(accepted)} of 15 keyword/platform results are accepted. Click a rank to see the actual answer screenshot.</p>
<table><thead><tr><th>Keyword</th><th>ChatGPT</th><th>Gemini</th><th>Copilot</th></tr></thead><tbody>{''.join(cells)}</tbody></table>
<p>These are the rankings stated by each AI platform, not an independent verification of business facts. The fractions are preserved as returned. Exact observation times (UTC) and responses are in <a href="rankings.csv">rankings.csv</a>. Direct readiness tests are excluded. {"The first ChatGPT result required local screenshot recovery from the same paid answer, with no new generation; the raw failed attempt is preserved." if recovered else ""}</p>
<h2>Evomi usage for these runs</h2><table><tr><th>Run</th><th>MB used</th><th>Automatic successes</th></tr>{cost_rows}<tr><th>Total, including the interrupted run</th><td>{total:.2f}</td><td>{sum(c['successes'] for c in costs)}</td></tr></table>
<p>{len(reviewed)} additional saved capture(s) were accepted after visual and OCR review despite automatic framing or business-name validation rejections; no paid rerun was needed. Evidence status is recorded per row in the CSV.</p>
<p>Failed attempts still cost bandwidth. The total includes the initial interrupted run; it is not just the cheaper cache-enabled passes. Warm-cache test results do not establish fleet-wide savings. Evomi is account-wide, with delayed deductions.</p>
<small>Local report only. No backend upload or historical-date replacement was performed. Raw attempts are preserved in attempts.json.</small></html>'''
    (out/'index.html').write_text(document)
    print(json.dumps({'output':str(out),'accepted':len(accepted),'total_pairs':15,'total_metered_mb':total}))


if __name__=='__main__':main()
