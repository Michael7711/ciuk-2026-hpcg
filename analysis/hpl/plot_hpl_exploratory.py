#!/usr/bin/env python3
"""
Create tables and figures for the exploratory HPL tuning runs.

Usage:
    python analysis/plot_hpl_exploratory.py
    python analysis/plot_hpl_exploratory.py path/to/hpl_runs.csv
    python analysis/plot_hpl_exploratory.py path/to/hpl_runs.csv --outdir path/to/output

The script separates the current exploratory campaign into:
    1. Problem size (N)
    2. Block size (NB)
    3. MPI process grid (P x Q)
    4. MPI/OpenMP layout

For repeated configurations, mean values are plotted and the standard deviation is
used as an error bar where available.
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


METRICS = {
    'hpl_runtime_s': ('HPL runtime', 'Runtime (s)'),
    'gflops': ('HPL performance', 'GFLOPS'),
    'energy_j': ('Energy consumption', 'Energy (J)'),
    'gflops_per_w': ('Energy efficiency', 'GFLOPS/W'),
}


def parse_args():
    parser = argparse.ArgumentParser(
        description='Analyse exploratory HPL benchmark runs.'
    )
    parser.add_argument(
        'csv',
        nargs='?',
        default='hpl/results/hpl_runs.csv',
        help='Path to hpl_runs.csv'
    )
    parser.add_argument(
        '--outdir',
        default='hpl/results/exploratory_analysis',
        help='Directory for generated tables and figures'
    )
    return parser.parse_args()


def load_results(csv_path):
    df = pd.read_csv(csv_path)

    required = {
        'run_id', 'nodes', 'mpi_ranks', 'omp_threads',
        'N', 'NB', 'P', 'Q',
        'hpl_runtime_s', 'gflops', 'energy_j',
        'avg_power_w', 'gflops_per_w',
        'residual_status', 'slurm_state'
    }

    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f'Missing required CSV columns: {sorted(missing)}'
        )

    # Only use successful benchmark measurements.
    df = df[
        (df['residual_status'] == 'PASSED')
        & (df['slurm_state'] == 'COMPLETED')
    ].copy()

    # Validation is a pipeline test rather than an exploratory benchmark.
    if 'purpose' in df.columns:
        df = df[df['purpose'] != 'validation'].copy()

    df['total_cpus'] = df['mpi_ranks'] * df['omp_threads']
    df['grid'] = df['P'].astype(str) + '×' + df['Q'].astype(str)
    df['mpi_omp'] = (
        df['mpi_ranks'].astype(str)
        + ' MPI × '
        + df['omp_threads'].astype(str)
        + ' OMP'
    )

    return df


def aggregate(df, group_cols):
    """Aggregate exact repeats of the same configuration."""
    metrics = list(METRICS) + ['avg_power_w']

    grouped = (
        df.groupby(group_cols, as_index=False)
        .agg(
            runs=('run_id', 'count'),
            **{
                f'{metric}_mean': (metric, 'mean')
                for metric in metrics
            },
            **{
                f'{metric}_std': (metric, 'std')
                for metric in metrics
            }
        )
    )

    # A single observation has undefined sample SD; show zero error bar instead.
    std_cols = [c for c in grouped.columns if c.endswith('_std')]
    grouped[std_cols] = grouped[std_cols].fillna(0.0)

    return grouped


def save_markdown_table(df, path, title):
    """Write a simple Markdown table without requiring the tabulate package."""
    display = df.copy()

    for col in display.select_dtypes(include='number').columns:
        if col in {'N', 'NB', 'P', 'Q', 'nodes', 'mpi_ranks',
                   'omp_threads', 'total_cpus', 'runs'}:
            continue
        display[col] = display[col].map(
            lambda x: f'{x:.3f}' if pd.notna(x) else ''
        )

    headers = list(display.columns)
    lines = [
        f'## {title}',
        '',
        '| ' + ' | '.join(headers) + ' |',
        '| ' + ' | '.join(['---'] * len(headers)) + ' |',
    ]

    for _, row in display.iterrows():
        lines.append(
            '| ' + ' | '.join(str(row[col]) for col in headers) + ' |'
        )

    path.write_text('\n'.join(lines) + '\n')


def save_table(df, outdir, name, title):
    csv_path = outdir / f'{name}.csv'
    md_path = outdir / f'{name}.md'

    df.to_csv(csv_path, index=False)
    save_markdown_table(df, md_path, title)

    print(f'\n{title}')
    print(df.to_string(index=False))


def line_plot(df, x, x_label, experiment_name, outdir):
    for metric, (metric_title, y_label) in METRICS.items():
        mean_col = f'{metric}_mean'
        std_col = f'{metric}_std'

        fig = plt.figure(figsize=(7, 4.5))
        ax = fig.gca()

        ax.errorbar(
            df[x],
            df[mean_col],
            yerr=df[std_col],
            marker='o',
            capsize=4
        )

        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        ax.set_title(f'{experiment_name}: {metric_title}')
        ax.grid(alpha=0.25)
        fig.tight_layout()

        safe_metric = metric.replace('_', '-')
        fig.savefig(
            outdir / f'{experiment_name.lower().replace(" ", "_")}_{safe_metric}.png',
            dpi=200,
            bbox_inches='tight'
        )
        plt.close(fig)



def dual_axis_performance_efficiency_plot(
    df,
    x,
    x_label,
    experiment_name,
    outdir,
    categorical=False
):
    """
    Plot mean GFLOPS on the left axis and mean GFLOPS/W on the right axis.

    Repeated configurations are already aggregated before reaching this function,
    so the line uses the mean value for each configuration. Standard-deviation
    error bars are shown where repeat measurements exist.
    """
    if categorical:
        x_values = np.arange(len(df))
        x_tick_labels = df[x].astype(str)
    else:
        x_values = df[x]
        x_tick_labels = None

    fig = plt.figure(figsize=(7.5, 4.8))
    ax1 = fig.gca()
    ax2 = ax1.twinx()

    perf = ax1.errorbar(
        x_values,
        df['gflops_mean'],
        yerr=df['gflops_std'],
        marker='o',
        linestyle='-',
        capsize=4,
        label='GFLOPS'
    )

    efficiency = ax2.errorbar(
        x_values,
        df['gflops_per_w_mean'],
        yerr=df['gflops_per_w_std'],
        marker='s',
        linestyle='--',
        capsize=4,
        label='GFLOPS/W'
    )

    ax1.set_xlabel(x_label)
    ax1.set_ylabel('GFLOPS')
    ax2.set_ylabel('GFLOPS/W')
    ax1.set_title(f'{experiment_name}: performance vs energy efficiency')
    ax1.grid(alpha=0.25)

    if categorical:
        ax1.set_xticks(x_values)
        ax1.set_xticklabels(x_tick_labels)

    handles = [perf, efficiency]
    labels = [h.get_label() for h in handles]
    ax1.legend(handles, labels, loc='best')

    fig.tight_layout()
    fig.savefig(
        outdir
        / f'{experiment_name.lower().replace(" ", "_")}_gflops_gflops_per_w.png',
        dpi=200,
        bbox_inches='tight'
    )
    plt.close(fig)


def bar_plot(df, x, x_label, experiment_name, outdir):
    positions = np.arange(len(df))

    for metric, (metric_title, y_label) in METRICS.items():
        mean_col = f'{metric}_mean'
        std_col = f'{metric}_std'

        fig = plt.figure(figsize=(7, 4.5))
        ax = fig.gca()

        ax.bar(
            positions,
            df[mean_col],
            yerr=df[std_col],
            capsize=4
        )

        ax.set_xticks(positions)
        ax.set_xticklabels(df[x])
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        ax.set_title(f'{experiment_name}: {metric_title}')
        ax.grid(axis='y', alpha=0.25)
        fig.tight_layout()

        safe_metric = metric.replace('_', '-')
        fig.savefig(
            outdir / f'{experiment_name.lower().replace(" ", "_")}_{safe_metric}.png',
            dpi=200,
            bbox_inches='tight'
        )
        plt.close(fig)


def problem_size_experiment(df, outdir):
    # Keep NB, process grid and parallel layout fixed.
    subset = df[
        (df['nodes'] == 1)
        & (df['mpi_ranks'] == 288)
        & (df['omp_threads'] == 1)
        & (df['NB'] == 256)
        & (df['P'] == 16)
        & (df['Q'] == 18)
        & (df['N'].isin([73728, 92928, 117248]))
    ].copy()

    table = aggregate(subset, ['N'])
    table = table.sort_values('N')

    save_table(
        table,
        outdir,
        'problem_size_N',
        'Problem size (N) experiment'
    )
    line_plot(table, 'N', 'Matrix size, N', 'Problem size N', outdir)
    dual_axis_performance_efficiency_plot(
        table,
        'N',
        'Matrix size, N',
        'Problem size N',
        outdir
    )


def block_size_experiment(df, outdir):
    # Keep N, process grid and parallel layout fixed.
    subset = df[
        (df['nodes'] == 1)
        & (df['mpi_ranks'] == 288)
        & (df['omp_threads'] == 1)
        & (df['N'] == 117248)
        & (df['P'] == 16)
        & (df['Q'] == 18)
        & (df['NB'].isin([128, 256, 512]))
    ].copy()

    table = aggregate(subset, ['NB'])
    table = table.sort_values('NB')

    save_table(
        table,
        outdir,
        'block_size_NB',
        'Block size (NB) experiment'
    )
    line_plot(table, 'NB', 'Block size, NB', 'Block size NB', outdir)
    dual_axis_performance_efficiency_plot(
        table,
        'NB',
        'Block size, NB',
        'Block size NB',
        outdir
    )


def process_grid_experiment(df, outdir):
    # Keep N, NB and MPI/OpenMP layout fixed; vary only P x Q.
    subset = df[
        (df['nodes'] == 1)
        & (df['mpi_ranks'] == 288)
        & (df['omp_threads'] == 1)
        & (df['N'] == 117248)
        & (df['NB'] == 256)
    ].copy()

    table = aggregate(subset, ['P', 'Q'])
    table['grid'] = table['P'].astype(str) + '×' + table['Q'].astype(str)

    # Order from most elongated to most square for easier interpretation.
    table['grid_ratio'] = table['Q'] / table['P']
    table = table.sort_values('grid_ratio', ascending=False)

    save_table(
        table.drop(columns='grid_ratio'),
        outdir,
        'process_grid_PQ',
        'MPI process-grid (P × Q) experiment'
    )
    bar_plot(table, 'grid', 'Process grid (P × Q)', 'Process grid PQ', outdir)
    dual_axis_performance_efficiency_plot(
        table,
        'grid',
        'Process grid (P × Q)',
        'Process grid PQ',
        outdir,
        categorical=True
    )


def mpi_omp_experiment(df, outdir):
    # All tested hybrid configurations at the representative N/NB.
    subset = df[
        (df['nodes'] == 1)
        & (df['N'] == 117248)
        & (df['NB'] == 256)
        & (df['total_cpus'] == 288)
    ].copy()

    # Aggregate exact repeats, preserving process-grid choice.
    all_configs = aggregate(
        subset,
        ['mpi_ranks', 'omp_threads', 'P', 'Q']
    )

    all_configs['grid'] = (
        all_configs['P'].astype(str)
        + '×'
        + all_configs['Q'].astype(str)
    )
    all_configs['layout'] = (
        all_configs['mpi_ranks'].astype(str)
        + '×'
        + all_configs['omp_threads'].astype(str)
    )

    all_configs = all_configs.sort_values(
        ['mpi_ranks', 'P'],
        ascending=[False, True]
    )

    save_table(
        all_configs,
        outdir,
        'mpi_omp_all_configs',
        'MPI/OpenMP experiment — all tested configurations'
    )

    # For a clean MPI/OpenMP comparison, use the best observed process grid
    # for each MPI/OpenMP layout, ranked by mean GFLOPS.
    best_idx = (
        all_configs.groupby(
            ['mpi_ranks', 'omp_threads']
        )['gflops_mean']
        .idxmax()
    )

    best = all_configs.loc[best_idx].copy()
    best = best.sort_values('mpi_ranks', ascending=False)
    best['layout_grid'] = (
        best['layout']
        + '\nP'
        + best['P'].astype(str)
        + '×Q'
        + best['Q'].astype(str)
    )

    save_table(
        best.drop(columns='layout_grid'),
        outdir,
        'mpi_omp_best_observed',
        'MPI/OpenMP experiment — best observed process grid per layout'
    )

    bar_plot(
        best,
        'layout_grid',
        'MPI ranks × OMP threads (best tested grid)',
        'MPI OMP',
        outdir
    )
    dual_axis_performance_efficiency_plot(
        best,
        'layout_grid',
        'MPI ranks × OMP threads (best tested grid)',
        'MPI OMP',
        outdir,
        categorical=True
    )


def main():
    args = parse_args()

    csv_path = Path(args.csv)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    df = load_results(csv_path)

    print(f'Loaded {len(df)} successful exploratory HPL runs from {csv_path}')

    problem_size_experiment(df, outdir)
    block_size_experiment(df, outdir)
    process_grid_experiment(df, outdir)
    mpi_omp_experiment(df, outdir)

    print(f'\nFinished. Outputs written to: {outdir}')


if __name__ == '__main__':
    main()
