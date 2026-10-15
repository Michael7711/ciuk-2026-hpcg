import copy
import os
from pathlib import Path
import subprocess
import time
import unittest
from unittest.mock import patch

import test_campaign as fixtures
from autotune import campaign as c
from autotune.config import Config
from autotune.jobs import render_job_script
from autotune.accounting import parse_accounting, step_estimate


class SequenceTest(unittest.TestCase):
    setUp = fixtures.CampaignTest.setUp
    summary = fixtures.CampaignTest.summary

    def official_sequence(self):
        self.settings['campaign'].update(mode='sequence', archive_slurm_energy=True,
            nodes=[1,2,4], scaling='weak', kind='final', repeats=1, max_trials=3,
            runtime_s=1860, points_per_node=320864256, cap_core_hours=1500,
            team_safe_balance_estimate_core_hours=3721.9, control_margin_s=180)
        self.settings['sequence']={'build':'reference', 'ranks_per_node':144,
                                   'threads':1, 'local_grid':[128,128,136]}
        self.state['candidates']=c.space(self.settings,self.hw)
        c.atomic(self.root/'state.json',self.state)
        return self.state['candidates']

    def test_full_budget_and_weak_scaling_and_final_validation(self):
        items=self.official_sequence()
        c.check_settings(self.settings,self.hw)
        self.assertAlmostEqual(c.sequence_reservation(items,self.settings,self.hw),1478.4)
        self.assertEqual([c.trial_seconds(i,self.settings) for i in items],[2640]*3)
        self.assertEqual([i['points'] for i in items],[320864256*n for n in (1,2,4)])
        self.assertEqual(len({tuple(sorted(i['config']['params'].items())) for i in items}),1)
        self.assertFalse(self.settings['safety']['allow_submit'])
        for item in items:
            n=item['config']['nodes']
            self.assertTrue(c.validate_output(self.summary(item,runtime=1860,memory=229.477*n),
                            item,self.hw,self.settings)['official_eligible'])
            for seconds,gb in [(1799,229.477*n),(1860,54*n)]:
                self.assertFalse(c.validate_output(self.summary(item,runtime=seconds,memory=gb),
                                 item,self.hw,self.settings)['usable'])

    def test_covers_scales_once_in_order(self):
        items=self.official_sequence()
        for i in items:
            choice,reason=c.select(self.state,self.settings,self.hw,1500)
            self.assertEqual(choice,i)
            self.assertIn('no adaptive repeats',reason)
            self.state['trials'].append({'item':i,'status':'done',
                'result':{'usable':True,'official_eligible':True,'gflops':100}})
        self.assertIsNone(c.select(self.state,self.settings,self.hw,1500)[0])

    def test_submission_chain_keeps_overlapping_parents_reserved(self):
        items=self.official_sequence()
        self.settings['safety']['allow_submit']=True
        jobs={}
        def submit(args):
            self.assertEqual(args[0],'sbatch')
            state=c.load(self.root)
            trial=state['trials'][-1]
            # Previous workers can still be running when they admit their successors.
            self.assertEqual(trial['status'],'intent')
            self.assertLessEqual(c.exposure(state,jobs),1500)
            jid=str(200+len(state['trials']))
            jobs[jid]={'id':jid,'name':trial['token'],'state':'RUNNING','hours':trial['reserved_core_hours']}
            return jid+'\n'
        with patch.object(c,'snapshots',side_effect=lambda settings:jobs), patch.object(c,'command',side_effect=submit) as command:
            for expected in (1,2,4):
                result=c.tick(self.root,True)
                self.assertEqual(result['candidate']['config']['nodes'],expected)
                state=c.load(self.root)
                state['trials'][-1].update(status='done',result={'usable':True,'official_eligible':True,'gflops':100})
                c.atomic(self.root/'state.json',state)
            self.assertIn('stopped',c.tick(self.root,True))
            self.assertEqual(command.call_count,3)
        self.assertAlmostEqual(c.exposure(c.load(self.root),jobs),1478.4)

    def test_insufficient_total_budget_blocks_even_first_job(self):
        self.official_sequence()
        self.settings['campaign']['cap_core_hours']=1000
        with self.assertRaisesRegex(ValueError,'entire scaling sequence'):
            c.check_settings(self.settings,self.hw)
        with patch.object(c,'command',side_effect=AssertionError('must not submit')):
            self.assertIn('remaining complete',c.tick(self.root)['stopped'])
        self.assertEqual(c.load(self.root)['trials'],[])

    def test_keeps_budget_for_remaining_larger_scales(self):
        items=self.official_sequence()
        self.state['trials']=[{'item':items[0],'status':'done','result':{'usable':True,'official_eligible':True},
                              'token':'hc-old','reserved_core_hours':211.2}]
        c.atomic(self.root/'state.json',self.state)
        self.assertEqual(c.tick(self.root)['candidate']['config']['nodes'],2)
        self.settings['campaign']['cap_core_hours']=1478.3
        self.assertIn('remaining complete',c.tick(self.root)['stopped'])

    def test_failure_abandonment_or_out_of_order_cannot_skip(self):
        items=self.official_sequence()
        for status,official in [('failed',False),('abandoned',False),('done',False)]:
            self.state['trials']=[{'item':items[0],'status':status,'failure_acknowledged_at':'yes',
                                  'result':{'usable':True,'official_eligible':official}}]
            with self.subTest(status=status),self.assertRaisesRegex(RuntimeError,'no skip'):
                c.select(self.state,self.settings,self.hw)
        self.state['trials']=[{'item':items[1],'status':'done','result':{'usable':True,'official_eligible':True}}]
        with self.assertRaisesRegex(RuntimeError,'sequence blocked'):
            c.select(self.state,self.settings,self.hw)

    def test_rejects_inconsistent_settings_and_memory(self):
        self.official_sequence()
        for key,value in [('nodes',[1,4,2]),('max_trials',4),('repeats',2),('scaling','strong'),
                          ('kind','diagnostic'),('points_per_node',323960832),('archive_slurm_energy',False)]:
            s=copy.deepcopy(self.settings); s['campaign'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):c.check_settings(s,self.hw)
        s=copy.deepcopy(self.settings);s['sequence']['threads']=3
        with self.assertRaises(ValueError):c.check_settings(s,self.hw)
        s=copy.deepcopy(self.settings);s['sequence']['local_grid']=[256]*3
        s['campaign']['points_per_node']=144*256**3
        with self.assertRaisesRegex(ValueError,'memory'):c.check_settings(s,self.hw)

    def test_requires_deadline_for_all_scales(self):
        self.official_sequence()
        self.settings['campaign']['deadline']=c.dt.datetime.fromtimestamp(time.time()+3000,c.UTC).isoformat()
        with self.assertRaisesRegex(ValueError,'entire scaling sequence'):c.check_settings(self.settings,self.hw)
        self.assertIn('all remaining',c.tick(self.root)['stopped'])

    def test_worker_script_and_rendering_each_scale(self):
        for item in self.official_sequence():
            n=item['config']['nodes']; cfg=Config(**item['config'])
            trial={'item':item,'seconds':2640,'deadline_epoch':time.time()+20000,'token':'hc-seq'}
            script=c.worker_script(self.root,trial,self.settings)
            for directive in (f'#SBATCH --nodes={n}', '#SBATCH --ntasks-per-node=144',
                '#SBATCH --cpus-per-task=2', '#SBATCH --qos=standard',
                '#SBATCH --time=00:44:00', '#SBATCH --no-requeue'):
                self.assertIn(directive,script)
            subprocess.run(['bash','-n'],input=script,text=True,check=True)
            local=copy.deepcopy(self.settings);local['hpcg']={'binary':str(self.binary)}
            local['slurm']['inline']=True
            rendered=render_job_script(cfg,local,self.hw,self.root,'fixture')
            self.assertIn(f'--nodes={n}',rendered)
            self.assertIn('--ntasks-per-node=144',rendered)
            subprocess.run(['bash','-n'],input=rendered,text=True,check=True)

    def test_archives_append_only_and_nonfatal_on_delay(self):
        items=self.official_sequence()
        self.state['trials']=[{'job_id':'12','item':items[0],
                              'result':{'gflops':135,'runtime_s':1860,'usable':True}}]
        raw='JobID|JobName|State|ElapsedRaw|ConsumedEnergyRaw|AllocNodes\n12|hc-x|RUNNING|2000|1000|1\n'
        with patch.object(c,'command',return_value=raw) as command:
            a=c.archive_accounting(self.root,self.state,self.settings)
            b=c.archive_accounting(self.root,self.state,self.settings)
            self.assertEqual(a['estimates']['12']['status'],'unavailable')
            self.assertNotEqual(a['raw_file'],b['raw_file'])
            self.assertEqual(Path(a['raw_file']).read_text(),raw)
            self.assertNotIn('-X',command.call_args.args[0])
            args=command.call_args.args[0]
            self.assertNotIn('+',args[args.index('-S')+1])
        with patch.object(c,'command',side_effect=subprocess.TimeoutExpired('sacct',45)):
            receipt=c.archive_accounting(self.root,self.state,self.settings)
            self.assertEqual(receipt['status'],'unavailable')
            self.assertTrue(Path(receipt['receipt_file']).exists())

    def test_worker_archives_step_before_chaining(self):
        self.settings['campaign']['archive_slurm_energy']=True
        self.settings['safety']['allow_submit']=True
        item=self.state['candidates'][0]
        self.state['trials']=[{'token':'hc-energy','job_id':'42','status':'submitted','item':item,
            'seconds':720,'deadline_epoch':time.time()+2000,'reserved_core_hours':57.6}]
        c.atomic(self.root/'state.json',self.state)
        def fake_run(args,cwd,output,seconds,root,env=None):
            (Path(cwd)/'HPCG-Benchmark_3.1_fixture.txt').write_text(self.summary(item))
            Path(output).write_text('fixture')
        events=[]
        def archive(*args,**kwargs):events.append('archive');return {'status':'captured'}
        def tick(*args,**kwargs):events.append('chain');return {'stopped':'test'}
        with patch.dict(os.environ,{'SLURM_JOB_ID':'42','SLURM_JOB_NUM_NODES':'1'}), \
             patch.object(c,'run_bounded',side_effect=fake_run), \
             patch.object(c,'archive_accounting',side_effect=archive), patch.object(c,'tick',side_effect=tick):
            c.worker(self.root,'hc-energy')
        self.assertEqual(events,['archive','chain'])
        self.assertEqual(c.load(self.root)['trials'][0]['result']['slurm_accounting']['status'],'captured')


class StepAccountingTest(unittest.TestCase):
    def records(self):
        return parse_accounting('JobID|JobName|State|ElapsedRaw|ConsumedEnergyRaw|AllocNodes\n'
            '1|hc-test|COMPLETED|265|273140|1\n1.batch|batch|COMPLETED|265|272294|1\n'
            '1.extern|extern|COMPLETED|265|273140|1\n1.0|bench_wrapper.sh|COMPLETED|257|270439|1\n')

    def test_uses_only_wrapper_step_and_preserves_whole_scope(self):
        r=step_estimate(self.records(),'1',134.942,134.134,1)
        self.assertAlmostEqual(r['step_average_power_w'],270439/257)
        self.assertAlmostEqual(r['estimated_gflops_per_w'],134.942*257/270439)
        self.assertEqual(r['whole_job_energy_j'],273140)
        self.assertFalse(r['benchmark_window_energy_verified'])
        self.assertNotIn('gflops_per_w',r)

    def test_duplicate_or_malformed_records_rejected(self):
        with self.assertRaisesRegex(ValueError,'columns'):parse_accounting('JobID|State\n1|COMPLETED')
        raw='JobID|JobName|State|ElapsedRaw|ConsumedEnergyRaw\n1|x|COMPLETED|1|2\n'
        with self.assertRaisesRegex(ValueError,'duplicate'):parse_accounting(raw+'1|x|COMPLETED|1|2\n')

    def test_missing_invalid_or_wrong_scope_is_unavailable(self):
        for field,value in [('ConsumedEnergyRaw','Unknown'),('ConsumedEnergyRaw','0'),
                            ('ConsumedEnergyRaw','nan'),('ElapsedRaw','0'),
                            ('State','RUNNING'),('JobName','other'),('AllocNodes','2'),('AllocNodes',''),
                            ('ExitCode','1:0')]:
            records=self.records();records['1.0'][field]=value
            with self.subTest(field=field,value=value):
                self.assertEqual(step_estimate(records,'1',134,134,1)['status'],'unavailable')
        records=self.records();del records['1.0']
        self.assertEqual(step_estimate(records,'1',134)['status'],'unavailable')
        self.assertEqual(step_estimate(self.records(),'1',float('inf'))['status'],'unavailable')
        self.assertEqual(step_estimate(self.records(),'1',134,300)['status'],'unavailable')
