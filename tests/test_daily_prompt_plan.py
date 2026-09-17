from collections import Counter
import csv
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from daily_prompt_plan import campaign_slots,cycle_day,result_key,remaining_jobs,PROMPT_TYPES,validate_typed_jobs,validate_typed_plan,reconcile_legacy_credits,validate_mixed_modes


class DailyPlanTests(unittest.TestCase):
    def items(self,n=5,campaign=1,business=2):
        return [dict(kw=dict(id=i+1,aeoPlanId=campaign),biz=dict(id=business)) for i in range(n)]

    def test_eight_even_with_one_keyword_and_priority_sized_inputs(self):
        for n in (1,5,8,12,20):
            slots=campaign_slots(self.items(n),'2026-09-09')
            self.assertEqual(len(slots),8)
            self.assertEqual(Counter(s['platform'] for s in slots),Counter(chatgpt=3,gemini=3,copilot=2))
            self.assertEqual(len({s['daily_slot_id'] for s in slots}),8)

    def test_mixed_mode_plan_is_five_type_three_voice(self):
        slots=campaign_slots(self.items(),'2026-09-09')
        jobs=[dict(s,campaign_id=1,business_id=2,prompt='prompt',follow_up='') for s in slots]
        self.assertEqual(Counter(j['mode'] for j in jobs),Counter(type=5,voice=3))
        self.assertEqual(validate_mixed_modes(jobs),1)

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

    def test_backfill_retry_uses_local_slot_identity(self):
        jobs=[dict(backfill_slot_id=f'daily:backfill:v1:2026-08-02:c1:b2:n{i}',
                   client_id=9,platform='chatgpt',keyword_text='same keyword') for i in range(1,4)]
        self.assertEqual(len(remaining_jobs({'waves':[jobs]},[dict(jobs[0],status='success')])),2)
        self.assertNotEqual(result_key(jobs[0]),result_key(jobs[1]))

    def test_backfill_remaining_rejects_zero_mock_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);plan=root/'backfill.json';remain=root/'remain.json'
            job=dict(backfill_slot_id='daily:backfill:v1:2026-08-02:c1:b2:n6',
                     backfill_prompt_type='historical_gap_6',client_id=9,platform='chatgpt',
                     keyword_text='service',business_id=2,targetDate='2026-08-02T12:00:00Z')
            plan.write_text(json.dumps(dict(daily_protocol='daily-backfill-v1',waves=[[job]])))
            result=root/'backfill_results_2026-08-02.csv'
            with result.open('w',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=[*job,'status','mocked_latitude','mocked_longitude'])
                writer.writeheader();writer.writerow({**job,'status':'success','mocked_latitude':'0','mocked_longitude':'0'})
            env={**__import__('os').environ,'DAILY_PLAN_PATH':str(plan),'DAILY_REMAIN_PATH':str(remain)}
            subprocess.run(['python3','_build_remaining.py','2026-08-02'],cwd=Path(__file__).parents[1],
                           env=env,check=True,capture_output=True,text=True)
            self.assertEqual(json.loads(remain.read_text())['total_jobs'],1)
            with result.open('w',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=[*job,'status','mocked_latitude','mocked_longitude'])
                writer.writeheader();writer.writerow({**job,'status':'success','mocked_latitude':'30.1','mocked_longitude':'-97.2'})
            subprocess.run(['python3','_build_remaining.py','2026-08-02'],cwd=Path(__file__).parents[1],
                           env=env,check=True,capture_output=True,text=True)
            self.assertEqual(json.loads(remain.read_text())['total_jobs'],0)

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
