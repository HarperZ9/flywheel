# Assessment of c:/dev, the models, the benchmarks, and a designed scaling demonstration

> **What this is.** The synthesis produced by the 10-agent assessment panel run on
> 2026-07-25, saved verbatim except for punctuation normalised to the project voice
> rules. It is a RECORD OF WHAT THE PANEL CONCLUDED, not a set of accepted facts.
>
> **What I verified myself, with live probes, before accepting it** (2026-07-26):
>
> | Panel claim | My probe | Result |
> |---|---|---|
> | The uplift arms are nested | read `uplift_bench.py:175`: `(("bare", 1), ("wrapped", n_candidates))`, and `_run_arm` starts `seed=0, temperature=0.0` in both | **REPRODUCED.** The wrapped arm's first candidate is the identical call to the bare arm's only candidate |
> | Zero bare-pass / wrapped-fail tasks | per-task outcome vectors across all 13 provider-runs in `artifacts/uplift/` | **REPRODUCED.** 0 in every run. 3 of 13 runs carry per-task data; the other 10 predate the `tasks` field, so for those the nesting finding rests on the code alone |
> | Four tasks pass in the wrapped arm at `attempts=1` that failed in the bare arm | same probe, run `20260714-125209` | **REPRODUCED.** 4 of 20 wrapped-only passes arrived on attempt 1, which is the seed-0 temp-0 call. Temperature-0 generation is not reproducible here |
> | `train_loss 0.035` describes nothing | read `checkpoint-2020/trainer_state.json` directly | **REPRODUCED.** 202 entries, first 0.7881, last 0.4439, min 0.35882, mean 0.49193, and no `train_loss` key anywhere in `log_history` |
> | `certificates/base.py` enforced only `_max` bounds | probe: `d_min=4` against a certificate declaring `d=1` | **REPRODUCED as a false accept (PASS).** Fixed in `a840c7f` |
> | `qa_battery` raises `KeyError: 'edges'` on the matmul oracle | ran it | **REPRODUCED.** Fixed in `a840c7f`, which then exposed 8 of 12 type-confusion mutants being accepted by `verify_scheme` |
> | A categorical scope bound raises `TypeError` | probe with a string bound | **DID NOT REPRODUCE.** `"GF4" > "GF2"` is a valid string comparison. The panel was wrong on this one |
>
> Everything else in this document is the panel's, at the panel's confidence, and is
> marked as such in its own text. Section 7 is a proposal, not an approved plan.

---

# Certified Commons: State of the Ground, Honest Evidence, and the One Claim That Ships

**Author:** chief architect | **Date:** 2026-07-26 | **Repo:** `C:\dev\local-model` @ `feat/cc1-phase0-ground`
**Register:** internal (`project-docs`). Local paths are correct here and forbidden on any public surface.

**Verified by me this session** (not inherited from the assessments): the seven Phase 1A-1C first-admission commits and their dates; both arms of `artifacts\uplift\uplift_hard_v2_20260714-140516.json` including denominators; `E:` capacity and every 32B/14B GGUF byte length; `Criterion._preimage` construction; `harness\uplift_bench.py:94-147` in full; the live Ollama roster. Everything else is attributed to the assessment or critique that verified it, with its citation. Where I corrected a claim from the corpus, I say so.

---

## 1. State of `C:\dev`, in one page

**Real, and load-bearing.** The Phase 1A-1C machinery exists and is coherent: seven commits, all first-admitted `2026-07-25` (`21c908d` criterion object, `344bb21` registry, `783429f` `CertificateOracle` base, `83ecf01` Zarankiewicz checker plus generator, `6ac0ba5` independent checker and cross-check, `146c779` receipt v2, `b320cd2` ledger with Merkle inclusion). Verified by me. `harness/lanes.py:79-108` declares seven lanes with install/command asymmetry mapped explicitly and `lane_status()` reports live/stale/declared/missing without faking a pass. `harness/gateway.py:1011-1019` puts every GET and POST behind `_authorized()`. `C:\dev\flywheel-desktop\lib` genuinely consumes the lane surface across 24 rail destinations. Four model artifacts hash-match their manifests (Surface 2, 4/4). CI runs five jobs on three OSes.

**Stale, and each instance is a false claim on a live surface.** `harness/superproject.py:31-49` hardcodes crucible 1.1.0 / index 2.8.0 / forum 1.12.0 against live 1.2.0 / 2.9.0 / 1.13.0, and its `routes_to` edges contradict the servers' own `next_actions`, so `spine()["closed"]` is computed over fiction (Surface 1). `harness/lanes.py:35` defines `TELOS_MANIFEST` and nothing ever reads it. `C:\dev\WORKSPACE-INDEX.md` (2026-06-19) and `C:\dev\AGENTS.md` (2026-06-26) both predate `lanes.py` and contain no lane row, so a session following the documented launch order finishes orientation without learning the lane layer exists. `PROJECT.md:146,185,205` still calls the 32B "aspirational" and "unproven" 14 days after it completed with `rc=0`. `m7_scorecard.json` at the repo root, the first evidence file a stranger opens, is a dry run against `qwen2.5:7b` whose local arm scores 0.0, and nothing in the file says so. `flywheel-desktop\HANDOFF-NEXT-SESSION.md:81` claims 15 destinations against `main.dart`'s 24.

**Duplicated.** Five `telos` checkouts, two of which (`public/telos`, `telos-oss-showcase`) share a head commit subject, i.e. a mirror. Three disagreeing hardcoded version tables. Two index clients across two transports, of which the better one (`context_envelope.py`, the only path that reaches `index.context.envelope`) has zero production callers. `UNVERIFIABLE` redefined as a bare string literal in six modules instead of importing `harness/verdict.py` (`buildc_receipt_bridge.py:30`, `context_envelope.py:23`, `selector.py:104`, `transitive_witness.py:36`, `world.py:32`). Two unreconciled copies of the scope envelope that already disagree: checkers declare `m_max=64`, the test criterion declares `m_max=40`, and the receipt binds the criterion's copy, i.e. the one that was **not** enforced. Four empty stub directories including `C:\dev\local-model\forum-ledger` sitting inside the flagship repo.

**Broken, ranked by consequence.** `harness/certificates/base.py:117-124` enforces only bound keys ending `_max`, silently skipping every other shape, so an out-of-domain certificate returns PASS (Surface 6 probe: `d_min=4` declared, `d=1` submitted, verdict PASS); and because `_in_scope` is called at `:166` **outside** the try that guards `check` at `:176-187`, a categorical bound named `field_max` raises an uncaught `TypeError` out of `verify()` instead of becoming UNVERIFIABLE/HARNESS. That is a false-accept path on the accept path. `harness/qa_mutations.py:84-85` reads `base["m"]`/`["n"]`/`["edges"]` before the class dispatch, so `qa_battery` raises `KeyError 'edges'` on the repo's own second oracle, which makes any second family `reward_eligible=False` via `QA_CARD_ABSENT` (`registry.py:157-158`). `harness/plugins.py:144` returns lane output with no hash, no witness, no ledger append, at the one genuinely cross-category seam, in a project whose invariant is *no receipt no accept*. `mcp_client.as_external_tools()` has zero production callers. `forum` and `learn` have no invocation site anywhere in `harness/`. And zero gateway routes expose any Phase 1A-1C module, so every invariant built this week is provable only by someone who can run Python in the repo.

---

## 2. The models, honestly

**What they are.** Both are real QLoRA continued-pretraining artifacts on Qwen2.5-Coder, not base weights with a name. Four hashes match their manifests. The 32B carries a complete single-attempt trace (`checkpoint-2019/trainer_state.json`: 2019 steps, epoch 0.25, `total_flos` 3.187e18, loss 1.767 → 0.7675, cosine LR decayed to 9.65e-9; supervisor log `rc=0` after attempt 1, 2026-07-11T23:03:52Z → 2026-07-12T19:54:33Z, ~20.8 h). The 14B carries a complete trace across three resumed invocations (`checkpoint-2020`: 202 log entries, loss 0.7881 → 0.4439).

**They are not a matched pair, on two independent axes of 8×.** The 14B saw 2 × 66,158,592 = 132,317,184 tokens at `seq_len` 2048. The 32B saw 2019 × 32 × 256 = 16,539,648 tokens at `seq_len` 256, from a corpus packed at `seq_len` 4096. `scripts/run_phase2_32b_supervised.sh:9-12` calls this "recipe parity with the shipped 14B artifact" on the grounds of matched optimizer-step count, which is the one axis that does not matter. Neither card states tokens-seen or training `seq_len`. Whether the 256-token windows respected the 4096-token pack boundaries is unrecorded, so it is unknown whether the 32B adapter partly learned truncation artifacts.

**The load-bearing defect.** `train_loss 0.035`, the project's most-cited number, is an HF Trainer end-of-run summary artifact of a thrice-resumed run: the numerator covers only the third segment (18:29:37 → 21:45:46 = 11,769 s, exactly the reported `train_runtime` 1.159e4) while the denominator is all 2020 steps. The model's minimum logged loss across the entire run is **0.35882**; the mean is 0.49193; the final is 0.4439. The same mechanism deflates the runtime by ~10×: the log's own progress bar reads `1881/2020 [30:59:28<2:20:48, 60.78s/it]`, so ~34 h, not 3.2 h. The companion figure `2.18` is the `train_loss` of a **2-step smoke** (`phase2-linux-14b-smoke.log`), so the ubiquitous "2.18 → 0.035" splices a smoke against a resume-corrupted average and describes no property of any model. `STATE.md:1087` recorded the truth mid-run ("2.18→0.44") and was overwritten at `STATE.md:859`.

It has propagated to 14 sites including `harness/model_profiles.py:23` (read at runtime), `tasks/research/gguf_ship_manifest_checkpoint2020.json:6` (**inside the provenance manifest strangers are asked to re-derive**), and `project-docs/releases/14B/shipped-page/MODEL_CARD.md:12` and `SPECS.md:41` (**public**). A wrong field inside the manifest is worse than a wrong README, because anyone who re-derives it finds 0.44, concludes the manifest is unreliable, and then discounts the four hashes in the same file that are correct.

By contrast the 32B's reporting is accurate ("final logged train loss ~0.768" against an actual 0.7675) and its card is the strongest document in the repo. Do not soften it.

**Currently unsupported claims.** (a) Any capability uplift for either model. The only base-vs-CPT comparison that exists is negative: HumanEval 141/164 base vs 136/164 CPT, Δ −3.05 pp, McNemar χ²_cc 0.696, p = 0.404. (b) `train_loss 0.035` and the 3.2 h runtime, in any form. (c) "Recipe parity." (d) That the 32B differs **behaviourally** from a plain q4_K_M quant of stock Qwen2.5-Coder-32B. Every hash in the provenance chain stays intact under a merge that silently no-opped, and a determinism smoke cannot distinguish those worlds because base weights are deterministic too. (e) That either model's evidence is reproducible by anyone else.

**What a stranger cannot re-check.** Six of eight evidence artifacts live only on `E:\local-model-run` and are absent from git: `humaneval_flywheel14b.json`, `humaneval_base_qwen14b.json`, `he_base_comparison.json`, `selector_comparison_headroom.json`, `selector_consensus_headroom.json`, `passn_curve_n32.json`, `difficulty_screen_hard_v2_110.json`. Total ~120 KB, so there is no size justification. What *is* committed is the two weakest artifacts: the 8-task easy set and the quarantined +10%. Worse, every `model_ref` in the set is now a dangling pointer: the live Ollama roster is `telos-coder-14b:latest`, `qwen2.5:0.5b`, `qwen2.5:3b`, `qwen2.5:7b` (verified by me), so `ollama:flywheel-local-coder-14b`, `ollama:flywheel-local-coder-32b`, and `ollama:qwen2.5-coder:14b-instruct-q4_K_M` all resolve to nothing. The last of those is the **control arm of the load-bearing negative** and has no sha256 recorded anywhere. The project's most trustworthy number rests on a model nobody can now identify.

**Contamination is unbounded and unauditable.** `E:\local-model-run\data\packed\PACK_COMPLETE.json` records `files_packed=17997`, `total_tokens=66158592`, and no file list, no source root, no per-file hashes, no snapshot date. `tasks/curated/hard_v2.jsonl` was first admitted `fcbde29` 2026-07-06 23:08:51 -0700, batch 3 on 07-07; the 32B CPT ran 07-11 → 07-12. `HumanEval.jsonl.gz` sits in the same `E:\local-model-run\data\` tree the packer wrote into. So the 32B may have been continued-pretrained on its own evaluation set and on HumanEval, and nothing in the record can rule either out. **Ruling: no number from `hard_v2` or HumanEval may be published for the 32B until an enumerated corpus manifest exists.** The 14B is cleaner by ordering only (CPT completed 2026-07-06T21:45:46Z, hours before first task admission), which bounds admission, not authorship.

**The one contamination bound that is airtight.** Every Phase 1A-1C file was first admitted 2026-07-25 (verified). Both CPT runs completed before it existed. Therefore the Zarankiewicz certificate family, its generator, and its checkers **cannot** be in either training corpus, and this holds without needing the pack manifest. That is the single strongest reason to run the demonstration in §5 on generated certificates rather than on `hard_v2`.

---

## 3. The benchmarks as they stand

| Instrument | Unit of claim | Verdict |
|---|---|---|
| `harness/uplift_bench.py` | per-provider pass-rate delta, wrapped minus bare, Newcombe 95% | **Void.** Nested arms |
| `harness/eval.py` (M7) | per-arm pass rate, MATCH/DRIFT | **Void as a verdict.** `if c.pass_rate >= b.pass_rate: "MATCH"`, no interval |
| `E:\...\he_base_comparison.json` | paired base-vs-CPT on HumanEval | **Survives on method, fails on reproducibility.** Best artifact in the repo |
| `selector_*_headroom.json` | oracle vs self-test vs consensus on a fixed pool | **The only experiment with real control structure.** No interval, no in-repo copy |
| `difficulty_screen_hard_v2_110.json` | single-shot temp-0 failure set | Instrument reading, correctly self-labelled. **Must never define an uplift denominator** |
| `harness/accountability_bench.py` | 8 harness-conformance dimensions | Sound and self-labelled near-tautological (1.0/1.0, strawman 0.0). **Keep off public surfaces** |
| `harness/benchmark_hygiene.py` | Lean kernel-bypass defect counts | Sound. Not a model benchmark, and says so |
| `harness/frontier.py` | throughput, `capability_per_gb` | **Void.** Divides a pass@N rate by disk size |
| six `*_bench.py` fixture suites | harness structural conformance | Sound, deterministic, re-runnable from a clean clone |

**Why every uplift number is void, at source.** `harness/uplift_bench.py:108-124`, which I read in full: `for seed in range(n_candidates)` with `temperature=0.0 if seed == 0 else 0.8` and `break` on the first oracle accept. The wrapped arm's first candidate **is** the bare arm's only candidate. Surface 3 confirmed zero bare-pass/wrapped-fail tasks across all three 14B runs. The delta is non-negative by construction, so the two-sided Newcombe interval tests a null that construction excluded, and `includes_zero=false` is a statement about sampling budget. The measured quantity is pass@N minus pass@1. Correctly named it is *verified pass@k*, and it is not uplift.

**The effect sits at the instrument's own resolution.** From my own dump of the best run: bare 46/110 = 0.4182, Wilson [0.3303, 0.5116]; wrapped 63/110 = 0.5727, Wilson [0.4794, 0.6612]; delta 0.1545, Newcombe [0.0225, 0.2792]. That is a half-width of **±12.8 pp** against a point estimate of 15.45 pp. The effect is 1.2× its own error bar, in one selected run of three at that configuration out of eleven artifacts, with `n_candidates` drifted from 3 to 5 mid-series, and both `uplift_bench.py:236` (newest mtime) and `frontier.py:68-88` (first-seen-newest) surfacing one run out of several with no multiplicity correction.

**The instrument is not reproducible at temperature 0, which voids pairing.** Two independent witnesses. Surface 3 found four tasks in the 125209 run that pass in the wrapped arm at `attempts=1`, the identical seed-0/temp-0 call that failed in the bare arm of the same run. Critique 1 found the difficulty screen scoring the same model on the same registry at 0.445 (49 saturating) against the bare arm's 46/110 = 0.418, a three-task disagreement on a measurement asserted to be deterministic. I checked one candidate explanation and **falsified it**: both arms report `graded=110`, `unverifiable=0`, so this is not a denominator asymmetry. The leading remaining hypothesis is prompt/KV-cache state, since the two arms run sequentially in one process against one server; second is the silent `except Exception: continue` at `:116-117`, which swallows a generation failure and burns an attempt without recording it, in direct violation of the standing never-swallow-errors rule.

**Nothing benchmark-related is in CI.** Five jobs, none of them a benchmark, no interval recompute, no `verify_findings()` call. The 14B page's numbers are currently correct by manual coincidence, not by gate. And `harness/findings.py:91` hardcodes `"McNemar p=0.0015"` as a string literal, attached to the artifact whose discordant counts give 0.0026, inside the module whose docstring promises exactly this cannot happen.

**Blunt verdict.** Two things survive a methodologist: `he_base_comparison.json` on method, and `project-docs/releases/14B/shipped-page/BENCHMARKS.md` on posture (it leads with the null, publishes [−0.236, +0.420], and names the tying arm). Everything else is instrument development. All eleven uplift artifacts get retired as such, including the +15.45 pp that `flywheel-desktop`'s Uplift view currently paints in the verified colour. The M7 +10% stays quarantined.

And the same page carries the worst single item in the record: `BENCHMARKS.md:58` says the public suites have not been run. HumanEval was run on 2026-07-09 over all 164 tasks and was **negative**. On a project whose stated core value is publishing nulls, the one unfavourable result is the one missing from the one public benchmark page.

---

## 4. What can be honestly demonstrated now

**No uplift exists.** Not measured, not pending measurement, not implied. The trainer has never run: `harness/rl_from_oracle.py`'s `PolicyOptimizer` is an unimplemented Protocol and `train/` contains only `qlora_cpt.py`. Every inference-time number is void per §3. The one training comparison that exists is negative and not significant. The elicitation-versus-expansion question is unresolved in the published record (Yue et al. vs the Invisible Leash vs ProRL), so "unresolved" is the accurate default and not a hedge.

**What needs the training stack first**, and therefore is out of scope: any uplift statement; any pass@k inversion diagnostic, which is a property of a trained policy; any position on elicitation versus expansion; any sigmoidal compute-performance fit, since the smallest published RL scaling ablation spent up to 16,000 datacenter GPU-hours per point with fitting beginning after ~1.5 k, against roughly 8,760 much-weaker hours per year of continuous operation on one 24 GB card. That last one is **structural, not temporary**. Say so in writing.

**What is demonstrable this cycle, stated precisely.** The accept path is a pure function of `(criterion hash, certificate bytes)`. It never receives model identity, never executes candidate code, and therefore yields byte-identical verdict digests for identical certificate bytes regardless of which model, size, family, backend, or quantization produced them.

**Three rulings on how to state it.**

> **RULING 1 (against Surface 1, 2, 3, 4; with Critique 2).** Stop saying "the environment scales." RLVE (`arXiv:2511.07317`) already owns "environment scaling" for scaling the *number* of environments and reports it as a capability gain, so the phrase will be read as the claim we are refusing to make. Say **size-invariant verification**, and prefer stating the mechanism over any trend.

> **RULING 2 (Critique 1 over Surface 5).** Surface 5's differential test as specified is close to vacuous: `certificates/base.py` never receives model identity, so permuting model-identity fields asserts that a pure function ignores an input it does not take. Replace it. The unit of observation is the **certificate body, not the model**: take the union of all bodies produced by all rungs, submit each through the accept path once per rung context, and assert one verdict digest and one receipt *subject* digest per body, with divergence permitted only in the receipt fields that record provenance. The headline is then a count, not a rate.

> **RULING 3 (Critique 2, adopted without qualification).** The claim is near-tautological and a reader who says so is right. The defence is not to inflate it. The defence is that the artifacts shipped alongside it are real and most published RLVR work does not ship them: four-way outcome tables with UNDECIDED and UNVERIFIABLE in the denominator, a pinned inference-stack fingerprint, a QA card with per-class Wilson bounds, an append-only ledger with consistency proofs, and a bundle that verifies offline with no network and no GPU. Put the limitation in the first paragraph of the public page, not the last.

---

## 5. The scaling demonstration, designed

**Instrument: generated Zarankiewicz certificates, not `hard_v2`.** Contamination-clean by timeline (§2, verified) and by construction (`generators.py:22-26` excludes published `z(m,n;2,2)` table parameters). It exercises the whole four-way surface: parse fail (CANDIDATE), out of scope (ENVIRONMENT), count overclaim (CANDIDATE FAIL), K22 violation (CANDIDATE FAIL), genuine PASS, and cross-check disagreement (UNDECIDED). `hard_v2` is not run for any comparison this cycle.

One design consequence, and it is the argument for deferring the §6 schema work rather than doing it first: the empty graph is K22-free with an honest declared count, so it PASSES. Do **not** add a threshold conjunct to the criterion, which would rehash it. Report the declared objective value alongside each verdict and stratify in the **reporting layer**. A rung that only ever emits the empty graph then reads honestly as "valid, worthless."

**The ladder.** Nine submission contexts, one engine, one quantization (q4_K_M), one fingerprint held identical.

| Rung | Role |
|---|---|
| qwen2.5-coder 0.5B / 1.5B / 3B / 7B | family-consistent small end |
| qwen2.5-coder-14B-instruct | base control for the 14B CPT |
| `telos-coder-14b` (cpt2020) | CPT arm |
| qwen2.5-coder-32B-instruct | base control for the 32B CPT |
| `telos-coder-32b` (cpt2019) | CPT arm, **not yet registered in Ollama** |
| one non-Qwen family at one size (OLMo 2 / Llama / Gemma class) | **family spot check, not generality** |

**Correction nobody in the corpus made.** The installed small models are `qwen2.5:0.5b/3b/7b`, the *general* Qwen2.5 line, while the trained artifacts are Qwen2.5-**Coder**. The existing "ladder" is two families, not one. Use `qwen2.5-coder` at every rung. Confidence high; verified against the live roster.

**The arms.** Generation is decoupled from selection: cache K candidates per instance per rung with **no early stopping**, content-addressed, each recording seed, temperature, model digest, engine, engine version, and quantization. Then every arm is an offline function of the cached pool, exactly paired, zero further GPU:

1. **single** (`pool[0]`, seed 0, temp 0) , baseline
2. **oracle-best-of-K** , treatment
3. **random-of-K** , compute-matched, oracle-free. This is the arm that breaks the nesting
4. **self-test-selected** and **consensus-selected** , the elicitation contrast, on the identical pool
5. **placebo acceptor** , the **spurious-reward control** at inference time: an acceptor matched on the oracle's accept rate carrying zero ground truth. If its lift is statistically indistinguishable from the oracle's, the oracle earned nothing
6. **pass@k curve** to K=8 at one rung only, as a diagnostic with no claim attached

Frozen now so it cannot be dropped later: any future training run **must** carry a random-reward arm and a format-only-reward arm (per `arXiv:2506.10947`, where random reward bought +21.4 pp on Qwen2.5-Math-7B and largely failed on Llama3 and OLMo2). Preregister them before the trainer exists.

**Statistics, seed-level variance primary.**

- **Primary variance component: between-seed.** Report an SD from r ≥ 3 full pipeline replicates (prefer 5), never a range presented as an SD. Critique 1's correction to Surface 5 is adopted: E[range] at n=2 is 1.128σ, so a 2.7 pp two-run spread implies σ ≈ 2.4 pp, not 1.35 pp.
- **Secondary: task population**, with standard errors **clustered** by difficulty band and generator seed, because the generator emits related groups and unclustered SEs are anticonservative (`arXiv:2411.00640`).
- **Interval: hierarchical bootstrap**, seed as the outer resample and instance as the inner, so the primary component dominates the width.
- **Primary test for any paired comparison: McNemar exact on discordant pairs**, and it may not be run until the determinism receipt shows the shared-generation invariant holds. `paired_bootstrap_diff` (`scripts/run_benchmark_ci.py:48`) and `mcnemar` (`scripts/analyze_selectors.py:27`) already exist and have never touched a `flywheel.uplift-bench/v1` document.
- **Published MDE, next to every result including every null.** Present single-run resolution on the task population is ±12.8 pp at n=110 (my dump). Detecting a few-point effect at that pairing quality needs order 10³ instances. Once generation is deterministic and arms share a cached pool, the binding quantity becomes the discordant-pair count and n falls sharply. Publish both numbers. Without an MDE, "no effect" and "no power" are indistinguishable to a reader.
- **Denominator: all four verdicts.** PASS, FAIL, UNDECIDED, UNVERIFIABLE, always, with the CANDIDATE / HARNESS / ENVIRONMENT attribution split reported separately.

> **RULING 4 (Critique 1 over Surface 3, with an operational carve-out for Critique 2).** Restricting a denominator to the 61 screened headroom tasks is **selection on the dependent variable** and would manufacture a positive result: the screen is defined by the same model failing the same temp-0 draw that constitutes the bare arm, so the bare rate on that subset is ~0 by construction and the "uplift" becomes a resampling recovery rate whose expectation is positive for a model with zero learning and an oracle with zero skill. **Forbidden as an uplift denominator, permanently, unless the screen is recomputed from independent seeds or a different model.** Permitted purely as a cost reduction in a run that computes **no** cross-arm rate comparison. Critique 2's operational instinct is right; its placement of the subset inside a comparison is not.

> **RULING 5 (Critique 1 partly over Critique 2).** A per-rung pass-rate table functions as a capability-scaling artifact whatever its caption says. But a conformance claim with no per-rung data is empty. Resolution: the **headline is a count with no rate in it** ("N distinct certificate bodies × 9 submission contexts = 9N verifications, N distinct verdict digests, zero disagreements"). Per-rung tables report **attribution and well-formedness only**, are ordered by rung id and never by size, compute **no** cross-rung delta or ordering, and sit behind an explicit not-comparable block listing the confounds inline: the 8× tokens and 8× context asymmetry, Qwen-only, one backend, contamination unbounded for the 32B on any set that may be in the pack.

**Preregistration: a file, not a module.**

> **RULING 6 (Critique 2 over Surfaces 3 and 5).** Preregistration derives its force from a hash committed before the run, not from a Python API. Write `project-docs/prereg/2026-07-XX-size-invariant-verification.md` fixing: criterion id and `criterion_sha256`, generator id and version, instance count and band distribution, K, the exact seed list, the nine rung identifiers each pinned by **weight sha256 and Ollama blob digest**, the full inference fingerprint, primary endpoint (verdict-digest invariance count), secondary endpoints, the declared MDE, the stopping rule, and the claim rule. Append its sha256 to the existing append-only ledger and git-tag it. Under one hour. Defer `harness/prereg.py`. Every scored run executed before the freeze permanently weakens the record and cannot be retrofitted, so the ordering is the whole point.

**Stopping rule, frozen.** Fixed instance set, fixed K, fixed seed list, one confirmatory run. No interim analysis, no peeking at outcomes, no extension on an unfavourable result. A run aborted for a mechanical reason is logged with its reason and the rerun is a **new** prereg hash that cites the aborted one. `newest-mtime-wins` selection is deleted from `uplift_bench.py:236` and `frontier.py:68-88`; the confirmatory run is named by hash.

**Claim rule, frozen.**

| Observed | Permitted statement |
|---|---|
| Zero verdict-digest disagreements across all contexts | "Verification is identical at every model size and family tested, for one oracle family, one backend, one quantization." Nothing about capability |
| Any disagreement, any body | **The claim has failed.** Publish the failure, the body, both digests, and the located divergence. Do not re-run to make it go away |
| Well-formedness near zero at small rungs | Report as expected. It is a property of the proposer, not of the environment |
| Any cross-rung rate difference | **Unclaimable.** Confounded by tokens, context, family, backend, contamination |
| Any inference-time arm difference | Reportable only as *verified pass@k* against the compute-matched oracle-free arm and the placebo acceptor, with McNemar and the MDE, and never as uplift |

**Modal outcome, stated honestly.** Invariance holds (near-certain: it is a pure function of data, so the informative result would be a bug). Well-formedness is ~0 % at 0.5B and 1.5B, single digits at 3B and 7B, low double digits at 14B, somewhat higher at 32B, with most non-PASS outcomes being parse failures attributed to CANDIDATE. Base and CPT rungs are indistinguishable within the seed-level SD. Non-Qwen behaves like the Qwen rung of comparable size, or does not, and either way n=1 supports no generality claim. The honest headline is: *verification is identical everywhere; capability is not measured, and this result says nothing about whether the environment is useful for training.*

**Cost, my derivation, moderate confidence.** From my own dump: bare 6,092 ms, wrapped 24,164 ms at 3.036 candidates, overhead 18,072 ms, so **8.9 s per additional candidate on the 14B**. At K=4 over 60 instances that is ~36 min per seed on the 14B, ~1.3 h on the 32B (~2.2×), and proportionally less below. Three seeds on the five rungs where a rate is reported plus one seed on the four small rungs, plus a K=8 pass@k sweep at one rung × 3 seeds, totals **~17 to 20 GPU-hours**, four evenings. Certificate prompts emit short JSON rather than code, so this is conservative. Seeds are not needed for invariance, which is deterministic per body; they are needed only where a rate is reported.

**Two blockers on the top rung.** `telos-coder-32b` is absent from Ollama (verified). And 18.49 GiB of weights on a 24 GB card leaves ~5.5 GB for KV cache and overhead, so if it spills to CPU offload the 1.3 h becomes days. Declared fallback, in the prereg: ship the eight-rung ladder and mark the 32B-CPT rung pending, rather than letting one rung hold the artifact.

---

## 6. Cross-category integration

**The structural fact that makes this cheap, and which appears nowhere in the record.** Fork risk is concentrated in exactly three files. Grepping `zarankiewicz|edges|k22|graph|bipartite|edge_count` across `ledger.py`, `bundle.py`, `contest.py`, `receipt_fields.py`, `verdict.py`, `merkle.py`, `why.py`, `gate.py` returns zero hits: `family` and `family_instance_id` are opaque strings, and the Merkle inclusion proofs, RFC 6962 consistency proofs, self-contained bundle, and contester-signed counter-receipt are all domain-blind. **The ledger, export, contest, and receipt-field layers admit a new domain with no schema change at all.** Protect that. The only coupling above the checker is two coverage-key lookups in `Receipt.does_not_prove()`.

**Minimal refactor, in dependency order.**

1. **`harness/qa_mutations_generic.py` plus a `Mutator` protocol** (`applicable_classes()`, `mutate(cert_text, cls, count, seed)`). Move the Zarankiewicz body out of `qa_mutations.py:84-165`. This removes the two-line `KeyError` that currently makes every second family reward-ineligible.
2. **`harness/oracle_qa.py:158-175`:** iterate `mutator.applicable_classes()` instead of the closed enum; add `NOT_APPLICABLE` as a third per-class state distinct from `INSUFFICIENT_N`, so "never attacked" stops reading as "attacked too few times"; emit a per-class Wilson upper bound alongside the total so 48 mutants in one class cannot mask 3 in another. Card schema v1 → v2; nothing downstream reads it structurally.
3. **`harness/certificates/base.py`:** typed `ScopeBound` supporting `max` / `min` / `in_set` / `equals`, refusing an unrecognized bound key **loudly at oracle construction** rather than skipping it at check time; move the `_in_scope` call at `:166` inside the try that guards `check` at `:176-187`; assert `oracle.scope_bounds == criterion.scope_bounds` at admission.
4. **`harness/certificates/family.py`:** an append-only record binding `family_id` to primary oracle, held-out oracle, generator, mutator, and `wire_format_id`, so `Criterion.generator_id` resolves to code. Today the seed-regeneration promise is an unverifiable string inside a signed record, for every family including Zarankiewicz.

> **RULING 7 (Critique 2 over Surface 6, with Critique 3's mechanism).** I verified `Criterion._preimage` is `asdict(self)` at `harness/criteria/spec.py:99`. Therefore **any** field addition (`wire_format_id`, `objective_direction="none"`, a pinned catalog in place of `seed_range`, a typed `reward_mapping`) rehashes every criterion and invalidates every prior ledger entry and any prereg made before it. Surface 6's steps 5, 6, and 7 and Ruling 6's freeze deadline are mutually exclusive, and whichever comes second loses. **Freeze the criterion schema exactly as it stands. Take only items 1 through 4 above, none of which touch `_preimage`.** Item 3 is hash-safe because existing bounds keep their canonical serialization: `{"m_max": 64}` still serializes identically, and only new criteria carry new bound shapes. The schema widening and the matmul port land next cycle as a **recorded amendment**, which the amendment lineage at `spec.py:108-119` already supports.

**The general mutation classes, named, replacing the graph-shaped ones.** Eight are family-free and belong in the generic mutator, parameterized off declared field names rather than hardcoded ones:

| General class | Replaces | Parameter |
|---|---|---|
| `TRAILING_GARBAGE` | itself, already generic at `:157-158` | none |
| `DECLARED_QUANTITY_OVERCLAIM` | `COUNT_OVERCLAIM` (`:123-124`) | `objective_field` |
| `TYPE_CONFUSION` | itself (`:125-156`) | list of integer field paths |
| `MEMBER_VIOLATES_DECLARED_DIMENSION` | `INDEX_OUT_OF_RANGE` + `NEGATIVE_INDEX` (`:117-121`) | dimension field names |
| `MEMBER_ARITY_OR_NESTING_ABUSE` | `STRUCTURE_ABUSE` (`:160-162`) | member arity |
| `FIELD_OMISSION` | new | required field list |
| `SCOPE_ESCAPE` | new, and it is the class that would have caught the `_in_scope` bug | declared bounds |
| `ENCODING_ABUSE` (duplicate JSON keys, NaN, Infinity, oversized ints) | new | none |

Two do not generalize cleanly and must be handled explicitly. `DUPLICATE_EDGE` **inverts**: duplicating a rank-1 triple changes the tensor, so it is a count inflation for graphs and a semantic mutation for matmul. Split it into `DUPLICATE_MEMBER_COUNT_INFLATION` and `DUPLICATE_MEMBER_SEMANTIC`, with per-family applicability. `ADD_EDGE` (`:90-110`) is the deepest coupling and the least transferable: it enumerates `(r,c)` over `range(m) × range(n)` and calls `_reference_free`, which hardwires imports of both Zarankiewicz predicates for ground truth. Rename it `SEMANTIC_NEAR_MISS`, keep it **per family**, and accept that each family owes its own near-miss constructor and its own two independent predicates. That is the irreducible per-family cost, and it is what makes a QA card mean anything.

**Gateway routes: three GETs this cycle, no POSTs.**

- `GET /api/criteria` , `criterion_id`, version, `criterion_sha256`, domain, decision rule, `reward_eligible` with its reason, amendment lineage
- `GET /api/qa?criterion=` , per-class mutant counts, per-class Wilson upper bound, `NOT_APPLICABLE` states, denominators, and the card's own stated limit that it quantifies the sample and never the imagination
- `GET /api/ledger/head` , tree size, root, latest inclusion path

Thin wrappers in the style of `gateway.py:1077-1079` and `:1148-1150`. **No POST.** `POST /api/check` must not violate the no-execution property at `certificates/base.py`, and `POST /api/contest` needs a contester signing key that the desktop charter forbids the app from collecting. No run-the-bench button: a pleasant UI that manufactures unregistered comparisons is precisely the failure mode.

**Desktop surfaces: four items, none of them a new destination.**

1. The four-way verdict fix in `lib/theme/tokens.dart:99-115` and `lib/models/render_status.dart:16-20`, landing **the same day** the first four-way route goes live. Today `statusColor` has no `UNDECIDED` case and its default branch returns drift, so a raw `UNDECIDED` paints as a candidate **failure**, reintroducing at the render layer the exact misattribution `harness/verdict.py` exists to prevent. Within the verdict-only-colour canon: `UNDECIDED` shares the unverifiable colour but always carries its own word plus its `UndecidedReason`, and Attribution renders as a second mark, since colour must never be the sole carrier.
2. One receipt v2 renderer leading with `does_not_prove` and the denominator, with both digests labelled by their job (`subject_sha256` is verdict-free so two verifiers who disagree still produce the same subject id and the disagreement can be **located**).
3. One `CertificateView` registry with a **mandatory raw-JSON fallback**, so a new family is never blocked on Dart work. Name the file `certificate_view.dart`; `lib/views/family_view.dart` already exists and is an unrelated variable-typeface view.
4. Annotate or remove the `UPLIFT MEASURED` pill.

> **RULING 8 (Critique 2 over Surface 4).** The demonstration surface is an offline-verifiable **bundle plus one static page**, not a criterion-first Flutter destination. The desktop is a competent renderer of a gateway that has not been told about Phase 1A; the gap is upstream, and Surface 4 planned its work against code it admits it never launched.

> **RULING 9 (Critique 2 over Surface 1, decisive).** Making crucible the verdict authority and forum the ledger of record does **not** convert a self-consistent claim into a stranger-checkable one, because the operator wrote crucible and forum. Cross-repo agreement between your own software is a second copy of your own judgement plus a contract negotiation Surface 1 itself prices as expensive. Independence must come from software the operator did not author: a Lean kernel, z3, sympy, networkx, nauty. Cut the lanes from the verification story and move the unfulfilled spec §7 lane roles into §8's deliberately-not-built list. No lane work is on the critical path.

---

## 7. Ordered plan, one maintainer, one GPU

**Phase 0 , Honesty repairs. Zero GPU, ~1.5 days. Nothing else starts first.**

1. Correct `train_loss 0.035` to the measured curve (0.7881 → 0.4439, mean 0.4919, min 0.3588, 2020 steps, 2 epochs, ~132.3 M tokens, ~34 h across three resumed invocations) and the deflated 3.2 h runtime in all 14 sites, as a plain `CORRECTIONS` entry recording old value, new value, and reason. The manifest and shipped-page instances are urgent. **Ruling: Critique 2 over Surface 2 on mechanism.** Use a corrections file, not the criteria amendment machinery, which is for hashed criteria and not for documentation.
2. Restore the HumanEval negative on `project-docs/releases/14B/shipped-page/BENCHMARKS.md` with its interval and p-value, and delete line 58. One paragraph, highest credibility return of any item in this plan.
3. Commit the seven evidence JSONs (~120 KB) plus a name → GGUF sha256 → Ollama blob digest resolution table covering every arm including base controls.
4. Delete the hardcoded p-value at `harness/findings.py:91`; make `scripts/analyze_selectors.py` **write** its McNemar block and read the field.
5. Add tokens-seen and training `seq_len` to both cards; delete the "recipe parity" language at `scripts/run_phase2_32b_supervised.sh:9-12`.
6. Add a no-model CI job that recomputes intervals from committed artifacts and calls `verify_findings()`, failing on drift.
7. Annotate or remove the desktop uplift pill. Retire all eleven uplift artifacts as instrument development.

**Phase 1 , Instrument correctness and provenance. Mostly zero GPU, ~2 days plus one background job.**

8. **Merge-landed, two checks answering two different questions.** Both f16 GGUFs are exactly 65,535,970,080 bytes (verified by me), which is expected for a LoRA merge and therefore uninformative, so nobody's size argument settles it. **(a)** Streaming byte diff of `qwen2.5-coder-32b-base-f16.gguf` against `telos-coder-32b-merged-f16.gguf`, reporting first differing offset and count of differing 1 MB blocks. Zero differing blocks means the merge no-opped. Background job, no GPU. **(b)** Generation differential at temp 0 with a fixed seed over ~20 fixed prompts on the two q4_K_M artifacts, asserting output digests differ, which proves the delta survived quantization. Quantize the base locally from the f16 already on disk (772.6 GB free, verified); no download. **Ruling: this two-check split is mine and supersedes all three critiques, which proposed only (b) and thereby conflate "the merge no-opped" with "q4 rounded the delta away."** First verify whether that f16 is base or instruct, since the CPT sat on one of them.
9. **Determinism receipt.** k=5 repeats of one fixed configuration on `hard_v2` at K=1, temp 0, publishing the per-task disagreement matrix and the observed flip rate. ~56 min GPU. No comparison computed. This either exonerates the instrument or condemns it, and either outcome is a deliverable. Add a run-level assertion that arms sharing a nominal first generation produce byte-identical output per task, and record the control-pass/treatment-fail count, which must be capable of being nonzero.
10. Fix the silent `except Exception: continue` at `uplift_bench.py:116-117`. It violates the standing never-swallow rule and is a live candidate mechanism for item 9's disagreements.
11. **`harness/pool.py`.** Decouple generation from selection: K candidates per instance with no early stopping, full fingerprint per candidate, content-addressed on disk; plus an offline evaluator computing single / oracle / random / self / consensus / placebo / pass@k from the cache. **Ruling: this is the single best idea in the entire corpus and no assessment proposed it.** It retires the nesting defect, makes every arm exactly paired, makes McNemar applicable, makes the pass@k curve free, and makes the whole analysis re-runnable by a stranger on a laptop with no GPU and no network. It also dissolves the Surface 3 / Surface 5 cost dispute: replicates looked expensive only because the inline loop discards candidates.
12. **`_in_scope` and the QA generality fixes**, items 1 through 4 of §6. Hash-safe by Ruling 7.
13. **Enumerated corpus manifest.** Per-file path, sha256, byte count for all 17,997 files, plus source root and snapshot date; re-pack if the packer's list is unrecoverable. Then exact and fuzzy match of every task prompt and every oracle against it, plus partial-prefix probes. Until this exists, no 32B number on `hard_v2` or HumanEval may be published.

**Phase 2 , Freeze, then run. ~17 to 20 GPU-hours over four evenings.**

14. Register `telos-coder-32b` and the base control rungs in Ollama; confirm the 32B is servable at the needed context; pin every rung by weight sha256 and blob digest.
15. **Freeze.** Write the prereg, hash it, append to the ledger, git-tag. Nothing scored runs before this.
16. Generate the cached pools across all nine rungs per the design in §5.
17. Verify offline: invariance count, per-rung attribution and well-formedness, QA card, ledger head.
18. Bundle plus one static page, then **hand it to one actual person and ask them to run the verify script.** That single act converts self-consistency into third-party checkability and costs nothing. **Ruling: Critique 2's observation, and no assessment made it.**

**Phase 3 , Small debt items, anytime, each removes a false claim.** Map lane health onto `harness/verdict.py` and delete the six `UNVERIFIABLE` literals (1 h). Receipt-wrap **or disable** `POST /api/plugins/call`; an unreceipted seam into a no-receipt-no-accept project should not stay open while it waits for a wrapper. **Delete** `superproject.py`'s version and route tables outright rather than teaching them to read the manifest; deleting a stale claim is cheaper than maintaining a fresh one. Add lane rows to `WORKSPACE-INDEX.md` and `AGENTS.md`. Delete the four empty stub directories. Record in `project-docs/records/PROJECT-LINEAGE-MAP.md` whether `telos-oss-showcase` is a mirror.

**Deliberately NOT built this cycle, and stated as a choice.** Any RL training under verified reward: `PolicyOptimizer` stays an unimplemented Protocol. `harness/prereg.py`, `uplift_stats.py`, `control_arms.py`, the cost meter, the model adapter layer. The criterion schema widening, the matmul port, per-family `SEMANTIC_NEAR_MISS` constructors, the conjunct-level `check()` return, the Coverage widening, the family registry beyond a minimal binding, and any executing-verifier sibling base class for Lean. All POST gateway routes. The criterion-first desktop destination and the receipt-v2 renderer beyond item 2 of §6. Any lane integration into the verification story. Any pass@k inversion program. Any sigmoidal compute fit. Any cross-family uplift arm set, which means a training run per family and is unavailable at this compute permanently.

One correction that must go into the spec in the same commit as this plan: **spec §7's lane roles are aspiration, and §8 does not disclose it.** Move them.

---

## 8. The honest nulls, as they would ship

- **No capability uplift exists for either model, in any form.** The only base-versus-CPT comparison is negative and not significant: HumanEval 141/164 base against 136/164 after continued pretraining, Δ −3.05 pp, McNemar χ²_cc 0.696, p = 0.404. That is our result and we are not softening it. The 32B has no task benchmark of any kind.
- **All eleven inference-time uplift artifacts are void as comparisons**, including the +15.45 pp with a Newcombe interval that excludes zero. The two arms are nested: the treatment's first candidate is the baseline's only candidate, so the delta cannot be negative and the interval tests a null that construction excluded. The quantity measured is verified pass@k. The +10 % hard-set lift stays quarantined: n=10, one task, interval [−0.236, +0.420].
- **`train_loss 0.035` describes nothing.** The minimum loss logged across all 2020 steps is 0.3588. The number is a resume-accounting artifact. The same mechanism deflates the reported 3.2 h runtime by roughly 10×; the real figure is ~34 h.
- **The instrument is not reproducible at temperature 0.** Four tasks in one run pass in one arm and fail in the other at the identical seed and temperature, and the difficulty screen and the baseline arm disagree on three tasks of a nominally identical measurement. Until that is explained, no paired statistic on this instrument is valid.
- **We cannot yet claim the 32B behaves differently from its base model.** Every hash in the provenance chain would remain intact under a merge that silently changed nothing, and a determinism smoke cannot distinguish those worlds because base weights are deterministic too.
- **We cannot bound contamination.** The corpus manifest records a file count and no file list, no hashes, and no snapshot date. The 32B trained after the evaluation task set was committed and from a data tree containing HumanEval. No 32B number on either set is publishable until an enumerated manifest exists.
- **Stranger offline reproducibility is currently unmet for every real result.** Six of eight evidence artifacts are absent from the repo; the two present are a dry run against a 7B and the quarantined result. Three model references in the evidence set resolve to nothing, including the control arm of our load-bearing negative, which has no weight hash anywhere.
- **The two trained sizes are not a matched pair.** 8× difference in tokens seen and 8× in training context. "Recipe parity" meant equal optimizer-step count, which is the one axis that does not matter.
- **Verification identity is not capability identity, and the claim is near-tautological.** The accept path is a pure function of criterion hash and certificate bytes. That it ignores model identity is a design property, not a discovery. It says nothing about whether the environment is useful for training. A reader who calls it thin is correct; the artifacts around it are the substance.
- **Cross-family generality of the verification apparatus is not demonstrated.** The QA battery raises `KeyError` on this repo's own second oracle, so a second family is structurally reward-ineligible today. Until that lands, the honest claim is "identical criteria, identical checkers, identical receipt schema, identical verification at every model size, **for one oracle family, one model family, one backend, one quantization**." And "adding a family is one checker plus one generator" is currently **false by measurement**; do not write it down until items 1 through 4 of §6 have landed.
- **We take no position on whether verified reward creates capability or sharpens sampling.** The published record disagrees and settling it needs pass@k sweeps at multiple scales across multiple families.
- **We make no scaling-law claim and never will at this compute.** The smallest published RL scaling ablation spent up to 16,000 datacenter GPU-hours per point with fitting beginning after ~1,500. One 24 GB consumer card yields on the order of 8,760 much weaker hours per year. This is structural, not a backlog item.
- **`accountability_bench` scoring 1.0 on all eight dimensions supports no claim about quality**, as its own emitted artifact says. It stays off every public surface.

---

## 9. Rulings ledger

| # | Dispute | Ruling | Why |
|---|---|---|---|
| 1 | Phrase "the environment scales" (S1/S2/S3/S4) vs "size-invariant verification" (C1/C2/S5) | **Size-invariant verification** | RLVE owns "environment scaling" for a capability claim; readers will hear that one |
| 2 | S5's model-blindness differential vs C1's vacuity objection | **C1.** Unit of observation is the certificate body, not the model | `base.py` never receives model identity, so permuting it asserts nothing |
| 3 | Inflate the invariance claim vs concede its thinness (C2) | **C2, adopted verbatim** | The defence is the surrounding artifacts, not the claim |
| 4 | S3's headroom-subset denominator vs C1 fatal vs C2 fixable | **C1 on statistics, C2's instinct only outside comparisons** | Screen and baseline share the same draws; regression to the mean would be reported as verification earning capability |
| 5 | C1 forbids per-size tables; C2 requires them | **Split.** Count as headline, attribution and well-formedness only per rung, no cross-rung delta, confounds inline | A rate table reads as a capability curve; no per-rung data leaves the claim empty |
| 6 | `harness/prereg.py` as blocker (S3/S4/S5) vs a hashed file (C2) | **C2** | Force comes from the hash and the timestamp, not the API; the freeze deadline cannot be retrofitted |
| 7 | S6's seven-step schema refactor first vs C2's freeze-first | **C2, mechanism from C3.** Items 1-4 only | `_preimage` is `asdict` (verified `spec.py:99`); any field addition rehashes every criterion |
| 8 | S4's criterion-first desktop view vs C2's bundle plus page | **C2** | The gap is upstream; S4 never launched the app it planned against |
| 9 | S1's crucible-as-verdict-authority as the stranger-checkability fix vs C2 | **C2, decisively** | The operator wrote crucible; independence requires software he did not author |
| 10 | S3 "replicates expensive" vs S5 "ladder near-zero" | **Neither.** ~17-20 GPU-hours, from measured 8.9 s per candidate | Both skipped the arithmetic; expense was an artifact of the discard-on-accept loop |
| 11 | S5's seed SD 1.35 pp vs C1's 2.4 pp | **C1**, and the binding component is the ±12.8 pp task-population half-width I measured | E[range] at n=2 is 1.128σ |
| 12 | Determinism defect as one finding (S3) vs instrument-fatal (C1) | **C1** | It voids pairing, which every interval depends on |
| 13 | C1's mismatched-denominator hypothesis | **Falsified by me.** Both arms `graded=110`, `unverifiable=0` | Checked directly; the nesting and non-determinism defects stand on their own |
| 14 | Merge-landed check design (all three critiques propose generation only) | **Superseded.** Two checks: f16 byte diff, then q4 generation differential | Both f16 files are byte-identical in length, so size settles nothing, and the two checks answer different questions |
| 15 | Which models form the ladder | **`qwen2.5-coder` at every rung**, not the installed `qwen2.5` general line | Unnamed in the corpus: the existing ladder mixes two families |