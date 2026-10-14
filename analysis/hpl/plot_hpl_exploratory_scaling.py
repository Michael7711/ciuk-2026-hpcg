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
    5. Strong scaling
    6. Memory-scaled node scaling
    7. Constant-computational-work-per-node scaling

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



def latest_row(df):
    """Return the most recent row from a non-empty DataFrame."""
    if df.empty:
        raise ValueError('Expected at least one matching scaling run.')
    if 'timestamp_utc' in df.columns:
        return df.sort_values('timestamp_utc').iloc[-1]
    return df.iloc[-1]


def get_scaling_baseline(df):
    """
    Select the most recent 1-node scaling baseline.

    This deliberately selects the latest successful N=117248, NB=256,
    P=8, Q=36, 288-MPI x 1-OMP run so a rerun on the current pipeline
    supersedes earlier exploratory repeats.
    """
    candidates = df[
        (df['nodes'] == 1)
        & (df['mpi_ranks'] == 288)
        & (df['omp_threads'] == 1)
        & (df['N'] == 117248)
        & (df['NB'] == 256)
        & (df['P'] == 8)
        & (df['Q'] == 36)
    ].copy()

    return latest_row(candidates)


def get_latest_purpose_run(df, purpose):
    """Select the most recent successful run for a purpose label."""
    return latest_row(df[df['purpose'] == purpose].copy())


def build_scaling_table(df, strategy):
    """
    Build one scaling table from the latest run at each node count.

    strategy:
        'strong'  -> fixed N
        'memory'  -> N proportional to sqrt(nodes)
        'compute' -> N proportional to cbrt(nodes)
    """
    baseline = get_scaling_baseline(df)

    rows = [baseline.to_dict()]
    for nodes in (2, 3, 4):
        rows.append(
            get_latest_purpose_run(df, f'{strategy}{nodes}').to_dict()
        )

    table = pd.DataFrame(rows).sort_values('nodes').reset_index(drop=True)

    n1 = float(table.loc[table['nodes'] == 1, 'N'].iloc[0])
    t1 = float(table.loc[table['nodes'] == 1, 'hpl_runtime_s'].iloc[0])

    table['energy_kj'] = table['energy_j'] / 1000.0
    table['speedup_vs_1node'] = t1 / table['hpl_runtime_s']
    table['parallel_efficiency_pct'] = (
        table['speedup_vs_1node'] / table['nodes'] * 100.0
    )

    if strategy == 'strong':
        table['ideal_runtime_s'] = t1 / table['nodes']
        table['ideal_speedup'] = table['nodes'].astype(float)
        table['runtime_deviation_pct'] = (
            (table['hpl_runtime_s'] - table['ideal_runtime_s'])
            / table['ideal_runtime_s']
            * 100.0
        )
        table['scaling_quantity_ratio'] = 1.0
        table['scaling_quantity_name'] = 'N / N1'

    elif strategy == 'memory':
        # Matrix storage is proportional to N^2. This ratio should be ~1.
        table['ideal_runtime_s'] = t1 * np.sqrt(table['nodes'])
        table['ideal_speedup'] = np.nan
        table['runtime_deviation_pct'] = (
            (table['hpl_runtime_s'] - table['ideal_runtime_s'])
            / table['ideal_runtime_s']
            * 100.0
        )
        table['scaling_quantity_ratio'] = (
            (table['N'] / n1) ** 2 / table['nodes']
        )
        table['scaling_quantity_name'] = '(N/N1)^2 / nodes'
        table['speedup_vs_1node'] = np.nan
        table['parallel_efficiency_pct'] = np.nan

    elif strategy == 'compute':
        # LU work is approximately proportional to N^3. This ratio should be ~1.
        table['ideal_runtime_s'] = t1
        table['ideal_speedup'] = np.nan
        table['runtime_deviation_pct'] = (
            (table['hpl_runtime_s'] - table['ideal_runtime_s'])
            / table['ideal_runtime_s']
            * 100.0
        )
        table['scaling_quantity_ratio'] = (
            (table['N'] / n1) ** 3 / table['nodes']
        )
        table['scaling_quantity_name'] = '(N/N1)^3 / nodes'
        table['speedup_vs_1node'] = np.nan
        table['parallel_efficiency_pct'] = np.nan

    else:
        raise ValueError(f'Unknown scaling strategy: {strategy}')

    keep = [
        'nodes', 'mpi_ranks', 'omp_threads', 'N', 'NB', 'P', 'Q',
        'hpl_runtime_s', 'ideal_runtime_s', 'runtime_deviation_pct',
        'speedup_vs_1node', 'ideal_speedup', 'parallel_efficiency_pct',
        'gflops', 'energy_kj', 'avg_power_w', 'gflops_per_w',
        'scaling_quantity_ratio'
    ]

    return table[keep]


def scaling_runtime_theory_plot(table, strategy_name, outdir):
    """Plot measured runtime against the simple theoretical expectation."""
    fig = plt.figure(figsize=(7.5, 4.8))
    ax = fig.gca()

    ax.plot(
        table['nodes'],
        table['hpl_runtime_s'],
        marker='o',
        linestyle='-',
        label='Measured runtime'
    )
    ax.plot(
        table['nodes'],
        table['ideal_runtime_s'],
        marker='s',
        linestyle='--',
        label='Ideal/theoretical runtime'
    )

    ax.set_xticks(table['nodes'])
    ax.set_xlabel('Nodes')
    ax.set_ylabel('HPL runtime (s)')
    ax.set_title(f'{strategy_name}: measured vs theoretical runtime')
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()

    fig.savefig(
        outdir / f'{strategy_name.lower().replace(" ", "_")}_runtime_vs_theory.png',
        dpi=200,
        bbox_inches='tight'
    )
    plt.close(fig)


def strong_scaling_speedup_plot(table, outdir):
    """Plot measured strong-scaling speedup against ideal linear speedup."""
    fig = plt.figure(figsize=(7.5, 4.8))
    ax = fig.gca()

    ax.plot(
        table['nodes'],
        table['speedup_vs_1node'],
        marker='o',
        linestyle='-',
        label='Measured speedup'
    )
    ax.plot(
        table['nodes'],
        table['ideal_speedup'],
        marker='s',
        linestyle='--',
        label='Ideal speedup'
    )

    ax.set_xticks(table['nodes'])
    ax.set_xlabel('Nodes')
    ax.set_ylabel('Speedup relative to 1 node')
    ax.set_title('Strong scaling: measured vs ideal speedup')
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()

    fig.savefig(
        outdir / 'strong_scaling_speedup.png',
        dpi=200,
        bbox_inches='tight'
    )
    plt.close(fig)


def strong_scaling_efficiency_plot(table, outdir):
    """Plot parallel efficiency for the strong-scaling experiment."""
    fig = plt.figure(figsize=(7.5, 4.8))
    ax = fig.gca()

    ax.plot(
        table['nodes'],
        table['parallel_efficiency_pct'],
        marker='o'
    )

    ax.set_xticks(table['nodes'])
    ax.set_xlabel('Nodes')
    ax.set_ylabel('Parallel efficiency (%)')
    ax.set_title('Strong scaling: parallel efficiency')
    ax.grid(alpha=0.25)
    fig.tight_layout()

    fig.savefig(
        outdir / 'strong_scaling_parallel_efficiency.png',
        dpi=200,
        bbox_inches='tight'
    )
    plt.close(fig)


def scaling_dual_axis_plot(table, strategy_name, outdir):
    """Plot GFLOPS and GFLOPS/W against node count on separate y-axes."""
    fig = plt.figure(figsize=(7.5, 4.8))
    ax1 = fig.gca()
    ax2 = ax1.twinx()

    perf = ax1.plot(
        table['nodes'],
        table['gflops'],
        marker='o',
        linestyle='-',
        label='GFLOPS'
    )[0]

    efficiency = ax2.plot(
        table['nodes'],
        table['gflops_per_w'],
        marker='s',
        linestyle='--',
        label='GFLOPS/W'
    )[0]

    ax1.set_xticks(table['nodes'])
    ax1.set_xlabel('Nodes')
    ax1.set_ylabel('GFLOPS')
    ax2.set_ylabel('GFLOPS/W')
    ax1.set_title(f'{strategy_name}: performance and energy efficiency')
    ax1.grid(alpha=0.25)
    ax1.legend(
        [perf, efficiency],
        [perf.get_label(), efficiency.get_label()],
        loc='best'
    )
    fig.tight_layout()

    fig.savefig(
        outdir / f'{strategy_name.lower().replace(" ", "_")}_gflops_gflops_per_w.png',
        dpi=200,
        bbox_inches='tight'
    )
    plt.close(fig)


def scaling_energy_plot(table, strategy_name, outdir):
    """Plot total measured job energy against node count."""
    fig = plt.figure(figsize=(7.5, 4.8))
    ax = fig.gca()

    ax.plot(
        table['nodes'],
        table['energy_kj'],
        marker='o'
    )

    ax.set_xticks(table['nodes'])
    ax.set_xlabel('Nodes')
    ax.set_ylabel('Total energy (kJ)')
    ax.set_title(f'{strategy_name}: energy to solution')
    ax.grid(alpha=0.25)
    fig.tight_layout()

    fig.savefig(
        outdir / f'{strategy_name.lower().replace(" ", "_")}_energy_to_solution.png',
        dpi=200,
        bbox_inches='tight'
    )
    plt.close(fig)


def combined_scaling_runtime_plot(tables, outdir):
    """Compare measured runtime trends for all three scaling strategies."""
    fig = plt.figure(figsize=(7.8, 5.0))
    ax = fig.gca()

    labels = {
        'strong': 'Strong scaling',
        'memory': 'Memory-scaled',
        'compute': 'Constant work/node',
    }
    markers = {
        'strong': 'o',
        'memory': 's',
        'compute': '^',
    }

    for key, table in tables.items():
        ax.plot(
            table['nodes'],
            table['hpl_runtime_s'],
            marker=markers[key],
            label=labels[key]
        )

    ax.set_xticks([1, 2, 3, 4])
    ax.set_xlabel('Nodes')
    ax.set_ylabel('HPL runtime (s)')
    ax.set_title('Node scaling: runtime comparison')
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()

    fig.savefig(
        outdir / 'scaling_runtime_comparison.png',
        dpi=200,
        bbox_inches='tight'
    )
    plt.close(fig)


def combined_scaling_gflops_plot(tables, outdir):
    """Compare HPL performance across all three scaling strategies."""
    fig = plt.figure(figsize=(7.8, 5.0))
    ax = fig.gca()

    labels = {
        'strong': 'Strong scaling',
        'memory': 'Memory-scaled',
        'compute': 'Constant work/node',
    }
    markers = {
        'strong': 'o',
        'memory': 's',
        'compute': '^',
    }

    for key, table in tables.items():
        ax.plot(
            table['nodes'],
            table['gflops'],
            marker=markers[key],
            label=labels[key]
        )

    ax.set_xticks([1, 2, 3, 4])
    ax.set_xlabel('Nodes')
    ax.set_ylabel('GFLOPS')
    ax.set_title('Node scaling: HPL performance comparison')
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()

    fig.savefig(
        outdir / 'scaling_gflops_comparison.png',
        dpi=200,
        bbox_inches='tight'
    )
    plt.close(fig)


def scaling_experiments(df, outdir):
    """
    Produce the key tables and figures for the final exploratory node-scaling block.

    The most recent run is used when a purpose was repeated, so the rerun of the
    1-node baseline and strong2 on the current pipeline supersede earlier runs.
    """
    tables = {
        'strong': build_scaling_table(df, 'strong'),
        'memory': build_scaling_table(df, 'memory'),
        'compute': build_scaling_table(df, 'compute'),
    }

    names = {
        'strong': 'Strong scaling',
        'memory': 'Memory-scaled scaling',
        'compute': 'Constant work per node',
    }

    for key, table in tables.items():
        save_table(
            table,
            outdir,
            f'scaling_{key}',
            names[key]
        )
        scaling_runtime_theory_plot(
            table,
            names[key],
            outdir
        )
        scaling_dual_axis_plot(
            table,
            names[key],
            outdir
        )
        scaling_energy_plot(
            table,
            names[key],
            outdir
        )

    strong_scaling_speedup_plot(tables['strong'], outdir)
    strong_scaling_efficiency_plot(tables['strong'], outdir)
    combined_scaling_runtime_plot(tables, outdir)
    combined_scaling_gflops_plot(tables, outdir)

    combined = pd.concat(
        [
            table.assign(strategy=names[key])
            for key, table in tables.items()
        ],
        ignore_index=True
    )

    save_table(
        combined[
            [
                'strategy', 'nodes', 'N', 'P', 'Q',
                'hpl_runtime_s', 'ideal_runtime_s',
                'runtime_deviation_pct', 'gflops',
                'energy_kj', 'gflops_per_w'
            ]
        ],
        outdir,
        'scaling_summary',
        'Node-scaling summary'
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
    scaling_experiments(df, outdir)

    print(f'\nFinished. Outputs written to: {outdir}')


if __name__ == '__main__':
    main()
