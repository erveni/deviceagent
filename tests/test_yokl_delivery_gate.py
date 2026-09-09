import json
from pathlib import Path
import tempfile
import unittest
from tools.yokl_delivery_gate import require_chatgpt_proof


class DeliveryGateTests(unittest.TestCase):
    def test_requires_real_success_cost_identity_and_rollback(self):
        leg={'status':'valid','successful_pairs':1,'actual_pairs':[['3635221','chatgpt']],'used_mb':4.5}
        meter={'status':'complete','keywords':[5221],'legs':[leg]}
        wrapper={'status':'complete','restored_health':{'versionCode':79,'accessibility':True},'restored_no_tun0':True}
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            for folder in ('yokl_chatgpt_one_20260909_metered','yokl_chatgpt_one_20260909_direct'):
                (root/folder).mkdir()
            def save():
                (root/'yokl_chatgpt_one_20260909_metered/report.json').write_text(json.dumps(meter))
                (root/'yokl_chatgpt_one_20260909_direct/report.json').write_text(json.dumps(wrapper))
            save();self.assertEqual(require_chatgpt_proof(root)['used_mb'],4.5)
            for target,key,bad in [(leg,'successful_pairs',0),(leg,'used_mb',15),
                (leg,'used_mb',0),(leg,'actual_pairs',[['3635221','gemini']]),
                (meter,'status','candidate-running'),(wrapper,'restored_no_tun0',False),
                (wrapper['restored_health'],'versionCode',84),
                (wrapper['restored_health'],'accessibility',False)]:
                old=target[key];target[key]=bad;save()
                with self.assertRaises(ValueError):require_chatgpt_proof(root)
                target[key]=old


if __name__=='__main__':unittest.main()
