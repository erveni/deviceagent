"""Offline conditional proxy budget; no API, phone, purchases, or production writes.

python3 tools/forecast_proxy_costs.py --inputs proxy_forecast_20260908/inputs.json
Optional --output NEW.csv creates a spreadsheet-readable file, refusing overwrite.
Other-provider estimates assume workload-equivalent bytes and success rate;
their actual measured multiplier must replace the default 1 before migration.
"""
import argparse
import csv
import io
import json
import math
from pathlib import Path


def forecast(c):
    for key, value in c.items():
        if key not in ('as_of', 'currency'):
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f'Invalid nonnegative numeric input: {key}')
    if c['ranking_sample_successes'] <= 0 or c['pilot_accepted_successes'] <= 0:
        raise ValueError('Success denominators must be positive')
    daily = c['days'] * c['daily_billed_mb'] / 1000
    per_success = c['ranking_sample_billed_mb'] / c['ranking_sample_successes']
    scenarios = [('daily_only_ranking_paused', 0, 1), ('one_sweep', 1, 1),
                 ('base_two_sweeps', c['base_sweeps_per_month'], 1),
                 ('base_plus_planning_buffer', c['base_sweeps_per_month'], 1+c['planning_buffer_fraction']),
                 ('fourteen_day_cadence_sensitivity', c['days']/14, 1)]
    rows = []
    for name, sweeps, buffer in scenarios:
        ranking = c['pairs_per_sweep'] * sweeps * per_success / 1000
        total = (daily + ranking) * buffer
        other = total * c['cross_provider_workload_multiplier']
        costs = {
            'Evomi Core subscription': c['evomi_monthly_fee'] + max(0,total-c['evomi_included_gb'])*c['evomi_overage_usd_per_gb'],
            'DataImpulse standard targeted (conditional)': other*c['dataimpulse_standard_usd_per_gb']*c['dataimpulse_targeting_multiplier'],
            'Rayobyte Professional (conditional)': other*c['rayobyte_professional_usd_per_gb'],
            'Decodo PAYG (conditional)': other*c['decodo_payg_usd_per_gb'],
        }
        for provider, dollars in costs.items():
            rows.append(dict(scenario=name,provider=provider,days=c['days'],
                             planned_ranking_successes=round(c['pairs_per_sweep']*sweeps,3),
                             daily_gb_before_buffer=round(daily,6),ranking_gb_before_buffer=round(ranking,6),
                             planning_buffer_multiplier=buffer,evomi_equivalent_total_gb=round(total,6),
                             conditional_monthly_usd=round(dollars,2)))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    rows=forecast(json.loads(args.inputs.read_text()))
    stream=io.StringIO()
    writer=csv.DictWriter(stream,fieldnames=rows[0].keys())
    writer.writeheader();writer.writerows(rows)
    result=stream.getvalue()
    if args.output:
        with args.output.open('x',newline='') as output:
            output.write(result)
    print(result,end='')


if __name__=='__main__':
    main()
