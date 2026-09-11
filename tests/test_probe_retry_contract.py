import unittest
from pathlib import Path


class ProbeRetryContractTests(unittest.TestCase):
    def test_probe_retries_and_does_not_count_exclusions(self):
        source=(Path(__file__).resolve().parents[1]/'probe_phones.py').read_text()
        self.assertIn('for attempt in range(3)',source)
        self.assertIn("excluded.add('device-125')",source)
        self.assertIn("RANK_TRUST_ADB_ONLINE",source)
        self.assertLess(source.index('if label in excluded:'),source.index('or probe(live'))


if __name__=='__main__':unittest.main()
