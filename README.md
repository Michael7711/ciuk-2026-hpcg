# CIUK 2026 - HPCG

My work on the HPCG benchmark for the CIUK 2026 EPCC Cluster Challenge, using Cirrus. The aim is to improve performance and energy efficiency, then demonstrate scaling from one to four nodes with reproducible results.

## Completed experiments

- Built and validated an HPCG 3.1 reference implementation with Cray CCE 19.
- Compared problem sizes and MPI/OpenMP layouts on one Cirrus node. A larger reference run reached **134.124 GFLOP/s** with 288 MPI ranks, one thread per rank and **231.733 GB** of reported data memory.
- Developed a Python and Slurm optimisation controller; all **41 automated tests passed on Cirrus**.
- Verified automatic job chaining with jobs **558642 → 558643**, including stopping at the two-trial limit.
- Compiled and numerically validated GCC 14 (**558644**), AOCC 5 (**558647**) and CCE 19 without fast math (**558649**).

These are **diagnostic results**, not official competition results. The compiler and chaining smoke tests used deliberately small problems to check that the workflow works; their performance ratings should not be used to choose the final compiler.

Settings, measurements, validation status and campaign locations are recorded in the [experiment log](docs/hpcg/experiment_log.md).

## Current work: overnight optimisation

The next stage is unattended diagnostic optimisation on Cirrus. Rather than manually submitting each run, the controller records a result, uses the measurements to select the next experiment and submits its successor through Slurm. It screens compilers under matching conditions, then explores promising MPI/OpenMP layouts and active CPU utilisation. Repeated measurements help distinguish a useful improvement from run-to-run variation.

The performance search will use realistic, memory-resident HPCG problems, with approximately comparable equation counts during CPU-layout comparisons. Every submitted allocation counts towards a fixed campaign reservation cap, including pending and failed jobs. The controller stops at its limits or on a critical failure. Short diagnostic runs let us narrow the choices before spending the budget on official runs of at least 30 minutes.

The overnight campaign's live settings and Slurm job ID have **not yet been verified** for this update, so they are not listed here. The overnight optimisation is not recorded as completed. The controller workflow itself has been tested successfully.

Whole-job Slurm energy can include compilation, setup and teardown; it is not necessarily benchmark-window energy. The current controller optimises **GFLOP/s**, with energy-efficiency optimisation deferred until an appropriate measurement window is verified.

## Planned experiments

Repeat the strongest configurations at representative problem sizes, test one-to-four-node scaling, and run the finalists for at least **1800 reported benchmark seconds** with the required memory footprint. Final results will need measured energy, clearly labelled GFLOP/s/W, reproducible scripts and presentation material.

The [controller guide](docs/hpcg/autotuning-controller.md) describes selection, budget accounting, provenance, validation and emergency stopping. Repository templates retain submission-disabled defaults; this documentation update does not change any campaign or enable submissions.

The automation is based on [Rory's CIUK project](https://github.com/roryhory/ciuk-2026-epcc). HPCG itself comes from the [official benchmark repository](https://github.com/hpcg-benchmark/hpcg).
