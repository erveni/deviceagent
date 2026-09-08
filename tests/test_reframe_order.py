"""AST-isolated ordering/selection tests; no dispatcher or device imports."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


def calls(node, name):
    return [n for n in ast.walk(node) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name) and n.func.id == name]


def has_not(node, name):
    return any(isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not)
               and isinstance(n.operand, ast.Name) and n.operand.id == name
               for n in ast.walk(node))


class ReframeOrderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse((Path(__file__).resolve().parents[1] / 'audit_dispatch_http.py').read_text())
        cls.repairs = sorted(calls(cls.tree, 'reframe_same_answer'), key=lambda n: n.lineno)
        assert len(cls.repairs) == 2
        guarded = [n for n in ast.walk(cls.tree) if isinstance(n, ast.If)
                   and 'RANK_GEMINI_SAME_ANSWER_REFRAME' in ast.unparse(n.test)
                   and calls(n, 'reframe_same_answer')]
        cls.early, cls.late = sorted(guarded, key=lambda n: n.lineno)
        # Choose the smallest enclosing conditional of the main CDP selection,
        # excluding the inner chatgpt-vs-other routing conditional.
        cls.cdp = next(n for n in ast.walk(cls.tree) if isinstance(n, ast.If)
                       and has_not(n.test, 'ss_local')
                       and calls(n, '_cdp_strip_map_screenshot'))

    def test_early_repair_precedes_dom_cleanup(self):
        cleanup = calls(self.cdp, '_cdp_strip_map_screenshot')[0]
        self.assertLess(self.repairs[0].lineno, cleanup.lineno)
        self.assertLess(cleanup.lineno, self.repairs[1].lineno)

    def test_both_paths_default_off(self):
        for node in (self.early, self.late):
            with self.subTest(line=node.lineno):
                env_reads = [n for n in ast.walk(node.test) if isinstance(n, ast.Call)
                             and any(isinstance(a, ast.Constant)
                                     and a.value == 'RANK_GEMINI_SAME_ANSWER_REFRAME'
                                     for a in n.args)]
                self.assertEqual(len(env_reads), 1)
                self.assertEqual(ast.literal_eval(env_reads[0].args[1]), '0')
                # Short circuit must avoid any phone/screenshot call by default.
                self.assertFalse(eval(compile(ast.Expression(node.test), '<guard>', 'eval'),
                                      {'os': SimpleNamespace(environ={})}))

    def test_repaired_screenshot_skips_all_cdp_selection(self):
        namespace = {'ss_local': '/mock/repaired.png', 'capture_prompt': None,
                     'platform': 'gemini', 'status': 'success',
                     'os': SimpleNamespace(environ={}),
                     '_cdp_strip_map_screenshot': Mock(), '_cdp_js_frame_screenshot': Mock()}
        exec(compile(ast.Module(body=[self.cdp], type_ignores=[]), '<selection>', 'exec'), namespace)
        namespace['_cdp_strip_map_screenshot'].assert_not_called()
        namespace['_cdp_js_frame_screenshot'].assert_not_called()
        self.assertEqual(namespace['ss_local'], '/mock/repaired.png')

    def test_failed_early_repair_preserves_cdp_fallback(self):
        strip = Mock(return_value='/mock/legacy-cdp.png')
        namespace = {'ss_local': '', 'capture_prompt': None, 'platform': 'gemini',
                     'status': 'success', 'os': SimpleNamespace(environ={}),
                     'serial': 'dummy', 'device_idx': 0, 'keyword_id': 42,
                     '_cdp_strip_map_screenshot': strip, '_cdp_js_frame_screenshot': Mock()}
        exec(compile(ast.Module(body=[self.cdp], type_ignores=[]), '<selection>', 'exec'), namespace)
        strip.assert_called_once_with('dummy', 0, 'gemini', 42)
        self.assertEqual(namespace['ss_local'], '/mock/legacy-cdp.png')

    def test_both_repair_callbacks_require_strict_ocr(self):
        for repair in self.repairs:
            with self.subTest(line=repair.lineno):
                callback = next(k.value for k in repair.keywords if k.arg == 'ocr_validator')
                self.assertIsInstance(callback, ast.Lambda)
                guard = calls(callback, '_screenshot_has_expected_rank')
                self.assertEqual(len(guard), 1)
                self.assertEqual(len(guard[0].args), 2)
        expected_guard = next(n for n in self.tree.body if isinstance(n, ast.FunctionDef)
                              and n.name == '_screenshot_has_expected_rank')
        for name in ('_screenshot_has_answer', '_recover_rank_via_ocr'):
            call = calls(expected_guard, name)[0]
            self.assertTrue(ast.literal_eval(next(k.value for k in call.keywords if k.arg == 'strict')))

    def test_no_second_repair_after_early_attempt(self):
        self.assertTrue(has_not(self.late.test, '_reframe_attempted'))
        assignments = [n for n in ast.walk(self.early) if isinstance(n, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == '_reframe_attempted'
                               for t in n.targets)]
        self.assertEqual(len(assignments), 1)
        self.assertIs(ast.literal_eval(assignments[0].value), True)
        self.assertLess(assignments[0].lineno, self.repairs[0].lineno)


if __name__ == '__main__':
    unittest.main()
