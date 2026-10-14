"""Configuration representation and validation."""
import tomllib
from dataclasses import dataclass, field

BENCHMARKS = ("hpl", "hpcg")
KINDS = ("diagnostic", "final")
HPCG_FINAL_MIN_RUNTIME_S = 1800

# HPL.dat knobs that are tunable but have a fixed default if not given.
HPL_DEFAULTS = {
    'pfact': 2,
    'rfact': 2,
    'bcast': 1,
    'depth': 0,
}


@dataclass
class Hardware:
    """Physical cores only (SMT siblings are never used). Topology levels nest:
    cores_per_node = sockets x cores_per_socket; NUMA domains and L3 groups tile the node."""
    cores_per_node: int
    sockets_per_node: int
    numa_per_node: int
    l3_per_node: int
    mem_mib_per_node: int  # memory Slurm will schedule (scontrol RealMemory), not nominal RAM
    max_mem_fraction: float = 0.85  # HPL matrix may use at most this share of that memory

    @property
    def cores_per_socket(self):
        return self.cores_per_node // self.sockets_per_node

    @property
    def cores_per_numa(self):
        return self.cores_per_node // self.numa_per_node

    @property
    def cores_per_l3(self):
        return self.cores_per_node // self.l3_per_node

    @property
    def mem_bytes(self):
        return self.mem_mib_per_node * 2**20


@dataclass
class Config:
    benchmark: str  # "hpl" or "hpcg"
    nodes: int
    ranks_per_node: int
    threads: int  # OpenMP threads per rank; each rank owns (cores_per_node / ranks_per_node)
    #               cores, so threads < that share means an under-populated layout
    # hpl:  N, NB, P, Q (+ optional pfact, rfact, bcast, depth)
    # hpcg: nx, ny, nz (per-rank local grid), runtime_s
    params: dict = field(default_factory=dict)
    kind: str = "diagnostic"  # "diagnostic" (short, exploratory) or "final"

    @property
    def mpi_ranks(self):
        return self.nodes * self.ranks_per_node


def validate(cfg, hw):
    """Return a list of problems; an empty list means the config is valid."""
    errors = []
    if cfg.benchmark not in BENCHMARKS:
        return [f"unknown benchmark {cfg.benchmark!r}"]
    if cfg.kind not in KINDS:
        errors.append(f"kind must be one of {KINDS}")
    if cfg.nodes < 1 or cfg.ranks_per_node < 1 or cfg.threads < 1:
        errors.append("nodes, ranks_per_node and threads must be >= 1")
    elif hw.cores_per_node % cfg.ranks_per_node:
        errors.append(f"ranks_per_node must divide {hw.cores_per_node} cores (each rank gets an equal core share)")
    elif cfg.threads > hw.cores_per_node // cfg.ranks_per_node:
        errors.append(
            f"{cfg.threads} threads exceed the {hw.cores_per_node // cfg.ranks_per_node}-core "
            f"share of each of {cfg.ranks_per_node} ranks per node"
        )

    p = cfg.params
    required = ("N", "NB", "P", "Q") if cfg.benchmark == "hpl" else ("nx", "ny", "nz", "runtime_s")
    missing = [k for k in required if k not in p]
    if missing:
        return errors + [f"missing params: {missing}"]

    if cfg.benchmark == "hpl":
        if p["N"] < 1 or p["NB"] < 1 or p["N"] % p["NB"] != 0:
            errors.append("N and NB must be positive and N must be a multiple of NB")
        if p["P"] * p["Q"] != cfg.mpi_ranks:
            errors.append(f"P*Q = {p['P'] * p['Q']} but MPI ranks = {cfg.mpi_ranks}")
        matrix_bytes = 8 * p["N"] ** 2
        limit_bytes = hw.max_mem_fraction * cfg.nodes * hw.mem_bytes
        if matrix_bytes > limit_bytes:
            errors.append(f"matrix needs {matrix_bytes / 1e9:.0f} GB, limit is {limit_bytes / 1e9:.0f} GB")
    else:
        for k in ("nx", "ny", "nz"):
            if p[k] < 8 or p[k] % 8 != 0:
                errors.append(f"{k} must be a positive multiple of 8")
        if p["runtime_s"] <= 0:
            errors.append("runtime_s must be > 0")
        if cfg.kind == "final" and p["runtime_s"] < HPCG_FINAL_MIN_RUNTIME_S:
            errors.append(f"final HPCG runs need runtime_s >= {HPCG_FINAL_MIN_RUNTIME_S}")
    return errors


def load_settings(path):
    """Read a settings TOML file (see clusters/*.toml). Returns (settings dict, Hardware)."""
    with open(path, "rb") as f:
        settings = tomllib.load(f)
    return settings, Hardware(**settings["hardware"])


def apply_overrides(settings, assignments):
    """Apply 'a.b.c=<toml value>' strings (e.g. 'hpl.n=[80640]', 'slurm.walltime_s=600') to the settings dict,
    so one cluster file can serve several experiment stages without editing it."""
    for item in assignments or []:
        key, _, raw = item.partition("=")
        node = settings
        *path, leaf = key.strip().split(".")
        for part in path:
            node = node.setdefault(part, {})
        node[leaf] = tomllib.loads(f"v = {raw}")["v"]
    return settings
