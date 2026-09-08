import json
from pathlib import Path
import tempfile
import unittest

from tools.summarize_ranking_phases import summarize


class PhaseSummaryTests(unittest.TestCase):
    def run_trace(self, amounts, pids=None):
        rows = [dict(status='ok', gost_pid=(pids or [1]*len(amounts))[i],
                     time=100+i, phase=['ready', 'periodic', 'before_stop'][i],
                     services=[dict(input_bytes=0, output_bytes=n)])
                for i, n in enumerate(amounts)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'trace.jsonl'
            path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            return summarize(path)

    def test_differences_not_sum_of_counters(self):
        result = self.run_trace([100, 200, 500])
        self.assertEqual(result['local_total_mb'], .0005)
        self.assertEqual(result['phase_intervals'][0]['local_mb'], .0004)

    def test_rejects_counter_regression(self):
        with self.assertRaises(ValueError):
            self.run_trace([100, 200, 150])

    def test_rejects_multiple_processes(self):
        with self.assertRaises(ValueError):
            self.run_trace([100, 200, 500], [1, 1, 2])
