import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location('cache_summary', Path(__file__).resolve().parents[1] / 'tools/summarize_cache_pilot.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CachePilotSummaryTests(unittest.TestCase):
    def test_partial_leg_preserves_failures_network_and_separate_pid_maxima(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'keywords.json').write_text('[12, 34]')
            (root / 'report.json').write_text(json.dumps({'status': 'partial', 'legs': [
                {'name': 'candidate', 'status': 'partial', 'before_mb': 100, 'after_mb': 91.5}],
                'remaining_keyword_ids': [34]}))
            leg = root / 'candidate'; leg.mkdir()
            (leg / 'results_2026.csv').write_text(
                'campaign_id,biz_name,keyword,platform,device,status,duration_s,rank_position,rank_total,screenshot,error\n'
                '90012,Biz A,alpha,gemini,device-104,success,10,1,3,/shot-a.png,\n'
                '90034,Biz B,beta,gemini,device-104,input failed,11,,,,,missing input\n')
            (leg / 'cache_prepared_kw12.json').write_text('{"ok":true,"cache_reuse_verified":false}')
            (leg / 'network_kw12.jsonl').write_text('\n'.join(json.dumps(x) for x in [
                {'event': 'trace_start', 'missing_early_events_possible': True},
                {'event': 'resource_finished', 'encoded_bytes': 10, 'served_from_cache': True},
                {'event': 'resource_finished', 'encoded_bytes': None, 'from_disk_cache': False},
                {'event': 'trace_stop', 'unfinished_requests': 2}]) + '\n')
            (leg / 'gost_phases.jsonl').write_text('\n'.join(json.dumps(x) for x in [
                {'source': 'gost_metrics_cumulative', 'pid': 1, 'gost_pid': 10, 'services': [{'service': 's', 'input_bytes': 2, 'output_bytes': 4}]},
                {'source': 'gost_metrics_cumulative', 'pid': 1, 'gost_pid': 10, 'services': [{'service': 's', 'input_bytes': 5, 'output_bytes': 3}]},
                {'source': 'gost_metrics_cumulative', 'pid': 2, 'gost_pid': 11, 'services': [{'service': 's', 'input_bytes': 7, 'output_bytes': 9}]}]) + '\n')
            result = MODULE.summarize(root)
            self.assertEqual(result['remaining_keyword_ids'], [34])
            leg_result = result['legs'][0]
            self.assertEqual((leg_result['completed_rows'], leg_result['successful_rows'], leg_result['failure_rows']), (2, 1, 1))
            self.assertEqual(leg_result['evomi_delta_mb'], 8.5)
            self.assertEqual(len(leg_result['gost_final_maxima_separate_not_summed']), 2)
            self.assertEqual(leg_result['gost_final_maxima_separate_not_summed'][0]['input_bytes'], 5)
            net = result['per_keyword']['12']['network'][0]
            self.assertEqual((net['cache_hits'], net['encoded_bytes_finished'], net['unfinished_requests']), (1, 10, 2))
            self.assertEqual(result['per_keyword']['12']['screenshot_paths'], ['/shot-a.png'])

    def test_unreported_partial_uses_csv_ids_for_remaining(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'keywords.json').write_text('[12, 34]')
            (root / 'report.json').write_text('{"status":"candidate-running"}')
            leg = root / 'candidate'; leg.mkdir()
            (leg / 'results.csv').write_text('campaign_id,status\n100012,success\n')
            self.assertEqual(MODULE.summarize(root)['remaining_keyword_ids'], [34])


if __name__ == '__main__':
    unittest.main()
