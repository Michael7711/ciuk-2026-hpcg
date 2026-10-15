# CIUK Cluster Challenge 2026 – HPCG Benchmark

This log separates completed diagnostic experiments, completed official-duration benchmarks, analysis and possible future work. Numerical `VALID` status and the controller's duration/memory eligibility checks do not establish formal competition acceptance. As of the team update on 15 October 2026, all further HPCG compute jobs are paused while remaining HPL requirements are coordinated.

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

All nine original result records retain benchmark-window energy as unavailable and no benchmark GFLOP/s/W. The campaign optimised performance. The recovered accounting below adds a separate, retrospective Slurm-step estimate; it does not alter those historical result records or make an energy objective available to the controller.

### Recovered Slurm-step energy analysis — 15 October 2026

Source: [`analysis/hpcg/overnight-20261015-sacct-energy.psv`](../../analysis/hpcg/overnight-20261015-sacct-energy.psv), SHA-256 `c4cc65eb50e0dcf0ff19049c4c182df856be71822e4a68bebd1be915bbe89466`. Its 36 unique allocation/step records match all nine job IDs in the diagnostic table above. All records are `COMPLETED`; each `.0` is named `bench_wrapper.sh`. The jobs used one exclusive node each. A read-only accounting check on 558657 also confirmed one allocated node and 288 allocated CPUs for its `.0` step. No historical campaign files were changed.

| Job | Build / MPI ranks × threads | GFLOP/s | Whole-job energy (J) | `.0` energy (J) | `.0` elapsed (s) | Step-average power (W) | Estimated GFLOP/s/W |
|---|---|---:|---:|---:|---:|---:|---:|
| 558650 | CCE reference / 288×1 | 134.942 | 273140 | 270439 | 257 | 1052.292 | 0.1282 |
| 558651 | CCE strict / 288×1 | 132.918 | 274050 | 269594 | 261 | 1032.927 | 0.1287 |
| 558653 | GCC 14 / 288×1 | 134.293 | 269130 | 266029 | 256 | 1039.176 | 0.1292 |
| 558654 | AOCC 5 / 288×1 | 133.793 | 269963 | 266458 | 258 | 1032.783 | 0.1295 |
| 558656 | CCE reference, repeat / 288×1 | 134.894 | 271615 | 268882 | 256 | 1050.320 | 0.1284 |
| 558657 | CCE reference / 144×1 | 135.342 | 231331 | 228809 | 247 | 926.352 | 0.1461 |
| 558658 | CCE reference / 144×2 | 134.188 | 264250 | 261950 | 249 | 1052.008 | 0.1276 |
| 558659 | CCE reference / 72×1 | 131.806 | 216374 | 214062 | 255 | 839.459 | 0.1570 |
| 558660 | GCC 14, repeat / 288×1 | 133.809 | 267498 | 264883 | 258 | 1026.678 | 0.1303 |

For each job, `step_average_power_w = .0 ConsumedEnergyRaw / .0 ElapsedRaw`, in joules per second. The final column is `HPCG GFLOP/s / step_average_power_w`. For example, 558657 gives `228809 / 247 = 926.352 W`, then `135.342 / 926.352 = 0.146102 estimated GFLOP/s/W`. Whole-job energy is displayed independently. **Never add `.batch`, `.extern`, `.0` and allocation energy:** their accounting intervals overlap. The sum of the allocation rows alone remains the historical **2337351 J** total.

The `.0` interval includes HPCG initialisation, setup and validation as well as the timed benchmark. These steps lasted 247–261 s, while reported benchmark times were 132.209–136.346 s. Dividing step energy by the shorter reported benchmark runtime would produce a misleading power value. Using step-average power with the HPCG rating is an explicitly labelled estimate; it does not establish timed benchmark-window efficiency. Sensor scope, sampling cadence and boundary effects also matter. A read-only Cirrus configuration check found `acct_gather_energy/pm_counters` and `JobAcctGatherFrequency=task=30,energy=30,filesystem=30,network=30`; that is an accounting interval, not a verified sensor accuracy or update rate.

The performance/energy-estimate trade-off is visible within CCE reference:

- **144×1 (558657)** had the highest individual performance, **135.342 GFLOP/s**, with **926.352 W** step-average power and **0.1461 estimated GFLOP/s/W**.
- **72×1 (558659)** had the highest efficiency estimate, **0.1570 GFLOP/s/W**, at **131.806 GFLOP/s** and **839.459 W**. Relative to 144×1, it was approximately **2.61% slower**, used **9.38% less average step power**, and had a **7.47% higher efficiency estimate**.
- Against the individual **288×1 baseline 558650**, 72×1 was approximately **2.32% slower**, with **20.23% less average step power** and a **22.44% higher efficiency estimate**. The 144×2 run had no observed performance or energy-estimate advantage over 144×1 in these samples.

These are diagnostic observations, with just one measurement for each reduced-rank layout, slightly different equation counts and potentially different nodes/system conditions. The apparent 0.31% performance gain over the repeated 288×1 mean remains unconfirmed. The compiler anchors have similar power estimates but too few repeats for an energy ranking. The observations support testing both speed and energy trade-offs, not a proven optimum or a causal claim about idle cores.

Reproduce the join, validation and calculations from the repository with Python 3.11+:

```sh
python3 analysis/hpcg/overnight_energy.py
```

The analysis rejects missing or duplicate job IDs, unmatched job sets and unusable measurements. `--output NEW.csv` writes a new derived file and refuses to overwrite one. The raw PSV and historical benchmark table remain the inputs. The companion [analysis notebook](../../analysis/hpcg/overnight-energy.ipynb) contains the executed standard-library calculations and the nine-job table; its Jupyter frontend execution remains unverified.


## Experiment 8: Official-Duration Weak Scaling — completed

Date: **15 October 2026**. The unattended sequence ran **18:42:28–20:23:07 BST**, completing all three scheduled node counts. These are official-duration benchmark measurements, separate from the short diagnostics above. All passed the controller's eligibility checks; **formal competition acceptance has not been established**.

### Verified configuration and provenance

| Setting | Recorded value |
|---|---|
| Campaign directory | `/epccfs/tc079/tc079/shared/hpcg/runs/tc079cheu1/campaign-official-144-20261015-01` |
| Deployed controller | `controller-official-20261015-v1/`, under the same user run root |
| Campaign settings | `controller-official-20261015-v1/work/official-144-20261015-v1.toml` |
| Mode / order | `sequence`, weak scaling; 1 → 2 → 4 nodes, one run at each size |
| Build | HPCG 3.1, `cce19-reference`; CCE 19.0.0, Cray `CC` MPI wrapper |
| Flags | `-O3 -ffast-math -fopenmp` |
| Modules | `PrgEnv-cray/8.6.0`, `cce/19.0.0`, `cray-mpich/8.1.32` |
| Executable | `/epccfs/tc079/tc079/shared/hpcg/build/bin/xhpcg` |
| Executable SHA-256 | `1ecfef30466d29e1a5f830d4f9bb7a0f431b1d3d77b14c953ee3a460899321de` |
| Source hash in ledger | `dd94e9371a3f1b21972f60a84d8a787137b6771ef5df60fac08c9a50404596ca` |
| Controller hash in ledger | `425868d29ffc917631e1d8fa82f1974186baf057b4d0a338d378bf7f567c48f1` |
| Settings hash in ledger | `6d817843b250d83cd66c9a430b62ad4701e22d2b608a9f257f6e2bcf44789047` |
| Per-node layout | 144 MPI ranks × 1 OpenMP thread; 144 active cores, 288 allocated cores |
| Local grid | 128×128×136 per rank at every scale |
| Equations per node | 320864256; totals 320864256, 641728512 and 1283457024 |
| Requested duration / kind | 1860 s / `final` |
| Scheduler | Exclusive standard partition, standard QoS; no automatic requeue |
| Reservation per node | 2640 s = 44 min: 1860 benchmark + 600 setup + 180 controller/accounting |
| Trial limit / cap | Three trials / 1500 core-hours |
| Pending timeout / finish deadline | 7200 s / 16 October 2026, 18:00 UTC (19:00 BST) |
| Energy archival | `archive_slurm_energy=true`; raw PSV snapshots and separate JSON estimate receipts |

The previously documented 1500-hour proposal became this completed campaign. The frozen settings retain a **3721.9-core-hour pre-launch advisory balance estimate**; the earlier prediction of 2221.9 hours outside that allowance was a planning calculation, not an observed remaining balance. The newer shared accounting snapshot below supersedes those figures for team planning. The repository's disabled template and the enabled settings used for this completed campaign are distinct; no settings were changed during this documentation update.

### Performance, validation and weak scaling

| Nodes | Job | Total MPI ranks | GFLOP/s | Reported HPCG time (s) | Total data memory (GB) | Weak-scaling efficiency | Validation |
|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 565006 | 144 | 135.094 | 1898.57 | 229.477 | 100% | VALID; four checks PASSED; controller eligible |
| 2 | 566113 | 288 | 269.818 | 1857.91 | 458.954 | 99.86% | VALID; four checks PASSED; controller eligible |
| 4 | 569661 | 576 | 533.317 | 1879.79 | 917.907 | 98.69% | VALID; four checks PASSED; controller eligible |

For `N` nodes, weak-scaling efficiency is `GFLOP/s(N) / (N × 135.094) × 100`. The four-node speedup is `533.317 / 135.094 = 3.94775`, approximately **3.95×**. Local dimensions, rank count per node and equations per node stayed fixed, so this is a weak-scaling comparison, not strong scaling.

All three original reports show spectral convergence, symmetry, iteration-count and reproducibility checks as `PASSED`, the expected ranks/threads/local grid, and at least **1800 reported benchmark seconds**. Reported data memory is approximately **229.477 GB/node**, above the controller's **206.158 GB/node** minimum (one quarter of nominal 768 GiB), and below its memory ceiling. The ledger and each `result.json` record `usable=true` and `official_eligible=true`. These are the controller's checks, not an assertion that competition organisers have accepted the results.

Original summaries are under the campaign's `runs/` directory:

| Job | Run directory | Original HPCG report |
|---|---|---|
| 565006 | `hpcg-final-n1-144x1-f55e825c-r1` | `HPCG-Benchmark_3.1_2026-10-15_19-16-05.txt` |
| 566113 | `hpcg-final-n2-144x1-9e7be705-r1` | `HPCG-Benchmark_3.1_2026-10-15_19-49-22.txt` |
| 569661 | `hpcg-final-n4-144x1-29be9860-r1` | `HPCG-Benchmark_3.1_2026-10-15_20-23-03.txt` |

These reports, `result.json`, `build.json`, ledger entries and the chaining logs were checked through **read-only SSH** for this documentation update. Resolved paths may use the equivalent `/mnt/nfs/epccfs/projects/...` prefix. No original report, result, setting or ledger was modified.

### Unattended execution and stopping evidence

Job **565006** recorded submission of **566113**; job **566113** recorded submission of **569661**. Their selection reason was `predefined weak-scaling sequence; cover 1 then 2 then 4 nodes; no adaptive repeats`. Job **569661** recorded `stopped: max_trials` and **1478.4 reserved core-hours**. The chain covered each intended node count once, validated each result before proceeding, and required no persistent SSH connection or login-node controller process.

This is separate from Experiment 7's reservation-limit stop. The diagnostics stopped because another reservation would not fit; the official sequence stopped because all three scheduled trials had run. Neither campaign used remaining allowance as a reason to launch extra work automatically.

### Recovered final energy accounting

Final snapshot: `accounting/20261015T195613.739074Z-c77bbeb3.psv`, with a matching JSON receipt, under the completed campaign directory. The receipt records capture at **19:56:13 UTC / 20:56:13 BST on 15 October 2026**. All allocation and step rows are `COMPLETED` with exit status `0:0`; `.0` is `bench_wrapper.sh`. The `.0` records cover **1, 2 and 4 nodes**, with **288, 576 and 1152 allocated CPUs**, and node lists matching their allocations.

| Nodes / job | Whole-job energy (J) | `.0` step energy (J) | `.0` duration (s) | Step-average power (W) | Estimated GFLOP/s/W |
|---|---:|---:|---:|---:|---:|
| 1 / 565006 | 2013794 | 2011120 | 2013 | 999.066 | 0.135220 |
| 2 / 566113 | 3826830 | 3821762 | 1988 | 1922.415 | 0.140354 |
| 4 / 569661 | 8120129 | 8108790 | 2012 | 4030.214 | 0.132330 |

`step_average_power_w = .0 ConsumedEnergyRaw / .0 ElapsedRaw`; `estimated_gflops_per_w = HPCG GFLOP/s / step_average_power_w`. For example, the four-node estimate is `533.317 / (8108790 / 2012) = 0.132330 GFLOP/s/W`, rounded. Use the total step energy and total HPCG performance across all nodes; **do not multiply the already aggregated energy by node count**.

These estimates cover the Slurm benchmark-wrapper step, including initialisation, setup and validation outside HPCG's timed benchmark window. They **do not verify timed-window energy efficiency**. The final receipts retain `energy_scope="slurm_benchmark_wrapper_step"` and `benchmark_window_energy_verified=false`. The original benchmark `gflops_per_w` values remain **null** (blank in the corresponding reporting rows), and their benchmark energy scope remains unavailable. The estimates are separate archival fields; no benchmark record was backfilled or overwritten.

**Never add allocation, `.batch`, `.extern` and `.0` energy readings:** their intervals overlap. In these multi-node jobs `.batch` covers only the first node, while `.0` covers the full benchmark allocation. The whole-job energies above are recorded separately and must not be added to step energies. Automatic captures occurred after each benchmark, and the final archival snapshot recovered completed allocation totals after the last worker exited; early running-job readings are not the final measurements.

### Actual allocation usage versus conservative reservations

| Nodes / job | Allocation elapsed (s) | Allocated CPUs | Actual core-hours | Ledger reservation (core-hours) |
|---|---:|---:|---:|---:|
| 1 / 565006 | 2021 | 288 | 161.68 | 211.2 |
| 2 / 566113 | 1996 | 576 | 319.36 | 422.4 |
| 4 / 569661 | 2020 | 1152 | 646.40 | 844.8 |
| Total | | | **1127.44** | **1478.4** |

Actual usage is `sum(allocation ElapsedRaw × AllocCPUS) / 3600`, using only allocation rows, not overlapping steps. It includes setup, benchmark and controller time, and counts all allocated cores even though only 144 per node were configured to execute benchmark threads. The reported HPCG runtime and the wrapper-step duration are different intervals and are not used to calculate allocation core-hours.

Reservations use the full **2640-second allocation limit**, including conservative setup/controller allowances, rather than observed elapsed time. The ledger retained **1478.4** against its **1500-core-hour cap**, even though actual usage was **1127.44**. The **350.96-hour difference** was not refunded to extend this campaign; the 21.6-hour cap headroom was not an instruction to start more jobs. Neither the reservation total nor this campaign's actual usage is a verified live team SAFE balance.

## Analysis: What the Controller Demonstrated

The project progressed from the initial small Slurm pipeline tests to **558642 → 558643** automatic chaining, isolated GCC/AOCC/CCE-strict compilation and validation, **nine VALID adaptive diagnostics**, and finally the completed **1 → 2 → 4-node official-duration sequence**. Compiler screening used matching conditions and separate build identities; repeated anchors and measured performance guided subsequent nearby MPI/OpenMP and CPU-utilisation choices. The expanded **58-test suite passed on Cirrus**, as reported by the team, following the earlier 41-test validation. This documentation-only review did not rerun the suite or locate a retained Cirrus test-console log in the inspected controller directories.

The experiments demonstrated normal unattended operation, reproducible build identity, numerical validation, result-driven diagnostic selection, a clean no-fit reservation stop, fixed coverage of each node count, and automatic accounting capture followed by final archival. Near-linear weak scaling was observed for the chosen CCE 144×1 configuration. The two-node run had the highest step-based efficiency estimate in the official sequence; the four-node run had the highest total performance and power.

These observations do **not** prove a globally optimal compiler/layout or an energy optimum. There is one official measurement per node count, no repeated official scaling curve, and no official-duration 72×1 comparison. The earlier apparent 0.31% diagnostic improvement over 288×1 remains unconfirmed by matched repeated measurements. Benchmark-window counter access, synchronisation and sensor calibration remain unverified, as do formal competition acceptance and some live failure/deadline/crash/concurrent-admission paths. Automated safeguards and successful normal runs do not establish every site-specific failure behavior.

## Current Team Budget and Compute Pause

The team has confirmed a **5000-core-hour total allocation**. The latest team-supplied **shared Slurm accounting snapshot**, recorded for this documentation update on **15 October 2026**, showed:

| Quantity | Snapshot value (core-hours) |
|---|---:|
| Total team allocation | 5000 |
| Shared accounting usage | 4294.48 |
| Estimated remaining | **705.52** |

`5000 − 4294.48 = 705.52`. This is a dated accounting estimate, **not a verified live SAFE balance**. The exact export timestamp and underlying shared-team report were not supplied or independently verified during this review; the **20:56:13 BST** timestamp above belongs to the official campaign's energy archive, not this shared balance report. Other team jobs may change the balance. Do not treat old template/advisory values or the campaign's unspent reservation margin as current shared funds.

**All further HPCG compute jobs are paused while the team coordinates the remaining HPL requirements.** The additional **72×1 official-duration experiment has not been launched**. This is the team's operational pause; this documentation update does not change any submission gate, job or campaign state.

## Possible Future Work — Compute Subject to Team Agreement

Current non-compute work is to analyse and present the completed measurements, retain original reports and accounting, and confirm the competition's acceptance and energy-reporting requirements. Any later compute work needs a newly agreed allowance after HPL coordination:

- Repeat matched 144×1 and 288×1 comparisons before accepting the apparent 0.31% diagnostic improvement.
- Consider the unlaunched 72×1 official-duration comparison and other compiler/layout choices, accounting for measurement variation and node count.
- Repeat the weak-scaling curve if an agreed budget permits; do not infer an optimum from one run per scale.
- Investigate synchronised, per-node measurement of the actual timed HPCG region before reporting benchmark-window GFLOP/s/W.

Completed official-duration measurements remain distinct from the historical diagnostics and from possible future experiments. No further HPCG compute is authorised by this log.
