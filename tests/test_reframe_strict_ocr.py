"""Offline tests: compile only the OCR guard, never import fleet/proxy runtime."""
import ast
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class StrictReframeOCRTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).resolve().parents[1] / 'audit_dispatch_http.py'
        tree = ast.parse(source.read_text())
        selected = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == '_screenshot_has_answer':
                selected.append(node)
            elif isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id in {'_ANSWER_RE', '_WALL_RE'}
                    for target in node.targets):
                selected.append(node)
        assert len(selected) == 3, 'Expected exactly two regexes and the OCR guard'
        cls.isolated = compile(ast.Module(body=selected, type_ignores=[]), str(source), 'exec')

    def setUp(self):
        self.run = Mock(return_value=SimpleNamespace(returncode=0, stdout='[RANK: 2/5]'))
        self.env = {}
        self.exists = Mock(return_value=True)
        namespace = {
            're': re,
            'os': SimpleNamespace(environ=self.env, path=SimpleNamespace(exists=self.exists)),
            'subprocess': SimpleNamespace(run=self.run),
            '_OCR_BIN': '/mock/ocr', '_OCR_WARNED': False,
            'print': Mock(),
        }
        exec(self.isolated, namespace)
        self.guard = namespace['_screenshot_has_answer']

    def test_disabled_ocr_fails_strict_preserves_default(self):
        self.env['OCR_VALIDATE_SCREENSHOT'] = '0'
        self.assertFalse(self.guard('/mock/frame.png', strict=True))
        self.assertTrue(self.guard('/mock/frame.png'))
        self.run.assert_not_called()

    def test_missing_ocr_fails_strict_preserves_default(self):
        self.exists.side_effect = lambda path: path != '/mock/ocr'
        self.assertFalse(self.guard('/mock/frame.png', strict=True))
        self.assertTrue(self.guard('/mock/frame.png'))
        self.run.assert_not_called()

    def test_missing_screenshot_fails_strict_preserves_default(self):
        self.exists.side_effect = lambda path: path != '/mock/frame.png'
        self.assertFalse(self.guard('/mock/frame.png', strict=True))
        self.assertTrue(self.guard('/mock/frame.png'))
        self.run.assert_not_called()

    def test_empty_path_fails_strict_preserves_default(self):
        self.assertFalse(self.guard('', strict=True))
        self.assertTrue(self.guard(''))
        self.run.assert_not_called()

    def test_timeout_fails_strict_preserves_default(self):
        self.run.side_effect = subprocess.TimeoutExpired('mock OCR', 40)
        self.assertFalse(self.guard('/mock/frame.png', strict=True))
        self.assertTrue(self.guard('/mock/frame.png'))

    def test_execution_error_fails_strict_preserves_default(self):
        self.run.side_effect = OSError('mock executable unavailable')
        self.assertFalse(self.guard('/mock/frame.png', strict=True))
        self.assertTrue(self.guard('/mock/frame.png'))

    def test_nonzero_exit_cannot_verify_rank_in_strict_mode(self):
        self.run.return_value = SimpleNamespace(returncode=1, stdout='[RANK: 2/5]')
        self.assertFalse(self.guard('/mock/frame.png', strict=True))
        self.assertTrue(self.guard('/mock/frame.png'))

    def test_valid_rank_accepted_in_both_modes_with_bounded_command(self):
        self.assertTrue(self.guard('/mock/frame.png', strict=True))
        self.assertTrue(self.guard('/mock/frame.png'))
        self.run.assert_called_with(['/mock/ocr', '/mock/frame.png'],
                                    capture_output=True, text=True, timeout=40)

    def test_blank_or_nonanswer_rejected_in_both_modes(self):
        for text in ['', 'Sign in to continue', 'An unrelated browser page']:
            with self.subTest(text=text):
                self.run.return_value = SimpleNamespace(returncode=0, stdout=text)
                self.assertFalse(self.guard('/mock/frame.png', strict=True))
                self.assertFalse(self.guard('/mock/frame.png'))

    def test_captcha_overrides_rank_marker(self):
        self.run.return_value = SimpleNamespace(returncode=0, stdout='Verify you are human [RANK: 2/5]')
        self.assertFalse(self.guard('/mock/frame.png', strict=True))
        self.assertFalse(self.guard('/mock/frame.png'))


if __name__ == '__main__':
    unittest.main()
