import unittest

from tools.build_stale_date_maps import build
from tools.verify_stale_consolidation import expected_date,verify


class StaleConsolidationDateTests(unittest.TestCase):
    def test_maps_exclude_run_day_and_keep_platform_specific_prior(self):
        rows=[{'keywordId':7,'platform':'ChatGPT','date':'2026-08-18'},
              {'keywordId':7,'platform':'Gemini','date':'2026-08-19'},
              {'keywordId':7,'platform':'ChatGPT','date':'2026-09-02'}]
        keyword,platform=build(rows,'2026-09-02')
        self.assertEqual(keyword['7'],'2026-08-19')
        self.assertEqual(platform['7|chatgpt'],'2026-08-18')

    def test_expected_date_is_pair_prior_plus_fourteen(self):
        expected=expected_date(7,'chatgpt',{'7':'2026-08-19'},
                               {'7|chatgpt':'2026-08-18'},{},'2026-09-02')
        self.assertEqual(expected,'2026-09-01')

    def test_never_ranked_uses_keyword_creation_date(self):
        expected=expected_date(8,'copilot',{}, {}, {8:{'createdAt':'2026-08-30T12:00:00Z'}},'2026-09-02')
        self.assertEqual(expected,'2026-08-30')

    def test_verifier_rejects_wrong_or_duplicate_dates(self):
        row={'campaign_id':'10007','platform':'chatgpt','date':'2026-09-01','status':'success'}
        self.assertEqual(verify([row],{'7':'2026-08-19'},{'7|chatgpt':'2026-08-18'},{},'2026-09-02'),1)
        with self.assertRaises(ValueError):verify([{**row,'date':'2026-09-02'}],{'7':'2026-08-19'},{'7|chatgpt':'2026-08-18'},{},'2026-09-02')
        with self.assertRaises(ValueError):verify([row,row],{'7':'2026-08-19'},{'7|chatgpt':'2026-08-18'},{},'2026-09-02')


if __name__=='__main__':unittest.main()
