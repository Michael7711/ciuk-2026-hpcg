"""Run-and-record automation, only for cluster configs that explicitly allow submission.

One experiment = prepare run dir -> sbatch --wait (one job at a time) -> parse + log. A loop repeats
this, choosing the next configs either at random or with the GP (model.suggest). Safety:
- `[safety] allow_submit = true` must be set in the cluster config (the Cirrus config says false).
- `[budget]` caps the node-hours charged since a start time, read from sacct (so builds, smoke tests
  and failed jobs all count); a job is refused if its worst-case wall time could exceed the cap.
"""
import getpass
import json
import os
import random
import signal
import subprocess
import time
from pathlib import Path

from .candidates import generate
from .config import HPL_DEFAULTS, Config, validate
from .jobs import prepare_run, run_id, walltime_s
from .model import suggest, training_rows
from .prior import prior_init, prior_order
from .results import _slurm_seconds, fetch_sacct, load_rows, record_run


def require_submit_allowed(settings):
    if not settings.get("safety", {}).get("allow_submit"):
        raise PermissionError("[safety] allow_submit is not true in this cluster config: submit by hand")


def node_hours_used(settings, hw):
    """Node-hours charged since [budget] since (core-seconds / cores_per_node), including running jobs."""
    out = subprocess.run(
        ["sacct", "-u", getpass.getuser(), "-S", settings["budget"]["since"], "-X", "-n", "-P",
         "--format=JobID,ElapsedRaw,AllocCPUS"], capture_output=True, text=True, check=True).stdout
    core_seconds = sum(int(f[1]) * int(f[2]) for f in (line.split("|") for line in out.splitlines())
                       if len(f) >= 3 and f[1] and f[2])
    return core_seconds / (hw.cores_per_node * 3600)


def submit_and_wait(run_dir, settings):
    """sbatch --wait: blocks until the job ends (so at most one of our jobs runs at a time)."""
    require_submit_allowed(settings)
    r = subprocess.run(["sbatch", "--parsable", "--wait", "job.sh"], cwd=run_dir,
                       capture_output=True, text=True)
    job_id = r.stdout.strip().split(";")[0]
    if not job_id:  # a job that ran and failed still prints its id; no id means it never started
        raise RuntimeError(f"sbatch failed: {r.stderr.strip()}")
    return job_id


def time_left_s(alloc_id):
    """Seconds left in our own allocation, or None if squeue cannot say."""
    out = subprocess.run(["squeue", "-h", "-j", str(alloc_id), "-o", "%L"], capture_output=True, text=True).stdout.strip()
    return _slurm_seconds(out) if out and out[0].isdigit() else None


def run_inline(run_dir, settings):
    """Run job.sh as srun steps INSIDE the allocation we are already in ([slurm] inline = true): one queue wait for
    a whole stage instead of one per evaluation. The run is killed (whole process group, so the srun step dies too)
    if it exceeds walltime_s. Returns (job_id, wall seconds); output goes to slurm-<job_id>.out like a batch job."""
    alloc = os.environ.get("SLURM_JOB_ID")
    if not alloc:
        raise RuntimeError("[slurm] inline = true must run inside an allocation (sbatch/salloc), not on a login node")
    cap = settings["slurm"]["walltime_s"]
    left = time_left_s(alloc)
    if left is not None and left < cap + 60:
        raise RuntimeError(f"allocation has {left:.0f}s left; one run may need {cap}s: stopping before starting it")
    job_id = f"{alloc}-{int(time.time())}"
    t0 = time.time()
    with open(Path(run_dir) / f"slurm-{job_id}.out", "w") as out:
        proc = subprocess.Popen(["bash", "job.sh"], cwd=run_dir, stdout=out, stderr=subprocess.STDOUT,
                                start_new_session=True)
        try:
            proc.wait(timeout=cap)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
    return job_id, time.time() - t0


def evaluate(cfg, settings, hw, runs_dir, log):
    """Run one configuration for real and log it. Returns the CSV row."""
    require_submit_allowed(settings)
    used, cap = node_hours_used(settings, hw), settings["budget"]["max_node_hours"]
    worst = walltime_s(cfg, settings) / 3600 * cfg.nodes
    if used + worst > cap:
        raise RuntimeError(f"budget: {used:.3f} node-h used + {worst:.3f} worst case for this job > cap {cap}")
    run_dir = prepare_run(cfg, settings, hw, runs_dir)
    if settings["slurm"].get("inline"):
        job_id, elapsed = run_inline(run_dir, settings)
        return record_run(run_dir, job_id, log, None, elapsed_s=elapsed)      # energy: not recorded inline
    job_id = submit_and_wait(run_dir, settings)
    return record_run(run_dir, job_id, log, fetch_sacct(job_id),
                      settings.get("energy", {}).get("sacct_min_window_s", 0))


def unseen(cands, rows, runs_dir):
    """Candidates neither in the log nor already prepared in runs_dir."""
    seen = {r["run_id"] for r in rows}
    return [c for c in cands if run_id(c) not in seen and not (Path(runs_dir) / run_id(c)).exists()]


def load_config_list(path, hw):
    """Explicit evaluation list for stages that re-measure chosen configurations (transfer subsets, weak scaling,
    repeats). JSON: [{"nodes": 1, "ranks_per_node": 32, "threads": 4, "params": {"N": ..., "NB": ..., "P": ..., "Q": ...}}]."""
    cfgs = [Config("hpl", d["nodes"], d["ranks_per_node"], d["threads"],
                   {**HPL_DEFAULTS, **d['params']}) for d in json.load(open(path))]
    bad = [(c, validate(c, hw)) for c in cfgs if validate(c, hw)]
    if bad:
        raise ValueError(f"invalid configs in {path}: {bad[0]}")
    return cfgs


def pick(strategy, rows, cands, n, beta, min_rows, seed, hw=None, full=None, n_init=6, noise_sd=0.02, order=None):
    """Next n configurations. `cands` are the unseen ones, `full` the whole candidate list (for the deterministic start).
    random    uniform without replacement
    gp        random start (suggest falls back to a seeded random design below min_rows usable rows), then GP-UCB
    heuristic walk down the hardware prior (autotune/prior.py)
    hybrid    prior_init start, then GP-UCB; if failures leave too few usable rows, keep walking the prior
    """
    if strategy == "random":
        return random.Random(f"{seed}-{len(rows)}").sample(cands, min(n, len(cands)))
    if strategy == "list":                      # the given order, skipping what was already evaluated
        return [c for c in order if c in cands][:n]
    if strategy == "heuristic":
        return prior_order(cands, hw)[:n]
    if strategy == "hybrid":
        if len(rows) < n_init:
            start = [c for c in prior_init(full or cands, hw, n_init) if c in cands]
            return start[:min(n, n_init - len(rows))]
        if len(training_rows(rows, "gflops")) < min_rows:
            return prior_order(cands, hw)[:n]
    return [c for c, _ in suggest(rows, cands, n, 0.0, beta, min_rows, seed, noise_sd=noise_sd)]


def run_loop(benchmark, strategy, max_new, batch, nodes, kind, settings, hw, runs_dir, log,
             beta=1.0, min_rows=6, seed=0, report=print, config_list=None):
    """Evaluate up to max_new new configurations, `batch` chosen per round from the log so far."""
    done = 0
    while done < max_new:
        rows = load_rows(log, benchmark) if Path(log).exists() else []
        full = config_list if strategy == "list" else generate(benchmark, hw, nodes, settings[benchmark], kind)
        cands = unseen(full, rows, runs_dir)
        if not cands:
            break
        noise_sd = settings.get("model", {}).get("noise_sd", 0.02)
        for cfg in pick(strategy, rows, cands, min(batch, max_new - done), beta, min_rows, seed,
                        hw=hw, full=full, n_init=min_rows, noise_sd=noise_sd, order=config_list):
            row = evaluate(cfg, settings, hw, runs_dir, log)
            done += 1
            report(f"[{strategy} {done}/{max_new}] {cfg.ranks_per_node}x{cfg.threads} {cfg.params} -> "
                   f"{row['gflops']} GFLOPS ({row['validation']}), used "
                   f"{node_hours_used(settings, hw):.3f}/{settings['budget']['max_node_hours']} node-h")
    return done
