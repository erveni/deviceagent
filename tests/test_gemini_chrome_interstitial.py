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


if __name__ == '__main__':
    unittest.main()
