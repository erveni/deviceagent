"""Real screenshot writer regression, isolated from all fleet imports."""
import ast
import base64
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import unittest


class ReframeSourceArtifactTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / 'audit_dispatch_http.py'
        tree = ast.parse(source.read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == '_write_b64_screenshot')
        self.temp = tempfile.TemporaryDirectory(prefix='reframe-writer-test-')
        self.addCleanup(self.temp.cleanup)
        namespace = {'datetime': datetime, 'timezone': timezone, 'os': os,
                     'base64': base64, 'AUDIT_RESULTS_DIR': self.temp.name}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
        self.writer = namespace['_write_b64_screenshot']
        # Valid one-pixel PNG, decoded by the real writer into only this tempdir.
        self.image = ('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC'
                      'AAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')

    def test_reframe_source_is_written_and_preserved_separately(self):
        paths = [self.writer(self.image, 'gemini', 64, artifact=artifact)
                 for artifact in ('', 'app_original', 'reframe_source')]
        self.assertEqual(len(set(paths)), 3)
        for path in paths:
            self.assertTrue(Path(path).is_relative_to(self.temp.name))
            self.assertEqual(Path(path).read_bytes(), base64.b64decode(self.image))
        self.assertTrue(paths[-1].endswith('_reframe_source.png'))

    def test_unknown_or_pathlike_artifact_stays_rejected(self):
        for artifact in ('unknown', '../escape', '/tmp/escape', 'reframe_source/extra'):
            with self.subTest(artifact=artifact), self.assertRaises(ValueError):
                self.writer(self.image, 'gemini', 64, artifact=artifact)
        self.assertEqual(list(Path(self.temp.name).rglob('*.png')), [])


if __name__ == '__main__':
    unittest.main()
