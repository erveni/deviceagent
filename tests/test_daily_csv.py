"""No device/proxy calls; exercise the real CSV writer with temporary outputs."""
import csv
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

with patch.dict(os.environ, {'ONLY_ONLINE':'0'}):
    from device_dispatch import append_row, CSV_FIELDS
from daily_prompt_plan import DAILY_FIELDS


class DailyCsvTests(unittest.TestCase):
    def test_new_csv_retains_slot_and_false_discovery(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'results.csv'
            append_row(str(path),dict(date='2026-09-09',daily_slot_id='slot',
                prompt_type='brand_verification',prompt_cycle_day=0,is_discovery=False))
            with (Path(folder)/'results_2026-09-09.csv').open() as f:
                reader=csv.DictReader(f);row=next(reader)
                self.assertEqual(reader.fieldnames,CSV_FIELDS+DAILY_FIELDS)
                self.assertEqual(row['prompt_cycle_day'],'0')
                self.assertEqual(row['is_discovery'],'False')

    def test_historical_header_preserved_and_typed_append_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'results.csv';dated=Path(folder)/'results_2026-09-09.csv'
            with dated.open('w',newline='') as f:csv.writer(f).writerow(CSV_FIELDS)
            append_row(str(path),dict(date='2026-09-09',status='success'))
            before=dated.read_bytes()
            with self.assertRaises(ValueError):
                append_row(str(path),dict(date='2026-09-09',daily_slot_id='new-slot'))
            self.assertEqual(dated.read_bytes(),before)
            with dated.open() as f:self.assertEqual(next(csv.reader(f)),CSV_FIELDS)


if __name__=='__main__':unittest.main()
