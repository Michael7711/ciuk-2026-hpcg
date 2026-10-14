"""Plot progress from the first HPL GP-autotuning experiment.

Reads the provenance-aware autotune_runs.csv and generates:

1. Performance vs energy Pareto frontier.
2. Cumulative best performance across the tuning sequence.
3. GP prediction vs measured performance for GP-guided batches.

The GP prediction values stored below are the predictions printed by the
autotuner at selection time. This is deliberate: recomputing predictions
using the final dataset would leak future observations into the comparison.

Usage
-----
From the repository root:

    python analysis/hpl/plot_hpl_autotune_progress.py

Optionally:

    python analysis/hpl/plot_hpl_autotune_progress.py \
        --csv hpl/results/autotune_runs.csv \
        --output-dir analysis/hpl/figures/autotune_progress
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import OrderedDict
from pathlib import Path

import matplotlib

matplotlib.use('Agg')

import matplotlib.pyplot as plt


# ---------------------------------------------------------------------------
# Experiment definition
# ---------------------------------------------------------------------------

# This script intentionally plots the first restricted search space only.
# Later NB/N search phases therefore will not silently change these figures.
RESTRICTED_SPACE = {
    'N': 117248,
    'NB': 256,
    'pfact': 2,
    'rfact': 2,
    'bcast': 1,
    'depth': 0,
}

# Predictions printed by the GP when each configuration was selected.
#
# Format:
# run_id: {
#     'batch': int,
#     'prediction': predicted GFLOPS,
#     'log_std': predictive standard deviation on the log-performance scale,
# }
GP_PREDICTIONS = {
    # GP-guided batch 1
    'hpl-diagnostic-n1-72x4-41d8f4c9': {
        'batch': 1,
        'prediction': 12840.0,
        'log_std': 0.07,
    },
    'hpl-diagnostic-n1-144x2-dcd54081': {
        'batch': 1,
        'prediction': 12680.0,
        'log_std': 0.07,
    },
    'hpl-diagnostic-n1-288x1-dff0562b': {
        'batch': 1,
        'prediction': 12590.0,
        'log_std': 0.07,
    },
    'hpl-diagnostic-n1-72x4-d98b2913': {
        'batch': 1,
        'prediction': 12580.0,
        'log_std': 0.07,
    },

    # GP-guided batch 2
    'hpl-diagnostic-n1-144x2-5e458bc6': {
        'batch': 2,
        'prediction': 12870.0,
        'log_std': 0.04,
    },
    'hpl-diagnostic-n1-24x12-0a9ffb9a': {
        'batch': 2,
        'prediction': 12250.0,
        'log_std': 0.05,
    },
    'hpl-diagnostic-n1-288x1-0e33afb9': {
        'batch': 2,
        'prediction': 11540.0,
        'log_std': 0.03,
    },
}


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def as_float(row, key):
    """Read a required numeric CSV value."""
    value = row.get(key)

    if value in (None, ''):
        raise ValueError(f'Missing required value {key!r} in run {row.get("run_id")}')

    return float(value)


def as_int(row, key):
    """Read an integer-valued CSV field robustly."""
    return int(as_float(row, key))


def config_key(row):
    """Identity of an HPL benchmark configuration, ignoring kind/replicate."""
    return (
        as_int(row, 'nodes'),
        as_int(row, 'mpi_ranks'),
        as_int(row, 'omp_threads'),
        as_int(row, 'N'),
        as_int(row, 'NB'),
        as_int(row, 'P'),
        as_int(row, 'Q'),
        as_int(row, 'pfact'),
        as_int(row, 'rfact'),
        as_int(row, 'bcast'),
        as_int(row, 'depth'),
    )


def config_label(row):
    """Compact human-readable configuration label."""
    ranks = as_int(row, 'mpi_ranks')
    threads = as_int(row, 'omp_threads')
    p = as_int(row, 'P')
    q = as_int(row, 'Q')

    return f'{ranks}×{threads} P{p}×Q{q}'


def in_restricted_space(row):
    """True for rows belonging to the first completed restricted search."""
    if row.get('benchmark') != 'hpl':
        return False

    if row.get('validation') != 'PASSED':
        return False

    if row.get('parse_status') != 'ok':
        return False

    try:
        return all(
            as_int(row, key) == expected
            for key, expected in RESTRICTED_SPACE.items()
        )
    except (ValueError, TypeError):
        return False


def phase_for_row(row):
    """Experiment phase in which this row was selected."""
    prediction = GP_PREDICTIONS.get(row['run_id'])

    if prediction is None:
        return 'Pre-GP'

    return f'GP batch {prediction["batch"]}'


def load_rows(path):
    """Load valid HPL rows from the first restricted search space."""
    with path.open(newline='') as f:
        rows = list(csv.DictReader(f))

    selected = [row for row in rows if in_restricted_space(row)]

    if not selected:
        raise RuntimeError(
            f'No valid rows from the restricted HPL search were found in {path}'
        )

    return selected


# ---------------------------------------------------------------------------
# Aggregate repeated configurations
# ---------------------------------------------------------------------------

def aggregate_configs(rows):
    """Aggregate repeat measurements while preserving first-seen order."""
    grouped = OrderedDict()

    for index, row in enumerate(rows):
        key = config_key(row)

        if key not in grouped:
            grouped[key] = {
                'first_index': index,
                'rows': [],
            }

        grouped[key]['rows'].append(row)

    configs = []

    for group in grouped.values():
        rs = group['rows']

        first = rs[0]

        configs.append({
            'first_index': group['first_index'],
            'label': config_label(first),
            'phase': phase_for_row(first),
            'mpi_ranks': as_int(first, 'mpi_ranks'),
            'omp_threads': as_int(first, 'omp_threads'),
            'P': as_int(first, 'P'),
            'Q': as_int(first, 'Q'),
            'gflops': statistics.mean(as_float(r, 'gflops') for r in rs),
            'runtime_s': statistics.mean(as_float(r, 'runtime_s') for r in rs),
            'energy_j': statistics.mean(as_float(r, 'energy_j') for r in rs),
            'n': len(rs),
        })

    return configs


# ---------------------------------------------------------------------------
# Plot helpers
# ---------------------------------------------------------------------------

def save_figure(fig, output_dir, stem):
    """Save one figure as both high-resolution PNG and vector PDF."""
    png = output_dir / f'{stem}.png'
    pdf = output_dir / f'{stem}.pdf'

    fig.savefig(png, dpi=300, bbox_inches='tight')
    fig.savefig(pdf, bbox_inches='tight')

    print(f'Saved: {png}')
    print(f'Saved: {pdf}')


def pareto_frontier(configs):
    """Return non-dominated configs: minimize energy, maximize GFLOPS."""
    ordered = sorted(configs, key=lambda x: x['energy_j'])

    frontier = []
    best_gflops = -math.inf

    for config in ordered:
        if config['gflops'] > best_gflops:
            frontier.append(config)
            best_gflops = config['gflops']

    return frontier


# ---------------------------------------------------------------------------
# Figure 1: performance vs energy
# ---------------------------------------------------------------------------

def plot_performance_energy(configs, output_dir):
    """Performance/energy scatter with the measured Pareto frontier."""
    fig, ax = plt.subplots(figsize=(9, 6))

    phases = ['Pre-GP', 'GP batch 1', 'GP batch 2']
    markers = {
        'Pre-GP': 'o',
        'GP batch 1': 's',
        'GP batch 2': '^',
    }

    for phase in phases:
        points = [c for c in configs if c['phase'] == phase]

        if not points:
            continue

        ax.scatter(
            [c['energy_j'] / 1000 for c in points],
            [c['gflops'] for c in points],
            marker=markers[phase],
            s=75,
            label=phase,
            zorder=3,
        )

    frontier = pareto_frontier(configs)

    ax.plot(
        [c['energy_j'] / 1000 for c in frontier],
        [c['gflops'] for c in frontier],
        linestyle='--',
        linewidth=1.5,
        label='Pareto frontier',
        zorder=2,
    )

    performance_winner = max(configs, key=lambda c: c['gflops'])
    energy_winner = min(configs, key=lambda c: c['energy_j'])

    baseline_candidates = [
        c for c in configs
        if c['mpi_ranks'] == 288
        and c['omp_threads'] == 1
        and c['P'] == 8
        and c['Q'] == 36
    ]

    highlight = [
        (performance_winner, 'Max performance'),
        (energy_winner, 'Min energy'),
    ]

    if baseline_candidates:
        highlight.append((baseline_candidates[0], 'Pure-MPI baseline'))

    used = set()

    for config, description in highlight:
        key = config['label']

        if key in used:
            continue

        used.add(key)

        ax.annotate(
            f'{description}\n{config["label"]}',
            xy=(config['energy_j'] / 1000, config['gflops']),
            xytext=(8, 8),
            textcoords='offset points',
            fontsize=9,
        )

    ax.set_title('HPL performance vs energy-to-solution')
    ax.set_xlabel('Energy-to-solution (kJ)')
    ax.set_ylabel('Performance (GFLOPS)')
    ax.grid(alpha=0.25)
    ax.legend()

    fig.tight_layout()

    save_figure(
        fig,
        output_dir,
        '01_hpl_performance_energy_pareto',
    )

    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 2: cumulative best performance
# ---------------------------------------------------------------------------

def plot_cumulative_best(configs, output_dir):
    """Show improvement in best observed GFLOPS as configs are evaluated."""
    ordered = sorted(configs, key=lambda c: c['first_index'])

    best_so_far = []
    current_best = -math.inf

    for config in ordered:
        current_best = max(current_best, config['gflops'])
        best_so_far.append(current_best)

    x = list(range(1, len(ordered) + 1))

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.plot(
        x,
        best_so_far,
        marker='o',
        linewidth=2,
        label='Best observed performance',
    )

    # Six unique configurations were available before GP guidance began.
    pre_gp_end = 6
    batch1_end = 10

    ax.axvspan(
        0.5,
        pre_gp_end + 0.5,
        alpha=0.08,
        label='Initial design',
    )

    ax.axvspan(
        pre_gp_end + 0.5,
        batch1_end + 0.5,
        alpha=0.08,
        label='GP batch 1',
    )

    ax.axvspan(
        batch1_end + 0.5,
        len(ordered) + 0.5,
        alpha=0.08,
        label='GP batch 2',
    )

    pure_mpi = next(
        (
            c for c in ordered
            if c['mpi_ranks'] == 288
            and c['omp_threads'] == 1
            and c['P'] == 8
            and c['Q'] == 36
        ),
        None,
    )

    if pure_mpi is not None:
        ax.axhline(
            pure_mpi['gflops'],
            linestyle=':',
            linewidth=1.5,
            label='Repeated pure-MPI baseline',
        )

    pre_gp_best = max(c['gflops'] for c in ordered[:pre_gp_end])
    final_best = max(c['gflops'] for c in ordered)

    gp_gain = 100 * (final_best - pre_gp_best) / pre_gp_best

    ax.annotate(
        f'Pre-GP best\n{pre_gp_best:,.0f} GFLOPS',
        xy=(pre_gp_end, best_so_far[pre_gp_end - 1]),
        xytext=(-15, 18),
        textcoords='offset points',
        ha='right',
        fontsize=9,
    )

    ax.annotate(
        f'Final best\n{final_best:,.0f} GFLOPS\n+{gp_gain:.1f}% vs pre-GP best',
        xy=(len(ordered), final_best),
        xytext=(-10, -48),
        textcoords='offset points',
        ha='right',
        fontsize=9,
    )

    ax.set_title('Best HPL performance discovered during autotuning')
    ax.set_xlabel('Unique configuration evaluated')
    ax.set_ylabel('Best observed performance (GFLOPS)')
    ax.set_xticks(x)
    ax.grid(alpha=0.25)
    ax.legend()

    fig.tight_layout()

    save_figure(
        fig,
        output_dir,
        '02_hpl_cumulative_best_performance',
    )

    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 3: GP prediction accuracy
# ---------------------------------------------------------------------------

def plot_prediction_accuracy(rows, output_dir):
    """Compare selection-time GP predictions with measured performance."""
    observations = []

    for row in rows:
        model_output = GP_PREDICTIONS.get(row['run_id'])

        if model_output is None:
            continue

        predicted = model_output['prediction']
        actual = as_float(row, 'gflops')
        log_std = model_output['log_std']

        observations.append({
            'batch': model_output['batch'],
            'label': config_label(row),
            'predicted': predicted,
            'actual': actual,
            'log_std': log_std,
            'error_pct': 100 * (actual - predicted) / predicted,
        })

    if not observations:
        raise RuntimeError(
            'No GP-selected run IDs were found in the CSV. '
            'Check GP_PREDICTIONS at the top of the script.'
        )

    fig, ax = plt.subplots(figsize=(8, 7))

    markers = {
        1: 'o',
        2: 's',
    }

    for batch in sorted({o['batch'] for o in observations}):
        points = [o for o in observations if o['batch'] == batch]

        predictions = [o['predicted'] for o in points]
        actuals = [o['actual'] for o in points]

        # Convert ±1 log-standard-deviation into asymmetric GFLOPS errors.
        lower_errors = [
            p - p * math.exp(-o['log_std'])
            for p, o in zip(predictions, points)
        ]

        upper_errors = [
            p * math.exp(o['log_std']) - p
            for p, o in zip(predictions, points)
        ]

        mae = statistics.mean(abs(o['error_pct']) for o in points)
        mean_log_std = statistics.mean(o['log_std'] for o in points)

        ax.errorbar(
            predictions,
            actuals,
            xerr=[lower_errors, upper_errors],
            fmt=markers[batch],
            markersize=8,
            capsize=3,
            linestyle='none',
            label=(
                f'GP batch {batch} '
                f'(MAE {mae:.1f}%, mean log-SD {mean_log_std:.02f})'
            ),
        )

    all_values = [
        value
        for o in observations
        for value in (o['predicted'], o['actual'])
    ]

    lower = min(all_values) * 0.97
    upper = max(all_values) * 1.03

    ax.plot(
        [lower, upper],
        [lower, upper],
        linestyle='--',
        linewidth=1.5,
        label='Perfect prediction',
    )

    for observation in observations:
        ax.annotate(
            observation['label'],
            xy=(observation['predicted'], observation['actual']),
            xytext=(5, 5),
            textcoords='offset points',
            fontsize=8,
        )

    ax.set_xlim(lower, upper)
    ax.set_ylim(lower, upper)

    ax.set_title('GP prediction accuracy improves with additional observations')
    ax.set_xlabel('GP predicted performance (GFLOPS)')
    ax.set_ylabel('Measured performance (GFLOPS)')
    ax.grid(alpha=0.25)
    ax.legend()

    fig.tight_layout()

    save_figure(
        fig,
        output_dir,
        '03_hpl_gp_predicted_vs_actual',
    )

    plt.close(fig)


# ---------------------------------------------------------------------------
# Console summary
# ---------------------------------------------------------------------------

def print_summary(configs, rows):
    """Print the main numbers represented in the figures."""
    performance_winner = max(configs, key=lambda c: c['gflops'])
    energy_winner = min(configs, key=lambda c: c['energy_j'])

    ordered = sorted(configs, key=lambda c: c['first_index'])
    pre_gp_best = max(c['gflops'] for c in ordered[:6])

    print()
    print('Restricted HPL autotuning summary')
    print('---------------------------------')
    print(f'Valid observations:     {len(rows)}')
    print(f'Unique configurations:  {len(configs)}')
    print()
    print(
        'Performance winner:    '
        f'{performance_winner["label"]} — '
        f'{performance_winner["gflops"]:.0f} GFLOPS, '
        f'{performance_winner["energy_j"]:.0f} J'
    )
    print(
        'Energy winner:         '
        f'{energy_winner["label"]} — '
        f'{energy_winner["gflops"]:.0f} GFLOPS, '
        f'{energy_winner["energy_j"]:.0f} J'
    )

    final_best = performance_winner['gflops']

    print(
        'GP improvement:        '
        f'{100 * (final_best - pre_gp_best) / pre_gp_best:.2f}% '
        'over best pre-GP configuration'
    )

    for batch in (1, 2):
        run_ids = {
            run_id
            for run_id, values in GP_PREDICTIONS.items()
            if values['batch'] == batch
        }

        batch_rows = [
            row for row in rows
            if row['run_id'] in run_ids
        ]

        if not batch_rows:
            continue

        errors = []

        for row in batch_rows:
            prediction = GP_PREDICTIONS[row['run_id']]['prediction']
            actual = as_float(row, 'gflops')

            errors.append(
                abs(100 * (actual - prediction) / prediction)
            )

        mean_log_std = statistics.mean(
            GP_PREDICTIONS[row['run_id']]['log_std']
            for row in batch_rows
        )

        print(
            f'GP batch {batch}:            '
            f'MAE {statistics.mean(errors):.2f}%, '
            f'mean log-SD {mean_log_std:.3f}'
        )

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args():
    repo_root = Path(__file__).resolve().parents[2]

    parser = argparse.ArgumentParser(
        description='Plot progress from the first HPL GP-autotuning experiment.'
    )

    parser.add_argument(
        '--csv',
        type=Path,
        default=repo_root / 'hpl/results/autotune_runs.csv',
        help='path to provenance-aware autotune_runs.csv',
    )

    parser.add_argument(
        '--output-dir',
        type=Path,
        default=repo_root / 'analysis/hpl/figures/autotune_progress',
        help='directory for generated PNG/PDF figures',
    )

    return parser.parse_args()


def main():
    args = parse_args()

    if not args.csv.exists():
        raise FileNotFoundError(f'Results CSV not found: {args.csv}')

    args.output_dir.mkdir(parents=True, exist_ok=True)

    rows = load_rows(args.csv)
    configs = aggregate_configs(rows)

    print_summary(configs, rows)

    plot_performance_energy(configs, args.output_dir)
    plot_cumulative_best(configs, args.output_dir)
    plot_prediction_accuracy(rows, args.output_dir)


if __name__ == '__main__':
    main()