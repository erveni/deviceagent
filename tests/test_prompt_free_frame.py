"""Execute the production DOM guard against prompt visibility fixtures."""
import json
from pathlib import Path
import subprocess
import unittest
from tools.gemini_same_answer_reframe import _SELECTOR_JS, _safe_answer_clip


class PromptFreeFrameTests(unittest.TestCase):
    def test_visible_prompt_cannot_be_accepted_as_full_answer(self):
        script = r'''
const select = SELECTOR;
global.location={hostname:'gemini.google.com',protocol:'https:'};
global.innerHeight=1000;
global.getComputedStyle=()=>({display:'block',visibility:'visible',opacity:'1'});
let promptBottom=350;
const answer={innerText:'Answer [RANK: 2/3]',textContent:'Answer [RANK: 2/3]',
 getClientRects:()=>[{}],getBoundingClientRect:()=>({top:400,bottom:700}),querySelectorAll:()=>[]};
const prompt={getClientRects:()=>[{}],getBoundingClientRect:()=>({top:180,bottom:promptBottom})};
global.document={visibilityState:'visible',body:{innerText:'Tattoo'},querySelectorAll:s=>
 s==='model-response message-content'?[answer]:s==='user-query'?[prompt]:[]};
if(select('Tattoo',[2,3],false,null,null,true).full_answer_in_view)throw Error('accepted visible prompt');
promptBottom=159;
if(!select('Tattoo',[2,3],false,null,null,true).full_answer_in_view)throw Error('rejected hidden prompt');
promptBottom=350;
if(!select('Tattoo',[2,3],false,null,null,false).full_answer_in_view)throw Error('default changed');
'''.replace('SELECTOR', _SELECTOR_JS)
        result=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_host_requires_prompt_free_proof(self):
        source=(Path(__file__).resolve().parents[1]/'audit_dispatch_http.py').read_text()
        self.assertIn('_prompt_free or not _screenshot_has_expected_rank',source)
        self.assertIn('if _prompt_free and status in ("success", "no_rank") and not _prompt_free_verified:',source)

    def test_clip_requires_complete_finite_bounded_geometry(self):
        clip={'x':0,'y':288,'width':411,'height':272,'scale':1}
        good={'ok':True,'rank_in_view':True,'answer_fits':True,'answer_clip':clip}
        self.assertEqual(_safe_answer_clip(good),clip)
        for field in ('ok','rank_in_view','answer_fits'):
            self.assertIsNone(_safe_answer_clip(good | {field:False}))
        for field,value in [('x',-1),('width',0),('height',5000),('scale',2),('y',float('nan')),('width',True)]:
            self.assertIsNone(_safe_answer_clip(good | {'answer_clip':clip | {field:value}}))
