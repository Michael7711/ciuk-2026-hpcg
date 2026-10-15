"""Slurm wrapper-step power estimates, separate from benchmark-window efficiency.

Never aggregate allocation, batch, extern and numeric step energies: their intervals
can overlap. The legacy HPL results.parse_sacct contract is deliberately unchanged.
"""
import csv
import io
import math


def parse_accounting(text):
    reader = csv.DictReader(io.StringIO(text.strip()), delimiter='|')
    required = {'JobID', 'JobName', 'State', 'ElapsedRaw', 'ConsumedEnergyRaw'}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError('missing Slurm accounting columns')
    records = {}
    for row in reader:
        jid = (row.get('JobID') or '').strip()
        if not jid or jid in records:
            raise ValueError('empty or duplicate accounting job/step id')
        records[jid] = {k:v.strip() if v is not None else '' for k,v in row.items() if k}
    return records


def positive_number(value):
    try:
        x = float(value)
        return x if math.isfinite(x) and x > 0 else None
    except (TypeError, ValueError):
        return None


def step_estimate(records, job_id, gflops, benchmark_runtime_s=None, expected_nodes=None):
    jid = str(job_id)
    job, step = records.get(jid, {}), records.get(jid+'.0', {})
    out = {'energy_scope':'slurm_benchmark_wrapper_step',
           'benchmark_window_energy_verified':False, 'job_id':jid, 'step_id':jid+'.0',
           'whole_job_energy_j':positive_number(job.get('ConsumedEnergyRaw')),
           'whole_job_state':job.get('State'), 'status':'unavailable'}
    def unavailable(reason):
        return {**out, 'reason':reason}
    if not job or not step:
        return unavailable('allocation or benchmark-wrapper .0 record missing/delayed')
    if step.get('JobName') != 'bench_wrapper.sh' or step.get('State') != 'COMPLETED':
        return unavailable('benchmark-wrapper .0 step not completed or name mismatch')
    if step.get('ExitCode') not in (None, '', '0:0'):
        return unavailable('benchmark-wrapper step has nonzero exit status')
    energy, elapsed, perf = (positive_number(x) for x in
                            (step.get('ConsumedEnergyRaw'), step.get('ElapsedRaw'), gflops))
    if None in (energy, elapsed, perf):
        return unavailable('positive finite step energy, elapsed time and valid HPCG performance required')
    if benchmark_runtime_s is not None:
        runtime = positive_number(benchmark_runtime_s)
        if runtime is None or runtime > elapsed+1:  # ElapsedRaw has whole-second resolution.
            return unavailable('benchmark runtime inconsistent with wrapper-step duration')
    if expected_nodes is not None:
        try:
            nodes = int(step.get('AllocNodes', ''))
        except ValueError:
            return unavailable('step node coverage missing; check final accounting')
        if nodes != expected_nodes:
            return unavailable('step node count differs from benchmark allocation')
        out['accounted_nodes'] = nodes
    power = energy/elapsed
    if not math.isfinite(power) or power <= 0 or not math.isfinite(perf/power) or perf/power <= 0:
        return unavailable('nonfinite or zero derived power/efficiency')
    out.update(status='estimate', step_energy_j=energy, step_elapsed_s=elapsed,
               step_average_power_w=power, estimated_gflops_per_w=perf/power)
    return out
