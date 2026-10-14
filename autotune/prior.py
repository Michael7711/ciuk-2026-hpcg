"""Hardware-informed prior over configurations: a deterministic ranking from topology and HPL practice only.

FROZEN on 2026-10-13, before any measurement at the larger problem sizes (see docs/PREREGISTRATION_large_n.md).
It uses no measurements. Rules, most important first (lexicographic):

1. Layout: threads per rank closest to the cores of one L3 group
   (|log2(threads / cores_per_l3)|).

   Cirrus AMD EPYC 9825: each 12-core CCD shares 32 MB L3.
   A 12-thread rank can therefore occupy one CCD cleanly.
2. Block size NB: closest, in log scale, to 256. Why: DGEMM efficiency rises with NB (higher flops per byte) while
   panel factorisation, broadcast latency and load imbalance grow with it; published HPL guidance for AVX2/AVX-512
   BLAS libraries centres on a few hundred (AMD EPYC 9004 guide: 384). 256 is the geometric middle of 128-512.
   [folklore prior, weakest rule]
3. Process grid: squarest P x Q (|ln(Q/P)| smallest). Why: panel broadcast volume across process rows/columns is
   minimised when P ~ Q (HPL prefers P <= Q).
4. Ties: more ranks first (fewer threads), then smaller P. Only there so the order never depends on list order.

prior_init() gives a deliberately diverse start for a model: the prior-best configuration of every layout class
(so the GP sees layout contrast), then the next prior-best overall.
"""
import math

NB_CENTRE = 256


def prior_key(cfg, hw):
    p = cfg.params
    return (abs(math.log2(cfg.threads / hw.cores_per_l3)),
            abs(math.log2(p["NB"] / NB_CENTRE)),
            abs(math.log(p["Q"] / p["P"])),
            cfg.threads,
            p["P"])


def prior_order(cfgs, hw):
    """All candidates, best prior first."""
    return sorted(cfgs, key=lambda c: prior_key(c, hw))


def prior_init(cfgs, hw, n=6):
    """n configurations: prior-best of each layout class (classes ordered by their prior key), then fill with
    the next prior-best overall."""
    order = prior_order(cfgs, hw)
    best_per_layout = {}
    for c in order:
        best_per_layout.setdefault((c.ranks_per_node, c.threads), c)
    chosen = list(best_per_layout.values())[:n]
    for c in order:
        if len(chosen) >= n:
            break
        if c not in chosen:
            chosen.append(c)
    return chosen
