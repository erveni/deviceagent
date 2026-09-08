"""Offline guardrails for the audit-only rejected-submit path.

This project has no JVM test dependency configured.  Keep this focused source-level
test beside the Android code: it prevents the expensive `wait_generation` call from
being reintroduced after a failed audit submit, without requiring a device or APK.
"""

from pathlib import Path
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "app/src/main/java/com/deviceagent/AgentHttpServer.kt"


class AuditSubmitFailureRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        start = cls.source.index("fun executeAuditSessionStatic(")
        end = cls.source.index("fun executeCaptureSessionStatic(", start)
        cls.audit = cls.source[start:end]

    def test_failed_non_copilot_submit_captures_and_continues_before_any_wait(self) -> None:
        failure = '''if (!step("submit") { flowEngine.submit(platform) }) {
                            // A missing SEND button / rejected tap cannot recover by
                            // waiting for generation. Save the visible failure state
                            // for diagnosis, then release the proxy session promptly.
                            capture("")
                            pr.status = "error"; pr.error = "submit failed"; continue
                        }'''
        self.assertIn(failure, self.audit)
        after_failure = self.audit[self.audit.index(failure) + len(failure):]
        self.assertLess(
            after_failure.index('Thread.sleep(if (platform == "gemini") 400 else 2000)'),
            after_failure.index('if (!step("wait_generation") { flowEngine.waitForGeneration'),
        )

    def test_successful_non_copilot_submit_still_waits_for_generation(self) -> None:
        guard = 'if (!step("submit") { flowEngine.submit(platform) }) {'
        after_guard = self.audit[self.audit.index(guard):]
        self.assertIn('Thread.sleep(if (platform == "gemini") 400 else 2000)', after_guard)
        self.assertIn(
            'if (!step("wait_generation") { flowEngine.waitForGeneration(timeoutSec = genTimeoutSec) }) {',
            after_guard,
        )
        self.assertIn('pr.status = "error"; pr.error = "generation timeout"; continue', after_guard)

    def test_failed_non_copilot_input_captures_and_continues_before_submit(self) -> None:
        failure = '''if (!step("input") { flowEngine.inputText(prompt) }) {
                            // Keep the visible transient state that left the composer
                            // undiscoverable. This remains audit-only and returns before
                            // submit/generation, so it adds no further page traffic.
                            capture("")
                            pr.status = "error"; pr.error = "input failed"; continue
                        }'''
        self.assertIn(failure, self.audit)
        after_failure = self.audit[self.audit.index(failure) + len(failure):]
        self.assertLess(
            after_failure.index('if (!step("submit") { flowEngine.submit(platform) }) {'),
            after_failure.index('if (!step("wait_generation") { flowEngine.waitForGeneration'),
        )

    def test_copilot_submit_path_is_unchanged(self) -> None:
        copilot_start = self.audit.index('if (platform == "copilot")')
        copilot_end = self.audit.index("} else {", copilot_start)
        copilot = self.audit[copilot_start:copilot_end]
        self.assertIn(
            'if (!step("submit") { flowEngine.copilot.submit() }) {\n'
            '                            pr.status = "error"; pr.error = "submit failed"; continue',
            copilot,
        )
        self.assertNotIn('capture("")', copilot)


if __name__ == "__main__":
    unittest.main()
