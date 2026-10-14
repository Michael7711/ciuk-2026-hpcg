"""CLI: python -m autotune {candidates,prepare,manual-hpl,suggest,record,threads,usage,loop} ...

Only `loop` submits jobs, and only when the cluster config sets [safety] allow_submit = true."""
import argparse
import json
import sys
from pathlib import Path

from .candidates import generate, pq_pairs, sample
from .config import HPL_DEFAULTS, Config, apply_overrides, load_settings, validate
from .jobs import prepare_run
from .loop import load_config_list, node_hours_used, run_loop, unseen
from .model import suggest
from .results import check_binding, check_binding_report, check_threads, fetch_sacct, load_rows, record_run


def cmd_candidates(a, settings, hw):
    cands = generate(a.benchmark, hw, a.nodes, settings[a.benchmark], a.kind)
    print(f"{len(cands)} valid candidates")
    for c in sample(cands, a.n, a.seed):
        print(f"  {c.ranks_per_node}x{c.threads}  {c.params}")


def cmd_prepare(a, settings, hw):
    cands = generate(a.benchmark, hw, a.nodes, settings[a.benchmark], a.kind)
    for c in sample(cands, a.n, a.seed):
        run_dir = prepare_run(c, settings, hw, a.runs_dir)
        print(f"sbatch {run_dir}/job.sh")


def cmd_manual_hpl(a, settings, hw):
    """Prepare one hand-chosen HPL run (baselines, smoke tests). No P/Q given -> squarest grid."""
    ranks = a.nodes * a.ranks_per_node
    p, q = (a.P, a.Q) if a.P and a.Q else pq_pairs(ranks, 10**9)[-1]
    params = {
        **HPL_DEFAULTS,
        'N': a.N,
        'NB': a.NB,
        'P': p,
        'Q': q,
    }
    cfg = Config(
        'hpl',
        a.nodes,
        a.ranks_per_node,
        a.threads,
        params,
        a.kind,
    )
    if errors := validate(cfg, hw):
        sys.exit("invalid config: " + "; ".join(errors))
    print(f"sbatch {prepare_run(cfg, settings, hw, a.runs_dir)}/job.sh")


def cmd_threads(a, settings, hw):
    run_dir = Path(a.run_dir)
    cfg = Config(**json.loads((run_dir / "config.json").read_text()))
    print(f"expected: {cfg.mpi_ranks} ranks (all nodes) x {cfg.threads} threads; "
          f"snapshots cover node 0 only: {cfg.ranks_per_node} ranks x {cfg.threads}")
    if (run_dir / "thread_sample_2.txt").exists():
        print(check_threads(run_dir, Path(settings[cfg.benchmark]["binary"]).name[:15]))
    else:  # the job ended before the snapshots (delay is [slurm] thread_sample_after_s)
        print("no thread snapshots: the run finished before the first one was due, or sampling is off")
    outs = sorted(run_dir.glob("slurm-*.out"))
    print(f"expected: {hw.cores_per_node // cfg.ranks_per_node} cores per task, none shared")
    if list(run_dir.glob("bind_task_*.txt")):  # wrapper-bound (cluster's Slurm cannot bind)
        print("affinity each rank actually got (bind_task_*.txt):", check_binding_report(run_dir, hw.cores_per_node))
    elif outs:
        print("srun --cpu-bind=verbose masks:", check_binding(outs[-1].read_text(), hw.cores_per_node))


def cmd_suggest(a, settings, hw):
    """Pick the next experiments from the history, write their run dirs (no submission)."""
    rows = load_rows(a.log, a.benchmark) if Path(a.log).exists() else []
    cands = unseen(generate(a.benchmark, hw, a.nodes, settings[a.benchmark], a.kind), rows, a.runs_dir)
    for c, why in suggest(rows, cands, a.n, a.efficiency_weight, a.beta, a.min_rows, a.seed):
        print(f"{c.ranks_per_node}x{c.threads} {c.params}\n    {why}")
        if not a.dry_run:
            print(f"    sbatch {prepare_run(c, settings, hw, a.runs_dir)}/job.sh")


def cmd_loop(a, settings, hw):
    config_list = load_config_list(a.config_list, hw) if a.strategy == "list" else None
    n = run_loop(a.benchmark, a.strategy, a.max_new, a.batch, a.nodes, a.kind, settings, hw,
                 a.runs_dir, a.log, a.beta, a.min_rows, a.seed, config_list=config_list)
    print(f"{n} new evaluations; {node_hours_used(settings, hw):.3f} node-h used")


def cmd_usage(a, settings, hw):
    print(f"{node_hours_used(settings, hw):.3f} node-h used since {settings['budget']['since']} "
          f"(cap {settings['budget']['max_node_hours']})")


def cmd_record(a, settings, hw):
    row = record_run(a.run_dir, a.job_id, a.log, fetch_sacct(a.job_id) if a.sacct else None,
                     settings.get("energy", {}).get("sacct_min_window_s", 0), (a.energy_j, a.elapsed_s))
    print({k: row[k] for k in ("validation", "parse_status", "gflops", "energy_j", "energy_status", "gflops_per_w")})


def main():
    p = argparse.ArgumentParser(prog="autotune")
    p.add_argument("--settings", default="settings.toml")
    p.add_argument("--set", action="append", metavar="KEY=VALUE",
                   help="override a settings value for this call, e.g. --set hpl.n=[80640] --set slurm.walltime_s=600")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name, fn in (("candidates", cmd_candidates), ("prepare", cmd_prepare)):
        s = sub.add_parser(name)
        s.add_argument("benchmark", choices=["hpl", "hpcg"])
        s.add_argument("--nodes", type=int, default=1)
        s.add_argument("--kind", choices=["diagnostic", "final"], default="diagnostic")
        s.add_argument("-n", type=int, default=5, help="how many random candidates")
        s.add_argument("--seed", type=int, default=0)
        if name == "prepare":
            s.add_argument("--runs-dir", help="default: [paths] runs_dir in settings")
        s.set_defaults(fn=fn)

    s = sub.add_parser("manual-hpl", help="prepare one hand-chosen HPL run")
    s.add_argument("--nodes", type=int, default=1)
    s.add_argument("--ranks-per-node", type=int, required=True)
    s.add_argument("--threads", type=int, required=True)
    s.add_argument("--N", type=int, required=True)
    s.add_argument("--NB", type=int, required=True)
    s.add_argument("--P", type=int)
    s.add_argument("--Q", type=int)
    s.add_argument("--kind", choices=["diagnostic", "final"], default="diagnostic")
    s.add_argument("--runs-dir", help="default: [paths] runs_dir in settings")
    s.set_defaults(fn=cmd_manual_hpl)

    s = sub.add_parser("threads", help="were the OpenMP threads really running? (reads thread_sample_*.txt)")
    s.add_argument("run_dir")
    s.set_defaults(fn=cmd_threads)

    s = sub.add_parser("suggest", help="model-guided choice of the next runs")
    s.add_argument("benchmark", choices=["hpl", "hpcg"])
    s.add_argument("--nodes", type=int, default=1)
    s.add_argument("--kind", choices=["diagnostic", "final"], default="diagnostic")
    s.add_argument("-n", type=int, default=4, help="batch size")
    s.add_argument("--log", help="default: [paths] log in settings")
    s.add_argument("--runs-dir", help="default: [paths] runs_dir in settings")
    s.add_argument("--beta", type=float, default=2.0, help="exploration weight (0 = exploit only)")
    s.add_argument("--efficiency-weight", type=float, default=0.0,
                   help="weight of GFLOPS/W relative to GFLOPS (needs energy data)")
    s.add_argument("--min-rows", type=int, default=6, help="below this, use a random initial design")
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--dry-run", action="store_true", help="print only, write no run directories")
    s.set_defaults(fn=cmd_suggest)

    s = sub.add_parser("loop", help="SUBMITS JOBS (needs [safety] allow_submit): evaluate configs one at a time")
    s.add_argument("benchmark", choices=["hpl", "hpcg"])
    s.add_argument("--strategy", choices=["gp", "random", "heuristic", "hybrid", "list"], required=True)
    s.add_argument("--max-new", type=int, required=True, help="new evaluations to run in this call")
    s.add_argument("--batch", type=int, default=1, help="configs chosen per round (kriging believer for gp)")
    s.add_argument("--nodes", type=int, default=1)
    s.add_argument("--kind", choices=["diagnostic", "final"], default="diagnostic")
    s.add_argument("--beta", type=float, default=1.0, help="GP exploration weight")
    s.add_argument("--min-rows", type=int, default=6, help="below this many usable rows: random design")
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--config-list", help="JSON file of configurations, for --strategy list")
    s.add_argument("--log", help="default: [paths] log in settings")
    s.add_argument("--runs-dir", help="default: [paths] runs_dir in settings")
    s.set_defaults(fn=cmd_loop)

    s = sub.add_parser("usage", help="node-hours charged since [budget] since (from sacct)")
    s.set_defaults(fn=cmd_usage)

    s = sub.add_parser("record", help="parse a finished run and append it to the CSV log")
    s.add_argument("run_dir")
    s.add_argument("--job-id", required=True)
    s.add_argument("--log", help="default: [paths] log in settings")
    s.add_argument("--sacct", action="store_true", help="cross-check / fallback: whole-job Elapsed + ConsumedEnergyRaw")
    s.add_argument("--energy-j", type=float, help="manual energy reading (J)")
    s.add_argument("--elapsed-s", type=float, help="manual job elapsed time (s)")
    s.set_defaults(fn=cmd_record)

    a = p.parse_args()
    settings, hw = load_settings(a.settings)
    apply_overrides(settings, a.set)
    for name in ("runs_dir", "log"):
        if hasattr(a, name) and getattr(a, name) is None:
            setattr(a, name, settings["paths"][name])
    a.fn(a, settings, hw)


if __name__ == "__main__":
    main()
