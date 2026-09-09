"""Use the actual host OCR functions without importing fleet dispatch side effects."""
import ast
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def production_ocr_namespace():
    tree = ast.parse((ROOT / 'audit_dispatch_http.py').read_text())
    functions = {'_screenshot_has_answer', '_recover_rank_via_ocr',
                 '_parse_rank_markers', '_screenshot_has_expected_rank'}
    constants = {'_OCR_BIN', '_OCR_WARNED', '_ANSWER_RE', '_WALL_RE',
                 '_OCR_RANK_RE', '_OCR_EG_LOOKBACK', '_OCR_EG_RE'}
    nodes = [n for n in tree.body if
             (isinstance(n, ast.FunctionDef) and n.name in functions) or
             (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in constants for t in n.targets))]
    ns = dict(os=os, re=re, subprocess=subprocess, __file__=str(ROOT / 'audit_dispatch_http.py'))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'production-ocr-only', 'exec'), ns)
    return ns


def validate_direct_answer(serial, keyword, result, out):
    from tools.gemini_same_answer_reframe import reframe_same_answer
    text = result.get('response_text', '')
    markers = list(re.finditer(r'\[RANK:\s*(\d+)\s*/\s*(\d+)\]', text, re.I))
    valid = (result.get('status') in ('success', 'completed') and not result.get('error')
             and len(markers) == 1 and not text[markers[0].end():].strip()
             and not re.search(r'You said|Gemini said', text, re.I)
             and all(re.search(rf'(?m)^\s*{n}[.)]\s*\S', text) for n in (1, 2, 3)))
    if not valid:
        return {'ok': False, 'reason': 'incomplete_or_prompt_contaminated_native_answer'}
    rank = tuple(map(int, markers[0].groups()))
    if not 0 < rank[0] <= rank[1]:
        return {'ok': False, 'reason': 'invalid_native_rank'}
    ns = production_ocr_namespace()
    evidence = reframe_same_answer(serial, keyword, rank, out / 'validated_rank.png',
        prompt_free=True, ocr_validator=lambda path: ns['_screenshot_has_expected_rank'](path, rank))
    (out / 'validated_frame.json').write_text(json.dumps(evidence, indent=2))
    return evidence
