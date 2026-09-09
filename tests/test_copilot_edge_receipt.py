import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from tools.copilot_edge_receipt import consume_receipt


class ReceiptTests(unittest.TestCase):
    def test_scope_age_health_and_single_use(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            folder=root/'copilot_bootstrap_one_20260910_wrapper';folder.mkdir()
            path=folder/'edge_ready.json'
            serial='adb-149145555W002883-test'
            proof=dict(status='full_reset_ready',serial=serial,keyword_id=5225,proxy_connected=False,
                       prompts_submitted=0,at=time.time(),steps=['[copilot] reset_edge OK 40s'])
            path.write_text(json.dumps(proof))
            health=dict(versionCode=86,accessibility=True)
            with patch('tools.copilot_edge_receipt.__file__',str(root/'tools/receipt.py')):
                for key,value in [('at',time.time()-901),('proxy_connected',True),('prompts_submitted',1),
                                  ('steps',['[copilot] reset_edge OK','[copilot] submit OK'])]:
                    bad=dict(proof,**{key:value});path.write_text(json.dumps(bad))
                    with self.assertRaises(ValueError):consume_receipt(path,serial,5225,health)
                path.write_text(json.dumps(proof))
                with self.assertRaises(ValueError):consume_receipt(path,serial,5224,health)
                with self.assertRaises(ValueError):consume_receipt(path,serial,5225,dict(health,versionCode=85))
                consume_receipt(path,serial,5225,health)
                with self.assertRaises(FileExistsError):consume_receipt(path,serial,5225,health)


if __name__=='__main__':unittest.main()
