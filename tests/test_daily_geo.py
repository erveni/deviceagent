import unittest
from unittest.mock import patch
from daily_geo import coordinates,location_key
from tools.prepare_daily_city_geo import verified_result

class DailyGeoTests(unittest.TestCase):
    def test_no_headquarters_or_zero_fallback(self):
        with self.assertRaises(ValueError):coordinates('Miami','FL',{})
        bad={'miami|FL':dict(status='verified',latitude=0,longitude=0,timezone='America/New_York')}
        with self.assertRaises(ValueError):coordinates('Miami','FL',bad)

    def test_verified_city_and_timezone(self):
        cache={'miami|FL':dict(status='verified',latitude=25.77,longitude=-80.19,timezone='America/New_York')}
        self.assertEqual(coordinates(' Miami ','fl',cache),(25.77,-80.19,'America/New_York'))

    def test_wrong_state_city_rejected(self):
        row=dict(lat='25.77',lon='-80.19',name='Miami',address={'city':'Miami','ISO3166-2-lvl4':'US-FL'})
        self.assertEqual(verified_result([row],'Miami','FL')['status'],'verified')
        self.assertEqual(verified_result([row],'Miami','OH')['status'],'unresolved')
        self.assertEqual(verified_result([row],'Orlando','FL')['status'],'unresolved')

    def test_job_uses_campaign_coordinates_not_headquarters(self):
        from build_daily_eight import make_job
        from daily_prompt_plan import campaign_slots
        item=dict(kw=dict(id=1,aeoPlanId=2,keywordText='service'),
                  biz=dict(id=3,latitude=40.4,longitude=-111.8,timezone='America/Denver'))
        slot=campaign_slots([item],'2026-09-09')[0]
        session=dict(promptType=slot['prompt_type'],dailySlotId=slot['daily_slot_id'],
                     promptCycleDay=slot['prompt_cycle_day'],isDiscovery=slot['is_discovery'],
                     campaignId=2,businessId=3,keywordId=1,clientId=4,platform=slot['platform'],
                     city='Miami',state='FL',prompt='Who offers service in Miami?')
        with patch('build_daily_eight.coordinates',return_value=(25.77,-80.19,'America/New_York')):
            job=make_job(slot,session,'2026-09-09')
        self.assertEqual((job['biz_lat'],job['biz_lng'],job['biz_timezone']),
                         (25.77,-80.19,'America/New_York'))

if __name__=='__main__':unittest.main()
