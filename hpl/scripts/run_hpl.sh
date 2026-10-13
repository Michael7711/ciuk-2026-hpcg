#!/bin/bash
#SBATCH --job-name=hpl
#SBATCH --account=tc079-abszero
#SBATCH --partition=standard
#SBATCH --qos=short
#SBATCH --time=00:05:00

set -e
set -u
set -o pipefail

if [ "$#" -ne 4 ]; then
    echo "Usage: $0 <input_file> <nodes> <mpi_ranks> <omp_threads>"
    exit 1
fi

INPUT_FILE="$1"
NODES="$2"
MPI_RANKS="$3"
OMP_THREADS="$4"

RUN_ID="HPL-${SLURM_JOB_NAME#hpl_}-${SLURM_JOB_ID}"

REPO_ROOT=/epccfs/tc079/tc079/shared/ciuk-2026-epcc
HPL_ROOT="$REPO_ROOT/hpl"
HPL_BINARY="$HPL_ROOT/hpl-2.3/bin/Cirrus/xhpl"

RAW_DIR="$HPL_ROOT/results/raw"
WORK_ROOT="$HPL_ROOT/results/work"

WORK_DIR="$WORK_ROOT/$RUN_ID"
RAW_OUTPUT="$RAW_DIR/${RUN_ID}.out"
RAW_ERROR="$RAW_DIR/${RUN_ID}.err"

export OMP_NUM_THREADS="$OMP_THREADS"

mkdir -p "$RAW_DIR"
mkdir -p "$WORK_DIR"

cp "$INPUT_FILE" "$WORK_DIR/HPL.dat"

cd "$WORK_DIR"

echo "Starting $RUN_ID"
echo "Nodes:       $NODES"
echo "MPI ranks:   $MPI_RANKS"
echo "OMP threads: $OMP_THREADS"
echo "Input:       $INPUT_FILE"
echo

srun \
    --nodes="$NODES" \
    --ntasks="$MPI_RANKS" \
    --cpus-per-task="$OMP_THREADS" \
    --cpu-bind=cores \
    "$HPL_BINARY" \
    > "$RAW_OUTPUT" \
    2> "$RAW_ERROR"