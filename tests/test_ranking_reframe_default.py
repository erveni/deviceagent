"""Evaluate only the ranking launcher's recovery export, never launch a job."""
import os
from pathlib import Path
import subprocess
import unittest


class RankingRecoveryDefaultTests(unittest.TestCase):
    def value(self, override=None):
        source=(Path(__file__).resolve().parents[1]/'run_ranking_auto.sh').read_text()
        line=next(line for line in source.splitlines()
                  if line.startswith('export RANK_GEMINI_SAME_ANSWER_REFRAME='))
        env=os.environ.copy()
        env.pop('RANK_GEMINI_SAME_ANSWER_REFRAME',None)
        if override is not None:env['RANK_GEMINI_SAME_ANSWER_REFRAME']=override
        return subprocess.check_output(['bash','-c',line+'\nprintf %s "$RANK_GEMINI_SAME_ANSWER_REFRAME"'],
                                       env=env,text=True).strip()

    def test_ranking_default_enabled(self):
        self.assertEqual(self.value(),'1')

    def test_explicit_rollback_preserved(self):
        self.assertEqual(self.value('0'),'0')

    def test_explicit_enable_preserved(self):
        self.assertEqual(self.value('1'),'1')
