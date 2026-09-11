from pathlib import Path
import unittest


class GeminiChromeInterstitialTests(unittest.TestCase):
    def test_gemini_dismisses_signed_out_chrome_interstitial(self):
        source = (Path(__file__).resolve().parents[1] /
                  'app/src/main/java/com/deviceagent/FlowEngine.kt').read_text()
        block = source[source.index('"gemini" -> listOf('):
                       source.index('"chatgpt" -> listOf(', source.index('"gemini" -> listOf('))]
        self.assertIn('"Stay signed out"', block)
        self.assertIn('"Use without an account"', block)

    def test_dispatch_starts_chrome_before_offline_cache_reset(self):
        source = (Path(__file__).resolve().parents[1] /
                  'audit_dispatch_http.py').read_text()
        start = source.index("phase('offline_cache_prepare_start')")
        finish = source.index("phase('offline_cache_prepare_done')", start)
        block = source[start:finish]
        self.assertLess(block.index("'com.android.chrome/com.google.android.apps.chrome.Main'"),
                        block.index('prepare_chatgpt_cache'))
        self.assertLess(block.index('_dismiss_chrome_fre_off_proxy(serial)'),
                        block.index('prepare_chatgpt_cache'))

    def test_submit_uses_visible_prompt_matching_editor(self):
        source = (Path(__file__).resolve().parents[1] /
                  'app/src/main/java/com/deviceagent/FlowEngine.kt').read_text()
        helper = source[source.index('private fun findGeminiAuditPromptField'):
                        source.index('fun submitGeminiAudit')]
        self.assertIn('bounds.width() > 0', helper)
        self.assertIn('GeminiAuditEvidence.promptMatches', helper)
        submit = source[source.index('fun submitGeminiAudit'):
                        source.index('fun waitForGeminiAudit')]
        self.assertIn('findGeminiAuditPromptField()', submit)

    def test_chatgpt_signup_wall_is_reported_without_full_timeout(self):
        root = Path(__file__).resolve().parents[1]
        flow = (root / 'app/src/main/java/com/deviceagent/FlowEngine.kt').read_text()
        wait = flow[flow.index('fun waitForGeneration'):
                    flow.index('// ── response text capture')]
        self.assertIn('Sign in is required to continue', wait)
        self.assertIn('lastGenerationFailure = "signup_wall"', wait)
        server = (root / 'app/src/main/java/com/deviceagent/AgentHttpServer.kt').read_text()
        self.assertIn('flowEngine.lastGenerationFailure ?: "generation timeout"', server)

    def test_gemini_submit_retries_and_denies_microphone(self):
        source = (Path(__file__).resolve().parents[1] /
                  'app/src/main/java/com/deviceagent/FlowEngine.kt').read_text()
        submit = source[source.index('fun submitGeminiAudit'):
                        source.index('fun waitForGeminiAudit')]
        self.assertIn('repeat(3) attempts@', submit)
        self.assertIn('"Never allow"', submit)
        self.assertIn('return@attempts', submit)
        self.assertNotIn('findSendNode() ?: return false', submit)


if __name__ == '__main__':
    unittest.main()
