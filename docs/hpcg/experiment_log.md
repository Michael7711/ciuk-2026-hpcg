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

## Preparation Before the Overnight Campaign

The working controller allows us to run a sequence of diagnostic experiments without keeping a login-node process or manually submitting every job. The planned strategy was to screen compiler choices under matching conditions, then use measured performance to guide nearby MPI/OpenMP and CPU-utilisation experiments. Repeated measurements help assess noise before treating a small difference as an improvement.

Representative problem sizes are important: the 231.733 GB reference is a more useful starting point than the sub-gigabyte smoke tests. CPU-layout comparisons should keep total equation counts approximately comparable. Each build remains separately identified, and node counts are evaluated independently rather than assuming the one-node optimum transfers to four nodes.

The planned overnight search focused on **performance** first. Each pending or running allocation is already reserved against the fixed campaign cap. The controller selects, executes, validates and records each experiment before admitting a successor, and stops at its limits or on a critical failure. The campaign cap is distinct from the team's shared SAFE balance.

At the read-only documentation check on **15 October 2026, approximately 02:27 BST**, the submitting user's Slurm queue was empty. The inspected directory contained the completed canary ledgers, but no verified overnight campaign ledger or settings. This was the pre-launch observation. The campaign was subsequently launched and completed; its verified configuration, job IDs and results are recorded in Experiment 7 below.

### Why use short diagnostic runs first?

Full 30-minute benchmarks are expensive, especially across several nodes and compiler/layout combinations. Short diagnostics let us reject poor configurations, confirm numerical correctness and focus repeat measurements on promising candidates before spending the final-run budget. They also expose setup, compiler and controller problems cheaply. They cannot replace a long benchmark or establish final energy efficiency.

## Experiment 7: Overnight Adaptive Campaign — completed

Date: **15 October 2026**. The nine-job sequence ran from **02:30:45 to 03:10:28 BST** on Cirrus. This is the completed overnight diagnostic campaign; it is separate from the earlier controller and compiler smoke tests.

### Campaign configuration and evidence

| Setting | Verified value |
|---|---|
| Campaign directory | `/epccfs/tc079/tc079/shared/hpcg/runs/tc079cheu1/campaign-overnight-20261015-01` |
| Settings file | `controller-review/work/overnight-20261015.toml`, under the same user run root |
| Job sequence | 558650 → 558651 → 558653 → 558654 → 558656 → 558657 → 558658 → 558659 → 558660 |
| Resources | One exclusive standard Cirrus node; 288 allocated physical cores per job |
| HPCG mode | HPCG 3.1, `diagnostic`; performance objective |
| Requested benchmark duration | 120 s per trial |
| Workload target | 323960832 equations per node, with a 2.5% volume tolerance |
| Layout search | OpenMP counts 1/2/4/6/12; configured CPU fill fractions 1, 0.5 and 0.25 |
| Compiler/build screen | CCE reference, CCE strict, GCC 14 fast math and AOCC 5 fast math; Intel disabled |
| Repeats | Up to two measurements per candidate; repeat opportunity every four trials; 2% provisional noise band |
| Candidate space | 36 candidates; nine trials completed out of a maximum of 12 |
| Admission cap | 500 core-hours in full allocation reservations |
| Time limits | 420 s benchmark overhead allowance, 180 s build timeout for recipe builds, 60 s controller margin |
| Allocation reservation | 600 s / 48 core-hours for CCE reference; 780 s / 62.4 core-hours for other builds, including repeats |
| Pending timeout / campaign deadline | 7200 s / 10:00 BST on 15 October 2026 |

The settings file's values were checked against the ledger's frozen settings hash. The ledger retains the controller/source hashes, per-build executable hashes, selection reasons and reservations. Each `runs/` directory contains its input, raw HPCG summary, `result.json`, `build.json`, `provenance.json`, compiler version, modules and linked-library records. Some paths resolve to the equivalent `/mnt/nfs/epccfs/projects/...` location.

### All nine diagnostic measurements

All jobs below are `COMPLETED` in Slurm, numerically `VALID`, and passed the spectral-convergence, symmetry, iteration-count and reproducibility checks. Every trial used one node and 120 requested benchmark seconds; **none is an official 30-minute competition result**.

| Trial / job | Build | MPI ranks × threads | Local grid | GFLOP/s | Reported benchmark time (s) | Data memory (GB) |
|---|---|---|---|---:|---:|---:|
| 1 / 558650 | CCE reference | 288×1 | 104×104×104 | 134.942 | 134.134 | 231.733 |
| 2 / 558651 | CCE strict | 288×1 | 104×104×104 | 132.918 | 136.184 | 231.733 |
| 3 / 558653 | GCC 14 | 288×1 | 104×104×104 | 134.293 | 134.776 | 231.733 |
| 4 / 558654 | AOCC 5 | 288×1 | 104×104×104 | 133.793 | 135.289 | 231.733 |
| 5 / 558656 | CCE reference, repeat | 288×1 | 104×104×104 | 134.894 | 134.185 | 231.733 |
| 6 / 558657 | CCE reference | 144×1 | 128×128×136 | **135.342** | 132.209 | 229.477 |
| 7 / 558658 | CCE reference | 144×2 | 128×128×136 | 134.188 | 133.449 | 229.477 |
| 8 / 558659 | CCE reference | 72×1 | 152×168×176 | 131.806 | 136.346 | 231.395 |
| 9 / 558660 | GCC 14, repeat | 288×1 | 104×104×104 | 133.809 | 135.266 | 231.733 |

### Compiler comparison under matching conditions

The compiler anchors all used 288×1, a 104³ local grid and 323960832 equations. CCE reference, GCC and AOCC used `-O3 -ffast-math -fopenmp`; CCE strict used `-O3 -fopenmp`. Compiler versions were CCE 19.0.0, GCC 14.2.1 and AOCC 5.0.0, with the Cray `CC` MPI wrapper and Cray MPICH 8.1.32. Each build retained its own executable identity; these measurements do not pool different binaries into one response model.

| Build | Anchor jobs | Measurements | Mean GFLOP/s | Sample standard deviation (GFLOP/s) |
|---|---|---:|---:|---:|
| CCE reference | 558650, 558656 | 2 | **134.918** | 0.034 |
| GCC 14 | 558653, 558660 | 2 | 134.051 | 0.342 |
| AOCC 5 | 558654 | 1 | 133.793 | Not estimated from one run |
| CCE strict | 558651 | 1 | 132.918 | Not estimated from one run |

CCE reference led this small anchor comparison. That justifies focusing the limited diagnostic budget on it, but does not establish a general compiler ranking across all layouts or node counts. The two repeated groups also show why a single sample is insufficient: the GNU pair varied more than the CCE reference pair. Two samples provide only a limited estimate of noise.

### Adaptive selection and the candidate improvement

The recorded decisions show that this was a result-driven search:

1. Trials 1–4 screened the four compiler builds with the same anchor layout and workload.
2. Trial 5 repeated CCE reference after its leading initial anchor result. All four anchors were within the controller's 2% provisional close band.
3. The repeated CCE baseline averaged **134.918 GFLOP/s**, and the controller selected the nearby **144×1** CCE reference layout for trial 6.
4. After trial 6 produced the highest individual rating, **135.342 GFLOP/s**, the controller used 144×1 as its search pivot and tried **144×2** and **72×1** in trials 7–8.
5. Trial 9 repeated GNU, the highest-performing eligible anchor not yet repeated, to examine variation rather than spend every remaining trial on a new layout.

Job **558657** is the best individual result from this campaign. It configured 144 MPI ranks with one OpenMP thread per rank: 144 active cores out of 288 allocated, rather than the fully populated 288×1 baseline. The apparent difference is **0.424 GFLOP/s**, or `(135.342 / 134.918 - 1) × 100 ≈ 0.31%`.

**This is not yet a confirmed improvement.** The candidate has only one measurement, while the baseline has two. Its grid also contains **320864256 equations**, about **0.96% fewer** than the baseline's 323960832, and the global decomposition changes with the MPI layout. Approximate workload matching and a small observed baseline spread do not establish statistical significance. Selecting the best of several trials can also favour a noisy high sample. Repeat the candidate and baseline with matched workloads and interleaved run order before accepting a speedup.

The 72×1 trial contained 323592192 equations, approximately 0.11% below the target. The campaign therefore explored CPU utilisation at approximately comparable total volume, rather than simply shrinking the problem in proportion to the active-core count. These layout results do not establish energy savings.

### Actual Slurm usage versus reserved budget

| Quantity | Recorded value and interpretation |
|---|---|
| Actual Slurm allocation usage | **190.16 core-hours**, summed over these nine jobs only |
| Sum of whole-job elapsed time | 2377 s, each with 288 allocated CPUs |
| Ledger reservations retained | **489.6 core-hours**, including full worst-case job durations |
| Campaign reservation cap | 500 core-hours |
| Remaining reservation headroom | 10.4 core-hours; less than the 48-core-hour minimum next trial |
| Stopping condition | `candidate/repeat or remaining budget limit` in `slurm-558660.out` |

Actual usage is `sum(ElapsedRaw × AllocCPUS) / 3600 = 2377 × 288 / 3600 = 190.16 core-hours`, using allocation-level `sacct -X` records so job steps are not double-counted. It includes setup, controller work and compilation where performed, not just the timed HPCG solve. Even under-populated layouts reserve a whole node and are charged 288 allocated CPUs in this calculation.

The ledger retained five CCE-reference reservations at 48 core-hours and four other-build reservations at 62.4: `5 × 48 + 4 × 62.4 = 489.6`. It does not refund the difference between reserved and actual runtime. The campaign stopped cleanly after nine trials because another full reservation would exceed the cap; it did not reach its twelve-trial or 10:00 deadline limit. **489.6 is not the actual compute usage**, and **190.16 is not a verified debit or remaining balance from team SAFE**. Earlier smoke tests and other team jobs are outside this nine-job total.

### Energy-accounting limitations

Slurm recorded **2337351 J** summed over the nine whole jobs. This is a whole-job accounting total, not the energy consumed solely during the reported benchmark windows. It includes work outside the timed solve, and can include compilation for alternative builds. Compiler/setup overhead and allocation duration therefore affect this total independently of benchmark GFLOP/s.

All nine result records have benchmark-window energy unavailable and no benchmark GFLOP/s/W. The campaign optimised performance, not energy efficiency. Neither the 144×1 result nor its reduced configured active-core count proves lower benchmark energy or better GFLOP/s/W. That needs a verified measurement window, repeated comparisons and, for later scaling, coverage of every node.

## Current Work: Confirm the Candidate Result

The next measurement task is to repeat the 144×1 CCE reference candidate and interleave it with the 288×1 baseline under matched problem-size and timing conditions. The apparent 0.31% gain remains unconfirmed. No additional campaign is described as running here.

## Planned Experiments and Competition Results

- Repeat the 144×1 CCE reference candidate (job 558657) and the 288×1 baseline, matching equation counts as closely as possible and reporting variation before accepting the apparent 0.31% improvement.
- Measure scaling from one to four nodes, keeping strong- and weak-scaling comparisons clearly identified and recording the best configuration at each size.
- Run selected configurations for at least **1800 reported benchmark seconds**, with the required memory footprint, for official competition measurements.
- Verify benchmark-window energy measurement and multi-node coverage before reporting benchmark GFLOP/s/W.
- Assemble the final scripts, results, budget accounting and presentation material from the recorded evidence.

**No official 30-minute competition result is recorded in this log yet.** All measurements above are diagnostic.

### Energy interpretation

The energy values above, including the overnight total, are Slurm **whole-job** readings. They can include compilation, module loading, setup, teardown and controller work, as well as the timed benchmark. They are not necessarily equal to benchmark-window energy and are not converted into HPCG GFLOP/s/W here. The campaign results currently record benchmark-window energy as unavailable. A future energy comparison must state the measurement scope and account for every participating node.
