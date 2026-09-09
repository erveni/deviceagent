"""Source-contract checks; physical behavior is verified by the metered trial."""
from pathlib import Path
import unittest


class CopilotNetworkGuardTests(unittest.TestCase):
    def test_confirmation_is_scoped_to_prepared_audit_not_daily(self):
        root=Path(__file__).resolve().parents[1]
        source=(root/'app/src/main/java/com/deviceagent/AgentHttpServer.kt').read_text()
        self.assertEqual(source.count('confirmNetworkError = prepared'),1)
        self.assertIn('pr.error = flowEngine.copilot.lastWaitFailure',source)

    def test_visible_exact_error_has_bounded_confirmation(self):
        root=Path(__file__).resolve().parents[1]
        source=(root/'app/src/main/java/com/deviceagent/EdgeCopilotFlow.kt').read_text()
        guard=source[source.index('fun waitForAnswer('):source.index('// ── answer capture')]
        for required in ('confirmNetworkError: Boolean = false','networkNode.isVisibleToUser',
                         'equals("Network issues", ignoreCase = true)','networkBounds.intersects',
                         '>= 3000L','lastWaitFailure = "copilot_network_issues"'):
            self.assertIn(required,guard)
