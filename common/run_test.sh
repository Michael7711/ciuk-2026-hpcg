#!/bin/bash

#SBATCH --job-name=hpl_smoke
#SBATCH --account=tc079-abszero
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:05:00
#SBATCH --qos=short
#SBATCH --partition=standard
#SBATCH --output=hpl_smoke_%j.out
#SBATCH --error=hpl_smoke_%j.err

srun ../hpl/hpl/hpl_test 1000
