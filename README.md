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

Recovered Slurm accounting now provides a separate **wrapper-step average-power estimate** for all nine diagnostics. CCE 144×1 gives **0.1461 estimated GFLOP/s/W** at 135.342 GFLOP/s; 72×1 gives **0.1570** at 131.806 GFLOP/s; baseline job 558650 gives **0.1282**. These are not timed benchmark-window efficiencies. Whole-job and step intervals overlap and their energy readings must not be added. The [experiment log](docs/hpcg/experiment_log.md#recovered-slurm-step-energy-analysis--15-october-2026) records every raw value, calculation and limitation. The runs remain **diagnostic**, below 1800 reported seconds.

## Current work: prepare official-duration weak scaling

The proposed [disabled sequence configuration](autotune/clusters/cirrus-hpcg-official-sequence.toml) uses CCE reference **144 MPI ranks × 1 thread per node**, fixed local **128×128×136** grids, and **1860 requested seconds**, once each at **1, 2 and 4 nodes**. It requires at least 1800 reported seconds, numerical validation and the memory threshold before chaining to the next scale. The proposed **1500-core-hour cap** covers **1478.4 worst-case reservation hours** and leaves **2221.9** of the stated 3721.9 shared SAFE balance outside this allowance. Agree that allowance with the HPL team before launch.

The sequence is prepared for review and **has not been launched**. 144×1 is a provisional speed candidate; 72×1 is a provisional energy-estimate candidate. Repeated matched measurements are still needed to confirm either advantage. See the [controller guide](docs/hpcg/autotuning-controller.md#proposed-official-duration-sequence--not-launched) for validation, accounting, launch and stop commands.

## Planned experiments

Repeat the strongest configurations at representative problem sizes, test one-to-four-node scaling, and run the finalists for at least **1800 reported benchmark seconds** with the required memory footprint. Final results will need measured energy, clearly labelled GFLOP/s/W, reproducible scripts and presentation material.

The [controller guide](docs/hpcg/autotuning-controller.md) describes selection, budget accounting, provenance, validation and emergency stopping. Repository templates retain submission-disabled defaults; this documentation update does not change any campaign or enable submissions.

The automation is based on [Rory's CIUK project](https://github.com/roryhory/ciuk-2026-epcc). HPCG itself comes from the [official benchmark repository](https://github.com/hpcg-benchmark/hpcg).
