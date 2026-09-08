"""Mock the phone/CDP boundary: exercise actual helper control flow offline."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location(
    'reframe_layout_under_test', Path(__file__).resolve().parents[1] / 'tools/gemini_same_answer_reframe.py')
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)


class ReframeLayoutTests(unittest.TestCase):
    def run_helper(self, *, clipped=False, fit_at=0.65, ocr=True, restore_ok=True):
        client = Mock()
        client.call.return_value = {'result': {'result': {'subtype': 'node', 'objectId': 'original-node'}}}
        module = ModuleType('gemini_cdp_capture')
        module.CDP = Mock(return_value=client)
        base = {'ok': True, 'text': '[RANK: 2/3]', 'rank_in_view': True,
                'full_answer_in_view': False}
        final = base | {'full_answer_in_view': not clipped}
        # Candidate, move and initial frame are clipped.  Each attempted zoom has
        # a scroll evaluation followed by a guarded frame evaluation.
        snapshots = [base, base, base]
        for zoom in HELPER._READABLE_ZOOM_LEVELS:
            snapshots.extend([base, final if not clipped and zoom == fit_at else base])
            if not clipped and zoom == fit_at:
                break
        if not clipped:
            snapshots.append(final)  # post-screencap identity/layout check
        def operation(_client, _node, function, _arguments=()):
            if function == HELPER._ZOOM_SAVE:
                return {'value': '0.8', 'priority': 'important'}
            if function == HELPER._ZOOM_RESTORE:
                return {'ok': restore_ok}
            return {'ok': True}
        operations = Mock(side_effect=operation)
        def adb(args, **kwargs):
            if 'localabstract:chrome_devtools_remote_123' in args:
                return b'19876'
            if '/proc/net/unix' in args:
                return b'@chrome_devtools_remote_123\n'
            if 'screencap' in args:
                return b'\x89PNG\r\n\x1a\nmock'
            if '--remove' in args:
                return b''
            raise AssertionError('Unexpected device command ' + repr(args))
        tabs = [{'id': 'target', 'type': 'page', 'url': 'https://gemini.google.com/app',
                 'webSocketDebuggerUrl': 'ws://localhost/devtools/page/target'}]
        with tempfile.TemporaryDirectory(prefix='reframe-layout-test-') as directory:
            with patch.dict(sys.modules, {'gemini_cdp_capture': module}), \
                    patch.object(HELPER, '_evaluate', side_effect=snapshots), \
                    patch.object(HELPER, '_on_answer', operations), \
                    patch.object(HELPER.subprocess, 'check_output', side_effect=adb) as device, \
                    patch.object(HELPER.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(tabs).encode())), \
                    patch.object(HELPER.time, 'sleep'):
                validator = Mock(return_value=ocr)
                result = HELPER.reframe_same_answer('dummy', 'keyword', (2, 3),
                                                    Path(directory) / 'shot.png', ocr_validator=validator)
                operations.assert_called_with(client, 'original-node', HELPER._ZOOM_RESTORE,
                                              ('0.8', 'important'))
                self.assertTrue(any('--remove' in call.args[0] for call in device.call_args_list))
                client.close.assert_called_once()
                if clipped:
                    validator.assert_not_called()
                    self.assertFalse(any('screencap' in call.args[0] for call in device.call_args_list))
                return result

    def test_fit_after_zoom_succeeds_and_restores_original(self):
        result = self.run_helper()
        self.assertTrue(result['ok'])
        self.assertTrue(result['full_answer_in_view'])
        self.assertEqual(result['layout_zoom'], 0.65)

    def test_ladder_reaches_readable_half_size_without_relaxing_guard(self):
        result = self.run_helper(fit_at=0.50)
        self.assertTrue(result['ok'])
        self.assertEqual(result['layout_zoom'], 0.50)

    def test_still_clipped_returns_sanitized_geometry_after_all_readable_levels(self):
        result = self.run_helper(clipped=True)
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'full_answer_clipped_or_changed')
        self.assertEqual(result['layout_zoom'], 0.50)
        self.assertEqual(set(result['frame_diagnostics']), {
            'ok', 'reason', 'rank_in_view', 'full_answer_in_view', 'safe_band',
            'answer_rect', 'alignment_adjustments', 'rank_container_tag'})

    def test_still_clipped_fails_before_capture_and_restores(self):
        result = self.run_helper(clipped=True)
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'full_answer_clipped_or_changed')

    def test_ocr_failure_still_restores(self):
        result = self.run_helper(ocr=False)
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'caller_ocr_rejected')

    def test_restoration_failure_cannot_report_success(self):
        result = self.run_helper(restore_ok=False)
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'original_layout_restore_failed')


if __name__ == '__main__':
    unittest.main()
