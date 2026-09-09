import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from tools.copilot_offline_bootstrap import prepare,settle_wifi


class OfflineBootstrapTests(unittest.TestCase):
    def test_wifi_settlement_waits_for_late_bulk_download(self):
        clock=[0]
        def sleep(n):clock[0]+=n
        def adb(serial,*args,**kwargs):
            if args[:3]==('shell','ip','link'):return SimpleNamespace(returncode=0,stdout='1: lo: UP')
            n=1000 if clock[0]<120 else 12001000
            return SimpleNamespace(returncode=0,stdout=f' wlan0: {n} 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0')
        proof=settle_wifi('104',adb,now=lambda:clock[0],sleep=sleep)
        self.assertEqual(proof['wifi_bytes'],12000000)
        self.assertEqual(proof['elapsed_s'],150)

    def test_wifi_busy_refuses_paid_tunnel(self):
        clock=[0]
        def sleep(n):clock[0]+=n
        def adb(*args,**kwargs):
            return SimpleNamespace(returncode=0,stdout=f' wlan0: {int(clock[0]*1000000)} 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0')
        with self.assertRaises(ValueError):settle_wifi('104',adb,minimum_s=10,quiet_s=5,deadline_s=20,now=lambda:clock[0],sleep=sleep)

    def run_prepare(self,tunnel=False,steps=None):
        def adb(serial,*args,**kwargs):
            text=''
            if args[:3]==('shell','ip','link'):text='30: tun0: UP' if tunnel else '1: lo: UP'
            if args[:4]==('shell','settings','get','global'):text='null'
            if args[:3]==('shell','pm','clear'):text='Success'
            return SimpleNamespace(returncode=0,stdout=text)
        client=Mock(side_effect=adb)
        post=Mock(return_value={'step_log':steps or ['[copilot] reset_edge OK 55s']})
        replies=[io.BytesIO(json.dumps(r).encode()) for r in
                 ({'versionCode':86,'accessibility':True},{'running':False})]
        with patch('tools.copilot_offline_bootstrap.urllib.request.urlopen',side_effect=replies),patch('tools.copilot_offline_bootstrap.time.sleep'):
            result=prepare('adb-149145555W002883-test',19001,{'platform':'copilot'},client,post)
        return result,post

    def test_full_clear_reset_only_no_generation(self):
        result,post=self.run_prepare()
        self.assertEqual(result['status'],'full_reset_ready')
        self.assertEqual(result['prompts_submitted'],0)
        self.assertFalse(result['proxy_connected'])
        self.assertTrue(post.call_args.args[1]['copilotCacheResetOnly'])
        self.assertFalse(post.call_args.args[1]['copilotCacheTrial'])

    def test_refuses_tunnel_or_unexpected_generation(self):
        with self.assertRaises(ValueError):self.run_prepare(tunnel=True)
        with self.assertRaises(ValueError):self.run_prepare(steps=['[copilot] reset_edge OK','[copilot] submit OK'])

    def test_prep_precedes_proxy_and_is_default_off(self):
        root=Path(__file__).resolve().parents[1]
        source=(root/'audit_dispatch_http.py').read_text()
        self.assertLess(source.index("phase('offline_edge_prepare_done')"),source.index('phase("gost_start")'))
        self.assertIn("RANK_COPILOT_OFFLINE_BOOTSTRAP','0'",source)


if __name__=='__main__':unittest.main()
