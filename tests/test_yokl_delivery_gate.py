import json
import csv
from pathlib import Path
import tempfile
import unittest
from tools.yokl_delivery_gate import require_chatgpt_proof, require_copilot_proof, require_copilot_final_retry


class DeliveryGateTests(unittest.TestCase):
    def test_final_retry_cannot_repeat_success_or_unsettled_run(self):
        meter={'status':'complete','keywords':[5223,5224,5225],
               'legs':[{'status':'valid','successful_pairs':2,'used_mb':44}]}
        rows=[dict(campaign_id=str(3630000+k),client_id='329',platform='copilot',
                   status='ocr_no_answer' if k==5225 else 'success',
                   rank_position='' if k==5225 else '1') for k in (5223,5224,5225)]
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/'yokl_copilot_three_20260909_metered'
            (path/'candidate').mkdir(parents=True)
            def save():
                (path/'report.json').write_text(json.dumps(meter))
                with (path/'candidate/results.csv').open('w') as stream:
                    writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
            save();require_copilot_final_retry(name)
            for target,key,bad in [(meter,'status','running'),(meter['legs'][0],'used_mb',60),
                                   (rows[2],'status','success'),(rows[2],'platform','chatgpt'),
                                   (rows[2],'rank_position','1')]:
                old=target[key];target[key]=bad;save()
                with self.assertRaises(ValueError):require_copilot_final_retry(name)
                target[key]=old

    def test_copilot_continuation_requires_measured_success(self):
        leg={'status':'valid','successful_pairs':1,'actual_pairs':[['3635222','copilot']],'used_mb':12}
        meter={'status':'complete','keywords':[5222],'legs':[leg]}
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/'yokl_copilot_one_20260909_metered';path.mkdir()
            (path/'report.json').write_text(json.dumps(meter))
            self.assertEqual(require_copilot_proof(name)['used_mb'],12)
            for key,bad in [('used_mb',30),('successful_pairs',0),('actual_pairs',[['3635222','chatgpt']])]:
                old=leg[key];leg[key]=bad;(path/'report.json').write_text(json.dumps(meter))
                with self.assertRaises(ValueError):require_copilot_proof(name)
                leg[key]=old

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
