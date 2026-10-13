#!/usr/bin/env python3

import argparse
import csv
import fcntl
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


RESULT_PATTERN = re.compile(
    r'^\s*(\S+)\s+'
    r'(\d+)\s+'          # N
    r'(\d+)\s+'          # NB
    r'(\d+)\s+'          # P
    r'(\d+)\s+'          # Q
    r'([0-9.eE+-]+)\s+'  # Time
    r'([0-9.eE+-]+)\s*$' # GFLOPS
)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Record a completed HPL job.'
    )

    parser.add_argument('--job-id', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--csv', required=True)

    parser.add_argument('--nodes', type=int, required=True)
    parser.add_argument('--mpi-ranks', type=int, required=True)
    parser.add_argument('--omp-threads', type=int, required=True)

    parser.add_argument('--compiler', required=True)
    parser.add_argument('--compiler-flags', required=True)

    parser.add_argument('--purpose', required=True)
    parser.add_argument('--input-file', required=True)
    parser.add_argument('--repo-root', required=True)

    return parser.parse_args()


def parse_hpl_output(output_path):
    text = Path(output_path).read_text()

    results = []

    for line in text.splitlines():
        match = RESULT_PATTERN.match(line)

        if match and match.group(1).startswith('W'):
            results.append(match)

    if len(results) != 1:
        raise RuntimeError(
            f'Expected exactly one HPL result, found {len(results)}.'
        )

    match = results[0]

    residual_status = 'UNKNOWN'

    if '...... PASSED' in text:
        residual_status = 'PASSED'
    elif '...... FAILED' in text:
        residual_status = 'FAILED'

    return {
        'N': int(match.group(2)),
        'NB': int(match.group(3)),
        'P': int(match.group(4)),
        'Q': int(match.group(5)),
        'hpl_runtime_s': float(match.group(6)),
        'gflops': float(match.group(7)),
        'residual_status': residual_status,
    }


def get_sacct_job(job_id):
    command = [
        'sacct',
        '-j',
        job_id,
        '--noheader',
        '--parsable2',
        '--format=JobIDRaw,ElapsedRaw,ConsumedEnergyRaw,State',
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True,
    )

    for line in result.stdout.splitlines():
        fields = line.strip().split('|')

        if len(fields) < 4:
            continue

        returned_job_id, elapsed, energy, state = fields[:4]

        if returned_job_id != job_id:
            continue

        if not elapsed or not energy:
            continue

        return {
            'slurm_elapsed_s': int(elapsed),
            'energy_j': float(energy),
            'slurm_state': state,
        }

    raise RuntimeError(
        f'Accounting data for completed job {job_id} was not available.'
    )


def get_git_commit(repo_root):
    result = subprocess.run(
        ['git', '-C', repo_root, 'rev-parse', 'HEAD'],
        capture_output=True,
        text=True,
        check=True,
    )

    return result.stdout.strip()


def append_result(csv_path, row):
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        'run_id',
        'job_id',
        'timestamp_utc',
        'git_commit',
        'purpose',
        'nodes',
        'mpi_ranks',
        'omp_threads',
        'N',
        'NB',
        'P',
        'Q',
        'compiler',
        'compiler_flags',
        'hpl_runtime_s',
        'slurm_elapsed_s',
        'gflops',
        'energy_j',
        'avg_power_w',
        'gflops_per_w',
        'residual_status',
        'slurm_state',
        'input_file',
    ]

    with csv_path.open('a+', newline='') as file:
        fcntl.flock(file.fileno(), fcntl.LOCK_EX)

        file.seek(0, 2)
        needs_header = file.tell() == 0

        writer = csv.DictWriter(file, fieldnames=fieldnames)

        if needs_header:
            writer.writeheader()

        writer.writerow(row)

        fcntl.flock(file.fileno(), fcntl.LOCK_UN)


def main():
    args = parse_arguments()

    hpl = parse_hpl_output(args.output)
    accounting = get_sacct_job(args.job_id)

    energy_j = accounting['energy_j']
    slurm_elapsed_s = accounting['slurm_elapsed_s']

    if energy_j > 0 and slurm_elapsed_s > 0:
        avg_power_w = energy_j / slurm_elapsed_s
        gflops_per_w = hpl['gflops'] / avg_power_w
    else:
        avg_power_w = ''
        gflops_per_w = ''

    row = {
        'run_id': args.run_id,
        'job_id': args.job_id,
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'git_commit': get_git_commit(args.repo_root),
        'purpose': args.purpose,
        'nodes': args.nodes,
        'mpi_ranks': args.mpi_ranks,
        'omp_threads': args.omp_threads,
        'N': hpl['N'],
        'NB': hpl['NB'],
        'P': hpl['P'],
        'Q': hpl['Q'],
        'compiler': args.compiler,
        'compiler_flags': args.compiler_flags,
        'hpl_runtime_s': hpl['hpl_runtime_s'],
        'slurm_elapsed_s': slurm_elapsed_s,
        'gflops': hpl['gflops'],
        'energy_j': energy_j,
        'avg_power_w': avg_power_w,
        'gflops_per_w': gflops_per_w,
        'residual_status': hpl['residual_status'],
        'slurm_state': accounting['slurm_state'],
        'input_file': Path(args.input_file).name,
    }

    append_result(args.csv, row)

    print(f"Recorded {row['run_id']}")
    print(f"GFLOPS:     {row['gflops']:.3f}")
    print(f"Energy:     {row['energy_j']:.0f} J")

    if row['avg_power_w'] != '':
        print(f"Avg power:  {row['avg_power_w']:.2f} W")
        print(f"GFLOPS/W:   {row['gflops_per_w']:.4f}")
    else:
        print('Avg power:  N/A')
        print('GFLOPS/W:   N/A')

    print(f"Validation: {row['residual_status']}")


if __name__ == '__main__':
    main()
