"""Repair evidence must contain the actual rank, not merely visible list items."""
import ast
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class ExpectedRankTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'audit_dispatch_http.py').read_text())
        nodes = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        self.answer, self.recover = Mock(return_value=True), Mock(return_value=None)
        ns = {'_screenshot_has_answer': self.answer, '_recover_rank_via_ocr': self.recover}
        exec(compile(ast.Module(body=[nodes['_screenshot_has_expected_rank']], type_ignores=[]), '<rank-proof>', 'exec'), ns)
        self.guard = ns['_screenshot_has_expected_rank']
        self.run = Mock(return_value=SimpleNamespace(returncode=0, stdout='[RANK: 2/3]'))
        self.parser = Mock(return_value=('success', '2', '3', 'rank'))
        ns2 = {'os': SimpleNamespace(path=SimpleNamespace(exists=lambda path: True)),
               '_OCR_BIN': '/mock/ocr', '_OCR_RANK_RE': re.compile(r'\[?rank:\s*(\d+)\s*/\s*(\d+\+?)\]?', re.I),
               'subprocess': SimpleNamespace(run=self.run), '_parse_rank_markers': self.parser}
        exec(compile(ast.Module(body=[nodes['_recover_rank_via_ocr']], type_ignores=[]), '<strict-recovery>', 'exec'), ns2)
        self.actual_recover = ns2['_recover_rank_via_ocr']

    def test_numbered_list_without_rank_is_not_proof(self):
        self.assertFalse(self.guard('/mock/shot.png', (2, 3)))
        self.answer.assert_called_once_with('/mock/shot.png', strict=True)
        self.recover.assert_called_once_with('/mock/shot.png', strict=True)

    def test_wrong_rank_rejected_and_exact_rank_accepted(self):
        self.recover.return_value = ('success', '1', '3', 'rank')
        self.assertFalse(self.guard('/mock/shot.png', (2, 3)))
        self.recover.return_value = ('success', '2', '3', 'rank')
        self.assertTrue(self.guard('/mock/shot.png', (2, 3)))

    def test_strict_image_failure_short_circuits_recovery(self):
        self.answer.return_value = False
        self.assertFalse(self.guard('/mock/shot.png', (2, 3)))
        self.recover.assert_not_called()

    def test_strict_recovery_rejects_nonzero_even_with_rank_stdout(self):
        self.run.return_value.returncode = 1
        self.assertIsNone(self.actual_recover('/mock/shot.png', strict=True))
        self.assertEqual(self.actual_recover('/mock/shot.png'), ('success', '2', '3', 'rank'))

    def test_strict_recovery_rejects_missing_ambiguous_or_normalized_ranks(self):
        for text in ('1. First\n2. Second', '[RANK: 3/2]', '[RANK: 0/3]', '[RANK: 2/3] [RANK: 1/3]'):
            with self.subTest(text=text):
                self.run.return_value.stdout = text
                self.assertIsNone(self.actual_recover('/mock/shot.png', strict=True))
        self.parser.assert_not_called()

    def test_strict_recovery_accepts_valid_rank(self):
        self.assertEqual(self.actual_recover('/mock/shot.png', strict=True), ('success', '2', '3', 'rank'))


if __name__ == '__main__':
    unittest.main()
