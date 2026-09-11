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

    def test_public_name_matches_campaign_location_suffix(self):
        text="1. Today's Dentistry — local practice\n2. Fisher Dentistry\n3. Nampa Smiles\n[RANK: 1/8]"
        self.assertFalse(_rank_inconsistent(text,"Today's Dentistry Nampa",'copilot'))

    def test_public_name_matches_pipe_search_descriptor(self):
        text='1. Brazil Bronze Tanning Salon NYC — airbrush tans\n2. Tanning Spa NYC\n3. SUGARED + BRONZED\n[RANK: 1/8]'
        self.assertFalse(_rank_inconsistent(
            text,'Brazil Bronze Tanning Salon NYC | Spray Tan NYC, New York','copilot'))

    def test_location_suffix_does_not_match_short_generic_name(self):
        text='1. Crown Roofing\n2. Other\n3. Third\n[RANK: 1/8]'
        self.assertTrue(_rank_inconsistent(text,'Crown Roofing Dallas Extra','copilot'))


if __name__=='__main__':unittest.main()
