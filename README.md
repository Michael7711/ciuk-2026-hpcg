# CIUK 2026 - HPCG

My work on the HPCG benchmark for the CIUK 2026 EPCC Cluster Challenge, using Cirrus.

I'm testing different problem sizes, MPI/OpenMP configurations and node counts to see how they affect performance and energy use.

The experiments use Slurm and Python scripts to automate runs and collect results.

Experiment notes are in [docs/hpcg](docs/hpcg/experiment_log.md).

The automation is based on [Rory's CIUK project](https://github.com/roryhory/ciuk-2026-epcc). HPCG itself comes from the [official benchmark repository](https://github.com/hpcg-benchmark/hpcg).
