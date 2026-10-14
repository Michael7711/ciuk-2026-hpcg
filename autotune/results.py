"""Parse benchmark output and log experiments to CSV."""
import csv
import json
import os
import re
import subprocess
from pathlib import Path

COLUMNS = [
    'run_id', 'kind', 'benchmark', 'replicate',
    'build_id', 'binary_path', 'binary_sha256', 'git_commit',
    'nodes', 'mpi_ranks', 'omp_threads',
    'N', 'NB', 'P', 'Q', 'pfact', 'rfact', 'bcast', 'depth',
    'nx', 'ny', 'nz', 'hpcg_runtime_s',
    'runtime_s', 'elapsed_s', 'gflops', 'energy_j',
    'energy_window_s', 'energy_source', 'energy_status',
    'avg_power_w', 'gflops_per_w',
    'job_id', 'validation', 'parse_status', 'raw_output',
]
# validation:   HPL "PASSED"/"FAILED"; HPCG "VALID"/"INVALID"; otherwise "unknown"
# parse_status: "ok", "no_result_found", "no_output", "unsupported"
# energy_source: "pm_counters" (benchmark window, all nodes), "sacct" (whole job), "manual"
# energy_status: "ok", "missing", "inconsistent", "unverified_multinode", "low_resolution"
# Efficiency (avg_power_w, gflops_per_w) is only filled when energy_status == "ok".

# Set to True only after a real multi-node run shows the per-node counter files sum to a
# sensible total (e.g. close to sacct's ConsumedEnergyRaw for that job). Until then, multi-node
# energy is recorded but efficiency is withheld rather than risk a wrong GFLOPS/W.
MULTINODE_ENERGY_VERIFIED = False

NUMERIC = {"nodes", "mpi_ranks", "omp_threads", "N", "NB", "P", "Q", "pfact", "rfact", "bcast",
           "depth", "nx", "ny", "nz", "hpcg_runtime_s", "runtime_s", "elapsed_s", "gflops", "energy_j",
           "energy_window_s", "avg_power_w", "gflops_per_w"}

_HPL_RESULT = re.compile(r"^W[RC]\S+\s+\d+\s+\d+\s+\d+\s+\d+\s+(\S+)\s+(\S+)\s*$", re.M)
_HPL_CHECK = re.compile(r"\|\|Ax-b\|\|_oo/.*?=\s*\S+\s*\.+\s*(PASSED|FAILED)")
_HPCG_FINAL = re.compile(r"HPCG result is (VALID|INVALID) with a GFLOP/s rating of=\s*([\d.eE+-]+)")
_HPCG_TIME = re.compile(r"Benchmark Time Summary::Total=\s*([\d.eE+-]+)")


def parse_hpl(text):
    """Standard HPL / MP-LINPACK stdout: the 'WR..' result line plus residual check line(s)."""
    m = _HPL_RESULT.search(text)
    if not m:
        return {"parse_status": "no_result_found", "validation": "unknown"}
    checks = _HPL_CHECK.findall(text)
    if not checks:
        validation = "unknown"
    else:
        validation = "FAILED" if "FAILED" in checks else "PASSED"
    return {"parse_status": "ok", "validation": validation,
            "runtime_s": float(m.group(1)), "gflops": float(m.group(2))}


def parse_hpcg(text):
    """HPCG 3.1 HPCG-Benchmark_*.txt: 'Section::Key=value' lines (same keys as the older YAML)."""
    m = _HPCG_FINAL.search(text)
    if not m:
        return {"parse_status": "no_result_found", "validation": "unknown"}
    out = {"parse_status": "ok", "validation": m.group(1), "gflops": float(m.group(2))}
    t = _HPCG_TIME.search(text)
    if t:
        out["runtime_s"] = float(t.group(1))
    return out


PARSERS = {"hpl": parse_hpl, "hpcg": parse_hpcg}


def parse_output(benchmark, text):
    if benchmark not in PARSERS:
        return {"parse_status": "unsupported", "validation": "unknown"}
    return PARSERS[benchmark](text)


def _slurm_seconds(s):
    """'[D-][[HH:]MM:]SS[.fff]' -> seconds. squeue/sacct drop leading zero fields ('59:12' is 59 min 12 s)."""
    days, _, rest = s.strip().rpartition("-")
    total = 0.0
    for part in rest.split(":"):
        total = total * 60 + float(part)
    return int(days or 0) * 86400 + total


def parse_sacct(text, job_id, min_window_s=0):
    """Parse `sacct -j ID -n -P --format=JobID,Elapsed,ConsumedEnergyRaw` into an energy dict.

    This covers the WHOLE job (including Slurm startup), so it is a cross-check, not the
    benchmark-window measurement. Energy 0/empty means not recorded -> status "missing".
    Slurm samples node power every few tens of seconds (Kelvin2: IPMI, 10-30 s), so a job shorter
    than `min_window_s` is "low_resolution": energy is kept but no efficiency is derived from it.
    """
    for line in text.splitlines():
        fields = line.strip().split("|")
        if fields[0] == str(job_id) and len(fields) >= 3 and fields[1] and fields[2]:
            energy = float(fields[2])
            if energy:
                window = _slurm_seconds(fields[1])
                return {"energy_j": energy, "energy_window_s": window, "energy_source": "sacct",
                        "energy_status": "ok" if window >= min_window_s else "low_resolution"}
    return {"energy_source": "sacct", "energy_status": "missing"}


def _read_counter(path):
    """'<joules> J <microseconds> us' -> (joules, seconds)."""
    f = path.read_text().split()
    return float(f[0]), float(f[2]) / 1e6


def read_pm_counters(run_dir, nodes):
    """Benchmark-window energy summed over ALL nodes, from the wrapper's counter snapshots.

    Needs one energy_start_<host>.txt / energy_end_<host>.txt pair per allocated node; any
    mismatch (missing node, counter going backwards) is reported as "inconsistent", not summed.
    """
    run_dir = Path(run_dir)
    starts = {p.stem[len("energy_start_"):]: p for p in run_dir.glob("energy_start_*.txt")}
    ends = {p.stem[len("energy_end_"):]: p for p in run_dir.glob("energy_end_*.txt")}
    if not starts and not ends:
        return {"energy_source": "pm_counters", "energy_status": "missing"}
    out = {"energy_source": "pm_counters", "energy_status": "inconsistent"}
    if starts.keys() != ends.keys() or len(starts) != nodes:
        return out
    total, windows = 0.0, []
    for host in starts:
        (e0, t0), (e1, t1) = _read_counter(starts[host]), _read_counter(ends[host])
        if e1 < e0 or t1 <= t0:
            return out
        total += e1 - e0
        windows.append(t1 - t0)
    out.update(energy_j=total, energy_window_s=sum(windows) / len(windows),
               energy_status="ok" if nodes == 1 or MULTINODE_ENERGY_VERIFIED else "unverified_multinode")
    return out


def manual_energy(energy_j, window_s):
    if energy_j and window_s:
        return {"energy_j": energy_j, "energy_window_s": window_s,
                "energy_source": "manual", "energy_status": "ok"}
    return {"energy_source": "manual", "energy_status": "missing"}


_MASK = re.compile(r"cpu-bind=\w+\s+-\s+\S+,\s+task\s+(\d+)\s+(\d+)\s+\[\d+\]:\s+mask\s+(0x[0-9a-fA-F]+)")


def check_binding(text, cores_per_node):
    """Per-task CPU masks from srun's --cpu-bind=verbose lines (in slurm-<id>.out).

    Logical CPU i and i + cores_per_node are SMT siblings (verified on Cirrus), so a task's
    physical cores are {cpu % cores_per_node}. Expect: cores per task == its core share,
    logical CPUs per task == cores (one thread per core) or 2x (siblings allowed but unused
    when OMP_PLACES=cores), and no core shared between tasks.
    """
    masks = {}
    for m in _MASK.finditer(text):
        mask = int(m.group(3), 16)
        masks[int(m.group(1))] = [i for i in range(mask.bit_length()) if mask >> i & 1]
    return summarise_binding(masks, cores_per_node)


def _cpu_list(text):
    """'0-3,8' -> {0,1,2,3,8}"""
    out = set()
    for part in text.split(","):
        lo, _, hi = part.partition("-")
        out.update(range(int(lo), int(hi or lo) + 1))
    return out


def check_binding_report(run_dir, cores_per_node):
    """Same summary as check_binding, from the bind_task_*.txt files the wrapper writes when the cluster's
    Slurm cannot bind tasks. Lines: 'task <rank> local <i> cpus <list>'."""
    cpus = {}
    for path in Path(run_dir).glob("bind_task_*.txt"):
        f = path.read_text().split()
        cpus[int(f[1])] = sorted(_cpu_list(f[5]))
    return summarise_binding(cpus, cores_per_node)


def summarise_binding(cpus, cores_per_node):
    cores = {t: sorted({c % cores_per_node for c in v}) for t, v in cpus.items()}
    used = [c for v in cores.values() for c in v]
    return {
        "tasks": len(cpus),
        "logical_cpus_per_task": sorted({len(v) for v in cpus.values()}),
        "cores_per_task": sorted({len(v) for v in cores.values()}),
        "cores_shared_between_tasks": len(used) - len(set(used)),
        "first_tasks_cores": {t: (v[0], v[-1]) for t, v in sorted(cores.items())[:4]},
    }


def check_threads(run_dir, comm):
    """Summarise thread_sample_{1,2}.txt (written by job.sh) for processes named `comm`.

    Answers "are the OpenMP threads really running?" two ways:
    - per LIVE thread (ps -L): threads that exist and used >= half a core between the snapshots. This
      undercounts when the BLAS library creates and destroys worker threads between snapshots (seen with
      MKL + libgomp on Kelvin2): exited threads disappear from the listing together with their CPU time.
    - per PROCESS (cumulative CPU seconds of the whole thread group, exited threads included): the CPU
      time each rank used / interval = how many cores it kept busy. This is the robust measure; summed
      over ranks it should approach the cores in use during DGEMM (lower in serial phases).
    Snapshots from older jobs have no PROCESS section; then only the per-thread part is returned.
    """
    def load(name):
        lines = (Path(run_dir) / name).read_text().splitlines()
        threads, procs, in_proc = {}, {}, False
        for line in lines[2:]:  # line 0: epoch seconds, line 1: ps header
            if line.strip() == "PROCESS":
                in_proc = True
                continue
            f = line.split()
            if in_proc:
                if len(f) >= 4 and f[3] == comm and f[0].isdigit():
                    procs[int(f[0])] = (int(f[1]), int(f[2]))  # (cpu seconds, thread count)
            elif len(f) >= 5 and f[4] == comm:
                threads[(int(f[0]), int(f[1]))] = (int(f[2]), int(f[3]))  # (core, cpu seconds)
        return int(lines[0]), threads, procs

    t1, a, pa = load("thread_sample_1.txt")
    t2, b, pb = load("thread_sample_2.txt")
    interval = t2 - t1
    busy = {k for k in b if k in a and b[k][1] - a[k][1] >= 0.5 * interval}
    ranks = sorted({pid for pid, _ in b})
    out = {
        "ranks": len(ranks),
        "threads_per_rank": sorted(sum(1 for p, _ in b if p == r) for r in ranks),
        "busy_live_threads_per_rank": sorted(sum(1 for p, _ in busy if p == r) for r in ranks),
        "distinct_cores_busy_live": len({b[k][0] for k in busy}),
        "interval_s": interval,
    }
    if pb:
        used = sorted((pb[r][0] - pa[r][0]) / interval for r in pb if r in pa)
        out.update(cores_busy_per_rank=[round(u, 1) for u in used], total_cores_busy=round(sum(used), 1))
    return out


def make_row(
    cfg,
    run_id,
    parsed,
    job_id=None,
    energy=None,
    raw_output='',
    provenance=None,
):
    """Combine config + parsed output + energy dict into one CSV row dict.

    avg_power_w = energy_j / energy_window_s (all nodes together); gflops_per_w = gflops /
    avg_power_w, only when energy_status == "ok". The window covers the whole benchmark process
    (setup + solve), while gflops covers only the timed phase, so short runs read a little low.
    """
    p = cfg.params
    energy = energy or {}
    provenance = provenance or {}

    row = {c: "" for c in COLUMNS}
    row.update(
        run_id=run_id,
        kind=cfg.kind,
        benchmark=cfg.benchmark,
        replicate=provenance.get('replicate', ''),
        build_id=provenance.get('build_id', ''),
        binary_path=provenance.get('binary_path', ''),
        binary_sha256=provenance.get('binary_sha256', ''),
        git_commit=provenance.get('git_commit', ''),
        nodes=cfg.nodes,
        mpi_ranks=cfg.mpi_ranks,
        omp_threads=cfg.threads,
        job_id=job_id or '',
        hpcg_runtime_s=p.get('runtime_s', '') if cfg.benchmark == 'hpcg' else '',
        raw_output=raw_output,
    )
    for k in ("N", "NB", "P", "Q", "pfact", "rfact", "bcast", "depth", "nx", "ny", "nz"):
        row[k] = p.get(k, "")
    row.update({k: v for k, v in parsed.items() if k in COLUMNS})
    row.update({k: v for k, v in energy.items() if k in COLUMNS})
    if row["energy_status"] == "ok":
        row["avg_power_w"] = row["energy_j"] / row["energy_window_s"]
        if row["gflops"] != "":
            row["gflops_per_w"] = row["gflops"] / row["avg_power_w"]
    return row


def append_row(path, row):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    if not new and path.read_text().split("\n", 1)[0].split(",") != COLUMNS:
        raise ValueError(f"{path} has a different column layout (older version?); start a new log file")
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerow(row)


def load_rows(path, benchmark=None):
    """Read the log back as dicts with numeric columns as floats ('' -> None).

    Nothing is filtered: select kind / validation / parse_status yourself.
    """
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in NUMERIC:
            r[k] = float(r[k]) if r.get(k, "") != "" else None   # tolerate logs written before a column existed
    return [r for r in rows if benchmark in (None, r.get("benchmark"))]


def parse_sacct_elapsed(text, job_id):
    """Whole-job wall time (s) from the same sacct output, or None."""
    for line in text.splitlines():
        f = line.strip().split("|")
        if f[0] == str(job_id) and len(f) >= 2 and f[1]:
            return _slurm_seconds(f[1])
    return None


def fetch_sacct(job_id):
    return subprocess.run(
        ["sacct", "-j", str(job_id), "-n", "-P", "--format=JobID,Elapsed,ConsumedEnergyRaw"],
        capture_output=True, text=True, check=True).stdout


def record_run(run_dir, job_id, log, sacct_text=None, min_window_s=0, manual=(None, None), elapsed_s=None):
    """Parse a finished run directory and append one row to the CSV log. Returns the row.

    Energy preference: node counters around the benchmark (if the job wrote them) > sacct (whole
    job; `sacct_text` from fetch_sacct) > manual (energy_j, window_s).
    """
    from .config import Config  # local import: config does not depend on results
    provenance_path = run_dir / 'provenance.json'
    provenance = (
        json.loads(provenance_path.read_text())
        if provenance_path.exists()
        else {}
    )
    run_dir = Path(os.path.abspath(run_dir))
    cfg = Config(**json.loads((run_dir / "config.json").read_text()))
    raw = run_dir / f"slurm-{job_id}.out"
    if cfg.benchmark == "hpcg":  # HPCG 3.1 writes HPCG-Benchmark_*.txt (key-value; was YAML pre-3.1)
        summaries = sorted(run_dir.glob("HPCG-Benchmark*"))
        raw = summaries[-1] if summaries else raw
    parsed = (parse_output(cfg.benchmark, raw.read_text()) if raw.exists()
              else {"parse_status": "no_output", "validation": "unknown"})
    sacct = parse_sacct(sacct_text, job_id, min_window_s) if sacct_text else None
    energy = read_pm_counters(run_dir, cfg.nodes)
    if energy["energy_status"] == "missing":
        energy = sacct or manual_energy(*manual)
    elif sacct and sacct["energy_status"] == "ok" and "energy_j" in energy:
        print(f"cross-check: counters {energy['energy_j']:.0f} J over benchmark window, "
              f"sacct {sacct['energy_j']:.0f} J over whole job")
    row = make_row(
        cfg,
        run_dir.name,
        parsed,
        str(job_id),
        energy,
        str(raw),
        provenance,
    )
    elapsed = parse_sacct_elapsed(sacct_text, job_id) if sacct_text else elapsed_s
    row["elapsed_s"] = elapsed if elapsed is not None else ""     # compute cost of this evaluation
    append_row(log, row)
    return row
