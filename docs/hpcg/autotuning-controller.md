# HPCG campaign controller

Status: 15 October 2026. The Python/Slurm controller has passed all 41 automated tests on Cirrus, completed a two-job chaining test, and compiled and validated the GNU, AOCC and CCE strict recipes. The initial overnight campaign has also completed nine VALID diagnostics. Its best single result, 135.342 GFLOP/s at CCE reference 144×1, is an unconfirmed 0.31% above the repeated 288×1 baseline; it still needs repeat measurements. No official 30-minute result is claimed. Detailed settings and measurements are in the [experiment log](experiment_log.md).

## Cirrus environment and tested builds

Read-only inspection used the existing `ssh cirrus` session. A non-login shell does not expose `module`; use `bash --login` and `module load python/3.11.7`. The system Python is 3.9; the controller needs Python 3.11 or newer (`tomllib`).

| Environment | Compiler version | Recipe and validation |
|---|---|---|
| Cray | CCE 19.0.0 | Reference: `-O3 -ffast-math -fopenmp`; strict: `-O3 -fopenmp`, compiled and VALID in job 558649 |
| GNU | GCC 14.2.1 (`gcc-native/14.2`) | `CC`, `-O3 -ffast-math -fopenmp`; compiled and VALID in job 558644 |
| AMD | AOCC 5.0.0 (clang 17.0.6) | `CC`, `-O3 -ffast-math -fopenmp`; compiled and VALID in job 558647 |
| Intel | oneAPI DPC++/C++ 2025.0.4 | Wrapper availability checked only; disabled in the initial template and not benchmark-validated |

GNU, AOCC and CCE strict have now passed isolated compilation and HPCG numerical validation on Cirrus. The compiler smoke tests check the toolchain and run path; their tiny problem sizes do not establish the best compiler for a representative workload. Lmod automatically replaces the previous compiler/programming environment. New builds use the Cray `CC` MPI wrapper, preserve MPI and OpenMP, and run the existing `configure MPI_GCC_OMP` out of tree. That architecture name is only a setup-template name: the recipe overrides its `mpicxx`, compiler flags and link flags. Existing template GCC vectorisation flags had already been removed for CCE compatibility. No external BLAS requirement was found for this reference build.

Reference source: `/epccfs/tc079/tc079/shared/hpcg`, commit `114602d458d1034faa52b71e4c15aba9b3a17698`, with a modified `setup/Make.MPI_GCC_OMP`. The controller hashes the actual source/templates, including that edit, rather than trusting only the commit. It excludes existing build/run directories.

Reference binary: `build/bin/xhpcg`, SHA-256 `1ecfef30466d29e1a5f830d4f9bb7a0f431b1d3d77b14c953ee3a460899321de`. Linked libraries include Cray MPI 8.1.32 and CCE's `libcraymp`. The historical 288-rank, one-thread, 104³-local-grid result reports 134.124 GFLOP/s, 231.733 GB of data, four passed validation tests, and 134.952 seconds of benchmark time. It is numerically valid but too short for final submission.

Cirrus reports 288 allocatable physical CPUs and 744768 MiB of schedulable memory on standard nodes. Slurm's virtual socket layout reports 8 × 36; the physical architecture is two 144-core EPYC 9825 processors, eight NUMA domains and 24 twelve-core CCDs. Never infer physical sockets from `scontrol` alone. The inspected account permits `short` (20 minutes) and `standard` (48 hours) QoS. The earlier documentation check at approximately 02:27 BST preceded the overnight launch; the completed sequence is now recorded below. Queue observations are dated snapshots, not a live display.

Sources: [Cirrus hardware](https://docs.cirrus.ac.uk/user-guide/hardware/), [compiler environments](https://docs.cirrus.ac.uk/user-guide/development/), [HPCG official requirements](https://www.hpcg-benchmark.org/faq/index.html), [Slurm deadline semantics](https://slurm.schedmd.com/sbatch.html#OPT_deadline).

## Completed controller validation

The 41 automated tests passed on Cirrus. The live chaining campaign then ran **558642 → 558643** and stopped at `max_trials`. Separate GNU (**558644**), AOCC (**558647**) and CCE strict (**558649**) campaigns compiled their executables, passed all four HPCG V&V checks and stopped at their one-trial limits. Slurm records all five jobs as `COMPLETED`.

Results, selection reasons, validation status and executable provenance are retained in the corresponding campaign directories. The [completed-experiment records](experiment_log.md#experiment-5-autonomous-controller-and-job-chaining--completed) contain the measurements and paths. These canaries established the small-problem workflow before the representative overnight campaign. They do not validate every recovery path or replace longer competition runs.

Repository templates still default to `allow_submit=false`. The completed canaries and overnight campaign used their own explicitly enabled settings on Cirrus; those settings are not a blanket submission gate for other campaigns. The current controller optimises performance. It rejects efficiency and alternating objectives because a suitable benchmark-window measurement has not been verified. HPL's existing whole-job energy reporting remains available with its scope labelled explicitly.

## Controller and budget semantics

Use `python3 -m autotune.campaign` (Python 3.11+). The legacy HPL commands remain separate. The new controller reuses the existing input/job renderer, hardware layout generator, result parser and binary hashes. It uses only the standard library.

`init` freezes settings, controller code and actual HPCG source/templates; only `safety.allow_submit` may change later. State belongs under the shared `state_prefix`. One canonical state directory is one campaign. Do not copy an active ledger or delete trials to reset its budget.

Each worker runs one experiment inside its Slurm allocation, records it and selects a successor. No login-node daemon is required. Builds use private campaign directories, the Cray `CC` wrapper and the existing `configure MPI_GCC_OMP` template with explicit compiler/linker overrides. Build manifests record compiler modules, flags, source hash, libraries and executable hash. The hash cannot change within a build identity during a campaign.

The hard **campaign cap** is configurable up to 500 core-hours. Every durable submission intent is charged for its full exclusive-node allocation, including pending, running, completed, failed, cancelled and ambiguous submissions. Reservations are never refunded. Idle cores in under-populated layouts still cost 288 cores per node. Build timeout, benchmark runtime, setup margin, controller margin and Slurm minute rounding are included. A scheduler-visible increase in a campaign allocation is included in exposure; if exposure exceeds the cap the controller stops and requests cancellation of live campaign jobs.

Admission is locked across reconciliation, reservation persistence and submission. The intent is written atomically **before** `sbatch`. Simultaneous controllers using the same ledger cannot reserve the same remaining allowance twice. Ambiguous submission responses remain charged and are reconciled by unique token, never blindly retried. An automated concurrency regression verifies one submission and bounded reservation under competing calls. The completed canary chain and nine-job overnight campaign exercised the shared ledger and successor submission on Cirrus. Automated tests cover competing admissions; deliberate live lock contention and crash-recovery tests have not been performed.

Status separates these quantities:

| Field | Meaning |
|---|---|
| `campaign_reserved_core_hours` | Durable campaign reservations, conservatively increased by matching scheduler exposure |
| `campaign_cap_core_hours` | Hard admission allowance for this ledger |
| `other_submitting_user_job_exposure_core_hours` | Diagnostic exposure for other jobs visible for this user/account; unavailable without a scheduler snapshot |
| `scheduler_scope` | Explicitly `submitting_user_and_account_only` |
| `team_safe_balance_estimate_core_hours` | User-provided estimate (template: 4908.5), not an authoritative live balance |
| `team_safe_balance_verified` | Always false: no SAFE integration exists |

Other jobs are not silently conflated with the campaign allowance. **The controller cannot guarantee the team's shared SAFE balance across teammates or independent ledgers.** Agree each campaign/canary allowance with the team and check SAFE before authorising execution. If canaries count towards the initial 500 hours, subtract their allocated caps from the subsequent tuning cap. Do not authorise multiple independent 500-hour ledgers against one allowance. Concurrent jobs belonging to this ledger are all charged; other users' allocations require external coordination.

Scheduler queries are read-only and user/account scoped. `sacct` allocation fields may be zero/blank while pending; the controller first joins `squeue` by job ID and uses its requested node count and wall limit. If a record is temporarily absent from the queue, bounded `ReqNodes`/time-limit data can retain its reservation. If neither source bounds it, reconciliation blocks submission without labelling the job failed. A cancelled, never-allocated external job with zero elapsed time has zero actual cost. Queue/accounting command failures block progress.

Pending jobs have a Slurm finish deadline: the earlier of the campaign deadline and selection time + pending timeout + allocation duration. Expiry stops the chain because no worker starts to submit a successor. Inspection/resume is required. Automatic requeue is disabled; do not manually requeue campaign jobs.

Sources for pending/resource behavior: [Slurm accounting fields](https://slurm.schedmd.com/sacct.html#SECTION_Job-Accounting-Fields), [queue fields](https://slurm.schedmd.com/squeue.html), [deadline semantics](https://slurm.schedmd.com/sbatch.html#OPT_deadline).

## Small-budget adaptive strategy

The default design has four enabled builds: CCE reference, CCE without fast math, GNU fast math and AOCC fast math. Intel remains disabled. Layouts cover 72, 144 and 288 active cores and OpenMP counts 1/2/4/6/12, with hardware-aligned core shares. Reference workload: 323960832 equations per node, within 2.5% total-volume tolerance. Memory estimates use an explicit safety margin and an 80% schedulable-memory ceiling.

The decision process is deliberately small:

1. Run each build at a common hardware anchor (normally 288×1) for each configured node count. Compare builds only when the anchor's layout, problem dimensions, duration and kind match exactly.
2. Race observed anchor means separately for each node count. At the configured repeat interval, repeat the best/close anchor contenders to evaluate noise. The close band uses a 2% provisional floor and expands to twice the observed coefficient of variation when repeats exist.
3. Spend subsequent trials on unseen neighbouring layouts of the observed winning build, searching near that build's best measured configuration. Report repeat means and sample standard deviations. Selection reasons include the winning build, number of matched anchors, observed performance and search pivot.
4. Fall back explicitly to hardware exploration when no affordable measured neighbourhood remains. All choices remain subject to reservation and repeat limits. Failed candidates are excluded permanently from automatic selection.

No response model pools measurements from different executable builds. Build comparison is an explicit matched experiment, not fitting one function to mixed binaries. Node counts race independently, so the chosen compiler/layout may differ at 1, 2 and 4 nodes. Keep `nodes=[1]` for the small initial design, or choose the desired counts **before init**. Weak scaling keeps equations per node approximately constant; strong scaling keeps total equations approximately constant and may violate final per-node memory requirements on larger node counts.

A **synthetic automated test**, using the actual default reservation rules, screens four builds and then makes result-driven repeat/local-search decisions in seven trials totalling **489.6 reserved core-hours**. It also flips supplied anchor measurements and verifies that the chosen build changes. This earlier seven-trial synthetic fixture is separate from the nine-job overnight campaign. Their identical 489.6-hour reservation totals do not make the synthetic data a measured result; the actual campaign used different time allowances.

Limitations: one anchor per compiler is a noisy, layout-specific screen. A compiler that loses at 288×1 could win at a different hybrid layout; this small-budget strategy can miss it. The local search is not globally optimal and the close band is not a formal confidence interval. Repeats reduce uncertainty but do not establish causal explanations. The initial budget cannot thoroughly cover all builds, layouts and node counts; use later, separately authorised focused comparisons for promising alternatives and scaling.

## Completed overnight campaign: 15 October 2026

The initial unattended campaign ran **02:30:45–03:10:28 BST**, completing **nine VALID diagnostic HPCG runs** on one exclusive node. Its ledger is `/epccfs/tc079/tc079/shared/hpcg/runs/tc079cheu1/campaign-overnight-20261015-01/state.json`; its settings are `controller-review/work/overnight-20261015.toml` under the same user run root. The settings values were verified against the frozen ledger hash. The first job was **558650** and the last was **558660**; [Experiment 7](experiment_log.md#experiment-7-overnight-adaptive-campaign--completed) records every job and measurement.

The campaign used a performance objective, 120 requested benchmark seconds, a target of 323960832 equations per node and a 2.5% volume tolerance. Reported data memory was approximately 229–232 GB, rather than the sub-gigabyte canary problems. The enabled builds were CCE reference, CCE strict, GCC 14 and AOCC 5. The search allowed OpenMP counts 1/2/4/6/12 and CPU fill fractions 1, 0.5 and 0.25, with up to two measurements per candidate.

The selection log shows the intended adaptive behavior in practice:

1. Four matched 288×1, 104³-local-grid compiler anchors screened the builds.
2. A repeat of CCE reference produced a **134.918 GFLOP/s** baseline mean from jobs 558650 and 558656. The four anchors were within the provisional 2% close band.
3. The controller focused on CCE reference and tried **144×1** (558657), then used its **135.342 GFLOP/s** observation as the pivot for **144×2** (558658) and **72×1** (558659).
4. It repeated GNU (558660) to investigate variation. The GNU anchor pair averaged 134.051 GFLOP/s, compared with 133.793 for the single AOCC anchor and 132.918 for the single CCE strict anchor.

Job 558657 is a candidate improvement, not a confirmed speedup. The **0.31%** comparison uses a single 144×1 observation against a two-run baseline. The candidate also had about **0.96% fewer equations** and a different decomposition. The compiler screen likewise has too few repeats to establish a general ranking, and losing builds were not explored across all hybrid layouts. The next work is repeated, closely matched candidate-versus-baseline measurements.

### Budget and stopping evidence

The campaign had a **500-core-hour reservation cap**, a maximum of twelve trials, and a **10:00 BST deadline**. Its 120-second diagnostics used 420 seconds of overhead allowance and 60 seconds of controller margin; recipe builds also reserved a 180-second compile timeout. This gave 48 core-hours per CCE-reference trial and 62.4 per other-build trial, including repeats.

The nine trials retained **489.6 core-hours of reservations**. Job 558660's output records `candidate/repeat or remaining budget limit`: only **10.4 core-hours** remained, below the 48-hour minimum next reservation. This was a clean admission-budget stop, not a failed result, trial-limit stop or deadline expiry.

Actual allocation usage from the nine allocation-level Slurm records was **190.16 core-hours**: `2377 elapsed seconds × 288 allocated CPUs / 3600`. Idle cores in the 144×1 and 72×1 layouts remained part of whole-node allocations. Actual usage includes work outside the timed solve; it is not the benchmark-only compute cost or a verified team SAFE debit. The ledger's reservations were not refunded to extend the campaign automatically.

### Diagnostic and energy limits

All reported benchmark windows were approximately **132–136 seconds**, below 1800 seconds. Numerical VALID status does not make these official competition results. Short diagnostics allowed compiler/layout screening and noise checks before committing the resources for final 30-minute benchmarks.

Slurm's nine whole-job energy readings sum to **2337351 J**. They include startup, setup, controller work and compilation where performed, so they are not benchmark-window energy. Every result records benchmark-window energy as unavailable and leaves benchmark GFLOP/s/W unreported. Reduced configured CPU utilisation alone does not demonstrate an energy-efficiency improvement. The campaign optimised measured performance only.

## Results, energy and validation

Fresh run directories retain inputs, provenance, compiler/build manifests, Slurm output and `result.json`. The state ledger records each decision and reservation. The controller preserves earlier result files; historical experiment notes are maintained separately in the experiment log. `status` reports grouped means/standard deviations; `status --scheduler` adds current user-scoped scheduler exposure and whole-job energy.

A usable HPCG result needs successful process exit, one fresh summary, finite positive performance, all four passed V&V checks, matching ranks/threads/local grid, plausible runtime and safe reported data memory. Invalid or incomplete results are recorded as failed and create `STOP` before any successor submission. Failed Slurm jobs discovered during reconciliation also block the chain. There is no automatic failure retry.

Final eligibility additionally checks at least 1800 **reported** benchmark seconds and at least one quarter of nominal physical memory in reported data. A 4-node 30-minute solve alone costs at least 576 core-hours; final scaling requires a separately reviewed budget and procedure.

HPL retains its previous whole-job efficiency calculation, explicitly labelled with `energy_status=whole_job` and `energy_source=sacct`. Low-resolution or missing readings still withhold efficiency. CSV columns and append behavior remain compatible.

HPCG's whole-job energy remains diagnostic; no GFLOP/s/W is derived from it. Existing counter wrappers enclose the benchmark **process** (setup plus solve), not exactly the timed solver window. Any recorded counter value retains that scope; multi-node efficiency remains guarded as unverified. Neither such process readings nor a supplied path enable an efficiency objective. Enabling energy optimisation needs a separately implemented and verified measurement contract. No benchmark-window source is currently verified.

## Completed canaries and reproducing the checks

The following commands reproduce the settings-generation step for the completed checks; the job IDs and outcomes below refer to the runs already recorded on Cirrus. These commands create local settings only. They never build, contact Slurm, submit, or enable submission. Run from the repository using Python 3.11+:

```sh
python3 -m unittest discover -s tests -v
mkdir -p work
python3 -m autotune.campaign smoke-settings --settings autotune/clusters/cirrus-hpcg-campaign.toml --purpose chain --output work/chain-smoke.toml
python3 -m autotune.campaign smoke-settings --settings autotune/clusters/cirrus-hpcg-campaign.toml --purpose build --build gnu14-fast --output work/gnu-build-smoke.toml
python3 -m autotune.campaign smoke-settings --settings autotune/clusters/cirrus-hpcg-campaign.toml --purpose build --build aocc5-fast --output work/aocc-build-smoke.toml
python3 -m autotune.campaign smoke-settings --settings autotune/clusters/cirrus-hpcg-campaign.toml --purpose build --build cce19-strict --output work/cce-strict-build-smoke.toml
```

All generated configs have `allow_submit=false`, performance objective, fresh baseline/deadline, and a tiny 10-second diagnostic workload. They refuse to overwrite existing files. Regenerate timestamps before actual deployment.

| Completed check | Jobs and result | Layout | Full reservation | Hard cap |
|---|---|---|---|---|
| Chain | 558642 → 558643; both VALID, stopped at two trials | Reference 288×1, local 16³ | 19.2 core-hours total | 20 |
| GNU build | 558644; compilation succeeded, VALID | 144×2, local 16³ | 57.6 core-hours | 60 |
| AOCC build | 558647; compilation succeeded, VALID | 144×2, local 16³ | 57.6 core-hours | 60 |
| CCE strict build | 558649; compilation succeeded, VALID | 144×2, local 16³ | 57.6 core-hours | 60 |

The chain reserves two minutes per job. Each build canary reserves twelve minutes including a ten-minute build timeout, 90-second benchmark overhead and 20-second controller margin. These tiny runs test mechanics and validation, not representative performance, energy or final eligibility. The completed chain and compiler tests establish this small-problem path. Longer diagnostics are still needed to assess representative performance and memory use.

The completed ledgers are `campaign-chain-01`, `campaign-gnu-01`, `campaign-aocc-01` and `campaign-cce-strict-01` under `/epccfs/tc079/tc079/shared/hpcg/runs/tc079cheu1/`. The deployed controller is under `controller-review/` in that same directory. Each run retains `result.json`, `build.json`, `provenance.json`, `compiler.txt`, loaded-module information and raw HPCG output. Build directories retain the recipe, executable and its hash. These records were checked read-only for this documentation update.

Do not overwrite or reinitialise the completed campaign directories. A new campaign needs its own reviewed settings, ledger and budget allowance. Generated canary settings do not authorise any further campaign; the completed overnight run used its own campaign-specific settings. Both an explicitly enabled settings gate and `tick --submit` are required for a new launch; this documentation update does neither.

## Stop and explicit recovery

For an authorised future campaign, emergency stop creates a shared sentinel and cancels only its matching jobs:

```sh
python3 -m autotune.campaign stop --state "$HPCG_STATE"
```

Workers check `STOP` once per second. If scheduler access or locking fails, the sentinel remains. Manual fallback: `touch "$HPCG_STATE/STOP"`, inspect `status`, and cancel only verified campaign IDs. Never cancel all of the user's jobs.

Inspect failed trials and scheduler state before resuming. A normal `resume --submit` cannot clear an unacknowledged failure. After explicit human inspection, the recovery command is:

```sh
python3 -m autotune.campaign resume --state "$HPCG_STATE" --submit --acknowledge-failures
```

This records the acknowledgement, retains every reservation, excludes failed candidates from future automatic choices, and does not rerun failed trials. Partial builds require inspection; the controller does not delete them. Stop/review/reconfigure in a new budgeted campaign if the source, code or experimental settings must change.

An ambiguous `sbatch` response retains an intent and reservation. Reconcile against the scheduler first. Only after confirming absence with healthy scheduler/accounting data may a human use `abandon --state ... --token ...`; this retains cost and cannot abandon a visible live job. It is not an automatic retry mechanism.

## Current work and planned final benchmarking

The single-node canaries and initial representative overnight campaign are completed. The next task is to repeat the 144×1 CCE reference candidate against the 288×1 baseline with closely matched workloads and interleaved order. The apparent 0.31% gain remains unconfirmed. Follow-up work will examine other promising compiler/layout combinations and one-to-four-node scaling; a one-node optimum is not assumed to transfer unchanged.

The overnight run demonstrated a clean no-fit reservation-budget stop. Deadline expiry, live pending-job edge cases, deliberate failure/crash recovery and simultaneous live admissions have not all been demonstrated by these successful runs. Automated tests cover the safeguards, but do not prove every site-specific failure mode.

Final competition runs need at least 1800 reported benchmark seconds, the required memory footprint and reproducible performance/energy evidence. Benchmark-window instrumentation and multi-node energy aggregation still require verification; SAFE remains an external team check. The final results, scripts and presentation material will be assembled from qualifying measurements. No official 30-minute result or running follow-up campaign is claimed in the current records.
