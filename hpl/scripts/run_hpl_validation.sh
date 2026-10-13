#!/bin/bash

#SBATCH --job-name=hpl_validation
#SBATCH --account=tc079-abszero
#SBATCH --partition=standard
#SBATCH --qos=short

#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=1

#SBATCH --time=00:05:00

#SBATCH --output=/epccfs/tc079/tc079/shared/ciuk-2026-epcc/hpl/results/slurm/hpl_validation_%j.out
#SBATCH --error=/epccfs/tc079/tc079/shared/ciuk-2026-epcc/hpl/results/slurm/hpl_validation_%j.err


set -u
set -o pipefail


REPO_ROOT=/epccfs/tc079/tc079/shared/ciuk-2026-epcc
HPL_ROOT="$REPO_ROOT/hpl"

HPL_BINARY="$HPL_ROOT/hpl-2.3/bin/Cirrus/xhpl"
INPUT_FILE="$HPL_ROOT/inputs/HPL_validation.dat"

RAW_DIR="$HPL_ROOT/results/raw"
WORK_ROOT="$HPL_ROOT/results/work"

export OMP_NUM_THREADS=1

RUN_ID="HPL-validation-${SLURM_JOB_ID}"
WORK_DIR="$WORK_ROOT/$RUN_ID"

RAW_OUTPUT="$RAW_DIR/${RUN_ID}.out"
RAW_ERROR="$RAW_DIR/${RUN_ID}.err"


mkdir -p "$RAW_DIR"
mkdir -p "$WORK_DIR"

cp "$INPUT_FILE" "$WORK_DIR/HPL.dat"

cd "$WORK_DIR"

echo "Starting $RUN_ID"
echo "Nodes:       $SLURM_JOB_NUM_NODES"
echo "MPI ranks:   $SLURM_NTASKS"
echo "OMP threads: $OMP_NUM_THREADS"
echo

srun --cpu-bind=cores "$HPL_BINARY" \
    > "$RAW_OUTPUT" \
    2> "$RAW_ERROR"
