import json
from pathlib import Path
import unittest
from tools.forecast_proxy_costs import forecast

ROOT=Path(__file__).resolve().parents[1]


class ForecastTests(unittest.TestCase):
    def setUp(self):
        self.c=json.loads((ROOT/'proxy_forecast_20260908/inputs.json').read_text())

    def test_measured_success_cost_already_includes_retries(self):
        rows=forecast(self.c)
        row=next(r for r in rows if r['scenario']=='base_two_sweeps' and r['provider']=='Evomi Core subscription')
        self.assertEqual(row['conditional_monthly_usd'],305.50)
        self.assertAlmostEqual(row['evomi_equivalent_total_gb'],621.456246)

    def test_daily_and_targeting(self):
        rows=[r for r in forecast(self.c) if r['scenario']=='daily_only_ranking_paused']
        self.assertEqual(rows[0]['conditional_monthly_usd'],126.48)
        self.assertEqual(rows[1]['conditional_monthly_usd'],512.22)

    def test_invalid_denominator_and_nonfinite(self):
        for key,value in [('ranking_sample_successes',0),('daily_billed_mb',float('nan'))]:
            c=dict(self.c);c[key]=value
            with self.assertRaises(ValueError):forecast(c)


if __name__=='__main__':unittest.main()
