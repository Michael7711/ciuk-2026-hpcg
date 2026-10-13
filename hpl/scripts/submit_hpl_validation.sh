#!/bin/bash

set -e
set -u


REPO_ROOT=/epccfs/tc079/tc079/shared/ciuk-2026-epcc
HPL_ROOT="$REPO_ROOT/hpl"

RUN_SCRIPT="$HPL_ROOT/scripts/run_hpl_validation.sh"
RECORDER="$HPL_ROOT/scripts/record_hpl_result.py"

CSV_FILE="$HPL_ROOT/results/hpl_runs.csv"
INPUT_FILE="$HPL_ROOT/inputs/HPL_validation.dat"


# Submit HPL benchmark job and capture job ID
JOB_ID=$(sbatch --parsable "$RUN_SCRIPT")

RUN_ID="HPL-validation-${JOB_ID}"
RAW_OUTPUT="$HPL_ROOT/results/raw/${RUN_ID}.out"


echo "Submitted HPL job: $JOB_ID"


# Submit a tiny dependent post-processing job.
# It runs only if the HPL job completed successfully.
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
        --nodes 1 \
        --mpi-ranks 4 \
        --omp-threads 1 \
        --compiler 'PrgEnv-cray' \
        --compiler-flags=-O3 \
        --purpose 'validation' \
        --input-file '$INPUT_FILE' \
        --repo-root '$REPO_ROOT'"
)

echo "Submitted recorder job: $RECORD_JOB_ID"
echo "Recorder depends on HPL job $JOB_ID completing successfully."
