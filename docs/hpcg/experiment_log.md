# CIUK Cluster Challenge 2026 – HPCG Benchmark

This log separates completed diagnostics, current optimisation work and planned final benchmarking. A numerically `VALID` HPCG result is not automatically an official competition result: the reported duration and memory requirements must also be met.

## HPCG Benchmark: 14OCT2026

### Initial setup

HPCG version: 3.1

System: Cirrus, EPCC

Compiler optimisation flags:
-O3 -ffast-math -fopenmp

Two GCC-specific vectorisation flags were removed during compilation
because they were not supported by the active compiler.

### Initial smoke test

Configuration:
- Nodes: 1
- MPI ranks: 2
- OpenMP threads per rank: 1
- Local dimensions: 16 x 16 x 16
- Global dimensions: 32 x 16 x 16
- Total equations: 8192
- Requested benchmark duration: 60 seconds

Results:
- Slurm job ID: 558111
- Job status: COMPLETED
- Job elapsed time: 63 seconds
- HPCG benchmark time: 58.7928 seconds
- Performance: 8.11988 GFLOP/s
- Reported data memory: 0.00589974 GB

Validation:
- Spectral convergence: PASSED
- Symmetry: PASSED
- Iteration count: PASSED
- Reproducibility: PASSED
- HPCG numerical result: VALID

### Interpretation

The initial smoke test confirmed that HPCG could be compiled and
executed successfully through Slurm on Cirrus.

However, this was not an official HPCG benchmark result.

The execution time was below the required 1800 seconds, and the
problem size was much too small for representative full-node testing.

The next objective is to establish a reproducible benchmarking
pipeline using the team's existing autotuning framework.

### Next experiment at the time

Validate that the autotuner can generate and execute an HPCG Slurm
job and correctly record performance, runtime and energy consumption.

## Experiment 2: Automated HPCG Pipeline Validation

Date: 14 October 2026

### Objective

To verify that the team's existing autotuning framework can generate
and successfully execute an HPCG benchmark on Cirrus.

### Configuration

- Slurm job ID: 558365
- Compute nodes: 1
- MPI ranks: 288
- OpenMP threads per rank: 1
- Local dimensions: 16 x 16 x 16
- Requested benchmark duration: 60 seconds
- Exclusive node allocation: Enabled

### Results

- Slurm status: COMPLETED
- Job elapsed time: 75 seconds
- HPCG benchmark time: 57.5469 seconds
- HPCG performance: 546.025 GFLOP/s
- HPCG numerical result: VALID
- Slurm whole-job energy: 61830 J

### Observations

The automation successfully generated and executed an HPCG benchmark.

Compared with the initial two-rank smoke test, performance increased
substantially. However, the total problem size also increased, so this
is not a controlled strong-scaling comparison.

The local problem size is deliberately small and does not represent
the memory-intensive workload expected in official HPCG benchmarking.

The execution time also falls below the official 1800-second requirement.

Energy measurements were available through Slurm, but the reported
energy covers the whole job rather than exactly the HPCG benchmark
interval. Energy-efficiency comparisons therefore remain provisional.

### Conclusion

The job-generation and execution stages of the HPCG automation
pipeline have been validated successfully.

The next stage is to verify automatic CSV result collection, then
establish a representative full-node benchmark configuration.

## Experiment 3: MPI/OpenMP Comparison

Date: 14–15 October 2026

### Objective

Compare pure MPI and hybrid MPI/OpenMP configurations on one Cirrus node.

The local grid sizes were adjusted to keep the total problem size
roughly the same across the runs.

### Results

All runs used 288 physical cores and a requested runtime of 60 seconds.

| MPI ranks | OpenMP threads | Local grid | GFLOP/s | Job ID |
|---|---|---|---|---|
| 288 | 1 | 64x64x64 | 135.996 | 558489 |
| 144 | 2 | 80x80x80 | 136.042 | 558502 |
| 72 | 4 | 96x104x104 | 132.809 | 558503 |
| 48 | 6 | 112x112x128 | 131.060 | 558506 |
| 24 | 12 | 144x144x152 | 105.580 | 558512 |

All configurations passed HPCG numerical validation.

### Observations

The pure MPI and two-thread configurations performed almost identically.

Performance dropped slightly with four and six threads, while the
12-thread configuration was noticeably slower.

The OpenMP check confirmed that the four-thread configuration was
using all 288 physical cores, with no overlapping CPU assignments.
Average utilisation during the sampled interval was 274.9 cores.

The 288-rank configuration used 54.0342 GB of HPCG data memory.

These were short diagnostic runs, so the differences should not be
treated as conclusive. The problem sizes were also not exactly equal.

### Follow-up at the time

Repeat the comparison using a larger problem size that meets the
official memory requirement.

Test multi-node scaling and run the strongest configurations for
the required 1800 seconds.

## Experiment 4: Larger CCE Reference Problem — completed

Date: 15 October 2026

The small problems above verified the pipeline, but did not provide a representative memory workload. The next reference used 288 MPI ranks, one OpenMP thread per rank and a local grid of 104 × 104 × 104 on one node: **323960832 equations** in total.

| Setting or result | Recorded value |
|---|---|
| Slurm job | 558521 — COMPLETED |
| HPCG/compiler | HPCG 3.1, CCE 19 reference |
| Flags | `-O3 -ffast-math -fopenmp` |
| Requested benchmark duration | 120 s |
| Reported benchmark time | 134.952 s |
| Whole-job elapsed time | 262 s |
| GFLOP/s | 134.124 |
| Reported data memory | 231.733 GB |
| HPCG numerical result | VALID |
| Slurm whole-job energy | 273150 J |

The result is a larger diagnostic baseline, **not an official result**: its reported benchmark time is below 1800 seconds. Its lower rating than the tiny-grid pipeline test does not imply a regression; the workloads are very different.

Evidence is under `/epccfs/tc079/tc079/shared/hpcg/runs/tc079cheu1/autotune_runs/hpcg-diagnostic-n1-288x1-2ca4861f/`, including `config.json`, the HPCG summary and `slurm-558521.out`.

## Experiment 5: Autonomous Controller and Job Chaining — completed

Date: 15 October 2026

All **41 automated tests passed on Cirrus**. A separate two-run campaign then tested the real Slurm path: create a benchmark allocation, validate and record its result, submit the next job, and stop when the configured trial limit is reached.

Both runs used one exclusive node, CCE 19 reference, **288 MPI ranks × 1 thread**, a **16 × 16 × 16 local grid**, and a requested benchmark duration of **10 seconds**. This gives 1179648 equations and approximately 0.848223 GB of reported data memory across the job.

| Job | Reported benchmark time (s) | GFLOP/s | Whole-job elapsed (s) | Whole-job energy (J) | Validation |
|---|---:|---:|---:|---:|---|
| 558642 | 9.56027 | 540.266 | 30 | 15562 | VALID; four V&V checks PASSED |
| 558643 | 9.61757 | 545.903 | 29 | 15544 | VALID; four V&V checks PASSED |

Slurm reports both jobs as `COMPLETED`. The output of job **558642** records submission of **558643**; the second job records `stopped: max_trials`. The ledger retains **19.2 reserved core-hours** against a **20-core-hour cap**, even though actual elapsed time was much shorter. Reservations deliberately use full allocation time rather than refunding time after each result.

Evidence: `/epccfs/tc079/tc079/shared/hpcg/runs/tc079cheu1/campaign-chain-01/`. Its `state.json`, two `slurm-*.out` files and `runs/` directories retain the decisions, repeat numbers, raw HPCG output and validation results.

These runs establish that automatic chaining works. Their small memory footprint and roughly ten-second solve windows make them unsuitable for final performance or energy-efficiency comparisons.

## Experiment 6: Alternative Compiler Builds — completed

Date: 15 October 2026

Each compiler campaign built a separate executable and ran one numerical validation test on one exclusive node. All three used **144 MPI ranks × 2 OpenMP threads**, a **16 × 16 × 16 local grid**, and **10 requested benchmark seconds**: 589824 equations per job. Slurm reports every job as `COMPLETED`.

| Compiler/build | Job | Flags | Benchmark time (s) | GFLOP/s | Data memory (GB) | Validation |
|---|---|---|---:|---:|---:|---|
| GCC 14.2.1 / `gnu14-fast` | 558644 | `-O3 -ffast-math -fopenmp` | 9.72941 | 338.679 | 0.424116 | VALID; four V&V checks PASSED |
| AOCC 5 / `aocc5-fast` | 558647 | `-O3 -ffast-math -fopenmp` | 9.79473 | 305.642 | 0.424115 | VALID; four V&V checks PASSED |
| CCE 19 / `cce19-strict` | 558649 | `-O3 -fopenmp` | 10.2012 | 278.527 | 0.424115 | VALID; four V&V checks PASSED |

AOCC 5 reports a clang 17.0.6 compiler front end. “Strict” here identifies the CCE recipe without `-ffast-math`; it does not assert that every floating-point optimisation is disabled. Builds use the Cray `CC` MPI wrapper and Cray MPICH 8.1.32.

| Job | Whole-job elapsed (s) | Slurm whole-job energy (J) | Campaign directory |
|---|---:|---:|---|
| 558644 | 26 | 15015 | `campaign-gnu-01` |
| 558647 | 48 | 21286 | `campaign-aocc-01` |
| 558649 | 28 | 15501 | `campaign-cce-strict-01` |

Campaign directories are under `/epccfs/tc079/tc079/shared/hpcg/runs/tc079cheu1/`. Each contains its `state.json`, compiler build directory and per-run records. Verified records include `build.json`, `provenance.json`, `compiler.txt`, the executable SHA-256, recipe flags, loaded-module information and the raw HPCG summary. Some records use the equivalent resolved `/mnt/nfs/epccfs/projects/...` path.

Each one-job compiler campaign stopped at `max_trials`, retaining **57.6 reserved core-hours** against its **60-core-hour cap**. These reservations include the possible compile time; they are not measured execution costs.

The runs confirm that the alternative builds compile and pass HPCG's numerical checks. They do **not** establish GCC as the best compiler for the real workload. These are single, tiny-problem diagnostics. The earlier 288-rank reference smoke tests also have twice as many equations, so they are not matching compiler comparisons.

## Current Work: Unattended Overnight Optimisation

The working controller allows us to run a sequence of diagnostic experiments without keeping a login-node process or manually submitting every job. The current strategy is to screen compiler choices under matching conditions, then use measured performance to guide nearby MPI/OpenMP and CPU-utilisation experiments. Repeated measurements help assess noise before treating a small difference as an improvement.

Representative problem sizes are important: the 231.733 GB reference is a more useful starting point than the sub-gigabyte smoke tests. CPU-layout comparisons should keep total equation counts approximately comparable. Each build remains separately identified, and node counts are evaluated independently rather than assuming the one-node optimum transfers to four nodes.

The overnight search is intended to optimise **performance** first. Each pending or running allocation is already reserved against the fixed campaign cap. The controller selects, executes, validates and records each experiment before admitting a successor, and stops at its limits or on a critical failure. The campaign cap is distinct from the team's shared SAFE balance.

At the read-only documentation check on **15 October 2026, approximately 02:27 BST**, the submitting user's Slurm queue was empty. The inspected directory contained the completed canary ledgers, but no verified overnight campaign ledger or settings. The overnight campaign's actual configuration and job ID are therefore **not recorded yet**, and the optimisation is **not described as completed**. This section records the strategy, not a claim that an overnight run is active.

### Why use short diagnostic runs first?

Full 30-minute benchmarks are expensive, especially across several nodes and compiler/layout combinations. Short diagnostics let us reject poor configurations, confirm numerical correctness and focus repeat measurements on promising candidates before spending the final-run budget. They also expose setup, compiler and controller problems cheaply. They cannot replace a long benchmark or establish final energy efficiency.

## Planned Experiments and Competition Results

- Repeat promising configurations on representative memory workloads and check whether observed performance differences persist.
- Measure scaling from one to four nodes, keeping strong- and weak-scaling comparisons clearly identified and recording the best configuration at each size.
- Run selected configurations for at least **1800 reported benchmark seconds**, with the required memory footprint, for official competition measurements.
- Verify benchmark-window energy measurement and multi-node coverage before reporting benchmark GFLOP/s/W.
- Assemble the final scripts, results, budget accounting and presentation material from the recorded evidence.

**No official 30-minute competition result is recorded in this log yet.** All measurements above are diagnostic.

### Energy interpretation

The energy values above are Slurm **whole-job** readings. They can include compilation, module loading, setup, teardown and controller work, as well as the timed benchmark. They are not necessarily equal to benchmark-window energy and are not converted into HPCG GFLOP/s/W here. The campaign results currently record benchmark-window energy as unavailable. A future energy comparison must state the measurement scope and account for every participating node.
