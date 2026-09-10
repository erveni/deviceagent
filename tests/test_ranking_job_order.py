import unittest
from ranking_job_order import mixed_platform_order


class RankingJobOrderTests(unittest.TestCase):
    def specs(self):
        return [(n,{},platform,'ranking') for platform in ('chatgpt','gemini','copilot') for n in range(20)]

    def test_is_deterministic_complete_and_mixed(self):
        source=self.specs();first=mixed_platform_order(source,'date-seed')
        self.assertEqual(first,mixed_platform_order(source,'date-seed'))
        self.assertCountEqual(first,source)
        for offset in range(0,len(first),3):
            self.assertEqual({spec[2] for spec in first[offset:offset+3]},
                             {'chatgpt','gemini','copilot'})

    def test_handles_exhausted_platform_without_dropping_jobs(self):
        source=[(1,{},'copilot','ranking'),(2,{},'chatgpt','ranking'),(3,{},'chatgpt','ranking')]
        self.assertCountEqual(mixed_platform_order(source,'x'),source)


if __name__=='__main__':unittest.main()
