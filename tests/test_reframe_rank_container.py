"""Real selector against parsed HTML fixtures, offline with Node's JS engine."""
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

SPEC = importlib.util.spec_from_file_location(
    'rank_container_helper', Path(__file__).resolve().parents[1] / 'tools/gemini_same_answer_reframe.py')
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)


class FixtureParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.root = {'tag': 'message-content', 'children': []}
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = {'tag': tag, 'children': []}
        self.stack[-1]['children'].append(node)
        self.stack.append(node)

    def handle_endtag(self, tag):
        self.stack.pop()

    def handle_data(self, data):
        self.stack[-1]['children'].append(data)


class RankContainerTests(unittest.TestCase):
    def check_markup(self, markup, expected_tag=None, answer_override=None):
        parser = FixtureParser()
        parser.feed(markup)
        script = r"""
const select=SELECTOR;
let selected=null;
function build(source){
 const children=source.children.map(c=>typeof c==='string'?c:build(c));
 const descendants=()=>children.filter(c=>typeof c!=='string').flatMap(c=>[c,...c.querySelectorAll('*')]);
 const text=children.map(c=>typeof c==='string'?c:c.textContent).join('');
 return {tag:source.tag,innerText:text,textContent:text,querySelectorAll:descendants,
   getClientRects:()=>[{}],getBoundingClientRect:()=>({top:200,bottom:500}),
   scrollIntoView(){selected=this.tag}};
}
const answer=build(FIXTURE);
const override=OVERRIDE;if(override!==null)answer.innerText=override;
global.document={visibilityState:'visible',body:{innerText:'mobile app development'},
 querySelectorAll:s=>s==='model-response message-content'?[answer]:[]};
global.location={hostname:'gemini.google.com',protocol:'https:'};global.innerHeight=1000;
global.getComputedStyle=()=>({display:'block',visibility:'visible',opacity:'1'});
const result=select('mobile app development',[2,3],true,null);
console.log(JSON.stringify({result,selected}));
""".replace('SELECTOR', HELPER._SELECTOR_JS).replace('FIXTURE', json.dumps(parser.root)).replace('OVERRIDE', json.dumps(answer_override))
        response = subprocess.run(['node', '-e', script], text=True, capture_output=True, timeout=10, check=True)
        evidence = json.loads(response.stdout)
        if expected_tag is None:
            self.assertFalse(evidence['result']['ok'])
            self.assertEqual(evidence['result']['reason'], 'ambiguous_rank_container')
            self.assertIsNone(evidence['selected'])
        else:
            self.assertTrue(evidence['result']['ok'])
            self.assertEqual(evidence['result']['rank_container_tag'], expected_tag)
            self.assertEqual(evidence['selected'], 'message-content')

    def test_actual_rank_paragraph_has_inline_business_link(self):
        # Structure/text from the real failed paid answer; Angular comments and
        # styling attributes omitted because they do not affect containment.
        self.check_markup('<p data-path-to-node="7"><response-element>'
                          '<map-location-reference-link-block><button><span>Carrot Software</span>'
                          '</button></map-location-reference-link-block></response-element>'
                          ' ranks approximately around position 2.\n[RANK: 2/3]</p>', 'p')

    def test_marker_split_across_inline_spans(self):
        self.check_markup('<p><span>[RANK: </span><b>2</b><span>/3]</span></p>', 'p')

    def test_smallest_complete_marker_descendant_wins(self):
        self.check_markup('<p>Some answer <span>[RANK: 2/3]</span></p>', 'span')

    def test_two_incomparable_matching_containers_fail_closed(self):
        self.check_markup('<p>[RANK: 2/3]</p><p>[RANK: 2/3]</p>',
                          answer_override='Rendered answer [RANK: 2/3]')


if __name__ == '__main__':
    unittest.main()
