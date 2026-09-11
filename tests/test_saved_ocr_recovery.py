import unittest
from audit_dispatch_http import _parse_rank_markers,_rank_inconsistent
from tools.recover_saved_ocr import recover


class SavedOcrRecoveryTests(unittest.TestCase):
    def test_approximate_numeric_rank_is_valid(self):
        self.assertEqual(_parse_rank_markers('[RANK: ~12/13]','ocr')[1:3],('12','13'))

    def test_safe_saved_pair_recovers_without_generation(self):
        row={'status':'ocr_no_answer','platform':'copilot','biz_name':'Target Co',
             'response_text':'1. One\n2. Two\n3. Three\n[RANK: ~12/13]'}
        fixed=recover(row,'1. One\n2. Two\n3. Three\n[RANK: ~12/13]')
        self.assertEqual((fixed['status'],fixed['rank_position'],fixed['rank_total']),('success','12','13'))

    def test_missing_list_or_mismatched_rank_stays_rejected(self):
        row={'status':'ocr_no_answer','platform':'copilot','biz_name':'Target Co',
             'response_text':'1. One\n2. Two\n3. Three\n[RANK: 12/13]'}
        self.assertIsNone(recover(row,'[RANK: 12/13]'))
        self.assertIsNone(recover(row,'1. One\n2. Two\n3. Three\n[RANK: 11/13]'))

    def test_zero_rank_is_not_top_three_fabrication(self):
        self.assertFalse(_rank_inconsistent('1. One\n2. Two\n3. Three\n[RANK: 0/8]','Target Co','copilot'))


if __name__=='__main__':unittest.main()
