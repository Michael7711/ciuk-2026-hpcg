"""Bounded HPCG Slurm job chain. Standard library only; no login-node daemon.

State is an atomic JSON ledger under an advisory lock. Every submission consumes its
full allocation reservation permanently. Uncertain submissions are never retried.
Use python -m autotune.campaign --help. Legacy HPL commands are independent.
"""
import argparse
import copy
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import signal
import statistics
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict

from .config import Config, Hardware, load_settings, validate
from .candidates import rank_layouts
from .jobs import binary_sha256, prepare_run, render_job_script, walltime_s
from .results import make_row, parse_hpcg, read_pm_counters

UTC = dt.timezone.utc
TERMINAL = {'COMPLETED', 'FAILED', 'CANCELLED', 'TIMEOUT', 'OUT_OF_MEMORY',
            'NODE_FAIL', 'PREEMPTED', 'BOOT_FAIL', 'DEADLINE', 'REVOKED'}


def stamp():
    return dt.datetime.now(UTC).isoformat()


def epoch(value):
    x = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if x.tzinfo is None:
        raise ValueError('timestamps must include timezone, e.g. +00:00')
    return x.timestamp()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def atomic(path, obj):
    path = Path(path)
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('w') as f:
        json.dump(obj, f, indent=2, allow_nan=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def locked(root):
    with (root / 'LOCK').open('r+') as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def command(args, **kw):
    return subprocess.run(args, check=True, text=True, capture_output=True,
                          timeout=45, **kw).stdout


def source_hash(source):
    """Actual source and make templates, including local edits; excludes runs/builds/Git."""
    source = Path(source)
    paths = [source / 'configure', source / 'Makefile.ext', source / 'bin/hpcg.dat']
    paths += sorted((source / 'src').glob('*'))
    paths += sorted((source / 'setup').glob('Make.*'))
    h = hashlib.sha256()
    for path in paths:
        if path.is_file():
            h.update(str(path.relative_to(source)).encode())
            h.update(path.read_bytes())
    if not (source / 'src/main.cpp').is_file():
        raise ValueError('HPCG source tree missing src/main.cpp')
    return h.hexdigest()


def grid(points_per_rank):
    """Near-cubic multiples of eight; choose closest volume then aspect ratio."""
    n = (points_per_rank ** (1 / 3)) / 8
    values = range(max(1, int(n) - 3), int(n) + 5)
    choices = [(8*x, 8*y, 8*z) for x in values for y in values for z in values
               if x <= y <= z and z / x <= 1.5]
    return min(choices, key=lambda d: (abs(math.prod(d) / points_per_rank - 1), d[2]/d[0]))


def space(settings, hw):
    c = settings['campaign']
    out = []
    for b in settings['builds']:
        if not b.get('enabled', True):
            continue
        for nodes in c['nodes']:
            target = c['points_per_node'] * (nodes if c['scaling'] == 'weak' else 1)
            for rpn, threads in rank_layouts(hw, c['fill']):
                if threads not in c['threads'] or rpn < c['min_ranks_per_node']:
                    continue
                dims = grid(target / (nodes*rpn))
                points = math.prod(dims) * rpn * nodes
                if abs(points / target - 1) > c['volume_tolerance']:
                    continue
                # Conservative upper bound includes allocator/setup overhead beyond data memory.
                mem = points / nodes * c['memory_bytes_per_point'] * c['memory_headroom']
                if mem > hw.mem_bytes * hw.max_mem_fraction:
                    continue
                cfg = Config('hpcg', nodes, rpn, threads,
                             dict(zip(('nx','ny','nz'), dims), runtime_s=c['runtime_s']), c['kind'])
                if validate(cfg, hw):
                    continue
                item = {'build': b['id'], 'config': asdict(cfg), 'points': points,
                        'estimated_peak_bytes_per_node': mem}
                item['key'] = digest(item)
                out.append(item)
    if not out:
        raise ValueError('no memory-safe comparable candidates')
    return out


def check_settings(s, hw):
    c = s['campaign']
    positive = ['physical_memory_bytes_per_node', 'cap_core_hours', 'max_trials', 'repeats',
                'points_per_node', 'runtime_s', 'memory_bytes_per_point',
                'memory_headroom', 'pending_timeout_s', 'build_timeout_s', 'control_margin_s',
                'repeat_every', 'min_ranks_per_node', 'team_safe_balance_estimate_core_hours']
    for k in positive:
        if not math.isfinite(c[k]) or c[k] <= 0:
            raise ValueError(f'campaign.{k} must be positive and finite')
    if c['cap_core_hours'] > 500 or c['cap_core_hours'] > c['team_safe_balance_estimate_core_hours']:
        raise ValueError('campaign cap must be <=500 and <= the advisory SAFE estimate (not a live balance)')
    for k in ('max_trials','repeats','points_per_node','runtime_s',
              'pending_timeout_s','build_timeout_s','control_margin_s','repeat_every','min_ranks_per_node'):
        if type(c[k]) is not int:
            raise ValueError(f'campaign.{k} must be an integer')
    performance_only(s)
    if c['scaling'] not in ('weak','strong'):
        raise ValueError('unknown scaling')
    if not math.isfinite(c['noise_tolerance']) or not 0 <= c['noise_tolerance'] <= .25:
        raise ValueError('noise_tolerance must be between 0 and 0.25')
    margin=s['slurm'].get('hpcg_overhead_s',600)
    if type(margin) is not int or margin<=0:
        raise ValueError('hpcg_overhead_s must be a positive integer')
    if not c['nodes'] or any(type(n) is not int or not 1 <= n <= 4 for n in c['nodes']):
        raise ValueError('node counts must be 1..4')
    if not c['threads'] or any(type(n) is not int or n < 1 for n in c['threads']):
        raise ValueError('threads must be positive integers')
    if not c['fill'] or any(not 0 < f <= 1 for f in c['fill']):
        raise ValueError('fill must be in (0,1]')
    if not 0 < c['volume_tolerance'] <= 0.1 or c['memory_headroom'] < 1:
        raise ValueError('volume tolerance must be <=10%; memory headroom must be >=1')
    if epoch(c['deadline']) <= time.time():
        raise ValueError('deadline has passed')
    if epoch(c['budget_since']) > time.time():
        raise ValueError('budget_since is in the future')
    if c['kind'] == 'final' and c['runtime_s'] < 1800:
        raise ValueError('final runs require >=1800 seconds requested')
    if not s.get('builds'):
        raise ValueError('at least one build is required')
    ids = [b['id'] for b in s['builds']]
    if len(ids) != len(set(ids)) or any(not x or not all(ch.isalnum() or ch in '-_' for ch in x) for x in ids):
        raise ValueError('build ids must be unique safe names')
    for b in s['builds']:
        if not b.get('enabled', True):
            continue
        if 'binary' in b:
            if binary_sha256(b['binary']) != b['sha256']:
                raise ValueError(f"binary hash mismatch: {b['id']}")
        elif not b.get('flags') or not b.get('modules'):
            raise ValueError('build recipe requires flags and modules')
    if s['slurm'].get('inline') or s['slurm'].get('extra_directives'):
        raise ValueError('campaign requires dedicated allocation; extra directives unsupported')
    if any(k in s.get('env', {}) for k in ('OMP_NUM_THREADS','OMP_PLACES','OMP_PROC_BIND')):
        raise ValueError('OpenMP placement and thread count must come from candidate')
    if s.get('energy', {}).get('counter') and not Path(s['energy']['counter']).is_absolute():
        raise ValueError('energy counter must be an absolute path')
    if s['slurm'].get('srun_flags'):
        raise ValueError('campaign does not accept srun resource overrides')
    if not Path(c['source']).is_absolute() or not Path(c['state_prefix']).is_absolute():
        raise ValueError('source and state_prefix must be absolute shared paths')
    if hw.cores_per_node != 288:
        raise ValueError('Cirrus campaign expects 288 physical cores per exclusive node')
    for item in space(s, hw):
        trial_seconds(item, s)  # validate QoS limits before any submission


def trial_seconds(item, settings):
    cfg = Config(**item['config'])
    c = settings['campaign']
    recipe = next(b for b in settings['builds'] if b['id']==item['build'])
    seconds = walltime_s(cfg, settings) + (0 if 'binary' in recipe else c['build_timeout_s']) + c['control_margin_s']
    seconds = math.ceil(seconds/60)*60  # Slurm rounds time limits up to whole minutes.
    limit = settings['slurm']['final_max_walltime_s' if cfg.kind == 'final' else 'max_walltime_s']
    if seconds > limit:
        raise ValueError(f'trial reservation {seconds}s exceeds configured QoS limit {limit}s')
    return seconds


def compatible(item, result):
    """No transfer across compiler/binary, node count, volume policy or duration."""
    a, b = item['config'], result['item']['config']
    return (item['build'] == result['item']['build'] and a['nodes'] == b['nodes']
            and a['kind'] == b['kind'] and a['params']['runtime_s'] == b['params']['runtime_s'])


def performance_only(settings):
    if settings['campaign']['objective'] != 'performance':
        raise ValueError('efficiency/alternate selection unavailable: no verified benchmark-window '
                         'energy measurement; use objective=performance')


def layout_key(item):
    cfg=item['config']
    return (cfg['nodes'], cfg['kind'], tuple(sorted(cfg['params'].items())),
            cfg['ranks_per_node'], cfg['threads'])


def select(state, settings, hw, affordable=None):
    """Small-budget measured racing, followed by local layout search. No pooled model.

    Screen builds at a common anchor per node count. Match the actual workload and
    layout when comparing builds. Then spend on the observed winner's neighbours;
    periodically repeat close contenders. A one-point screen is provisional.
    """
    performance_only(settings)
    c=settings['campaign']
    trials=state['trials']
    counts={i['key']:sum(t['item']['key']==i['key'] for t in trials) for i in state['candidates']}
    failed={t['item']['key'] for t in trials if t.get('status')=='failed'}
    pool=[i for i in state['candidates'] if counts[i['key']]<c['repeats'] and i['key'] not in failed
          and (affordable is None or trial_seconds(i,settings)*hw.cores_per_node*i['config']['nodes']/3600<=affordable)]
    if not pool:
        return None, 'candidate/repeat or remaining budget limit'
    order={b['id']:n for n,b in enumerate(settings['builds'])}
    groups={}
    for i in state['candidates']:
        groups.setdefault((i['config']['nodes'],i['build']),[]).append(i)
    def hardware(i):
        cfg=i['config']
        active=cfg['ranks_per_node']*cfg['threads']
        return (hw.cores_per_node-active,cfg['threads'],-cfg['ranks_per_node'])
    anchors={key:min(items,key=hardware) for key,items in groups.items()}
    unscreened=[i for i in anchors.values() if counts[i['key']]==0 and i in pool]
    if unscreened:
        i=min(unscreened,key=lambda i:(i['config']['nodes'],order[i['build']]))
        return i, f'hardware anchor screen; build={i["build"]}, nodes={i["config"]["nodes"]}; matched layout/workload'
    measured={}
    known={i['key']:i for i in state['candidates']}
    for t in trials:
        r=t.get('result',{})
        value=r.get('gflops')
        if (known.get(t['item']['key'])==t['item'] and t.get('status')=='done'
                and r.get('usable') and value is not None and math.isfinite(value) and value>0):
            measured.setdefault(t['item']['key'],[]).append(value)
    def mean(i):
        return statistics.mean(measured[i['key']])
    node_options=[]
    for nodes in sorted({i['config']['nodes'] for i in pool}):
        # Only exact matching anchor layouts may race against each other.
        by_layout={}
        for (n,build_id),anchor in anchors.items():
            if n==nodes and anchor['key'] in measured:
                by_layout.setdefault(layout_key(anchor),[]).append(anchor)
        if not by_layout:
            continue
        comparisons=max(by_layout.values(),key=lambda xs:(len(xs),-order[xs[0]['build']]))
        winner=max(comparisons,key=mean)
        best=mean(winner)
        noise=max([c['noise_tolerance']]+[2*statistics.stdev(measured[i['key']])/mean(i)
                  for i in comparisons if len(measured[i['key']])>1])
        close=[i for i in comparisons if mean(i)>=best*(1-noise)]
        local=[i for i in pool if i['config']['nodes']==nodes and i['build']==winner['build']]
        repeats=[i for i in close if i in pool and counts[i['key']]>0]
        if trials and len(trials)%c['repeat_every']==0 and repeats:
            choice=min(repeats,key=lambda i:(counts[i['key']],-mean(i),order[i['build']]))
            reason=f'measured race repeat for noise; anchor mean={mean(choice):.6g} GFLOP/s; {len(close)} contenders within {noise:.1%}'
        elif local:
            observed=[i for i in groups[(nodes,winner['build'])] if i['key'] in measured]
            pivot=max(observed,key=mean)
            unseen=[i for i in local if counts[i['key']]==0]
            if unseen:
                def distance(i):
                    a,b=i['config'],pivot['config']
                    return (abs(math.log2(a['ranks_per_node']/b['ranks_per_node']))+
                            abs(math.log2(a['threads']/b['threads'])),hardware(i))
                choice=min(unseen,key=distance)
            else:
                choice=min(local,key=lambda i:(counts[i['key']],-mean(i) if i['key'] in measured else 0))
            reason=(f'measured race/local search; build={winner["build"]} won {len(comparisons)} matched anchors '
                    f'at {best:.6g} GFLOP/s; search near its best observed layout '
                    f'{pivot["config"]["ranks_per_node"]}x{pivot["config"]["threads"]} '
                    f'({mean(pivot):.6g} GFLOP/s); provisional, no cross-build response model')
        else:
            continue
        node_options.append((sum(t['item']['config']['nodes']==nodes for t in trials),nodes,choice,reason))
    if node_options:
        _,_,item,reason=min(node_options,key=lambda x:x[:2])
        return item,reason
    # Winner exhausted or unaffordable: keep exploring other measured strata, explicitly.
    i=min(pool,key=lambda i:(counts[i['key']],hardware(i),order[i['build']]))
    return i,'hardware fallback: no affordable measured winner neighbour; no usable cross-build model'


def snapshots(settings):
    """Submitting-user/account view only; this is NOT the team's SAFE balance.

    Pending allocations may be zero/blank in sacct. Defer their resource validation
    until after joining squeue, and fall back to requested resources if needed.
    """
    c=settings['campaign']
    if not os.environ.get('USER'):
        raise RuntimeError('USER is required for scheduler reconciliation')
    fields='JobIDRaw,JobName%100,State,ElapsedRaw,AllocCPUS,AllocNodes,TimelimitRaw,ConsumedEnergyRaw,ReqNodes'
    text=command(['sacct','-X','-u',os.environ['USER'],'-A',settings['slurm']['account'],
                  '-S',dt.datetime.fromtimestamp(epoch(c['budget_since'])).strftime('%Y-%m-%dT%H:%M:%S'),
                  '-n','-P',f'--format={fields}'])
    records={}
    for line in text.splitlines():
        f=line.strip().split('|')
        if len(f)<9 or not f[0].isdigit():
            raise RuntimeError('malformed/unsupported accounting snapshot')
        jid,name,status,elapsed,cpus,allocated,minutes,energy,requested=f[:9]
        records[jid]={'id':jid,'name':name,'state':status.split()[0].rstrip('+'),
                      'elapsed':elapsed,'cpus':cpus,'allocated':allocated,
                      'minutes':minutes,'energy_j':energy,'requested':requested}
    queue=command(['squeue','-h','-u',os.environ['USER'],'-A',settings['slurm']['account'],
                   '-o','%i|%j|%T|%D|%l'])
    from .results import _slurm_seconds
    jobs={}
    for line in queue.splitlines():
        f=line.strip().split('|')
        if len(f)!=5 or not f[0].isdigit():
            raise RuntimeError('malformed/unsupported queue snapshot')
        jid,name,status,nodes,limit=f
        try:
            hours=int(nodes)*288*_slurm_seconds(limit)/3600
        except ValueError as e:
            raise RuntimeError('unknown queue node/walltime reservation') from e
        if int(nodes)<1 or hours<=0 or not math.isfinite(hours):
            raise RuntimeError('unknown queue node/walltime reservation')
        jobs[jid]={'id':jid,'name':name,'state':status,'hours':hours,
                   'energy_j':records.get(jid,{}).get('energy_j','')}
    def integer(value):
        return int(value) if value.isdigit() else 0
    for jid,r in records.items():
        nodes=max(integer(r['allocated']),integer(r['requested']))
        cpus=max(integer(r['cpus']),nodes*288)
        if jid in jobs:
            # Queue is authoritative for the current state/resources. Never replace a
            # live pending record with stale sacct state or its zero allocation.
            continue
        if r['state'] in TERMINAL:
            elapsed=integer(r['elapsed'])
            if not r['elapsed'].isdigit() or (elapsed>0 and cpus==0):
                raise RuntimeError('unknown terminal accounting cost')
            hours=elapsed*cpus/3600
        else:
            if not r['minutes'].isdigit() or int(r['minutes'])<=0 or nodes<1:
                raise RuntimeError('active job absent from squeue with no bounded requested resources; retry reconciliation')
            hours=int(r['minutes'])*60*cpus/3600
        jobs[jid]={'id':jid,'name':r['name'],'state':r['state'],'hours':hours,'energy_j':r['energy_j']}
    return jobs


def campaign_jobs(state,jobs):
    names={t['token'] for t in state['trials']}
    ids={t.get('job_id') for t in state['trials']}
    return {jid:j for jid,j in jobs.items() if jid in ids or j['name'] in names}


def exposure(state, jobs):
    """Campaign ceiling only. Other users/jobs are NOT deducted from this allowance."""
    total=0
    for t in state['trials']:
        matching=[j for j in jobs.values() if j['id']==t.get('job_id') or j['name']==t['token']]
        if len(matching)>1:
            raise RuntimeError('multiple jobs for one reservation; safety stop required')
        total+=max(t['reserved_core_hours'],matching[0]['hours'] if matching else 0)
    return total


def budget_report(state,settings,jobs):
    owned=campaign_jobs(state,jobs or {})
    return {'campaign_reserved_core_hours':exposure(state,jobs or {}),
            'campaign_cap_core_hours':settings['campaign']['cap_core_hours'],
            'other_submitting_user_job_exposure_core_hours':(sum(j['hours'] for jid,j in jobs.items() if jid not in owned) if jobs is not None else None),
            'scheduler_snapshot_available':jobs is not None,
            'scheduler_scope':'submitting_user_and_account_only',
            'team_safe_balance_estimate_core_hours':settings['campaign']['team_safe_balance_estimate_core_hours'],
            'team_safe_balance_verified':False}


def load(root):
    return json.loads((root/'state.json').read_text())


def settings_for(state):
    live,hw=load_settings(state['settings_path'])
    frozen=copy.deepcopy(live)
    frozen.get('safety',{}).pop('allow_submit',None)
    if digest(frozen)!=state['settings_hash']:
        raise RuntimeError('settings changed; start a separate campaign (only safety.allow_submit may change)')
    if source_hash(live['campaign']['source'])!=state['source_hash']:
        raise RuntimeError('HPCG source changed since init')
    if code_hash()!=state['controller_hash']:
        raise RuntimeError('controller code changed since init; stop and review')
    return live,hw


def code_hash():
    return digest({p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(Path(__file__).parent.glob('*.py'))})


def stopped(root):
    return (root/'STOP').exists()


def enabled(settings):
    if settings.get('safety',{}).get('allow_submit') is not True:
        raise PermissionError('submission disabled: set safety.allow_submit=true only after review')


def reconcile(state,jobs):
    for t in state['trials']:
        matches=[j for j in jobs.values() if j['name']==t['token'] or j['id']==t.get('job_id')]
        if len(matches)>1:
            raise RuntimeError('multiple scheduler jobs match one intent; emergency stop required')
        if matches:
            j=matches[0]
            t['job_id']=j['id']
            if j.get('energy_j'):
                t['whole_job_energy_j']=j['energy_j']
            if t['status'] not in ('done','failed','abandoned'):
                if j['state'] in TERMINAL:
                    t['status']='failed'
                    t['error']='scheduler terminal without completed worker: '+j['state']
                elif t['status']=='intent':
                    t['status']='submitted'
        elif t['status'] in ('intent','submitted','running'):
            raise RuntimeError(f"unresolved submission {t['token']}; never automatically resubmit; reconcile/abandon explicitly")


def worker_script(root,t,settings):
    cfg=Config(**t['item']['config'])
    local=copy.deepcopy(settings)
    local['hpcg']={'binary':'/unused'}
    text=render_job_script(cfg,local,Hardware(**settings['hardware']),root,t['token'])
    directives=[line for line in text.splitlines() if line.startswith('#!') or line.startswith('#SBATCH')]
    seconds=t['seconds']
    directives=[line for line in directives if not line.startswith('#SBATCH --time=')]
    directives += [f'#SBATCH --time={seconds//3600:02}:{seconds%3600//60:02}:{seconds%60:02}',
                   '#SBATCH --no-requeue']
    # Slurm local absolute deadline is interpreted in Cirrus local time; epoch -> local.
    deadline=dt.datetime.fromtimestamp(t['deadline_epoch']).strftime('%Y-%m-%dT%H:%M:%S')
    directives += [f'#SBATCH --deadline={deadline}']
    repo=Path(__file__).resolve().parents[1]
    return '\n'.join(directives+["set -eu",f'cd {shlex.quote(str(repo))}',
        'module load python/3.11.7', f'exec {shlex.quote(sys.executable)} -m autotune.campaign worker --state {shlex.quote(str(root))} --token {t["token"]}', ''])


def tick(root, submit=False):
    with locked(root):
        state=load(root)
        settings,hw=settings_for(state)
        if stopped(root):
            return {'stopped':'STOP file present'}
        if submit:
            enabled(settings)
        jobs=snapshots(settings)
        reconcile(state,jobs)
        failures=[t for t in state['trials'] if t['status']=='failed' and not t.get('failure_acknowledged_at')]
        if failures:
            if submit:
                (root/'STOP').touch()
                atomic(root/'state.json',state)
            return {'stopped':'unacknowledged failure; inspect and explicitly acknowledge before resume',
                    'failed_tokens':[t['token'] for t in failures]}
        used=exposure(state,jobs)
        if used>settings['campaign']['cap_core_hours']:
            if submit:
                (root/'STOP').touch()
                atomic(root/'state.json',state)
                live=[j['id'] for j in campaign_jobs(state,jobs).values() if j['state'] not in TERMINAL]
                if live:
                    command(['scancel',*live])
            return {'stopped':'campaign reservation exceeds cap; safety stop',
                    'budget':budget_report(state,settings,jobs)}
        active=[t for t in state['trials'] if t['status'] in ('intent','submitted','running')]
        if active:
            if submit:
                atomic(root/'state.json',state)
            return {'waiting':active[0]['token'],'job_id':active[0].get('job_id')}
        c=settings['campaign']
        if len(state['trials'])>=c['max_trials']:
            return {'stopped':'max_trials','reserved_core_hours':used}
        item,why=select(state,settings,hw,c['cap_core_hours']-used)
        if item is None:
            return {'stopped':why,'reserved_core_hours':used}
        seconds=trial_seconds(item,settings)
        cost=seconds*hw.cores_per_node*item['config']['nodes']/3600
        now=time.time()
        deadline=min(epoch(c['deadline']),now+c['pending_timeout_s']+seconds)
        if now+seconds+30>deadline:
            return {'stopped':'deadline cannot fit complete next trial'}
        out={'candidate':item,'reason':why,'reserved_core_hours':used,
             'next_reservation_core_hours':cost,'cap_core_hours':c['cap_core_hours'],
             'budget':budget_report(state,settings,jobs)}
        if not submit:
            return out
        # Persist intent BEFORE sbatch. Any exception leaves this reservation in place.
        t={'item':item,'token':'hc-'+uuid.uuid4().hex[:20], 'status':'intent',
           'reserved_core_hours':cost,'seconds':seconds,'deadline_epoch':deadline,
           'selected_at':stamp(),'reason':why}
        state['trials'].append(t)
        atomic(root/'state.json',state)
        script=root/(t['token']+'.sh')
        script.write_text(worker_script(root,t,settings))
        if stopped(root):
            return {'stopped':'STOP appeared before submission; intent retained'}
        jid=command(['sbatch','--parsable',str(script)]).strip().split(';')[0]
        if not jid.isdigit():
            raise RuntimeError('ambiguous sbatch response; intent retained for reconciliation')
        t.update(job_id=jid,status='submitted')
        atomic(root/'state.json',state)
        return {**out,'submitted':jid}


def run_bounded(args,cwd,output,seconds,root,env=None):
    """Kill process group on stop, timeout or controller signal; Slurm also limits the allocation."""
    with Path(output).open('w') as f:
        proc=subprocess.Popen(args,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        end=time.monotonic()+seconds
        try:
            while proc.poll() is None:
                if stopped(root) or time.monotonic()>end:
                    raise RuntimeError('STOP or subprocess time limit')
                time.sleep(1)
            if proc.returncode:
                raise RuntimeError(f'subprocess exited {proc.returncode}; see {output}')
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid,signal.SIGTERM)
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid,signal.SIGKILL)
                    proc.wait()


def build(root,settings,build_id):
    b=next(b for b in settings['builds'] if b['id']==build_id)
    if 'binary' in b:
        if binary_sha256(b['binary'])!=b['sha256']:
            raise RuntimeError('prebuilt executable changed')
        return {'binary':b['binary'],'sha256':b['sha256'],'modules':b['modules'], 'recipe':b}
    path=root/'builds'/build_id
    manifest=path/'manifest.json'
    if manifest.exists():
        m=json.loads(manifest.read_text())
        if m['sha256']!=binary_sha256(m['binary']):
            raise RuntimeError('cached build hash changed')
        return m
    path.mkdir(parents=True,exist_ok=False)  # partial builds require inspection; never overwrite
    source=Path(settings['campaign']['source']).resolve()
    flags='$(HPCG_DEFS) '+ ' '.join(b['flags'])
    script='\n'.join(['set -eu','module restore',
        *[f'module load {shlex.quote(m)}' for m in b['modules']],
        'module list > modules.txt 2>&1','CC --version > compiler.txt 2>&1',
        f'{shlex.quote(str(source/"configure"))} MPI_GCC_OMP',
        f'make -j 8 CXX=CC LINKER=CC {shlex.quote("CXXFLAGS="+flags)} {shlex.quote("LINKFLAGS="+flags)}',
        'ldd bin/xhpcg > libraries.txt'])
    (path/'build.sh').write_text(script+'\n')
    run_bounded(['bash','--login','build.sh'],path,path/'build.log',settings['campaign']['build_timeout_s'],root)
    binary=str(path/'bin/xhpcg')
    m={'binary':binary,'sha256':binary_sha256(binary),'modules':b['modules'],'recipe':b,
       'source_hash':source_hash(source)}
    atomic(manifest,m)
    return m


def validate_output(text,item,hw,settings):
    parsed=parse_hpcg(text)
    cfg=Config(**item['config'])
    fields=dict(line.split('=',1) for line in text.splitlines() if '=' in line)
    def number(key):
        x=float(fields[key])
        if not math.isfinite(x):
            raise ValueError('nonfinite output')
        return x
    try:
        p=cfg.params
        required={'Machine Summary::Distributed Processes':cfg.mpi_ranks,
                  'Machine Summary::Threads per processes':cfg.threads,
                  'Local Domain Dimensions::nx':p['nx'], 'Local Domain Dimensions::ny':p['ny'],
                  'Local Domain Dimensions::nz':p['nz']}
        good=all(number(k)==v for k,v in required.items())
        tests=[v for k,v in fields.items() if k.endswith('::Result')]
        good &= len(tests)>=4 and all(v=='PASSED' for v in tests)
        runtime=number('Benchmark Time Summary::Total')
        memory=number('Memory Use Information::Total memory used for data (Gbytes)')*1e9
        good &= (parsed.get('validation')=='VALID' and parsed.get('gflops',0)>0
                 and math.isfinite(parsed['gflops']) and runtime>=0.8*p['runtime_s']
                 and memory>0 and memory/cfg.nodes <= hw.mem_bytes*hw.max_mem_fraction)
        official=(good and runtime>=1800 and memory/cfg.nodes>=settings['campaign']['physical_memory_bytes_per_node']/4)
        if cfg.kind=='final':
            good &= official
        return {**parsed,'usable':bool(good),'official_eligible':bool(official),
                'reported_data_bytes':memory,'runtime_s':runtime}
    except (KeyError,ValueError,TypeError):
        return {**parsed,'usable':False,'official_eligible':False}


def worker(root,token):
    def interrupted(signum,frame):
        raise RuntimeError(f'worker signal {signum}')
    signal.signal(signal.SIGTERM,interrupted)
    signal.signal(signal.SIGINT,interrupted)
    with locked(root):
        state=load(root)
        settings,hw=settings_for(state)
        enabled(settings)
        t=next(t for t in state['trials'] if t['token']==token)
        jid=os.environ.get('SLURM_JOB_ID')
        if not jid or (t.get('job_id') and jid!=t['job_id']) or t['status'] not in ('intent','submitted'):
            raise RuntimeError('worker allocation/intent mismatch or already executed')
        cfg=Config(**t['item']['config'])
        if int(os.environ.get('SLURM_JOB_NUM_NODES','0'))!=cfg.nodes:
            raise RuntimeError('allocation node count mismatch')
        if stopped(root) or time.time()>t['deadline_epoch']-t['seconds']:
            raise RuntimeError('worker started after latest safe start or STOP')
        t.update(job_id=jid,status='running',started_at=stamp())
        atomic(root/'state.json',state)
        item=copy.deepcopy(t['item'])
    try:
        manifest=build(root,settings,item['build'])
        with locked(root):
            current=load(root)
            hashes=current.setdefault('build_hashes',{})
            previous=hashes.get(item['build'])
            if previous is not None and previous!=manifest['sha256']:
                raise RuntimeError('build executable identity changed within campaign')
            hashes[item['build']]=manifest['sha256']
            atomic(root/'state.json',current)
        local=copy.deepcopy(settings)
        local['slurm']['modules']=manifest['modules']
        local['slurm']['reset_modules']=True
        local['slurm']['inline']=True
        local['slurm']['thread_sample_after_s']=0
        local['hpcg']={'binary':manifest['binary'],'build_id':item['build']}
        local['paths']={'required_prefix':str(root)}
        replicate=1+sum(x['item']['key']==item['key'] for x in state['trials'] if x['token']!=token)
        run_dir=prepare_run(cfg,local,hw,root/'runs',replicate=replicate)
        (run_dir/'build.json').write_text(json.dumps(manifest,indent=2))
        raw=run_dir/f'slurm-{jid}.out'
        # Preserve inherited allocation topology, but do not inherit a previous job's task count.
        env=dict(os.environ)
        env['SLURM_NTASKS']=str(cfg.mpi_ranks)
        env['SLURM_NTASKS_PER_NODE']=str(cfg.ranks_per_node)
        env['SLURM_CPUS_PER_TASK']=str(hw.cores_per_node//cfg.ranks_per_node)
        run_bounded(['bash','--login','job.sh'],run_dir,raw,walltime_s(cfg,local),root,env)
        summaries=list(run_dir.glob('HPCG-Benchmark_*.txt'))
        if len(summaries)!=1:
            raise RuntimeError('expected exactly one fresh HPCG summary')
        result=validate_output(summaries[0].read_text(),item,hw,settings)
        energy=read_pm_counters(run_dir,cfg.nodes)
        # Existing wrappers surround the benchmark PROCESS (setup+solve); never call it timed-solve energy.
        if energy.get('energy_status')=='ok' and (
                not math.isfinite(energy.get('energy_j',0)) or energy.get('energy_j',0)<=0
                or not math.isfinite(energy.get('energy_window_s',0))
                or energy.get('energy_window_s',0)<result.get('runtime_s',0)*.95
                or energy.get('energy_window_s',0)>walltime_s(cfg,local)):
            energy['energy_status']='inconsistent'
        row=make_row(cfg,run_dir.name,result,jid,energy,str(summaries[0]),
                     {'build_id':item['build'],'binary_path':manifest['binary'],
                      'binary_sha256':manifest['sha256'],'replicate':replicate})
        result.update(gflops_per_w=row.get('gflops_per_w') or None,
                      energy_scope='benchmark_process' if energy.get('energy_status')=='ok' else 'unavailable',
                      binary_sha256=manifest['sha256'],row=row)
        atomic(run_dir/'result.json',result)
        with locked(root):
            state=load(root)
            t=next(t for t in state['trials'] if t['token']==token)
            t.update(status='done' if result['usable'] else 'failed',result=result,
                     run_dir=str(run_dir),finished_at=stamp())
            atomic(root/'state.json',state)
        if not result['usable']:
            raise RuntimeError('invalid HPCG result: safety stop; no successor or automatic retry')
    except Exception as e:
        (root/'STOP').touch()  # Block admission before attempting the failure ledger write.
        with locked(root):
            state=load(root)
            t=next(t for t in state['trials'] if t['token']==token)
            t.update(status='failed',error=str(e),finished_at=stamp())
            atomic(root/'state.json',state)
        # Stop on unexpected failures; resume is an explicit inspection step.
        (root/'STOP').touch()
        raise
    if not stopped(root):
        # This job is marked done in our ledger but remains charged at its full reservation.
        print(json.dumps(tick(root,submit=True),indent=2))


def init(settings_path,root):
    settings,hw=load_settings(settings_path)
    check_settings(settings,hw)
    frozen=copy.deepcopy(settings)
    frozen.get('safety',{}).pop('allow_submit',None)
    prefix=Path(settings['campaign']['state_prefix']).resolve()
    if not root.resolve().is_relative_to(prefix):
        raise ValueError(f'campaign state must be under shared state_prefix {prefix}')
    root.mkdir(parents=True,exist_ok=False)
    (root/'LOCK').touch()
    atomic(root/'state.json',{'version':1,'created_at':stamp(),'settings_path':str(settings_path.resolve()),
        'settings_hash':digest(frozen),'source_hash':source_hash(settings['campaign']['source']),
        'controller_hash':code_hash(),'candidates':space(settings,hw),'trials':[]})
    return {'initialised':str(root),'candidates':len(space(settings,hw)),'submitted':False}


def stop(root):
    # Sentinel first: workers check it even if the ledger is temporarily locked.
    (root/'STOP').touch()
    with locked(root):
        state=load(root)
        settings,_=load_settings(state['settings_path'])
        jobs=snapshots(settings)
        names={t['token'] for t in state['trials']}
        ids=[j['id'] for j in jobs.values() if j['name'] in names and j['state'] not in TERMINAL]
        if ids:
            command(['scancel',*ids])
        return {'STOP':str(root/'STOP'),'cancel_requested':ids}


def report(root, scheduler=False):
    state=load(root)
    s,_=settings_for(state)
    jobs=None
    if scheduler:
        jobs=snapshots(s)
        for t in state['trials']:
            j=jobs.get(t.get('job_id'),{})
            if j.get('energy_j'):
                t['whole_job_energy_j']=j['energy_j']
    groups={}
    for t in state['trials']:
        r=t.get('result',{})
        if r.get('usable'):
            groups.setdefault(t['item']['key'],[]).append(t)
    rows=[]
    for ts in groups.values():
        vals=[t['result']['gflops'] for t in ts]
        eff=[t['result']['gflops_per_w'] for t in ts if t['result'].get('gflops_per_w')]
        rows.append({'build':ts[0]['item']['build'],'config':ts[0]['item']['config'],
                     'repeats':len(vals),'gflops_mean':statistics.mean(vals),
                     'gflops_sd':statistics.stdev(vals) if len(vals)>1 else None,
                     'gflops_per_w_mean':statistics.mean(eff) if eff else None,
                     'energy_scope':'benchmark_process' if eff else 'unavailable'})
    return {'stopped':stopped(root),'reserved_core_hours':sum(t['reserved_core_hours'] for t in state['trials']),
            'trials':state['trials'],'summary':rows,
            'scheduler':jobs, 'budget':budget_report(state,s,jobs)}



def smoke_settings(template, output, purpose='chain', build_id=None):
    """Prepare separate tiny chain/build canaries. This never builds or submits."""
    s,_=load_settings(template)
    if purpose=='chain':
        if build_id is not None:
            raise ValueError('--build applies only to --purpose build')
        s['builds']=[next(b for b in s['builds'] if 'binary' in b)]
        cap,trials,threads=20.0,2,[1]
    elif purpose=='build':
        recipes=[b for b in s['builds'] if b['id']==build_id and 'binary' not in b]
        if len(recipes)!=1:
            raise ValueError('--purpose build requires --build naming one compiler recipe')
        s['builds']=recipes
        s['builds'][0]['enabled']=True
        cap,trials,threads=60.0,1,[2]
    else:
        raise ValueError('unknown smoke purpose')
    s['safety']['allow_submit']=False
    s['slurm']['hpcg_overhead_s']=90
    now=dt.datetime.now(UTC)
    s['campaign'].update(cap_core_hours=cap,max_trials=trials,repeats=trials,nodes=[1],
                         threads=threads,fill=[1.0],runtime_s=10,kind='diagnostic',
                         points_per_node=(288 if purpose=='chain' else 144)*16**3,objective='performance',
                         control_margin_s=20,build_timeout_s=600,
                         budget_since=now.isoformat(),deadline=(now+dt.timedelta(days=1)).isoformat())
    lines=[]
    for section,values in s.items():
        if section=='builds':
            continue
        lines.append('['+section+']')
        lines += [k+' = '+json.dumps(v) for k,v in values.items()]
        lines.append('')
    for b in s['builds']:
        lines.append('[[builds]]')
        lines += [k+' = '+json.dumps(v) for k,v in b.items()]
    with output.open('x') as f:
        f.write('\n'.join(lines)+'\n')
    return {'settings':str(output),'purpose':purpose,'build':s['builds'][0]['id'],
            'allow_submit':False,'max_trials':trials,'cap_core_hours':cap}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('init',help='validate and initialise; no submissions or Slurm calls')
    a.add_argument('--settings',type=Path,required=True)
    a.add_argument('--state',type=Path,required=True)
    a=sub.add_parser('plan',help='validate candidate space without writes, Slurm or builds')
    a.add_argument('--settings',type=Path,required=True)
    a=sub.add_parser('smoke-settings',help='write a disabled, minimal chain or single-compiler canary')
    a.add_argument('--settings',type=Path,required=True)
    a.add_argument('--output',type=Path,required=True)
    a.add_argument('--purpose',choices=['chain','build'],default='chain')
    a.add_argument('--build',help='one recipe id; required for --purpose build')
    for name in ('tick','status','stop','worker','resume','abandon'):
        a=sub.add_parser(name)
        a.add_argument('--state',type=Path,required=True)
        if name=='resume':
            a.add_argument('--acknowledge-failures',action='store_true',help='after inspection, acknowledge failed trials; never retries those candidates')
        if name=='status':
            a.add_argument('--scheduler',action='store_true',help='read current queue and accounting, including whole-job energy')
        if name in ('worker','abandon'):
            a.add_argument('--token',required=True)
        if name in ('tick','resume'):
            a.add_argument('--submit',action='store_true',help='explicitly allow submissions; also needs settings safety gate')
            a.add_argument('--dry-run',action='store_true',help='read scheduler and show decision without any writes/submission')
    a=p.parse_args(argv)
    root=a.state.resolve() if hasattr(a,'state') else None
    if a.cmd=='smoke-settings':
        result=smoke_settings(a.settings,a.output,a.purpose,a.build)
    elif a.cmd=='plan':
        s,hw=load_settings(a.settings)
        check_settings(s,hw)
        result={'candidates':space(s,hw),'cap_core_hours':s['campaign']['cap_core_hours'],
                'note':'dry run: no Slurm calls, writes, builds or submissions'}
    elif a.cmd=='init':
        result=init(a.settings,root)
    elif a.cmd=='worker':
        worker(root,a.token)
        return
    elif a.cmd=='stop':
        result=stop(root)
    elif a.cmd=='status':
        result=report(root,a.scheduler)
    elif a.cmd=='abandon':
        with locked(root):
            state=load(root)
            s,_=settings_for(state)
            jobs=snapshots(s)
            t=next(t for t in state['trials'] if t['token']==a.token)
            if any((j['name']==a.token or j['id']==t.get('job_id')) and j['state'] not in TERMINAL for j in jobs.values()):
                raise RuntimeError('cannot abandon a live/pending job; stop/cancel it first')
            if t['status'] in ('done','failed'):
                raise RuntimeError('completed trials cannot be abandoned')
            t['status']='abandoned'  # Keep full cost and consumed repeat slot.
            atomic(root/'state.json',state)
        result={'abandoned':a.token,'reservation_retained':True}
    else:
        if a.submit and a.dry_run:
            p.error('--submit and --dry-run are mutually exclusive')
        if a.cmd=='resume' and a.submit:
            with locked(root):
                state=load(root)
                s,_=settings_for(state)
                enabled(s)
                reconcile(state,snapshots(s))
                failures=[t for t in state['trials'] if t['status']=='failed' and not t.get('failure_acknowledged_at')]
                if failures and not a.acknowledge_failures:
                    (root/'STOP').touch()
                    atomic(root/'state.json',state)
                    raise RuntimeError('inspect failures, then resume with --acknowledge-failures; no automatic retry')
                for trial in failures:
                    trial['failure_acknowledged_at']=stamp()
                atomic(root/'state.json',state)
                (root/'STOP').unlink(missing_ok=True)
        result=tick(root,submit=a.submit)
    print(json.dumps(result,indent=2,allow_nan=False))


if __name__=='__main__':
    main()
