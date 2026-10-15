import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('overnight_energy', ROOT/'analysis/hpcg/overnight_energy.py')
energy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(energy)


class OvernightEnergyTest(unittest.TestCase):
    def setUp(self):
        self.log=(ROOT/'docs/hpcg/experiment_log.md').read_text()
        self.raw=(ROOT/'analysis/hpcg/overnight-20261015-sacct-energy.psv').read_text()

    def test_nine_jobs_join_and_preliminary_values_and_totals(self):
        rows=energy.analyse(self.log,self.raw)
        self.assertEqual(len(rows),9)
        self.assertEqual(sum(r['whole_job_energy_j'] for r in rows),2337351)
        by_job={r['job_id']:r for r in rows}
        for jid,value in [('558657',0.14610209388616707),('558659',0.15701306163634834),
                          ('558650',0.12823628988422528)]:
            self.assertAlmostEqual(by_job[jid]['estimated_gflops_per_w'],value)
        self.assertTrue(all(not r['benchmark_window_energy_verified'] for r in rows))

    def test_job_mismatch_missing_energy_and_duplicates_fail(self):
        for raw in (self.raw.replace('558657','999999'),
                    self.raw.replace('558657.0|bench_wrapper.sh|COMPLETED|247|228809',
                                     '558657.0|bench_wrapper.sh|COMPLETED|247|Unknown'),
                    self.raw+self.raw.splitlines()[1]+'\n'):
            with self.assertRaises(ValueError):energy.analyse(self.log,raw)

    def test_overlap_steps_do_not_affect_derived_power(self):
        altered='\n'.join(line.replace(line.split('|')[-1],'999999999')
                          if '.extern|' in line or '.batch|' in line else line
                          for line in self.raw.splitlines())
        self.assertEqual(energy.analyse(self.log,self.raw),energy.analyse(self.log,altered))
