"""Source-level safety boundaries for the experimental native cache mode."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CacheTrialGuardTests(unittest.TestCase):
    def test_pilot_keeps_separate_keyword_evidence(self):
        source = (ROOT/'audit_dispatch_http.py').read_text()
        self.assertIn('f"_kw{int(keyword_id)}" if os.environ.get("RANK_CACHE_PILOT") == "1" else ""', source)
        self.assertIn('f"cache_prepared{cache_evidence_suffix}.json"', source)
        self.assertIn('f"network{cache_evidence_suffix}.jsonl"', source)

    def test_native_default_off_and_gemini_only(self):
        source = (ROOT/'app/src/main/java/com/deviceagent/AgentHttpServer.kt').read_text()
        self.assertEqual(source.count('geminiCachePrepared: Boolean = false'), 2)
        self.assertEqual(source.count('json.optBoolean("geminiCachePrepared", false)'), 2)
        self.assertIn('geminiCachePrepared && platformsFilter == "gemini" && platform == "gemini"', source)
        daily = source[source.index('fun executeSessionStatic('):source.index('fun executeAuditSessionStatic(')]
        self.assertNotIn('geminiCachePrepared', daily)
        self.assertIn('flowEngine.resetChrome(fullClear = true)', daily)

    def test_dispatch_gate_and_no_full_clear_after_preparation(self):
        source = (ROOT/'audit_dispatch_http.py').read_text()
        start = source.index('if os.environ.get("RANK_GEMINI_CACHE_TRIAL", "0") == "1":')
        block = source[start:source.index('# Same for Edge', start)]
        self.assertIn('device_label != "device-104"', block)
        self.assertIn('not _RANK_SINGLE_ATTEMPT', block)
        self.assertIn('cache_health_allowed(cache_health, cache_evidence)', block)
        self.assertIn('combined cache evidence trial requires prompt-free proof', block)
        self.assertLess(block.index('if not cache_prepared.get("ok")'),
                        block.index('body["geminiCachePrepared"] = True'))
        self.assertIn('elif os.environ.get("CHROME_HARD_CLEAR", "1") == "1":', block)
