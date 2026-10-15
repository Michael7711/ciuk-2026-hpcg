# CIUK 2026 - HPCG

My work on the HPCG benchmark for the CIUK 2026 EPCC Cluster Challenge, using Cirrus. The aim is to improve performance and energy efficiency, then demonstrate scaling from one to four nodes with reproducible results.

**Current status — 15 October 2026:** the official-duration 1 → 2 → 4-node campaign is complete. **All further HPCG compute jobs are paused** while the team coordinates the remaining HPL requirements. The additional 72×1 official-duration experiment has **not been launched**.

## Completed diagnostic experiments

- Built and validated an HPCG 3.1 reference implementation with Cray CCE 19.
- Compared problem sizes and MPI/OpenMP layouts on one Cirrus node. An initial larger reference run reached **134.124 GFLOP/s** with 288 MPI ranks, one thread per rank and **231.733 GB** of reported data memory.
- Developed a Python and Slurm optimisation controller. The initial **41 automated tests passed on Cirrus**; the expanded suite subsequently passed **58 tests on Cirrus**.
- Verified automatic job chaining with jobs **558642 → 558643**, including stopping at the two-trial limit.
- Compiled and numerically validated GCC 14 (**558644**), AOCC 5 (**558647**) and CCE 19 without fast math (**558649**).
- Completed the **15 October 2026 overnight campaign**: nine numerically VALID diagnostics, with measured compiler screening, repeats and adaptive CPU-layout selection.

These are **diagnostic results**, not official competition results. The compiler and chaining smoke tests used deliberately small problems to check that the workflow works; their performance ratings should not be used to choose the final compiler.

Settings, measurements, validation status and campaign locations are recorded in the [experiment log](docs/hpcg/experiment_log.md).

## Completed overnight campaign: 15 October 2026

The unattended campaign ran from **02:30 to 03:10 BST**, submitting nine Slurm jobs automatically and stopping when another full reservation would not fit its 500-core-hour cap. All nine jobs completed and passed HPCG numerical validation. They used one exclusive Cirrus node and 120 requested benchmark seconds, with approximately comparable problems using **229–232 GB** of reported data memory.

The best individual result was **135.342 GFLOP/s**, using the **CCE reference build, 144 MPI ranks and one OpenMP thread per rank** (job **558657**). The repeated **288×1 CCE reference baseline averaged 134.918 GFLOP/s**. The apparent **0.31% improvement is not confirmed**: the 144×1 configuration was measured only once and used about 0.96% fewer equations. It is a candidate for repeated testing, not an established speedup.

The compiler screen used matching 288×1, 104³-local-grid conditions. CCE reference led the observed anchor results, so the controller repeated it and explored 144×1, 144×2 and 72×1 layouts. It also repeated GNU to assess variation. The [experiment log](docs/hpcg/experiment_log.md#experiment-7-overnight-adaptive-campaign--completed) contains all nine measurements, compiler means, selection reasons and campaign paths.

Actual Slurm allocation usage was **190.16 core-hours**; the controller retained **489.6 core-hours of worst-case reservations**. These are different quantities. The remaining 10.4 hours of reservation headroom could not fit another trial, so the controller stopped even though actual usage was much lower.

Recovered Slurm accounting now provides a separate **wrapper-step average-power estimate** for all nine diagnostics. CCE 144×1 gives **0.1461 estimated GFLOP/s/W** at 135.342 GFLOP/s; 72×1 gives **0.1570** at 131.806 GFLOP/s; baseline job 558650 gives **0.1282**. These are not timed benchmark-window efficiencies. Whole-job and step intervals overlap and their energy readings must not be added. The [experiment log](docs/hpcg/experiment_log.md#recovered-slurm-step-energy-analysis--15-october-2026) records every raw value, calculation and limitation. The runs remain **diagnostic**, below 1800 reported seconds.

## Completed official-duration weak-scaling campaign

On **15 October 2026**, the controller completed **565006 → 566113 → 569661** unattended, then stopped at its three-trial limit. All runs used **CCE 19 reference**, **144 MPI ranks × 1 OpenMP thread per node**, a fixed **128×128×136 local grid per rank**, and **1860 requested benchmark seconds**. The workload was **320864256 equations per node**.

| Nodes | Slurm job | GFLOP/s | Reported HPCG runtime (s) | Weak-scaling efficiency | Validation |
|---:|---:|---:|---:|---:|---|
| 1 | 565006 | 135.094 | 1898.57 | 100% | VALID; controller eligible |
| 2 | 566113 | 269.818 | 1857.91 | 99.86% | VALID; controller eligible |
| 4 | 569661 | 533.317 | 1879.79 | 98.69% | VALID; controller eligible |

Efficiency is `GFLOP/s(N) / (N × 135.094) × 100`. Four nodes achieved **3.95×** the one-node performance. All three reports passed the four numerical checks and the controller's duration and memory eligibility checks. **Controller eligibility does not establish formal competition acceptance**, which has not been verified.

Final Slurm accounting was archived for all three jobs:

| Nodes | Whole-job energy (J) | Wrapper-step energy (J) | Step duration (s) | Step-average power (W) | Estimated GFLOP/s/W |
|---:|---:|---:|---:|---:|---:|
| 1 | 2013794 | 2011120 | 2013 | 999.066 | 0.135220 |
| 2 | 3826830 | 3821762 | 1988 | 1922.415 | 0.140354 |
| 4 | 8120129 | 8108790 | 2012 | 4030.214 | 0.132330 |

These estimates divide HPCG performance by average power over the Slurm `bench_wrapper.sh` `.0` step. They include setup and validation outside HPCG's timed window. They **do not verify benchmark-window energy**, do not populate the original `gflops_per_w` field, and must not be combined with overlapping whole-job, `.batch` or `.extern` energy readings. The two-node run had the highest step-based estimate in this sequence; one measurement per node count does not establish a general energy optimum.

The campaign used **1127.44 actual core-hours**: 161.68, 319.36 and 646.40 at 1, 2 and 4 nodes. Its ledger retained **1478.4 core-hours of conservative reservations** under a **1500-core-hour cap**. Reservations cover full allocation limits; actual usage uses allocation elapsed time and allocated CPUs. The difference was not refunded to admit extra trials.

Campaign: `/epccfs/tc079/tc079/shared/hpcg/runs/tc079cheu1/campaign-official-144-20261015-01`. The [experiment log](docs/hpcg/experiment_log.md#experiment-8-official-duration-weak-scaling--completed) records original report paths, build provenance, chaining evidence and the final accounting snapshot.

## Team budget and possible future work

The team has confirmed a **5000-core-hour total allocation**. The latest team-supplied shared Slurm accounting snapshot, recorded for this update on **15 October 2026**, showed **4294.48 core-hours used** and **705.52 estimated remaining**. This is a dated accounting snapshot, **not a verified live SAFE balance**; its exact shared-report export time was not supplied. The controller's frozen pre-launch balance estimate is historical and must not be used as the current balance.

**Further HPCG compute remains paused.** Coordinate the remaining HPL requirements before considering more HPCG runs. The additional 72×1 official-duration experiment has not been launched. Possible later work includes matched repeats against 288×1, tests of 72×1 and other configurations at each node count, and verified timed-window energy instrumentation, subject to a new agreed allowance. The observed scaling curve and adaptive search do not prove an optimal HPCG configuration or confirm the earlier apparent 0.31% diagnostic speedup.

Current work is analysis and presentation: retain the original reports and accounting, explain the diagnostic-to-official progression, and confirm the competition's submission and energy-reporting requirements. The [controller guide](docs/hpcg/autotuning-controller.md) records what was tested, how budgets and failure stops work, and what remains unverified. Repository templates retain submission-disabled defaults; this documentation update changes no code, configuration, job or campaign state.

The automation is based on [Rory's CIUK project](https://github.com/roryhory/ciuk-2026-epcc). HPCG itself comes from the [official benchmark repository](https://github.com/hpcg-benchmark/hpcg).
