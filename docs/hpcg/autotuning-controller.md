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

The initial **adaptive campaign cap** remains configurable up to 500 core-hours. The separate, explicit `mode="sequence"` supports a reviewed larger cap for official-duration 1/2/4-node runs; it admits only a predefined final weak-scaling sequence whose entire worst-case reservation fits that cap. Merely changing an adaptive campaign to `kind="final"` does not remove its 500-hour guard. Every durable submission intent is charged for its full exclusive-node allocation, including pending, running, completed, failed, cancelled and ambiguous submissions. Reservations are never refunded. Idle cores in under-populated layouts still cost 288 cores per node. Build timeout, benchmark runtime, setup margin, controller margin and Slurm minute rounding are included. A scheduler-visible increase in a campaign allocation is included in exposure; if exposure exceeds the cap the controller stops and requests cancellation of live campaign jobs.

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

Slurm's nine whole-job energy readings sum to **2337351 J**. They include startup, setup, controller work and compilation where performed, so they are not benchmark-window energy. The original results still record benchmark-window energy as unavailable. Recovered `.0` wrapper-step readings now support separately labelled estimates: 144×1 gives 0.1461 and 72×1 gives 0.1570 estimated GFLOP/s/W. These are performance divided by step-average power, not timed benchmark-window efficiency; the [nine-job energy table](experiment_log.md#recovered-slurm-step-energy-analysis--15-october-2026) preserves all measurements and the method. Reduced CPU utilisation alone proves neither energy savings nor the best layout. The campaign optimised measured performance only.

## Results, energy and validation

Fresh run directories retain inputs, provenance, compiler/build manifests, Slurm output and `result.json`. The state ledger records each decision and reservation. The controller preserves earlier result files; historical experiment notes are maintained separately in the experiment log. `status` reports grouped means/standard deviations; `status --scheduler` adds current user-scoped scheduler exposure and whole-job energy.

A usable HPCG result needs successful process exit, one fresh summary, finite positive performance, all four passed V&V checks, matching ranks/threads/local grid, plausible runtime and safe reported data memory. Invalid or incomplete results are recorded as failed and create `STOP` before any successor submission. Failed Slurm jobs discovered during reconciliation also block the chain. There is no automatic failure retry.

Final eligibility additionally checks at least 1800 **reported** benchmark seconds and at least one quarter of nominal physical memory in reported data. A 4-node 30-minute solve alone costs at least 576 core-hours. The disabled sequence proposal below supplies a separate final-scaling budget and procedure.

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

The chain reserves two minutes per job. Each build canary reserves twelve minutes including a ten-minute build timeout, 90-second benchmark overhead and 20-second controller margin. These tiny runs test mechanics and validation, not representative performance, energy or final eligibility. The completed chain and compiler tests establish this small-problem path. The later overnight campaign assessed representative problems; official-duration and multi-node operation remain to be verified.

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


## Proposed official-duration sequence — not launched

`autotune/clusters/cirrus-hpcg-official-sequence.toml` is a **new disabled proposal**, separate from every completed campaign. It uses `mode="sequence"`, one prebuilt CCE reference executable with its verified SHA-256, and exactly three ordered experiments. The original adaptive template, compiler race, HPL renderer/parser/CSV workflow and historical campaigns remain separate. No submission has been enabled and no job ID exists for this proposal.

| Setting | Proposed value |
|---|---|
| Order / repeats | 1 → 2 → 4 nodes, exactly once each; `max_trials=3`, `repeats=1` |
| Build | `cce19-reference`, existing CCE 19.0.0 binary; no compilation |
| Per-node layout | 144 MPI ranks, 1 OpenMP thread/rank; 288 allocated cores/node, 2-core share/rank |
| Total MPI ranks | 144, 288, 576 |
| Local grid | 128×128×136 on every rank at every scale |
| Workload | 320864256 equations/node; totals 320864256, 641728512, 1283457024 |
| Duration / kind | 1860 requested benchmark seconds; `final` |
| Validation | >=1800 reported benchmark seconds; four V&V passes; matching rank/thread/grid counts; memory bounds |
| Memory | Previously observed 229.477 GB/node; minimum 206.158 GB/node; conservative peak estimate 360.972 GB/node |
| Scheduler | Exclusive standard partition, standard QoS; no requeue; same binding as tested diagnostics |
| Time reservation | 1860 benchmark + 600 setup allowance + 180 controller/accounting = 2640 s = 44 min/job |
| Pending timeout | 7200 s per successor; Slurm finish deadline also bounded by campaign deadline |
| Proposed cap / shared SAFE estimate | 1500 / 3721.9 core-hours; user-provided balance, not a live check |
| Submission | `allow_submit=false`; explicit `tick --submit` also required |

The file's `deadline=2026-10-16T18:00:00+00:00` is an editable template stop time (19:00 BST), **not the challenge deadline**. Review it and `budget_since` before init. Queue availability and the HPCG allowance must also be reviewed before launch. Read-only inspection confirmed the reference executable hash, standard QoS access and 744768 MiB scheduled memory per node. Generated scripts and guards have been tested locally; the new sequence itself has not run on Cirrus.

**Why 144×1:** it is the best observed diagnostic speed candidate and already has a representative numerically valid run. The 0.31% advantage over the repeated 288×1 baseline is unconfirmed. **72×1** is a credible energy-oriented alternative, with 2.61% less observed performance than 144×1 and a 7.47% higher Slurm-step efficiency estimate, but only one sample. Its alternative settings would be `sequence.ranks_per_node=72`, `sequence.local_grid=[152,168,176]`, `campaign.points_per_node=323592192`, and `campaign.fill=[0.25]`, before init; all node counts would then use that same layout. Do not switch layouts within one weak-scaling curve or launch both configurations against the one 1500-hour allowance. A full sequence for both would reserve 2956.8 core-hours, leaving only 765.1 of the stated shared balance and little room for HPL. The current proposal prioritises getting one valid scaling sequence first; matched repeats and configuration choices specific to each node count need a later reviewed allowance.

### Budget and progression

| Nodes | Allocated cores | Allocation limit | Worst-case reservation (core-hours) |
|---:|---:|---:|---:|
| 1 | 288 | 44 min | 211.2 |
| 2 | 576 | 44 min | 422.4 |
| 4 | 1152 | 44 min | 844.8 |
| Total | | 132 min serial allocation time | **1478.4** |

The calculation is `nodes × 288 × 2640 / 3600`; under-filled layouts still pay for every allocated core. The 1500-hour cap leaves 21.6 hours of ledger headroom and **2221.9 core-hours outside this allowance**, about 59.7% of the user-reported SAFE balance. Actual usage can be lower, but reservations are never refunded to admit more jobs. This cap does not reserve funds in SAFE or coordinate teammates/other ledgers. Check the team's current commitments and agree the allowance before enabling it. Do not promise this balance to HPL without checking their concurrent spending.

`plan` and `init` require the entire sequence to fit the cap and the finish deadline even without queue delays. Before every admission, the controller checks existing full reservations plus **all remaining scales**, under the existing lock. It never prunes an unaffordable 4-node run to spend the remainder at one node. The ledger must be a successful prefix of 1 → 2 → 4; an invalid, failed, abandoned, duplicate or out-of-order trial blocks progression rather than skipping or automatically retrying it. Each completed final result gates its successor. These are eligibility checks, not acceptance by the competition organisers.

Each worker submits the next job before exiting. No SSH session, login daemon or persistent terminal is needed once the first job is accepted. Serial allocation limits total 2 h 12 min; queue waits may add up to two hours per admission before its finish-deadline window expires. A pending job that expires does not have a running worker to submit a successor. The campaign stops and needs inspection; automatic recovery/requeue is deliberately absent. Timeouts, invalid output, unexpected failures and scheduler failures stop progression. `STOP`, durable intents, ambiguous-submission reconciliation and all reservation safeguards still apply.

### Preserving energy evidence without claiming a timed window

This sequence sets `archive_slurm_energy=true`. After each benchmark, a single bounded read-only `sacct` query captures all allocation and step records for known campaign jobs, including node lists/counts, allocated CPUs, state, exit status, start/end, elapsed seconds and raw joules. Unique timestamped PSV files and JSON receipts go under the **new campaign's `accounting/` directory**. No original reports, `result.json`, completed ledgers or previous snapshots are overwritten by later collections. Workers also recollect predecessors, whose final whole-job accounting is then available.

The `.0` estimate requires the completed `bench_wrapper.sh` step, positive finite energy/time/performance, a consistent benchmark duration and the expected accounted node count. It retains `energy_scope="slurm_benchmark_wrapper_step"` and `benchmark_window_energy_verified=false`. It does not populate the existing benchmark `gflops_per_w`, train an energy objective, or change HPL whole-job reporting. For multi-node runs use the **aggregated step joules / step wall seconds** and total HPCG GFLOP/s; do not multiply already aggregated energy by node count. Verify per-node coverage from the step node list before accepting multi-node estimates.

Accounting may lag. A missing/delayed energy record or `sacct` timeout produces an explicit unavailable receipt and does not invalidate otherwise valid HPCG output or trigger a benchmark retry. The last worker cannot capture its own final whole-job reading while its allocation is still running. After completion, collect a fresh append-only snapshot with `archive-accounting` below. Slurm retains the accounting independently of the SSH session; that final collection needs no new allocation. If the latest receipt still lacks a completed `.0` or final allocation totals, inspect and collect again rather than reporting a zero value. A failed filesystem write stops the worker, preserving the existing failure-stop behavior.

Read-only Cirrus inspection found `AcctGatherEnergyType=acct_gather_energy/pm_counters`, `JobAcctGatherFrequency=task=30,energy=30,filesystem=30,network=30`, `AcctGatherNodeFreq=0` and no profile plugin. Those settings do not prove sensor resolution, direct user access to compute-node counters or timed-solve coverage. Login-node RAPL paths and an installed `ipmitool` do not establish whole-node energy access on AMD compute nodes. The existing counter wrapper surrounds the full process and has no verified multi-node timed-window contract. Precise monitoring would require an accessible whole-node counter on every allocated node, consistent units/rollover handling and synchronised reads at actual HPCG timed-region boundaries, normally requiring benchmark instrumentation or a verified sampling/marker method. This remains unverified and is not enabled by the proposal. Do not delay valid long benchmarks for it: retain the original HPCG reports and use the explicitly scoped Slurm-step estimate as the fallback.

Sources: [HPCG duration/memory requirements](https://hpcg-benchmark.org/faq/), [Slurm energy fields and exclusive allocations](https://slurm.schedmd.com/sacct.html), [Slurm accounting configuration](https://slurm.schedmd.com/slurm.conf.html).

### Validate locally and on Cirrus before authorising launch

The local review changes have not been deployed to Cirrus. Keep the old `controller-review/` checkout and all completed campaign directories intact. Put the reviewed implementation in a **fresh controller directory**, for example `/epccfs/tc079/tc079/shared/hpcg/runs/tc079cheu1/controller-official-20261015`, before running these commands. This also avoids breaking the frozen code hashes of historical campaigns. Do not update code underneath an active campaign.

From that new checkout on Cirrus:

```sh
module load python/3.11.7
python3 -m unittest discover -s tests -v
python3 analysis/hpcg/overnight_energy.py
python3 -m autotune.campaign plan --settings autotune/clusters/cirrus-hpcg-official-sequence.toml
```

`plan` is the no-submission dry run: it validates the existing binary, memory, full-sequence budget, QoS limit and deadline without writing files or calling Slurm. Expected order: 1/2/4; expected total reservation: 1478.4; submission remains disabled. The revised implementation still needs this local-to-Cirrus validation and a real standard-QoS multi-node run. The earlier short-QoS canary validated chaining, not the new mode or multi-node numerical/performance behavior.

Once the code, allowance and finish time are reviewed, prepare **new** settings and state; never reuse a completed campaign path:

```sh
mkdir -p work
cp -n autotune/clusters/cirrus-hpcg-official-sequence.toml work/official-144-20261015.toml
export HPCG_SETTINGS="$PWD/work/official-144-20261015.toml"
export HPCG_STATE=/epccfs/tc079/tc079/shared/hpcg/runs/tc079cheu1/campaign-official-144-20261015-01
# Review/edit deadline, budget_since and agreed cap in HPCG_SETTINGS before init.
# Confirm allow_submit is still false and HPCG_STATE does not already exist.
python3 -m autotune.campaign plan --settings "$HPCG_SETTINGS"
python3 -m autotune.campaign init --settings "$HPCG_SETTINGS" --state "$HPCG_STATE"
python3 -m autotune.campaign tick --state "$HPCG_STATE" --dry-run
```

These commands do not submit. After **separate execution authorisation**, change only `safety.allow_submit` to true in that new settings file and launch once:

```sh
# Future authorised launch only; not executed during this review.
python3 -m autotune.campaign tick --state "$HPCG_STATE" --submit
```

After the first `submitted` job ID is returned, the chain can run without SSH. Check progress or final accounting when convenient:

```sh
python3 -m autotune.campaign status --state "$HPCG_STATE" --scheduler
python3 -m autotune.campaign archive-accounting --state "$HPCG_STATE"
```

Emergency stop for a future authorised campaign:

```sh
python3 -m autotune.campaign stop --state "$HPCG_STATE"
```

The stop command creates `STOP` first and requests cancellation only for matching live campaign jobs. Manual sentinel fallback: `touch "$HPCG_STATE/STOP"`. No stop/cancel command was run during preparation. An unsuccessful fixed sequence needs human inspection and a separately budgeted recovery plan; acknowledgement does not skip or retry its failed scale.
