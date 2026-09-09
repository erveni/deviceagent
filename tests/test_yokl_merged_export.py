import unittest
from tools.export_yokl_merged import select_records


class MergedExportTests(unittest.TestCase):
    def row(self,**changes):
        return dict(dict(campaign_id='3635221',client_id='329',platform='gemini',status='success',rank_position='4',rank_total='4'),**changes)

    def test_failed_attempt_does_not_replace_success(self):
        result=select_records([self.row(status='error'),self.row()])
        self.assertEqual(len(result),1)

    def test_duplicate_success_requires_explicit_review(self):
        with self.assertRaises(ValueError):select_records([self.row(),self.row()])

    def test_wrong_client_and_bad_rank_rejected(self):
        for changes in ({'client_id':'330'},{'campaign_id':'3635226'},{'rank_position':'5'}):
            with self.assertRaises(ValueError):select_records([self.row(**changes)])


if __name__=='__main__':unittest.main()
