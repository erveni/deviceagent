from collections import Counter
import unittest
from daily_prompt_plan import campaign_slots,cycle_day,result_key,remaining_jobs,PROMPT_TYPES,validate_typed_jobs,validate_typed_plan,reconcile_legacy_credits


class DailyPlanTests(unittest.TestCase):
    def items(self,n=5,campaign=1,business=2):
        return [dict(kw=dict(id=i+1,aeoPlanId=campaign),biz=dict(id=business)) for i in range(n)]

    def test_eight_even_with_one_keyword_and_priority_sized_inputs(self):
        for n in (1,5,8,12,20):
            slots=campaign_slots(self.items(n),'2026-09-09')
            self.assertEqual(len(slots),8)
            self.assertEqual(Counter(s['platform'] for s in slots),Counter(chatgpt=3,gemini=3,copilot=2))
            self.assertEqual(len({s['daily_slot_id'] for s in slots}),8)

    def test_cycle_coverage_and_location_identity(self):
        coverage={t:set() for t in PROMPT_TYPES}
        for day in range(9,23):
            for slot in campaign_slots(self.items(),f'2026-09-{day:02d}'):
                coverage[slot['prompt_type']].add(slot['platform'])
        self.assertTrue(all(len(p)==3 for p in coverage.values()))
        self.assertEqual(cycle_day('2026-09-23'),0)
        self.assertNotEqual(campaign_slots(self.items(business=2),'2026-09-09')[0]['daily_slot_id'],
                            campaign_slots(self.items(business=3),'2026-09-09')[0]['daily_slot_id'])

    def test_retry_uses_slot_not_repeated_keyword_platform(self):
        jobs=[dict(s,client_id=9,campaign_id=1,biz_name='business',keyword_text='one keyword')
              for s in campaign_slots(self.items(1),'2026-09-09')]
        plan={'waves':[jobs]}
        rows=[dict(jobs[0],status='success'),dict(jobs[0],status='success')]
        self.assertEqual(len(remaining_jobs(plan,rows)),7)
        self.assertEqual(len(remaining_jobs(plan,[dict(jobs[0],status='error')])),8)
        old=dict(platform='chatgpt',client_id=9,campaign_id=1,biz_name='business',keyword='one keyword',status='success')
        self.assertEqual(len(remaining_jobs(plan,[old])),8) # legacy credits require explicit reconciliation
        self.assertEqual(len(remaining_jobs({'waves':[[old]]},[old])),0)

    def test_full_and_remaining_validation(self):
        jobs=[dict(s,campaign_id=1,business_id=2,prompt='Who provides this service?',follow_up='')
              for s in campaign_slots(self.items(),'2026-09-09')]
        self.assertEqual(validate_typed_jobs(jobs,'2026-09-09'),1)
        with self.assertRaises(ValueError):validate_typed_jobs(jobs[:1],'2026-09-09')
        self.assertEqual(validate_typed_jobs(jobs[:1],'2026-09-09',require_complete=False),1)
        with self.assertRaises(ValueError):
            validate_typed_jobs([dict(jobs[0],platform='perplexity')],'2026-09-09',require_complete=False)

    def test_legacy_credits_preserve_history_and_platform_quota(self):
        slots=campaign_slots(self.items(),'2026-09-09')
        old=dict(platform='gemini',client_id=9,campaign_id=1,business_id=2,
                 biz_name='Business',keyword_text='service')
        row=dict(old,status='success',date='2026-09-09')
        original=dict(row)
        remaining,manifest=reconcile_legacy_credits(slots,[row,row],{'waves':[[old]]},'2026-09-09')
        self.assertEqual(len(remaining),7)
        self.assertEqual(len(manifest['credits']),1)
        self.assertEqual(Counter(s['platform'] for s in remaining),Counter(chatgpt=3,gemini=2,copilot=2))
        self.assertEqual(row,original)
        self.assertIsNone(manifest['credits'][0]['historical_prompt_type'])
        with self.assertRaises(ValueError):
            reconcile_legacy_credits(slots,[dict(row,date='2026-09-10')],{'waves':[[old]]},'2026-09-09')
        with self.assertRaises(ValueError):
            reconcile_legacy_credits(slots,[dict(row,keyword_text='unknown')],{'waves':[[old]]},'2026-09-09')

    def test_legacy_outside_scope_is_reported_not_replayed(self):
        old=dict(platform='gemini',client_id=9,campaign_id=99,business_id=2,
                 biz_name='Business',keyword_text='service')
        remaining,manifest=reconcile_legacy_credits(campaign_slots(self.items(),'2026-09-09'),
            [dict(old,status='success',date='2026-09-09')],{'waves':[[old]]},'2026-09-09')
        self.assertEqual(len(remaining),8)
        self.assertEqual(len(manifest['outside_current_scope']),1)

    def test_transition_manifest_must_account_for_all_eight(self):
        old=dict(platform='gemini',client_id=9,campaign_id=1,business_id=2,
                 biz_name='Business',keyword_text='service')
        slots,manifest=reconcile_legacy_credits(campaign_slots(self.items(),'2026-09-09'),
            [dict(old,status='success',date='2026-09-09')],{'waves':[[old]]},'2026-09-09')
        jobs=[dict(s,campaign_id=1,business_id=2,prompt='Who provides this service?') for s in slots]
        plan=dict(daily_protocol='eight-v1',target_date='2026-09-09',total_jobs=7,
                  total_campaigns=1,legacy_transition=manifest,waves=[jobs])
        validate_typed_plan(plan)
        with self.assertRaises(ValueError):
            validate_typed_plan(dict(plan,total_jobs=6,waves=[jobs[:-1]]))
        with self.assertRaises(ValueError):
            validate_typed_plan(dict(plan,legacy_transition=dict(manifest,credits=manifest['credits']*2)))


if __name__=='__main__':unittest.main()
