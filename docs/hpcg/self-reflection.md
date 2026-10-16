# Self-reflection — CIUK 2026 EPCC HPCG Challenge

**Date:** 16 October 2026  
**Scope:** My HPCG contribution only, not the team's HPL work or a prediction of the team's competition ranking.  
**Status:** Reflection on the completed work, not a benchmark report or an organiser's assessment.

This document is for learning, not self-promotion. It is separate from the [experiment log](experiment_log.md), which holds the actual measurements and provenance, and the [controller documentation](autotuning-controller.md), which describes the implementation. I should update this reflection when I have new evidence, but should not rewrite past experimental results to match a later conclusion.

## Overall judgement

I completed the core HPCG execution task competently. I obtained valid official-duration runs at one, two and four nodes, documented the inputs and provenance, and used automation to run experiments within a budget. That is meaningful practical HPC work.

**My principal weakness was optimisation evidence, not execution.** I cannot show that my chosen final configuration is the fastest or most energy-efficient one available on Cirrus. My best apparent throughput improvement from the short tuning campaign was too small and insufficiently replicated to establish a real gain. The promising reduced-core energy result was not confirmed in an official-duration run.

I should not confuse the amount of work, the complexity of the controller, or the length of my documentation with the strength of the scientific result. The challenge assesses benchmark performance, energy efficiency, scaling and insight. A sophisticated script is valuable only where it produces reliable, interpretable evidence.

## What I completed and why it matters

- I established a working HPCG 3.1 workflow on Cirrus, progressing from smoke tests to larger memory-representative diagnostics.
- I compared compiler builds and MPI/OpenMP layouts, and used a measurement-driven autonomous controller to complete **nine VALID diagnostic runs**. The controller screened builds, repeated selected candidates, explored layouts and stopped when the next conservative reservation would exceed its campaign allowance.
- I completed **VALID official-duration weak-scaling runs** with CCE reference and **144 MPI ranks × 1 OpenMP thread per node**:

  | Nodes | HPCG GFLOP/s | Reported benchmark time | Weak-scaling efficiency |
  |---:|---:|---:|---:|
  | 1 | 135.094 | 1,898.57 s | 100% |
  | 2 | 269.818 | 1,857.91 s | 99.86% |
  | 4 | 533.317 | 1,879.79 s | 98.69% |

- I preserved Slurm accounting, original HPCG summaries, build hashes, controller settings, job IDs and decision records. I also copied the Cirrus HPCG workspace to my Mac and checked the copy with an rsync checksum dry run.

The scaling experiment is my strongest scientific result. The same local workload and MPI layout were maintained per node, and throughput increased by about 3.95× from one to four nodes. **This is weak scaling, not strong scaling**: the total workload increased with node count. I should be able to explain the difference without relying on a script or an AI response.

## What went well

### 1. Execution, validation and reproducibility

I moved beyond simply obtaining a GFLOP/s number. I checked numerical validity, benchmark duration and configuration consistency, and retained the files needed to trace results back to jobs and binaries. This reduces the risk of reporting an invalid or irreproducible result.

**Limit:** A successful controller eligibility check is not an organiser's formal acceptance. I still need to ensure the final package contains the required binaries, scripts, inputs, tables and plots.

### 2. Resource management

The overnight diagnostics actually used **190.16 core-hours**, while the controller retained **489.6 core-hours** of conservative reservations. The official 1/2/4-node sequence used **1,127.44 actual core-hours**, compared with **1,478.4 reserved**. I learned the difference between elapsed allocation cost and pre-admission worst-case budgeting.

**Limit:** The controller's campaign cap does not enforce the whole team's live allocation or control teammates' jobs. I still needed to coordinate the shared budget and stop when its availability became uncertain.

### 3. Honest reporting of uncertainty

My log distinguishes short diagnostics from official-duration results, reported HPCG performance from power estimates, and observations from hypotheses. For example, I did not report the overnight 144×1 result as a proven speedup.

**Limit:** Correct caveats do not make weak evidence stronger. They explain why an additional measurement would be necessary.

## Where I fell short

### 1. I did not establish a meaningful performance improvement

The best overnight CCE 144×1 run reached **135.342 GFLOP/s**, while two 288×1 reference measurements averaged **134.918 GFLOP/s**. The apparent advantage was only **0.31%**. The candidate was measured once, and its workload contained about **0.96% fewer equations**.

I therefore cannot claim the optimiser made HPCG 0.31% faster. A small difference between unlike or insufficiently repeated runs may reflect workload differences, measurement noise or selection of an unusually favourable sample.

**Next time:** Choose the baseline, acceptable workload tolerance, number of repeats and decision rule *before* an optimisation campaign. Compare matched cases and repeat the promising candidate; do not treat the single best result as proof.

### 2. I did not verify the strongest energy-efficiency hypothesis

The short **72 MPI × 1 thread** diagnostic achieved **131.806 GFLOP/s** with **0.1570 estimated GFLOP/s/W**, suggesting a performance–power trade-off from using fewer active cores. But I did not run this configuration at official duration. My final weak-scaling campaign instead used 144×1.

This is not a failure to complete the specified scaling task; the budget was limited and the official runs were a necessary priority. But it means I cannot claim to have found the best energy-efficient configuration.

**Next time:** Decide earlier whether throughput or energy efficiency is the primary selection objective, and reserve some budget for validating the highest-value finding rather than only completing a scaling curve.

### 3. Energy efficiency was estimated across mismatched time windows

For the official runs, I calculated average power from the Slurm `.0` benchmark-wrapper step and divided HPCG GFLOP/s by that power. The two-node estimate was **0.1404 GFLOP/s/W**, the highest among my three official configurations.

This is not a verified measurement of power *only during the HPCG timed benchmark region*. The wrapper includes setup and reporting. I cannot call this a precisely measured benchmark-window efficiency or a universal optimum.

**Next time:** Define the energy measurement scope at the beginning, check what instrumentation is actually available, and keep the raw joule and elapsed-time records. If timed-window measurement is unavailable, clearly label and justify the proxy.

### 4. Too few repeats, especially at official duration

I have one official result at each node count. That is enough to demonstrate an observed 1/2/4-node scaling curve, but not enough to estimate its variability or establish that small efficiency differences between node counts are stable.

**Next time:** Plan a few repeated baselines and use comparisons with meaningful uncertainty before making claims based on differences of a few percent or less. Under a fixed budget, fewer carefully controlled comparisons may be better than a wider search with one sample per setting.

### 5. I inferred a hardware bottleneck without directly measuring it

HPCG is often memory-bound, and my reduced-core results are consistent with memory bandwidth limiting throughput. However, I did not measure achieved bandwidth, relevant hardware counters or detailed kernel behaviour sufficiently to prove why performance changed.

**Next time:** Investigate component timings (e.g. SpMV, SymGS and MG), process binding and memory locality. Treat "memory bandwidth is the bottleneck" as a testable hypothesis, not a demonstrated cause.

### 6. I invested heavily in automation before completing the scientific argument

The controller has useful engineering features, including validation, provenance, conservative reservations and job chaining. But complexity did not itself establish a faster or more efficient benchmark. I could have spent more time earlier on a simple experiment matrix, measurement comparability and which results would actually support a claim.

**Next time:** Start with the marking criteria, a short list of hypotheses, a baseline and an evidence plan. Build automation only for repeated work or risks that justify it. I should be able to explain the experiment without the controller.

## AI assistance, authorship and responsibility

**I used AI-assisted tools to accelerate coding, Slurm/job scripting, debugging, technical investigation and documentation.** The controller also builds on existing team framework code, credited in the repository README. I should not present every script, implementation decision or explanation as independently authored from scratch. Exact authorship of individual code sections should be checked against Git history and discussed accurately rather than guessed.

AI assistance saved time, particularly while working in an unfamiliar HPC environment. That is a practical benefit, but it introduces a serious learning risk: **working code is not evidence that I personally understand all of it**.

I was responsible for deciding what to execute, coordinating compute use, checking outputs and retaining evidence, but automated tests and successful jobs do not establish that I could independently implement, debug or justify every safeguard. The repository reports 58 passing controller tests, but my reviewed evidence did not contain a retained console record for that expanded suite, and not every live failure mode was tested.

For future work I will disclose AI use in accordance with challenge and university rules. I will keep a record of what was inherited, AI-assisted, personally modified and independently verified. Before submitting or running generated code, I should be able to explain its inputs, outputs, resource implications, failure behaviour and key assumptions. When I cannot, that is a gap to close, not something to hide.

## Actions for the next challenges (Durham and UCL)

| Priority | Action | How I will know I improved |
|---|---|---|
| **1 — Before implementation** | Read the brief and marking rubric; turn every assessed claim into a required piece of evidence. | I have a small deliverables/evidence checklist before coding. |
| **2 — Before substantial compute** | Write a baseline, specific hypotheses, controlled variables, planned repeats and worst-case resource budget. | I can explain why each experiment is worth its cost. |
| **3 — During experiments** | Save raw outputs, job IDs, exact commands, input parameters, versions and failed attempts as they happen. | Another teammate can independently reproduce and audit a result. |
| **4 — When using AI** | Review generated code and explain the critical path, especially resource use, correctness checks and failure handling. | I can reproduce a key result or diagnose an error without asking AI to explain the entire system. |
| **5 — Before selecting a winner** | Compare like with like; repeat close results; report uncertainty and rejected hypotheses. | I can distinguish an observed difference from a supported improvement. |
| **6 — Before submission** | Produce the required tables, plots and narrative early enough for independent teammate review. | Each slide or conclusion links back to primary evidence. |

## Questions I should be able to answer independently

1. Why is my 1→2→4-node result **weak scaling**, and how is its efficiency calculated?
2. How did the adaptive controller choose the nine tests, and what exactly made it stop?
3. Why did using fewer active cores not reduce HPCG throughput proportionally? What evidence would distinguish possible causes?
4. What is the difference between energy (J), average power (W) and GFLOP/s/W? Which interval did I actually measure?
5. Why isn't a 0.31% one-off difference proof of faster code?
6. Which parts of the controller came from pre-existing code, which were AI-assisted, and which behaviours have I personally tested or understood?

If I cannot explain these without a script or assistant, I should treat that as unfinished learning even if the benchmark itself passed.

## Closing assessment

I completed the HPCG execution requirements and produced a strong observed weak-scaling dataset. I also built practical experience with Cirrus, Slurm, MPI/OpenMP, automated experiments and resource accounting.

I did **not** establish a top-ranked HPCG result, a statistically supported throughput gain, a verified timed-window energy optimum or a proven memory-bandwidth diagnosis. Those claims would go beyond the evidence.

For the next challenges, the most important improvement is **to design experiments around evidence and understanding, not around how many jobs or how much code I can produce**. I should aim to deliver fewer unsupported claims, better-controlled measurements, and a clearer account of what I personally learned and verified.
