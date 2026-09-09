import unittest
from daily_prompt_plan import campaign_slots
from tools.consolidate_typed_daily import collect

class ConsolidationTests(unittest.TestCase):
    def test_preserves_eight_distinct_types_and_actual_timestamps(self):
        slots=campaign_slots([dict(kw=dict(id=1,aeoPlanId=2),biz=dict(id=3))],'2026-09-09')
        jobs=[dict(s,client_id=4,campaign_id=2,business_id=3,prompt='test',follow_up='') for s in slots]
        plan=dict(daily_protocol='eight-v1',target_date='2026-09-09',total_jobs=8,total_campaigns=1,waves=[jobs])
        rows=[dict(j,status='success',date='2026-09-09',timestamp='2026-09-10T01:00:00Z') for j in jobs]
        selected,missing=collect(plan,rows+rows)
        self.assertEqual(len(selected),8);self.assertFalse(missing)
        self.assertTrue(all(r['timestamp']=='2026-09-10T01:00:00Z' for r in selected))
        self.assertEqual(len(collect(plan,rows[:3])[1]),5)

if __name__=='__main__':unittest.main()
