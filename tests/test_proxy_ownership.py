"""Offline guards against accidentally importing the sibling proxy manager."""
import ast
from pathlib import Path
import unittest
from unittest.mock import patch

from device_agent_proxy import gost_manager as g

ROOT = Path(__file__).resolve().parents[1]
CALLERS = (
    'audit_dispatch.py', 'audit_dispatch_http.py', 'copilot_geo_test.py',
    'probe_zips.py', 'probe_zips_expanded.py', 'test_residential_one.py',
    'tools/measure_idle_proxy.py',
)


class ProxyOwnershipTests(unittest.TestCase):
    def test_module_and_configuration_are_local(self):
        self.assertEqual(Path(g.__file__).resolve(),
                         ROOT / 'device_agent_proxy/gost_manager.py')
        self.assertEqual(Path(g.REPO_ROOT), ROOT)
        self.assertTrue((ROOT / 'device_agent_proxy/rayobyte_no_pool_cities.json').is_file())

    def test_callers_import_explicit_local_package(self):
        for name in CALLERS:
            with self.subTest(name=name):
                tree = ast.parse((ROOT / name).read_text())
                imports = [node.module for node in ast.walk(tree)
                           if isinstance(node, ast.ImportFrom)]
                self.assertIn('device_agent_proxy.gost_manager', imports)
                self.assertNotIn('gost_manager', imports)

    def test_env_loader_preserves_exported_settings(self):
        from unittest.mock import mock_open
        with patch.dict(g.os.environ, {'PROXY_PASSWORD': 'exported-test'}, clear=True), \
             patch.object(g.os.path, 'exists', return_value=True), \
             patch('builtins.open', mock_open(read_data="PROXY_PASSWORD='file-test'\nPROXY_PROVIDER='evomi'\n")):
            g._load_env_file('unused-test-path')
            self.assertEqual(g.os.environ['PROXY_PASSWORD'], 'exported-test')
            self.assertEqual(g.os.environ['PROXY_PROVIDER'], 'evomi')
