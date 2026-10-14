"""Generate hardware-valid candidate configurations."""
import itertools
import math
import random

from .config import HPL_DEFAULTS, Config, validate


def aligned(share, unit):
    """A core share is aligned with a topology unit if it fits inside it or is whole units."""
    return unit % share == 0 or share % unit == 0


def rank_layouts(hw, fills=(1.0,)):
    """(ranks_per_node, threads) layouts that respect the topology.

    Each rank owns an equal share of cores; the share must align with the L3 groups, NUMA
    domains and sockets (so no rank straddles a boundary unless it covers whole units).
    `fills` < 1 under-populates: only fill*share threads run per rank (e.g. to save energy
    or memory bandwidth contention); the other cores of the share stay idle.
    """
    layouts = []
    for share in range(1, hw.cores_per_node + 1):
        if hw.cores_per_node % share or not all(
            aligned(share, u) for u in (hw.cores_per_l3, hw.cores_per_numa, hw.cores_per_socket)
        ):
            continue
        for f in fills:
            threads = share * f
            if threads >= 1 and abs(threads - round(threads)) < 1e-9:
                layouts.append((hw.cores_per_node // share, round(threads)))
    return layouts


def pq_pairs(ranks, max_ratio):
    """Process grids P x Q = ranks with P <= Q <= max_ratio * P."""
    return [
        (p, ranks // p)
        for p in range(1, math.isqrt(ranks) + 1)
        if ranks % p == 0 and ranks // p <= max_ratio * p
    ]


def generate(benchmark, hw, nodes, space, kind="diagnostic"):
    """All valid configs for `nodes` nodes. `space` is the [hpl] / [hpcg] settings table."""
    configs = []
    allowed_threads = space.get("threads")  # optional whitelist, e.g. [1, 2, 4, 8, 16]: no rank spans a NUMA domain
    for rpn, threads in rank_layouts(hw, space.get("fill", [1.0])):
        if allowed_threads and threads not in allowed_threads:
            continue
        ranks = nodes * rpn
        if benchmark == "hpl":
            extras = [space.get(k, [v]) for k, v in HPL_DEFAULTS.items()]
            sizes = space["n"] if "n" in space else space["mem_fraction"]   # explicit N, or N from a memory fraction
            for (p, q), nb, size, extra in itertools.product(
                pq_pairs(ranks, space.get("max_pq_ratio", 4)),
                space["nb"],
                sizes,
                itertools.product(*extras),
            ):
                n_val = size if "n" in space else int(math.sqrt(size * nodes * hw.mem_bytes / 8) // nb) * nb
                params = {"N": n_val, "NB": nb, "P": p, "Q": q}
                params.update(zip(HPL_DEFAULTS, extra))
                configs.append(Config("hpl", nodes, rpn, threads, params, kind))
        elif benchmark == "hpcg":
            for (nx, ny, nz), runtime_s in itertools.product(space["local_dims"], space["runtime_s"]):
                params = {"nx": nx, "ny": ny, "nz": nz, "runtime_s": runtime_s}
                configs.append(Config("hpcg", nodes, rpn, threads, params, kind))
        else:
            raise ValueError(f"unknown benchmark {benchmark!r}")
    configs = [c for c in configs if not validate(c, hw)]
    return subset(configs, space) if "subset_size" in space else configs


def subset(configs, space):
    """A seeded random subset of the candidate space, for tables too expensive to measure exhaustively.

    Uses no measurements, so it is neutral to every search method. `subset_include` lists "RANKSxTHREADS/NB"
    selectors (e.g. "32x4/256") whose configurations (all their grids) are forced in, so a reference candidate is
    always present; the rest are drawn uniformly (`subset_seed`) up to `subset_size`."""
    must = set(space.get("subset_include", []))
    forced = [c for c in configs if f"{c.ranks_per_node}x{c.threads}/{c.params.get('NB')}" in must]
    rest = [c for c in configs if c not in forced]
    k = max(space["subset_size"] - len(forced), 0)
    chosen = forced + random.Random(space.get("subset_seed", 0)).sample(rest, min(k, len(rest)))
    return [c for c in configs if c in chosen]               # keep the generator's order


def sample(configs, n, seed=0):
    """Reproducible random subset; handy for the first batch before any model exists."""
    return random.Random(seed).sample(configs, min(n, len(configs)))
