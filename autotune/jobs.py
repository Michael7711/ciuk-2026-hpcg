"""Benchmark input files, Slurm script rendering and run-directory preparation."""
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path

from .config import HPL_DEFAULTS

HPL_DAT = """HPLinpack benchmark input file
Innovative Computing Laboratory, University of Tennessee
HPL.out      output file name (if any)
6            device out (6=stdout,7=stderr,file)
1            # of problems sizes (N)
{N}          Ns
1            # of NBs
{NB}         NBs
0            PMAP process mapping (0=Row-,1=Column-major)
1            # of process grids (P x Q)
{P}          Ps
{Q}          Qs
16.0         threshold
1            # of panel fact
{pfact}      PFACTs (0=left, 1=Crout, 2=Right)
1            # of recursive stopping criterium
4            NBMINs (>= 1)
1            # of panels in recursion
2            NDIVs
1            # of recursive panel fact.
{rfact}      RFACTs (0=left, 1=Crout, 2=Right)
1            # of broadcast
{bcast}      BCASTs (0=1rg,1=1rM,2=2rg,3=2rM,4=Lng,5=LnM)
1            # of lookahead depth
{depth}      DEPTHs (>=0)
2            SWAP (0=bin-exch,1=long,2=mix)
64           swapping threshold
0            L1 in (0=transposed,1=no-transposed) form
0            U  in (0=transposed,1=no-transposed) form
1            Equilibration (0=no,1=yes)
8            memory alignment in double (> 0)
"""

HPCG_DAT = """HPCG benchmark input file
Sandia National Laboratories; University of Tennessee, Knoxville
{nx} {ny} {nz}
{runtime_s}
"""

INPUT_FILE = {"hpl": "HPL.dat", "hpcg": "hpcg.dat"}

# Run by every task. If the cluster config names a node energy counter ([energy] counter), local rank 0
# on each node snapshots it just before and just after the benchmark process, so the window excludes
# Slurm startup/teardown and extra srun launches. Files hold "<joules> J <microsecond timestamp> us".
# Without a counter (e.g. Kelvin2: IPMI is root-only) the wrapper just runs the benchmark.
ENERGY_WRAPPER = """#!/bin/bash
if [ "$SLURM_LOCALID" = 0 ]; then
  cat @COUNTER@ > "energy_start_$(hostname).txt"
fi
"$@"
rc=$?
if [ "$SLURM_LOCALID" = 0 ]; then
  cat @COUNTER@ > "energy_end_$(hostname).txt"
fi
exit $rc
"""
PLAIN_WRAPPER = """#!/bin/bash
exec "$@"
"""


BIND_PRELUDE = """lo=$((SLURM_LOCALID * @SHARE@))   # first core of this rank's share
taskset -cp $lo-$((lo + @SHARE@ - 1)) $$ > /dev/null   # bind this process; the benchmark inherits the mask
echo "task $SLURM_PROCID local $SLURM_LOCALID cpus $(taskset -cp $$ | sed 's/.*: //')" > "bind_task_$SLURM_PROCID.txt"
"""


def render_wrapper(settings, share=None):
    """Per-task wrapper script. Optional parts, chosen by the cluster config:
    - [energy] counter: snapshot node energy around the benchmark (ENERGY_WRAPPER).
    - [slurm] binding = "wrapper": the cluster's Slurm cannot bind tasks (Kelvin2: TaskPlugin=task/cgroup only,
      so --cpu-bind is a silent no-op and every rank sees the whole node). The wrapper then gives local rank i
      the cores [i*share, (i+1)*share) with taskset and records the affinity it actually got. Core numbering is
      contiguous per NUMA/L3 group on both our clusters; SMT siblings (cpu + cores_per_node) stay unused.
    """
    counter = settings.get("energy", {}).get("counter")
    text = ENERGY_WRAPPER.replace("@COUNTER@", counter) if counter else PLAIN_WRAPPER
    if settings.get("slurm", {}).get("binding") == "wrapper":
        text = text.replace("#!/bin/bash\n", "#!/bin/bash\n" + BIND_PRELUDE.replace("@SHARE@", str(share)), 1)
    return text


def render_input(cfg):
    params = {**HPL_DEFAULTS, **cfg.params}
    return (HPL_DAT if cfg.benchmark == "hpl" else HPCG_DAT).format(**params)


def run_id(cfg):
    """Deterministic ID: same config -> same ID."""
    digest = hashlib.sha1(json.dumps(asdict(cfg), sort_keys=True).encode()).hexdigest()[:8]
    return f"{cfg.benchmark}-{cfg.kind}-n{cfg.nodes}-{cfg.ranks_per_node}x{cfg.threads}-{digest}"


def walltime_s(cfg, settings):
    if cfg.benchmark == "hpcg":
        return cfg.params["runtime_s"] + 600  # benchmark time + setup/teardown margin
    return settings["slurm"]["walltime_s"]


def render_job_script(cfg, settings, hw, run_dir):
    s = settings["slurm"]
    binary = settings[cfg.benchmark]["binary"]
    qos = s.get("final_qos") if cfg.kind == "final" else s.get("qos")
    seconds = walltime_s(cfg, settings)
    limit = s.get("final_max_walltime_s") if cfg.kind == "final" else s.get("max_walltime_s")
    if limit and seconds > limit:  # e.g. Cirrus `short` QoS 20 min, Kelvin2 sandbox 30 min
        raise ValueError(f"{seconds}s exceeds the {limit}s wall-time limit of this QoS/partition; "
                         "use kind=final or a shorter run")
    share = hw.cores_per_node // cfg.ranks_per_node  # cores owned by each rank
    lines = [
        "#!" + s.get("shell", "/bin/bash --login"),  # Cirrus needs a login shell for `module`
        f"#SBATCH --job-name={run_id(cfg)}",
        f"#SBATCH --nodes={cfg.nodes}",
        f"#SBATCH --ntasks-per-node={cfg.ranks_per_node}",
        f"#SBATCH --cpus-per-task={share}",
        "#SBATCH --hint=nomultithread",
        "#SBATCH --exclusive",
        f"#SBATCH --time={seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}",
        f"#SBATCH --output={run_dir}/slurm-%j.out",
    ]
    lines += [f"#SBATCH --{key}={val}" for key, val in
              (("account", s.get("account")), ("partition", s.get("partition")), ("qos", qos)) if val]
    lines += [f"#SBATCH {d}" for d in s.get("extra_directives", [])]  # cluster quirks, e.g. --mem=0
    lines += ["", "set -e", f'cd "{run_dir}"']
    lines += [f"module load {m}" for m in s.get("modules", [])]
    env = {
        "OMP_NUM_THREADS": cfg.threads,
        "OMP_PROC_BIND": "close",
        "OMP_PLACES": "cores",
        **settings.get("env", {}),
    }
    lines += [f"export {k}={v}" for k, v in env.items()]
    lines += ["", "# provenance for reproducibility"]
    lines += ["module list > modules.txt 2>&1 || true"] if s.get("modules") else [
        f"ldd {binary} > libs.txt 2>&1 || true  # no module system: record the libraries actually resolved"]
    lines += [
        'scontrol show job "$SLURM_JOB_ID" > job_info.txt || true',
        "lscpu -e=CPU,CORE,NODE,CACHE > topology.txt 2>&1 || true  # which logical CPUs share a core / L3",
        "",
    ]
    delay = s.get("thread_sample_after_s", 0)
    if delay:  # only sees this (first) node: enough for single-node runs
        snap = "{ date +%s; ps -eLo pid,tid,psr,cputimes,comm; echo PROCESS; ps -eo pid,cputimes,nlwp,comm; }"
        lines += [
            "# CPU-use snapshots 10 s apart (per live thread and per process, cumulative CPU seconds); see `autotune threads`",
            f"( sleep {delay}; {snap} > thread_sample_1.txt; sleep 10; {snap} > thread_sample_2.txt ) &",
            "",
        ]
    poll = settings.get("energy", {}).get("poll_scontrol_s")
    if poll:  # same IPMI sensor Slurm accounts from, but sampled by us at known times: lets us judge its quality
        lines += ["# node power as Slurm's IPMI view reports it, polled (informational; never used for efficiency)",
                  f'( while true; do echo "$(date +%s) $(scontrol show node $(hostname -s) | grep -o \'CurrentWatts=[0-9A-Za-z/]*\')" '
                  f">> power_trace.txt; sleep {poll}; done ) &", "POLL_PID=$!", ""]
    lines += [
        f"# each rank owns {share} cores (cpu-bind=cores); {cfg.threads} OpenMP threads run inside it",
        " ".join(["srun", *([f"--nodes={cfg.nodes}", f"--ntasks-per-node={cfg.ranks_per_node}"] if s.get("inline") else []),
                  f"--cpus-per-task={share}", "--cpu-bind=verbose,cores",
                  "--distribution=block:block", "--hint=nomultithread", *s.get("srun_flags", []),
                  "./bench_wrapper.sh", str(binary)]),
    ]
    lines += ['kill $POLL_PID 2>/dev/null || true'] if poll else []
    lines += [""]
    return "\n".join(lines)


def prepare_run(cfg, settings, hw, runs_dir):
    """Write config.json, the benchmark input file, wrapper and job.sh. Does NOT submit."""
    run_dir = Path(os.path.abspath(runs_dir)) / run_id(cfg)  # abspath: keep /epccfs symlink as given
    prefix = settings.get("paths", {}).get("required_prefix", "")
    if not str(run_dir).startswith(prefix):
        raise ValueError(f"{run_dir} must be under {prefix} (compute nodes cannot see other filesystems)")
    run_dir.mkdir(parents=True)  # raises if it exists: never overwrite raw outputs
    (run_dir / "config.json").write_text(json.dumps(asdict(cfg), indent=2))
    (run_dir / INPUT_FILE[cfg.benchmark]).write_text(render_input(cfg))
    (run_dir / "bench_wrapper.sh").write_text(render_wrapper(settings, hw.cores_per_node // cfg.ranks_per_node))
    (run_dir / "bench_wrapper.sh").chmod(0o755)
    (run_dir / "job.sh").write_text(render_job_script(cfg, settings, hw, run_dir))
    return run_dir
