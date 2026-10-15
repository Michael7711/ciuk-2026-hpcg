import copy
import csv
import threading
import json
import io
from contextlib import redirect_stdout
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from autotune import campaign as c
from autotune.config import Config, load_settings
from autotune.jobs import render_input, render_job_script, prepare_run, binary_sha256
from autotune.results import parse_hpl, parse_sacct, make_row, read_pm_counters, record_run, COLUMNS

TEMPLATE = Path(__file__).resolve().parents[1]/'autotune/clusters/cirrus-hpcg-campaign.toml'


class CampaignTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.source=self.base/'source'
        (self.source/'src').mkdir(parents=True)
        (self.source/'setup').mkdir()
        (self.source/'bin').mkdir()
        (self.source/'src/main.cpp').write_text('// fixture')
        for name in ('configure','Makefile.ext','bin/hpcg.dat','setup/Make.MPI_GCC_OMP'):
            (self.source/name).write_text('fixture')
        self.binary=self.base/'xhpcg'
        self.binary.write_text('fixture executable')
        self.settings,self.hw=load_settings(TEMPLATE)
        self.settings['campaign'].update(source=str(self.source),budget_since='2026-01-01T00:00:00+00:00',
                                         deadline='2099-01-01T00:00:00+00:00', state_prefix=str(self.base))
        self.settings['builds']=[{'id':'reference','binary':str(self.binary),
            'sha256':binary_sha256(self.binary),'modules':[]}]
        self.root=self.base/'state'
        self.root.mkdir()
        (self.root/'LOCK').touch()
        frozen=copy.deepcopy(self.settings)
        frozen['safety'].pop('allow_submit')
        self.state={'version':1,'settings_path':'fixture.toml','settings_hash':c.digest(frozen),
            'source_hash':c.source_hash(self.source),'controller_hash':c.code_hash(),
            'candidates':c.space(self.settings,self.hw),'trials':[]}
        c.atomic(self.root/'state.json',self.state)
        self.real_settings_for=c.settings_for
        self.mocks=[patch.object(c,'settings_for',return_value=(self.settings,self.hw)),
                    patch.object(c,'snapshots',return_value={})]
        for mock in self.mocks:
            mock.start()
            self.addCleanup(mock.stop)

    def summary(self,item=None,runtime=60,gflops='134.124',memory=231.733):
        cfg=(item or self.state['candidates'][0])['config']
        p=cfg['params']
        return '\n'.join([
            f'Machine Summary::Distributed Processes={cfg["nodes"]*cfg["ranks_per_node"]}',
            f'Machine Summary::Threads per processes={cfg["threads"]}',
            *[f'Local Domain Dimensions::{k}={p[k]}' for k in ('nx','ny','nz')],
            'Spectral Convergence Tests::Result=PASSED','Departure from Symmetry::Result=PASSED',
            'Iteration Count Information::Result=PASSED','Reproducibility Information::Result=PASSED',
            f'Benchmark Time Summary::Total={runtime}',
            f'Memory Use Information::Total memory used for data (Gbytes)={memory}',
            f'Final Summary::HPCG result is VALID with a GFLOP/s rating of={gflops}'])


    def test_initialise_smoke_and_immutable_provenance(self):
        output=self.base/'smoke.toml'
        c.smoke_settings(TEMPLATE,output)
        s,hw=load_settings(output)
        self.assertFalse(s['safety']['allow_submit'])
        self.assertEqual(s['campaign']['max_trials'],2)
        self.assertEqual(len(s['builds']),1)
        with self.assertRaises(FileExistsError):
            c.smoke_settings(TEMPLATE,output)
        fresh=self.base/'fresh'
        with patch.object(c,'load_settings',return_value=(self.settings,self.hw)):
            c.init(output,fresh)
            state=c.load(fresh)
            # Remove fixture-level patch to exercise actual freeze verification.
            with patch.object(c,'settings_for',new=self.real_settings_for):
                c.settings_for(state)
                self.settings['safety']['allow_submit']=True
                c.settings_for(state)  # Only the explicit safety gate can change.
                self.settings['campaign']['cap_core_hours']=499
                with self.assertRaisesRegex(RuntimeError,'settings changed'):
                    c.settings_for(state)
        self.assertTrue((fresh/'LOCK').exists())

    def test_locks_exclude_parallel_admission(self):
        with c.locked(self.root):
            with self.assertRaises(BlockingIOError):
                with c.locked(self.root):
                    self.fail('second controller acquired lock')

    def test_minute_rounding_is_reserved(self):
        item=copy.deepcopy(self.state['candidates'][0])
        item['config']['params']['runtime_s']=61
        self.assertEqual(c.trial_seconds(item,self.settings),780)

    def test_periodic_repeat_uses_only_valid_measurements(self):
        for item in self.state['candidates'][:4]:
            self.state['trials'].append({'item':item,'status':'done','result':{'usable':True,'gflops':134}})
        item,why=c.select(self.state,self.settings,self.hw)
        self.assertIn('repeat for noise',why)
        self.assertIn(item,[t['item'] for t in self.state['trials']])

    def test_unresolved_terminal_and_running_status(self):
        t={'token':'hc-x','status':'running','job_id':'1'}
        state={'trials':[t]}
        c.reconcile(state,{'1':{'id':'1','name':'hc-x','state':'RUNNING'}})
        self.assertEqual(t['status'],'running')
        c.reconcile(state,{'1':{'id':'1','name':'hc-x','state':'TIMEOUT'}})
        self.assertEqual(t['status'],'failed')

    def test_volume_memory_and_physical_utilisation(self):
        self.settings['campaign']['nodes']=[1,2,3,4]
        items=c.space(self.settings,self.hw)
        self.assertEqual({x['config']['nodes'] for x in items},{1,2,3,4})
        active=set()
        for x in items:
            n=x['config']['nodes']
            self.assertLessEqual(abs(x['points']/(n*323960832)-1),0.025)
            self.assertLess(x['estimated_peak_bytes_per_node'],self.hw.mem_bytes*.8)
            active.add(x['config']['ranks_per_node']*x['config']['threads'])
        self.assertTrue({72,144,288}.issubset(active))
        self.settings['campaign']['scaling']='strong'
        self.assertTrue(all(abs(x['points']/323960832-1)<=.025 for x in c.space(self.settings,self.hw)))

    def test_memory_guard_removes_unsafe_space(self):
        self.settings['campaign']['points_per_node']*=10
        with self.assertRaisesRegex(ValueError,'no memory-safe'):
            c.space(self.settings,self.hw)

    def test_settings_caps_bad_times_and_identity(self):
        c.check_settings(self.settings,self.hw)
        for key,value in [('cap_core_hours',501),('runtime_s',-1),('repeats',1.5),
                          ('pending_timeout_s',0),('volume_tolerance',.2),('memory_headroom',.9)]:
            s=copy.deepcopy(self.settings)
            s['campaign'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                c.check_settings(s,self.hw)
        self.binary.write_text('changed')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):
            c.check_settings(self.settings,self.hw)

    def test_dry_run_and_disabled_gate_do_not_write_or_submit(self):
        before=(self.root/'state.json').read_bytes()
        with patch.object(c,'command',side_effect=AssertionError('no submit')):
            result=c.tick(self.root)
            self.assertIn('candidate',result)
            with self.assertRaises(PermissionError):
                c.tick(self.root,True)
        self.assertEqual(before,(self.root/'state.json').read_bytes())
        self.assertFalse(list(self.root.glob('*.sh')))

    def test_atomic_intent_before_submit_and_duplicate_resume(self):
        self.settings['safety']['allow_submit']=True
        def submit(args):
            ledger=c.load(self.root)
            self.assertEqual(ledger['trials'][0]['status'],'intent')
            self.assertGreater(ledger['trials'][0]['reserved_core_hours'],0)
            self.assertEqual(args[0],'sbatch')
            return '12345\n'
        with patch.object(c,'command',side_effect=submit) as cmd:
            result=c.tick(self.root,True)
            self.assertEqual(result['submitted'],'12345')
            trial=c.load(self.root)['trials'][0]
            jobs={'12345':{'id':'12345','name':trial['token'],'state':'PENDING','hours':100}}
            with patch.object(c,'snapshots',return_value=jobs):
                self.assertEqual(c.tick(self.root,True)['job_id'],'12345')
            self.assertEqual(cmd.call_count,1)
        script=next(self.root.glob('hc-*.sh'))
        self.assertIn('--deadline=',script.read_text())
        self.assertIn('--no-requeue',script.read_text())
        subprocess.run(['bash','-n',str(script)],check=True)

    def test_uncertain_submit_keeps_reservation_and_never_retries(self):
        self.settings['safety']['allow_submit']=True
        with patch.object(c,'command',side_effect=subprocess.TimeoutExpired('sbatch',45)):
            with self.assertRaises(subprocess.TimeoutExpired):
                c.tick(self.root,True)
        state=c.load(self.root)
        self.assertEqual(len(state['trials']),1)
        self.assertEqual(state['trials'][0]['status'],'intent')
        with patch.object(c,'command',side_effect=AssertionError('duplicate submit')):
            with self.assertRaisesRegex(RuntimeError,'unresolved submission'):
                c.tick(self.root,True)
        trial=state['trials'][0]
        jobs={'9':{'id':'9','name':trial['token'],'state':'RUNNING','hours':1}}
        with patch.object(c,'snapshots',return_value=jobs):
            self.assertEqual(c.tick(self.root,True)['job_id'],'9')

    def test_external_pending_and_own_reservations_count_once(self):
        trial={'token':'hc-own','job_id':'1','reserved_core_hours':72}
        jobs={'1':{'id':'1','name':'hc-own','state':'RUNNING','hours':5},
              '2':{'id':'2','name':'external-pending','state':'PENDING','hours':450}}
        self.assertEqual(c.exposure({'trials':[trial]},jobs),72)
        report=c.budget_report({'trials':[trial]},self.settings,jobs)
        self.assertEqual(report['other_submitting_user_job_exposure_core_hours'],450)
        self.assertFalse(report['team_safe_balance_verified'])
        self.assertEqual(report['scheduler_scope'],'submitting_user_and_account_only')

    def test_cap_exact_boundary(self):
        cost=c.trial_seconds(self.state['candidates'][0],self.settings)*288/3600
        self.settings['campaign']['cap_core_hours']=cost
        self.assertEqual(c.tick(self.root)['next_reservation_core_hours'],cost)
        self.settings['campaign']['cap_core_hours']=cost-.001
        self.assertIn('stopped',c.tick(self.root))

    def test_expired_deadline_failure_and_stop_conditions(self):
        self.settings['campaign']['deadline']='2000-01-01T00:00:00+00:00'
        self.assertIn('deadline',c.tick(self.root)['stopped'])
        (self.root/'STOP').touch()
        self.assertIn('STOP',c.tick(self.root)['stopped'])
        (self.root/'STOP').unlink()
        self.settings['campaign']['deadline']='2099-01-01T00:00:00+00:00'
        self.settings['campaign']['max_trials']=0
        self.assertEqual(c.tick(self.root)['stopped'],'max_trials')

    def test_repeat_and_model_comparability(self):
        items=self.state['candidates']
        for i,item in enumerate(items[:6]):
            self.state['trials'].append({'item':item,'status':'done','result':{'usable':True,
                                        'gflops':100+i,'gflops_per_w':None}})
        self.settings['campaign']['objective']='performance'
        _,why=c.select(self.state,self.settings,self.hw)
        self.assertIn('measured race/local search',why)
        for t in self.state['trials']:
            t['item']=copy.deepcopy(t['item'])
            t['item']['build']='foreign-build'
        _,why=c.select(self.state,self.settings,self.hw)
        self.assertIn('hardware fallback',why)
        self.assertFalse(c.compatible(items[0],{'item':dict(items[0],config=dict(items[0]['config'],nodes=4))}))
        self.settings['campaign']['repeats']=1
        self.state['trials']=[{'item':item} for item in items]
        self.assertIsNone(c.select(self.state,self.settings,self.hw)[0])

    def test_result_validation_and_official_eligibility(self):
        item=self.state['candidates'][0]
        result=c.validate_output(self.summary(),item,self.hw,self.settings)
        self.assertTrue(result['usable'])
        self.assertFalse(result['official_eligible'])
        for text in [self.summary().replace('Result=PASSED','Result=FAILED',1),
                     self.summary().replace('Processes=288','Processes=999'),
                     self.summary(gflops='1e309'),self.summary(runtime=1),self.summary(memory=900),'truncated']:
            self.assertFalse(c.validate_output(text,item,self.hw,self.settings)['usable'])
        final=copy.deepcopy(item)
        final['config']['kind']='final'
        final['config']['params']['runtime_s']=1860
        self.assertFalse(c.validate_output(self.summary(runtime=1799),final,self.hw,self.settings)['usable'])
        self.assertTrue(c.validate_output(self.summary(runtime=1860),final,self.hw,self.settings)['official_eligible'])
        self.assertFalse(c.validate_output(self.summary(runtime=1860,memory=54),final,self.hw,self.settings)['usable'])

    def test_whole_job_energy_never_becomes_benchmark_efficiency(self):
        energy=parse_sacct('123|00:10:00|100000|\n','123')
        self.assertEqual(energy['energy_status'],'whole_job')
        row=make_row(Config(**self.state['candidates'][0]['config']),'run',{'gflops':134},energy=energy)
        self.assertEqual(row['gflops_per_w'],'')
        self.assertEqual(row['energy_j'],100000)
        (self.root/'energy_start_n1.txt').write_text('100 J 1000000 us')
        (self.root/'energy_end_n1.txt').write_text('200 J 2000000 us')
        self.assertEqual(read_pm_counters(self.root,1)['energy_status'],'ok')
        self.assertEqual(read_pm_counters(self.root,2)['energy_status'],'inconsistent')

    def test_stop_only_cancels_this_campaign(self):
        self.state['trials']=[{'token':'hc-owned','job_id':'12','status':'submitted'}]
        c.atomic(self.root/'state.json',self.state)
        jobs={'12':{'id':'12','name':'hc-owned','state':'PENDING'},
              '13':{'id':'13','name':'hpl-teammate','state':'RUNNING'}}
        with patch.object(c,'load_settings',return_value=(self.settings,self.hw)),\
             patch.object(c,'snapshots',return_value=jobs),patch.object(c,'command') as cmd:
            result=c.stop(self.root)
        cmd.assert_called_once_with(['scancel','12'])
        self.assertEqual(result['cancel_requested'],['12'])
        self.assertTrue((self.root/'STOP').exists())

    def test_stop_terminates_running_subprocess(self):
        (self.root/'STOP').touch()
        start=time.monotonic()
        with self.assertRaisesRegex(RuntimeError,'STOP'):
            c.run_bounded(['sleep','30'],self.root,self.root/'process.log',60,self.root)
        self.assertLess(time.monotonic()-start,5)

    def test_hpl_renderer_parser_and_new_run_containment(self):
        cfg=Config('hpl',1,288,1,{'N':73728,'NB':256,'P':16,'Q':18})
        self.assertIn('73728',render_input(cfg))
        settings=copy.deepcopy(self.settings)
        settings['hpl']={'binary':str(self.binary),'build_id':'hpl'}
        settings['slurm']['walltime_s']=600
        settings['paths']={'required_prefix':str(self.root)}
        text=render_job_script(cfg,settings,self.hw,self.root,'hpl-test')
        self.assertIn('--ntasks-per-node=288',text)
        self.assertIn('--cpus-per-task=1',text)
        hpl='WR00C2R4 73728 256 16 18 20.0 1234.0\n||Ax-b||_oo/test = 0.1 ...... PASSED'
        self.assertEqual(parse_hpl(hpl)['validation'],'PASSED')
        self.assertEqual(parse_hpl(hpl)['gflops'],1234)
        with self.assertRaisesRegex(ValueError,'must be under'):
            prepare_run(cfg,settings,self.hw,str(self.root)+'-escape')

    def test_worker_records_then_chains_and_never_replays(self):
        self.settings['safety']['allow_submit']=True
        item=self.state['candidates'][0]
        trial={'token':'hc-test','job_id':'42','status':'submitted','item':item,
               'seconds':720,'deadline_epoch':time.time()+2000,'reserved_core_hours':57.6}
        self.state['trials']=[trial]
        c.atomic(self.root/'state.json',self.state)
        def fake_run(args,cwd,output,seconds,root,env=None):
            (Path(cwd)/'HPCG-Benchmark_3.1_fixture.txt').write_text(self.summary(item))
            Path(output).write_text('fixture')
        with patch.dict(os.environ,{'SLURM_JOB_ID':'42','SLURM_JOB_NUM_NODES':'1'}),\
             patch.object(c,'run_bounded',side_effect=fake_run),\
             patch.object(c,'tick',return_value={'stopped':'max trials'}) as tick:
            c.worker(self.root,'hc-test')
            self.assertEqual(c.load(self.root)['trials'][0]['status'],'done')
            self.assertTrue(c.load(self.root)['trials'][0]['result']['usable'])
            tick.assert_called_once_with(self.root,submit=True)
            with self.assertRaisesRegex(RuntimeError,'already executed'):
                c.worker(self.root,'hc-test')


    def test_changed_binary_identity_in_worker_fails_closed(self):
        self.settings['safety']['allow_submit']=True
        item=self.state['candidates'][0]
        self.state['build_hashes']={'reference':'unexpected-previous-binary'}
        self.state['trials']=[{'token':'hc-hash','job_id':'42','status':'submitted','item':item,
                              'seconds':720,'deadline_epoch':time.time()+2000,'reserved_core_hours':57.6}]
        c.atomic(self.root/'state.json',self.state)
        with patch.dict(os.environ,{'SLURM_JOB_ID':'42','SLURM_JOB_NUM_NODES':'1'}),             patch.object(c,'run_bounded') as run:
            with self.assertRaisesRegex(RuntimeError,'identity changed'):
                c.worker(self.root,'hc-hash')
            run.assert_not_called()
        self.assertTrue((self.root/'STOP').exists())


    def test_hpl_whole_job_efficiency_appends_to_existing_csv_with_scope(self):
        cfg=Config('hpl',1,288,1,{'N':73728,'NB':256,'P':16,'Q':18})
        run=self.base/'hpl-run'
        run.mkdir()
        (run/'config.json').write_text(json.dumps(c.asdict(cfg)))
        (run/'slurm-123.out').write_text('WR00C2R4 73728 256 16 18 20.0 134.0\n'
                                        '||Ax-b||_oo/test = 0.1 ...... PASSED')
        log=self.base/'existing-hpl.csv'
        original=','.join(COLUMNS)+'\n'+','.join('' for _ in COLUMNS)+'\n'
        log.write_text(original)
        row=record_run(run,'123',log,'123|00:10:00|100000|\n')
        self.assertAlmostEqual(row['avg_power_w'],100000/600)
        self.assertAlmostEqual(row['gflops_per_w'],134/(100000/600))
        self.assertEqual(row['energy_status'],'whole_job')
        self.assertEqual(row['energy_source'],'sacct')
        self.assertTrue(log.read_text().startswith(original))
        with log.open(newline='') as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(rows[-1]['energy_status'],'whole_job')
        self.assertAlmostEqual(float(rows[-1]['gflops_per_w']),.804)
        low=make_row(cfg,'low',{'gflops':134},energy=parse_sacct('123|00:00:01|100|','123',30))
        self.assertEqual(low['gflops_per_w'],'')

    def test_performance_default_and_energy_objectives_fail_explicitly(self):
        self.assertEqual(self.settings['campaign']['objective'],'performance')
        for objective in ('efficiency','alternate'):
            self.settings['campaign']['objective']=objective
            with self.subTest(objective=objective):
                with self.assertRaisesRegex(ValueError,'no verified benchmark-window'):
                    c.check_settings(self.settings,self.hw)
                with self.assertRaisesRegex(ValueError,'no verified benchmark-window'):
                    c.select(self.state,self.settings,self.hw)

    def test_small_budget_selection_changes_when_observed_winner_changes(self):
        self.settings['builds']*=4
        self.settings['builds']=[dict(b,id='b'+str(i)) for i,b in enumerate(self.settings['builds'])]
        self.state['candidates']=c.space(self.settings,self.hw)
        self.state['trials']=[]
        used=0
        for value in (100,110,140,120):
            item,why=c.select(self.state,self.settings,self.hw,500-used)
            self.assertIn('anchor screen',why)
            used+=c.trial_seconds(item,self.settings)*288/3600
            self.state['trials'].append({'item':item,'status':'done',
                'result':{'usable':True,'gflops':value},'reserved_core_hours':57.6})
        choice,why=c.select(self.state,self.settings,self.hw,500-used)
        self.assertEqual(choice['build'],'b2')
        self.assertIn('measured race repeat',why)
        # Disable the repeat cadence to verify the next unseen layout is adaptive too.
        self.settings['campaign']['repeat_every']=99
        choice,why=c.select(self.state,self.settings,self.hw,500-used)
        self.assertEqual(choice['build'],'b2')
        self.assertEqual(sum(t['item']['key']==choice['key'] for t in self.state['trials']),0)
        self.assertIn('won 4 matched anchors',why)
        self.state['trials'][0]['result']['gflops']=180
        choice,_=c.select(self.state,self.settings,self.hw,500-used)
        self.assertEqual(choice['build'],'b0')
        self.assertLess(used+c.trial_seconds(choice,self.settings)*288/3600,500)


    def test_real_recipe_reservations_reach_adaptation_under_500(self):
        settings,_=load_settings(TEMPLATE)
        settings['builds'][0].update(binary=str(self.binary),sha256=binary_sha256(self.binary))
        self.state['candidates']=c.space(settings,self.hw)
        self.state['trials']=[]
        anchor_values={'cce19-reference':134,'cce19-strict':130,'gnu14-fast':145,'aocc5-fast':140}
        used=0
        reasons=[]
        while True:
            item,why=c.select(self.state,settings,self.hw,500-used)
            if item is None:
                break
            cost=c.trial_seconds(item,settings)*288*item['config']['nodes']/3600
            used+=cost
            reasons.append(why)
            self.state['trials'].append({'item':item,'status':'done','reserved_core_hours':cost,
                'result':{'usable':True,'gflops':anchor_values[item['build']]}})
            self.assertLessEqual(used,500)
        self.assertEqual(len(self.state['trials']),7)
        self.assertAlmostEqual(used,489.6)
        self.assertEqual([t['item']['build'] for t in self.state['trials'][4:]],['gnu14-fast']*3)
        self.assertTrue(any('measured race/local search' in why for why in reasons))

    def test_measured_winner_is_independent_per_node_count(self):
        self.settings['builds']=[dict(self.settings['builds'][0],id=x) for x in ('a','b')]
        self.settings['campaign']['nodes']=[1,2]
        self.settings['campaign']['repeat_every']=99
        self.state['candidates']=c.space(self.settings,self.hw)
        self.state['trials']=[]
        for value in (150,100,100,170):
            item,_=c.select(self.state,self.settings,self.hw)
            self.state['trials'].append({'item':item,'status':'done','result':{'usable':True,'gflops':value}})
        one,_=c.select(self.state,self.settings,self.hw)
        self.assertEqual((one['config']['nodes'],one['build']),(1,'a'))
        self.state['trials'].append({'item':one,'status':'done','result':{'usable':True,'gflops':140}})
        two,_=c.select(self.state,self.settings,self.hw)
        self.assertEqual((two['config']['nodes'],two['build']),(2,'b'))

    def test_failed_candidates_are_not_retried_after_acknowledgment(self):
        item=self.state['candidates'][0]
        self.state['trials']=[{'item':item,'status':'failed','failure_acknowledged_at':'reviewed'}]
        for _ in range(3):
            choice,_=c.select(self.state,self.settings,self.hw)
            self.assertNotEqual(choice['key'],item['key'])
            self.state['trials'].append({'item':choice,'status':'done','result':{'usable':True,'gflops':100}})

    def test_terminal_worker_failure_stops_instead_of_submitting_successor(self):
        item=self.state['candidates'][0]
        self.state['trials']=[{'item':item,'status':'submitted','token':'hc-fail','job_id':'5','reserved_core_hours':57.6}]
        c.atomic(self.root/'state.json',self.state)
        jobs={'5':{'id':'5','name':'hc-fail','state':'FAILED','hours':2}}
        self.settings['safety']['allow_submit']=True
        with patch.object(c,'snapshots',return_value=jobs),patch.object(c,'command') as cmd:
            self.assertIn('unacknowledged failure',c.tick(self.root,True)['stopped'])
            cmd.assert_not_called()
        self.assertTrue((self.root/'STOP').exists())
        self.assertEqual(c.load(self.root)['trials'][0]['status'],'failed')

    def test_invalid_result_records_failure_and_stops_before_chaining(self):
        self.settings['safety']['allow_submit']=True
        item=self.state['candidates'][0]
        self.state['trials']=[{'token':'hc-invalid','job_id':'42','status':'submitted','item':item,
                              'seconds':720,'deadline_epoch':time.time()+2000,'reserved_core_hours':57.6}]
        c.atomic(self.root/'state.json',self.state)
        def invalid(args,cwd,output,seconds,root,env=None):
            (Path(cwd)/'HPCG-Benchmark_3.1_fixture.txt').write_text(self.summary(item).replace('PASSED','FAILED',1))
        with patch.dict(os.environ,{'SLURM_JOB_ID':'42','SLURM_JOB_NUM_NODES':'1'}),             patch.object(c,'run_bounded',side_effect=invalid),patch.object(c,'tick') as tick:
            with self.assertRaisesRegex(RuntimeError,'invalid HPCG result'):
                c.worker(self.root,'hc-invalid')
            tick.assert_not_called()
        failed=c.load(self.root)['trials'][0]
        self.assertFalse(failed['result']['usable'])
        self.assertEqual(failed['status'],'failed')
        self.assertTrue((self.root/'STOP').exists())

    def test_simultaneous_controllers_cannot_overreserve_or_submit_twice(self):
        self.settings['safety']['allow_submit']=True
        self.settings['campaign']['cap_core_hours']=58
        entered=threading.Event()
        release=threading.Event()
        outputs=[]
        def submit(args):
            entered.set()
            self.assertTrue(release.wait(timeout=5))
            return '123'
        def first():
            try:
                outputs.append(c.tick(self.root,True))
            except Exception as e:
                outputs.append(e)
        with patch.object(c,'command',side_effect=submit) as cmd:
            thread=threading.Thread(target=first)
            thread.start()
            try:
                self.assertTrue(entered.wait(timeout=5))
                with self.assertRaises(BlockingIOError):
                    c.tick(self.root,True)
            finally:
                release.set()
                thread.join(timeout=5)
            self.assertEqual(cmd.call_count,1)
        self.assertEqual(outputs[0]['submitted'],'123')
        self.assertLessEqual(c.exposure(c.load(self.root),{}),58)
        self.assertEqual(len(c.load(self.root)['trials']),1)


    def test_overlapping_done_and_pending_jobs_remain_reserved(self):
        self.settings['campaign']['cap_core_hours']=120
        self.settings['safety']['allow_submit']=True
        items=self.state['candidates'][:2]
        self.state['trials']=[{'item':items[0],'token':'hc-done','job_id':'1','status':'done','reserved_core_hours':57.6},
                              {'item':items[1],'token':'hc-next','job_id':'2','status':'submitted','reserved_core_hours':57.6}]
        c.atomic(self.root/'state.json',self.state)
        jobs={'1':{'id':'1','name':'hc-done','state':'RUNNING','hours':57.6},
              '2':{'id':'2','name':'hc-next','state':'PENDING','hours':57.6}}
        self.assertAlmostEqual(c.exposure(self.state,jobs),115.2)
        with patch.object(c,'snapshots',return_value=jobs),patch.object(c,'command') as cmd:
            self.assertEqual(c.tick(self.root,True)['waiting'],'hc-next')
            cmd.assert_not_called()
        self.state['trials'][1]['status']='done'
        c.atomic(self.root/'state.json',self.state)
        with patch.object(c,'snapshots',return_value={}),patch.object(c,'command') as cmd:
            self.assertIn('remaining budget',c.tick(self.root,True)['stopped'])
            cmd.assert_not_called()

    def test_live_campaign_allocation_increase_is_not_silently_ignored(self):
        self.settings['safety']['allow_submit']=True
        self.settings['campaign']['cap_core_hours']=58
        item=self.state['candidates'][0]
        self.state['trials']=[{'item':item,'token':'hc-own','job_id':'12','status':'submitted','reserved_core_hours':57.6}]
        c.atomic(self.root/'state.json',self.state)
        jobs={'12':{'id':'12','name':'hc-own','state':'PENDING','hours':72}}
        with patch.object(c,'snapshots',return_value=jobs),patch.object(c,'command') as cmd:
            result=c.tick(self.root,True)
        self.assertIn('exceeds cap',result['stopped'])
        cmd.assert_called_once_with(['scancel','12'])
        self.assertTrue((self.root/'STOP').exists())


    def test_resume_requires_failure_acknowledgment_and_never_replays_it(self):
        self.settings['safety']['allow_submit']=True
        item=self.state['candidates'][0]
        self.state['trials']=[{'item':item,'status':'failed','token':'hc-failed','job_id':'5','reserved_core_hours':57.6}]
        c.atomic(self.root/'state.json',self.state)
        (self.root/'STOP').touch()
        jobs={'5':{'id':'5','name':'hc-failed','state':'FAILED','hours':2}}
        args=['resume','--state',str(self.root),'--submit']
        with patch.object(c,'snapshots',return_value=jobs),patch.object(c,'command',return_value='123') as cmd:
            with self.assertRaisesRegex(RuntimeError,'acknowledge-failures'):
                c.main(args)
            cmd.assert_not_called()
            self.assertTrue((self.root/'STOP').exists())
            with redirect_stdout(io.StringIO()):
                c.main(args+['--acknowledge-failures'])
            cmd.assert_called_once()
        state=c.load(self.root)
        self.assertTrue(state['trials'][0]['failure_acknowledged_at'])
        self.assertNotEqual(state['trials'][1]['item']['key'],item['key'])
        self.assertEqual(state['trials'][0]['reserved_core_hours'],57.6)

    def test_chain_and_build_smokes_are_separate_minimal_disabled_configs(self):
        chain=self.base/'chain.toml'
        c.smoke_settings(TEMPLATE,chain,'chain')
        s,hw=load_settings(chain)
        self.assertFalse(s['safety']['allow_submit'])
        self.assertEqual(s['campaign']['objective'],'performance')
        items=c.space(s,hw)
        self.assertEqual(len(items),1)
        self.assertEqual((items[0]['config']['ranks_per_node'],items[0]['config']['threads']),(288,1))
        self.assertEqual(c.trial_seconds(items[0],s)*288/3600*2,19.2)
        self.assertEqual(s['campaign']['max_trials'],2)
        for build_id in ('gnu14-fast','aocc5-fast','cce19-strict'):
            out=self.base/(build_id+'.toml')
            c.smoke_settings(TEMPLATE,out,'build',build_id)
            s,hw=load_settings(out)
            self.assertFalse(s['safety']['allow_submit'])
            self.assertEqual(s['campaign']['max_trials'],1)
            self.assertEqual([b['id'] for b in s['builds']],[build_id])
            items=c.space(s,hw)
            self.assertEqual(len(items),1)
            self.assertEqual((items[0]['config']['ranks_per_node'],items[0]['config']['threads']),(144,2))
            self.assertEqual(c.trial_seconds(items[0],s)*288/3600,57.6)
        with self.assertRaisesRegex(ValueError,'requires --build'):
            c.smoke_settings(TEMPLATE,self.base/'bad.toml','build')

    def test_worker_failure_sets_stop_and_preserves_cost(self):
        self.settings['safety']['allow_submit']=True
        item=self.state['candidates'][0]
        self.state['trials']=[{'token':'hc-test','job_id':'42','status':'submitted','item':item,
                              'seconds':720,'deadline_epoch':time.time()+2000,'reserved_core_hours':57.6}]
        c.atomic(self.root/'state.json',self.state)
        with patch.dict(os.environ,{'SLURM_JOB_ID':'42','SLURM_JOB_NUM_NODES':'1'}),\
             patch.object(c,'build',side_effect=RuntimeError('compiler failed')),patch.object(c,'tick') as tick:
            with self.assertRaisesRegex(RuntimeError,'compiler failed'):
                c.worker(self.root,'hc-test')
            tick.assert_not_called()
        self.assertTrue((self.root/'STOP').exists())
        state=c.load(self.root)
        self.assertEqual(state['trials'][0]['status'],'failed')
        self.assertEqual(state['trials'][0]['reserved_core_hours'],57.6)


class AccountingTest(unittest.TestCase):
    def test_accounting_queue_lag_and_terminal_cost(self):
        settings,_=load_settings(TEMPLATE)
        accounting='1|external|COMPLETED|100|288|1|20|1234|1|\n2|pending|PENDING|0|0|0|20||2|\n'
        queue='2|pending|PENDING|2|20:00\n3|lagged|RUNNING|1|10:00\n'
        with patch.object(c,'command',side_effect=[accounting,queue]):
            jobs=c.snapshots(settings)
        self.assertEqual(jobs['1']['hours'],8)
        self.assertEqual(jobs['2']['hours'],192)
        self.assertEqual(jobs['3']['hours'],48)


    def test_pending_zero_blank_allocations_join_queue_before_validation(self):
        settings,_=load_settings(TEMPLATE)
        for allocated in ('0',''):
            accounting=f'7|hc-pending|PENDING|0|0|{allocated}|Unknown||0|\n'
            queue='7|hc-pending|PENDING|2|20:00\n'
            with self.subTest(allocated=allocated),patch.object(c,'command',side_effect=[accounting,queue]):
                jobs=c.snapshots(settings)
            self.assertEqual(jobs['7']['state'],'PENDING')
            self.assertEqual(jobs['7']['hours'],192)
            state={'trials':[{'token':'hc-pending','status':'submitted','job_id':'7'}]}
            c.reconcile(state,jobs)
            self.assertEqual(state['trials'][0]['status'],'submitted')

    def test_pending_requested_resources_fallback_and_unresolved_guard(self):
        settings,_=load_settings(TEMPLATE)
        with patch.object(c,'command',side_effect=['7|hc-pending|PENDING|0|0|0|20||2|\n','']):
            self.assertEqual(c.snapshots(settings)['7']['hours'],192)
        with patch.object(c,'command',side_effect=['7|hc-pending|PENDING|0|0|0|20||0|\n','']):
            with self.assertRaisesRegex(RuntimeError,'no bounded requested resources'):
                c.snapshots(settings)

    def test_cancelled_never_allocated_job_has_zero_external_cost(self):
        settings,_=load_settings(TEMPLATE)
        with patch.object(c,'command',side_effect=['7|cancelled|CANCELLED|0|0||20||1|\n','']):
            self.assertEqual(c.snapshots(settings)['7']['hours'],0)

    def test_accounting_failure_and_unlimited_fail_closed(self):
        settings,_=load_settings(TEMPLATE)
        with patch.object(c,'command',side_effect=subprocess.CalledProcessError(1,'sacct')):
            with self.assertRaises(subprocess.CalledProcessError):
                c.snapshots(settings)
        with patch.object(c,'command',side_effect=['1|job|RUNNING|1|288|1|UNLIMITED||1|\n','']):
            with self.assertRaisesRegex(RuntimeError,'no bounded requested'):
                c.snapshots(settings)


if __name__=='__main__':
    unittest.main()
