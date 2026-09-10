import json
import unittest
from pathlib import Path


class BlackMonarchFirstTests(unittest.TestCase):
    def test_scope_and_delivery_are_exact(self):
        root=Path(__file__).resolve().parents[1]
        self.assertEqual(json.loads((root/'tools/black_monarch_keywords.json').read_text()),
                         [5186,5187,5188,5189,5190])
        source=(root/'run_black_monarch_first.sh').read_text()
        self.assertIn('PLATFORMS=chatgpt,gemini,copilot',source)
        self.assertIn('SKIP_BASE=1',source)
        self.assertIn('RANKING_SOURCES_GLOB="$CSV_GLOB"',source)
        self.assertIn('successes" != "15"',source)
        self.assertNotIn('run_stale_before_sep10_daily.sh',source)


if __name__=='__main__':unittest.main()
