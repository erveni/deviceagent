"""Scope/default guards for the deliberately opt-in Edge cache experiment."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class CopilotCacheTrialTests(unittest.TestCase):
    def test_native_flag_defaults_false_in_both_entry_points(self):
        source=(ROOT/'app/src/main/java/com/deviceagent/AgentHttpServer.kt').read_text()
        self.assertEqual(source.count('json.optBoolean("copilotCacheTrial", false)'),2)
        self.assertEqual(source.count('copilotCacheTrial: Boolean = false'),2)
        self.assertIn('copilotCacheTrial && platformsFilter == "copilot"',source)
        self.assertIn('verify_fresh_cached_conversation',source)

    def test_cache_exclusion_requires_explicit_opt_in_and_no_wipe_fallback(self):
        source=(ROOT/'app/src/main/java/com/deviceagent/EdgeCopilotFlow.kt').read_text()
        self.assertIn('fun reset(preserveCacheTrial: Boolean = false)',source)
        self.assertIn('"Cached images and files" to false',source)
        self.assertIn('"Tabs" to true',source)
        self.assertIn('if (!selectAllTimeRange()) return false',source)
        self.assertIn('cache trial reset refused; no full-wipe fallback',source)
        self.assertIn('if (!matches) return false',source)
        self.assertIn('s.findNode(text = "Personalize your web experience"',source)
        self.assertIn('s.findNode(text = "Not now", timeoutMs = 1500) ?: return false',source)

    def test_host_and_supervisor_keep_experiment_one_phone_one_job(self):
        host=(ROOT/'audit_dispatch_http.py').read_text()
        self.assertIn("RANK_COPILOT_CACHE_TRIAL','0'",host)
        self.assertIn("health.get('versionCode')!=85",host)
        self.assertIn('Copilot cache trial restricted to one device104 audit',host)
        supervisor=(ROOT/'tools/run_ranking_cost_pair.sh').read_text()
        self.assertIn("copilot_cache and (not copilot_yokl or keywords != [5225])",supervisor)
        self.assertIn("RANK_COPILOT_CACHE_TRIAL='0'",supervisor)
        self.assertIn("report['copilot_cache_measurement_only'] = True",supervisor)


if __name__=='__main__':unittest.main()
