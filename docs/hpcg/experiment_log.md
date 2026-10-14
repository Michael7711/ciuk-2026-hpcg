# CIUK Cluster Challenge 2026 – HPCG Benchmark

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

### Next experiment

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
