"""Reproduce the nine-job energy table from the preserved log and sacct PSV.

Run: python3 analysis/hpcg/overnight_energy.py [--output NEW.csv]
Output files use exclusive creation; existing data are never overwritten.
"""
import argparse
import csv
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from autotune.accounting import parse_accounting, step_estimate


def analyse(log_text, accounting_text):
    section = log_text.split('### All nine diagnostic measurements', 1)[1].split(
        '### Compiler comparison', 1)[0]
    results = {}
    for line in section.splitlines():
        fields = [v.strip().replace('**', '') for v in line.strip('|').split('|')]
        if not fields or not re.fullmatch(r'\d+ / \d+', fields[0]):
            continue
        job_id = fields[0].split(' / ')[1]
        if job_id in results:
            raise ValueError('duplicate HPCG job id')
        results[job_id] = dict(job_id=job_id, build=fields[1], layout=fields[2],
            local_grid=fields[3], gflops=float(fields[4]), benchmark_runtime_s=float(fields[5]))
    if len(results) != 9:
        raise ValueError('expected all nine overnight HPCG results')
    records = parse_accounting(accounting_text)
    if {j.split('.')[0] for j in records} != set(results):
        raise ValueError('HPCG/accounting job-id sets differ')
    rows = []
    for jid, result in results.items():
        if jid not in records or records[jid]['State'] != 'COMPLETED':
            raise ValueError('overnight allocation not completed')
        estimate = step_estimate(records, jid, result['gflops'], result['benchmark_runtime_s'])
        if estimate['status'] != 'estimate':
            raise ValueError(f'{jid}: {estimate.get("reason")}')
        if estimate['whole_job_energy_j'] is None:
            raise ValueError(f'{jid}: whole-job energy missing or invalid')
        rows.append({**result, **{k:estimate[k] for k in ('whole_job_energy_j',
            'step_energy_j', 'step_elapsed_s', 'step_average_power_w', 'estimated_gflops_per_w',
            'energy_scope', 'benchmark_window_energy_verified')}})
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--log', type=Path, default=ROOT/'docs/hpcg/experiment_log.md')
    p.add_argument('--accounting', type=Path, default=ROOT/'analysis/hpcg/overnight-20261015-sacct-energy.psv')
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    rows = analyse(a.log.read_text(), a.accounting.read_text())
    print('Sources SHA256: '+', '.join(f'{f.name}={hashlib.sha256(f.read_bytes()).hexdigest()}'
          for f in (a.log, a.accounting)), file=sys.stderr)
    if a.output:
        with a.output.open('x', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


if __name__ == '__main__':
    main()
