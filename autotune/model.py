"""Surrogate model (Gaussian process) and candidate selection.

Data flow (this is what `python -m autotune suggest` does):

    rows  = results.load_rows("results/experiments.csv", "hpl")   # history
    cands = candidates.generate(...)                              # discrete valid candidates
    new   = suggest(rows, cands, n=4)                             # -> jobs.prepare_run(...)

One model per benchmark (never mix HPL and HPCG rows). Everything is modelled on the log
scale, because configuration effects on GFLOPS are roughly multiplicative.
"""
import copy
import math
import random

import numpy as np

from .config import HPL_DEFAULTS, Config


# ---------- history rows -> Configs -> numeric features ----------

def row_to_config(row):
    """Rebuild the Config that produced a CSV row (see results.COLUMNS)."""
    nodes = int(row["nodes"])
    if row["benchmark"] == "hpl":
        params = {k: int(row[k]) if row[k] is not None else HPL_DEFAULTS.get(k)
                  for k in ("N", "NB", "P", "Q", *HPL_DEFAULTS)}
    else:
        params = {k: int(row[k]) for k in ("nx", "ny", "nz")}
        params["runtime_s"] = int(row["hpcg_runtime_s"])
    return Config(row["benchmark"], nodes, int(row["mpi_ranks"]) // nodes,
                  int(row["omp_threads"]), params, row["kind"])

def config_key(cfg):
    """Benchmark configuration identity, ignoring experiment kind/replicate."""
    return (
        cfg.benchmark,
        cfg.nodes,
        cfg.ranks_per_node,
        cfg.threads,
        tuple(sorted(cfg.params.items())),
    )

def features(cfg):
    """Config -> numeric vector. Edit freely: this is the main modelling decision.

    Layout terms are log2 (halving threads matters as much at 4 as at 64). HPCG's
    runtime_s is deliberately not a feature: it sets how long we measure, not how fast it is.
    """
    p = cfg.params
    f = [math.log2(cfg.nodes), math.log2(cfg.ranks_per_node), math.log2(cfg.threads)]
    if cfg.benchmark == "hpl":
        f += [math.log(p["N"]), p["NB"], math.log(p["Q"] / p["P"])]
        f += [p.get(k, v) for k, v in HPL_DEFAULTS.items()]
    else:
        f += [math.log(p["nx"] * p["ny"] * p["nz"])]
    return f


def training_rows(rows, target):
    """Rows usable for fitting `target`: parsed OK, target present, result not invalid.

    HPL must be PASSED. HPCG 'final' rows must be VALID; short HPCG 'diagnostic' rows are
    kept even if the benchmark flags them INVALID (assumed to be due to the short runtime;
    check this against real output).
    """
    keep = []
    for r in rows:
        if r["parse_status"] != "ok" or r.get(target) is None:
            continue
        if r["benchmark"] == "hpl" and r["validation"] != "PASSED":
            continue
        if r["benchmark"] == "hpcg" and r["kind"] == "final" and r["validation"] != "VALID":
            continue
        keep.append(r)
    return keep

def unique_training_config_count(rows, target):
    """Number of distinct usable benchmark configurations.

    Repeat measurements remain separate rows for GP fitting, but count as one
    configuration when deciding whether the initial design is complete.
    """
    return len({
        config_key(row_to_config(r))
        for r in training_rows(rows, target)
    })

# ---------- Gaussian process ----------

def _kernel(A, B, length_scale, kind):
    d = np.sqrt(((A[:, None, :] - B[None, :, :]) ** 2).sum(-1)) / length_scale
    if kind == "m32":
        s = math.sqrt(3) * d
        return (1 + s) * np.exp(-s)
    s = math.sqrt(5) * d
    return (1 + s + s * s / 3) * np.exp(-s)


class Surrogate:
    """GP regression on log(target) with one shared length scale.

    Choices (each justified on held-out data in experiments/gp_calibration.py, small-N Kelvin2 table):
    - kind "m32" (Matern-3/2): HPL performance has cliffs (bad layouts are 10x slower); smoother kernels
      (Matern-5/2, RBF) were MORE over-confident on held-out configs.
    - amps: the signal variance is fitted over a grid instead of being fixed to 1 (lower predictive NLPD).
    - noise_sd: measurement noise sd on the log scale (repeat runs of the same config: ~0.018 on Kelvin2).
      It is fixed to that measured value, not fitted: with ~10 points the likelihood cannot identify it and
      pushed it to the grid floor, which made the model over-confident. noise_sd=None restores the old
      behaviour (noise chosen from a grid), and kind="m52", amps=(1.0,) the old kernel.
    The length scale is chosen by maximising the marginal likelihood over a small grid.
    """
    AMPS = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)

    def __init__(self, kind="m32", amps=AMPS, noise_sd=0.02):
        self.kind, self.amps, self.noise_sd = kind, amps, noise_sd

    def fit(self, rows, target):
        rows = training_rows(rows, target)
        if len(rows) < 2:
            raise ValueError(f"need >= 2 usable rows to fit {target!r}, got {len(rows)}")
        F = np.array([features(row_to_config(r)) for r in rows], dtype=float)
        self.f_mean, self.f_std = F.mean(0), F.std(0)
        self.f_std[self.f_std == 0] = 1.0  # constant feature: contributes nothing
        self.X = (F - self.f_mean) / self.f_std
        y = np.log([r[target] for r in rows])
        self.y_mean, self.y_std = y.mean(), y.std() or 1.0
        self.z = (y - self.y_mean) / self.y_std

        noises = (1e-4, 1e-2, 1e-1) if self.noise_sd is None else ((self.noise_sd / self.y_std) ** 2,)
        best = None
        for ls in (0.5, 1, 2, 4, 8, 16):
            for amp in self.amps:
                for noise in noises:
                    self.ls, self.amp, self.noise = ls, amp, noise
                    self._factor()
                    ll = (-0.5 * self.z @ self.alpha - np.log(np.diag(self.L)).sum()
                          - 0.5 * len(self.z) * math.log(2 * math.pi))
                    if best is None or ll > best[0]:
                        best = (ll, ls, amp, noise)
        _, self.ls, self.amp, self.noise = best
        self._factor()
        return self

    def _factor(self):
        K = self.amp * _kernel(self.X, self.X, self.ls, self.kind) + (self.noise + 1e-8) * np.eye(len(self.X))
        self.L = np.linalg.cholesky(K)
        self.alpha = np.linalg.solve(self.L.T, np.linalg.solve(self.L, self.z))

    def predict(self, configs):
        """(mean, std) arrays on the log(target) scale; exp(mean) is the typical value."""
        X = (np.array([features(c) for c in configs], dtype=float) - self.f_mean) / self.f_std
        Ks = self.amp * _kernel(X, self.X, self.ls, self.kind)
        mean_z = Ks @ self.alpha
        v = np.linalg.solve(self.L, Ks.T)
        var_z = np.maximum(self.amp - (v ** 2).sum(0), 0.0)   # latent function; add self.noise for a new measurement
        return self.y_mean + self.y_std * mean_z, self.y_std * np.sqrt(var_z)

    def believe(self, config, log_value):
        """Copy of this model with a pretend observation added (same hyperparameters)."""
        m = copy.copy(self)
        x = (np.array(features(config), dtype=float) - self.f_mean) / self.f_std
        m.X = np.vstack([self.X, x])
        m.z = np.append(self.z, (log_value - self.y_mean) / self.y_std)
        m._factor()
        return m


# ---------- selection ----------

def select(configs, models, weights, n, beta=2.0):
    """Choose n configs by maximising an upper confidence bound.

    score = sum_t weights[t] * (mean_t + beta * std_t), all in log units, so it is a weighted
    geometric mean of optimistic GFLOPS (and GFLOPS/W). beta controls exploration: 0 trusts the
    model, larger values favour uncertain regions. For a batch we use the "kriging believer":
    after each pick the model pretends the prediction was observed, which lowers uncertainty
    around it and pushes the next pick elsewhere.
    """
    pool, chosen = list(configs), []
    for _ in range(min(n, len(pool))):
        score, means = np.zeros(len(pool)), {}
        for t, m in models.items():
            means[t], std = m.predict(pool)
            score += weights[t] * (means[t] + beta * std)
        i = int(score.argmax())
        c = pool.pop(i)
        chosen.append(c)
        models = {t: m.believe(c, means[t][i]) for t, m in models.items()}
    return chosen


def suggest(rows, configs, n, efficiency_weight=0.0, beta=2.0, min_rows=6, seed=0, noise_sd=0.02, make_model=None):
    """Next experiments to run. Returns [(Config, explanation string)].

    With fewer than `min_rows` unique usable configurations there is nothing to model, so it falls back
    to a seeded random initial design. efficiency_weight > 0 adds gflops_per_w (needs energy
    data in the log) to the objective with that weight relative to gflops (weight 1).
    """
    if unique_training_config_count(rows, 'gflops') < min_rows:
        return [(c, "initial design (not enough data to model)")
                for c in random.Random(seed).sample(configs, min(n, len(configs)))]
    weights = {"gflops": 1.0}
    if efficiency_weight > 0:
        weights["gflops_per_w"] = efficiency_weight
    make = make_model or (lambda: Surrogate(noise_sd=noise_sd))
    models = {t: make().fit(rows, t) for t in weights}
    chosen = select(configs, models, weights, n, beta)
    out = []
    for c in chosen:
        parts = []
        for t, m in models.items():
            mean, std = (a[0] for a in m.predict([c]))
            parts.append(f"{t} ~{math.exp(mean):.4g} (log-std {std:.2f})")
        out.append((c, ", ".join(parts)))
    return out
