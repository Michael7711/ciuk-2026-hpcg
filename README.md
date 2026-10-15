# CIUK 2026 - HPCG

My work on the HPCG benchmark for the CIUK 2026 EPCC Cluster Challenge, using Cirrus. The aim is to improve performance and energy efficiency, then demonstrate scaling from one to four nodes with reproducible results.

## Completed experiments

- Built and validated an HPCG 3.1 reference implementation with Cray CCE 19.
- Compared problem sizes and MPI/OpenMP layouts on one Cirrus node. An initial larger reference run reached **134.124 GFLOP/s** with 288 MPI ranks, one thread per rank and **231.733 GB** of reported data memory.
- Developed a Python and Slurm optimisation controller; all **41 automated tests passed on Cirrus**.
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

Whole-job Slurm energy includes work outside the timed solver and is not necessarily benchmark-window energy. No benchmark GFLOP/s/W is reported from this campaign. These remain **diagnostic results**, well below the 1800-second requirement for official competition benchmarks.

## Current work: confirm the candidate result

Repeat the 144×1 candidate and the 288×1 reference with matched workloads, and check whether the small performance difference persists. The initial overnight campaign is complete; no follow-up campaign or official result is claimed here.

## Planned experiments

Repeat the strongest configurations at representative problem sizes, test one-to-four-node scaling, and run the finalists for at least **1800 reported benchmark seconds** with the required memory footprint. Final results will need measured energy, clearly labelled GFLOP/s/W, reproducible scripts and presentation material.

The [controller guide](docs/hpcg/autotuning-controller.md) describes selection, budget accounting, provenance, validation and emergency stopping. Repository templates retain submission-disabled defaults; this documentation update does not change any campaign or enable submissions.

The automation is based on [Rory's CIUK project](https://github.com/roryhory/ciuk-2026-epcc). HPCG itself comes from the [official benchmark repository](https://github.com/hpcg-benchmark/hpcg).
