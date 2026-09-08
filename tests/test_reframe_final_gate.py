"""Execute actual final opt-in conditional without importing dispatcher runtime."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class FinalReframeGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'audit_dispatch_http.py').read_text())
        matches = [n for n in ast.walk(tree) if isinstance(n, ast.If)
                   and 'RANK_GEMINI_SAME_ANSWER_REFRAME' in ast.unparse(n.test)
                   and any(isinstance(statement, ast.Assign)
                           and any(isinstance(target, ast.Name) and target.id == 'status'
                                   for target in statement.targets)
                           and isinstance(statement.value, ast.Constant)
                           and statement.value.value == 'ocr_no_answer'
                           for statement in n.body)]
        assert len(matches) == 1
        cls.code = compile(ast.Module(body=matches, type_ignores=[]), '<actual-final-gate>', 'exec')

    def apply_gate(self, *, enabled=True, correct_rank=False, platform='gemini', capture_prompt=None):
        proof = Mock(return_value=correct_rank)
        namespace = {'os': SimpleNamespace(environ={'RANK_GEMINI_SAME_ANSWER_REFRAME': '1'} if enabled else {}),
                     'platform': platform, 'capture_prompt': capture_prompt,
                     'status': 'success', '_txt_rank': ('success', '2', '3', 'text'),
                     'ss_local': '/mock/list.png', '_screenshot_has_expected_rank': proof,
                     '_answer_ok': Mock(return_value=True)}
        exec(self.code, namespace)
        return namespace, proof

    def test_generic_list_without_numeric_rank_demoted_when_enabled(self):
        namespace, proof = self.apply_gate()
        self.assertEqual(namespace['status'], 'ocr_no_answer')
        proof.assert_called_once_with('/mock/list.png', (2, 3))
        namespace['_answer_ok'].assert_not_called()

    def test_correct_visible_rank_preserves_success(self):
        namespace, proof = self.apply_gate(correct_rank=True)
        self.assertEqual(namespace['status'], 'success')
        proof.assert_called_once_with('/mock/list.png', (2, 3))

    def test_default_off_preserves_historical_success_without_new_ocr(self):
        namespace, proof = self.apply_gate(enabled=False)
        self.assertEqual(namespace['status'], 'success')
        proof.assert_not_called()

    def test_other_platform_and_capture_modes_remain_unchanged(self):
        for args in ({'platform': 'chatgpt'}, {'capture_prompt': 'capture request'}):
            with self.subTest(args=args):
                namespace, proof = self.apply_gate(**args)
                self.assertEqual(namespace['status'], 'success')
                proof.assert_not_called()


if __name__ == '__main__':
    unittest.main()
