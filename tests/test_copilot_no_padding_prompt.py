from pathlib import Path
import unittest


class CopilotNoPaddingPromptTests(unittest.TestCase):
    def test_prompt_forbids_placeholder_rank_padding(self):
        source=(Path(__file__).resolve().parents[1]/
                'app/src/main/java/com/deviceagent/AgentHttpServer.kt').read_text()
        self.assertIn("Never number placeholders",source)
        self.assertIn("set [RANK: N+1/N+1]",source)
        self.assertIn("If X is greater than 3, list three genuine named competitors",source)


if __name__=='__main__':unittest.main()
