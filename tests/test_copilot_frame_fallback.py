import copy
import unittest
from unittest.mock import Mock
from tools.copilot_frame_fallback import capture_missing


class FrameFallbackTests(unittest.TestCase):
    def response(self):
        return dict(prompt='test',running=False,step_log=['[copilot] frame_shot OK'],
            platforms={'copilot':dict(response_text='answer [RANK: 1/8]',ranking_position=1,ranking_total='8',screenshot_path='',screenshot_b64='',error='')})

    def test_missing_image_only_same_idle_answer(self):
        r=self.response();cap=Mock(return_value=b'\x89PNG\r\n\x1a\nbytes')
        self.assertTrue(capture_missing('adb-149145555W002883-test',r,lambda:copy.deepcopy(r),cap))
        self.assertEqual(cap.call_count,1)
        for change in ('busy','changed','already_saved','unframed'):
            original=self.response();current=copy.deepcopy(original)
            if change=='busy':current['running']=True
            if change=='changed':current['platforms']['copilot']['response_text']='different'
            if change=='already_saved':original['platforms']['copilot']['screenshot_path']='existing.png'
            if change=='unframed':original['step_log']=[]
            cap.reset_mock()
            self.assertIsNone(capture_missing('adb-149145555W002883-test',original,lambda:current,cap))
            cap.assert_not_called()


if __name__=='__main__':unittest.main()
