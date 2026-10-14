#!/bin/bash

set -e
set -u

if [ "$#" -ne 5 ]; then
    echo "Usage: $0 <input_file> <nodes> <mpi_ranks> <omp_threads> <purpose>"
    echo
    echo "Example:"
    echo "$0 hpl/inputs/HPL_1node_baseline.dat 1 288 1 baseline"
    exit 1
fi

INPUT_ARG="$1"
NODES="$2"
MPI_RANKS="$3"
OMP_THREADS="$4"

if (( MPI_RANKS % NODES != 0 )); then
    echo "MPI ranks ($MPI_RANKS) must be divisible by nodes ($NODES)"
    exit 1
fi

if [ ! -f "$INPUT_FILE" ]; then
    echo "Input file not found: $INPUT_FILE"
    exit 1
fi

if (( MPI_RANKS % NODES != 0 )); then
    echo "MPI ranks ($MPI_RANKS) must be divisible by nodes ($NODES)"
    exit 1
fi

TASKS_PER_NODE=$((MPI_RANKS / NODES))

P=$(awk '$2 == "Ps" {print $1; exit}' "$INPUT_FILE")
Q=$(awk '$2 == "Qs" {print $1; exit}' "$INPUT_FILE")

if [[ -z "$P" || -z "$Q" ]]; then
    echo "Could not read P and Q from input file: $INPUT_FILE"
    exit 1
fi

if (( P * Q != MPI_RANKS )); then
    echo "Invalid HPL configuration:"
    echo "  P × Q = $P × $Q = $((P * Q))"
    echo "  MPI ranks = $MPI_RANKS"
    exit 1
fi

PURPOSE="$5"

REPO_ROOT=/epccfs/tc079/tc079/shared/ciuk-2026-epcc
HPL_ROOT="$REPO_ROOT/hpl"

RUN_SCRIPT="$HPL_ROOT/scripts/run_hpl.sh"
RECORDER="$HPL_ROOT/scripts/record_hpl_result.py"
CSV_FILE="$HPL_ROOT/results/hpl_runs.csv"

if [[ "$INPUT_ARG" = /* ]]; then
    INPUT_FILE="$INPUT_ARG"
else
    INPUT_FILE="$REPO_ROOT/$INPUT_ARG"
fi

if [ ! -f "$INPUT_FILE" ]; then
    echo "Input file not found: $INPUT_FILE"
    exit 1
fi

JOB_ID=$(sbatch \
    --parsable \
    --account=tc079-abszero \
    --partition=standard \
    --qos=standard \
    --nodes="$NODES" \
    --ntasks="$MPI_RANKS" \
    --ntasks-per-node="$TASKS_PER_NODE" \
    --cpus-per-task="$OMP_THREADS" \
    --exclusive \
    --time=00:10:00 \
    --job-name="hpl_${PURPOSE}" \
    --output="$HPL_ROOT/results/slurm/hpl_${PURPOSE}_%j.out" \
    --error="$HPL_ROOT/results/slurm/hpl_${PURPOSE}_%j.err" \
    "$RUN_SCRIPT" \
    "$INPUT_FILE" \
    "$NODES" \
    "$MPI_RANKS" \
    "$OMP_THREADS"
)

RUN_ID="HPL-${PURPOSE}-${JOB_ID}"
RAW_OUTPUT="$HPL_ROOT/results/raw/${RUN_ID}.out"

echo "Submitted HPL job: $JOB_ID"
echo "Run ID: $RUN_ID"

RECORD_JOB_ID=$(sbatch \
    --parsable \
    --dependency=afterok:$JOB_ID \
    --account=tc079-abszero \
    --partition=standard \
    --qos=short \
    --ntasks=1 \
    --cpus-per-task=1 \
    --time=00:02:00 \
    --job-name="record_${JOB_ID}" \
    --output="$HPL_ROOT/results/slurm/record_${JOB_ID}_%j.out" \
    --error="$HPL_ROOT/results/slurm/record_${JOB_ID}_%j.err" \
    --wrap="python3 '$RECORDER' \
        --job-id '$JOB_ID' \
        --run-id '$RUN_ID' \
        --output '$RAW_OUTPUT' \
        --csv '$CSV_FILE' \
        --nodes '$NODES' \
        --mpi-ranks '$MPI_RANKS' \
        --omp-threads '$OMP_THREADS' \
        --compiler 'PrgEnv-cray' \
        --compiler-flags=-O3 \
        --purpose '$PURPOSE' \
        --input-file '$INPUT_FILE' \
        --repo-root '$REPO_ROOT'"
)

echo "Submitted recorder job: $RECORD_JOB_ID"
echo "Recorder depends on HPL job $JOB_ID completing successfully."
