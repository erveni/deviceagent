import unittest
from pathlib import Path


class StaleAfterBlackTests(unittest.TestCase):
    def test_handoff_requires_verified_exact_fifteen(self):
        source=(Path(__file__).resolve().parents[1]/'resume_stale_after_black_monarch.sh').read_text()
        self.assertIn("COMPLETE + VERIFIED",source)
        self.assertIn('[ "$rows" != "15" ]',source)
        self.assertLess(source.index('COMPLETE + VERIFIED'),source.index('com.deviceagent.stalebeforesep10.plist'))
        self.assertIn('com.deviceagent.dailyfull',source)


if __name__=='__main__':unittest.main()
