# Project Telos — The Verified-Inference Harness

*A local-model flywheel: propose cheaply, verify with real oracles, ship a re-checkable receipt for every accept.*

---

## 1. What this is

This is a verified-inference harness built on one operation: **the reconcile**. Perceive a task, produce a candidate, check that candidate against a criterion the harness did not author, and carry a receipt a third party can re-walk to reproduce the verdict. A local 14B model *proposes*; real verifiers (pytest, executors, kernel benchmarks, judgment oracles) *dispose*; retrieval carries the knowledge; and every accepted answer emits a proof envelope binding task, candidate, oracle command, output hash, and verdict.

The thesis is that **frontier-grade output on verifiable tasks does not require frontier weights**. On a 24GB consumer GPU, a cheap replaceable proposer wrapped in a rigorous harness can match or beat a frontier model's single shot on oracle-backed slices — because the harness, not the weights, is where the correctness comes from. Layer A (the 14B QLoRA proposer) is a commodity; Layer B (the harness that verifies, chains, escalates, caches, and witnesses) is the moat and the research contribution.

Two invariants are load-bearing and never relaxed: **no receipt → no accept**, and **no learned model sits in the accept path** — an oracle the operator names does the deciding, never the proposer.

---

## 2. Architecture

The system is a layered spine. Content crosses each stage through a witnessed, criterion-conserving transform: `retrieve → propose → verify → envelope → witness`, extended stage by stage across milestones M0–M7. Each stage carries its own receipt; the receipts are meant to hash-link into a chain so tampering collapses the composite verdict to `UNVERIFIABLE`.

The core loop is wrapped by four supporting bands: **verification hardening** (proving the oracle itself discriminates good from bad, and defending the witness DAG against false-accepts), **self-recursive acceleration** (research intake, improvement discovery, efficiency telemetry, and a flywheel that raises the baseline each spin), **serving** (a deterministic proposer endpoint plus a Messages-API facade with per-turn receipts), and **perception** (criterion-conserving transpilation and the probe that validates it).

**Module map, grouped by layer:**

| Layer | Modules | Role |
|---|---|---|
| L1 · Core loop (M1–M3) | `loop.py`, `oracle.py`, `witness.py`, `envelope.py`, `search.py`, `proposer.py`, `task.py` | Minimal witnessed loop + diversified best-of-N search |
| L2 · Receipt chain & gates (M2) | `chain.py`, `boot.py`, `policy.py` | Hash-linked per-stage chain, context hydration, authorization gates |
| L3 · Escalation & caching (M4–M5) | `escalation.py`, `cache.py`, `proof_cache.py` | Cheap→expensive oracle gating; content- and proof-addressed caches |
| L4 · Verification hardening | `calibration.py`, `adversarial_corpus.py`, `failure_corpus.py`, `transitive_witness.py` | Verifier credibility gates + closure over the citation DAG |
| L5 · Self-recursive acceleration | `scout.py`, `intake.py`, `evolve.py`, `telemetry.py`, `flywheel.py` | Research synthesis, improvement discovery, efficiency feedback, compounding |
| L6 · Verifier-guided search (M6) | `mcts.py`, `budget_control.py` | MCTS-lite over repair actions; correlation-triggered budget reallocation |
| L7 · Serving & eval (M0, M7) | `serve.py`, `eval.py`, `messages_api.py` | Deterministic proposer, held-out eval framework, Messages facade |
| L8 · Perception & transpilation | `transpile.py`, `perception_probe.py` | Criterion-conserved encoding + its validation |
| L9 · Domain-specific oracles | `exec_oracle.py`, `kernel_oracle.py` | Dense-reward Python execution + GPU kernel verification |
| L10 · Infrastructure & reference | `extract.py`, `wiki.py`, `trustcard.py`, `membudget.py`, `quant_dither.py`, `tasks_lib.py`, `tasks_hard.py`, `feeds.py`, `map_elites.py`, `cli.py` | Adapters, second-brain, VRAM planning, benchmark fuel, runner |

The 10-layer partition is for clarity, not a hard dependency boundary; real call paths cross layers (e.g. `flywheel → evolve → scout → calibration`).

---

## 3. What is built

**42 harness modules**, all exported through `__init__.py`, backed by **46 test files / 268 tests / ~3,754 lines**. One line each, grouped by layer.

**Core loop**
- `loop.py` — M1 minimal witnessed loop (task → propose → verify → envelope → witness).
- `oracle.py` — verifier adapter protocol (PytestOracle, SeedOracle, SandboxedOracle); deterministic `output_hash`.
- `witness.py` — re-checkable verdict MATCH / DRIFT / UNVERIFIABLE with local re-run fallback.
- `envelope.py` — proof receipt for third-party reproducibility; extends to per-stage chain at M2.
- `search.py` — M3 best-of-N with diversified temperatures, correlation detector, voice-cap (fake-agreement) gate.
- `proposer.py` — model-agnostic proposer protocol; keeps the proposer off the accept path.
- `task.py` — Task IR (re-runnable `oracle_cmd`, candidate path, hidden tests); the unit the loop consumes.

**Receipt chain & gates**
- `chain.py` — M2 hash-linked receipt chain; tamper-evidence at every stage boundary.
- `boot.py` — invocation-time hydration packet; minimum-token context snapshot, freshness-gated.
- `policy.py` — layered authorization gates (server/tool/call); trace hygiene, no secrets in logs.

**Escalation & caching**
- `escalation.py` — M4 tiered oracle escalation (compile → test → property); compute spent only on live candidates.
- `cache.py` — M5 receipt cache keyed over task+prompt+model+seed+oracle+test content.
- `proof_cache.py` — proof-addressed memory keyed on *oracle-certified facts*, prompt dropped from the key.

**Verification hardening**
- `calibration.py` — proves an oracle discriminates known-good from known-bad before it is trusted.
- `adversarial_corpus.py` — crafted DAGs probing refutation paths; false-accept gate for the transitive witness.
- `failure_corpus.py` — content-addressed regression corpus; auto-grows from every real rejection, replays on verifier change.
- `transitive_witness.py` — criterion-conservation over the dependency DAG; UNVERIFIABLE-on-ancestor-drift; paraconsistent GLUT/GAP degradation.

**Self-recursive acceleration**
- `scout.py` — autonomous research curation; ranks ACTIONABLE / INSPIRATION / NOISE by falsifiable mechanism.
- `intake.py` — feed → rank → synthesize → meta-cycle pipeline; receipt-backed accumulation.
- `evolve.py` — meta-loop ranking improvement candidates by leverage × ease × falsifiability; auto-apply gated on a falsifier.
- `telemetry.py` — RunSignal → EfficiencyProfile; surfaces falsifiable efficiency insights.
- `flywheel.py` — spin engine: run → cache fills → telemetry profiles → evolve surfaces candidates → next spin from a higher baseline.

**Verifier-guided search**
- `mcts.py` — M6 MCTS-lite over repair actions with UCB1; climbs a dense oracle-reward gradient.
- `budget_control.py` — correlation-collapse as a budget trigger; redirects converged waves to diversity re-sampling.

**Serving & eval**
- `serve.py` — M0 deterministic proposer HTTP endpoint; `prompt_hash + seed → reproducible output`; prefix-cache memo.
- `eval.py` — M7 held-out eval framework; compares single_shot vs verified_inference vs ablations.
- `messages_api.py` — Anthropic Messages-API facade; per-turn receipt binding, tier aliasing, typed errors.

**Perception**
- `transpile.py` — cross-modal transpilation (grid quantization, color carriers), each labeled honestly.
- `perception_probe.py` — validates criterion-conserving encoding against a naive coarse baseline.

**Domain oracles**
- `exec_oracle.py` — Python executor dense oracle; subprocess run, stdout compare.
- `kernel_oracle.py` — KernelBench GPU verification (COMPILE → SINGLE-KERNEL → CORRECTNESS → SPEEDUP stub).

**Infrastructure & reference**
- `extract.py` — pulls runnable code from markdown fences; idempotent on clean code.
- `wiki.py` — verified second brain composing CODE + CORPUS nodes with drift-checking `verify()`.
- `trustcard.py` — detached HMAC signature + machine-readable trust card per wiki node.
- `membudget.py` — QLoRA VRAM planner with calibrated ±20% estimates.
- `quant_dither.py` — color-science weight quantization (deterministic / stochastic / blue-noise), honest bias tradeoff.
- `map_elites.py` — MAP-Elites quality-diversity archive; resists wrong-attractor convergence.
- `tasks_lib.py` — self-validating held-out oracle task set (M7 benchmark fuel).
- `tasks_hard.py` — edge-case-heavy set for measuring harness lift.
- `feeds.py` — normalizes scraped sources into the scout catalog with dedup + domain tagging.
- `cli.py` — runner with `--search` / `--boot` / `--cache` / `--policy` flags.

---

## 4. Measured results

Every number below is measured on this hardware and codebase. Bounds are stated inline; do not read past them.

**14B continued pre-training — DONE, verified.** Qwen2.5-Coder-14B-Instruct, QLoRA (LoRA r=16), 2 epochs, **2020/2020 steps, train_loss 2.18 → 0.035, rc=0** (checkpoint-2020). On Windows this ran at ~131 s/step; a Linux smoke of the same config measured **87 s/step at 21.04 GB peak** (≈34% faster, and it barely fits). The 14B in 4-bit occupies ~9GB of weights, leaving ~1.5GB free for activations — the reason it trains where the 32B does not.

**M7 easy set — 8/8 (100%).** All tasks pass, all receipts **100% reproducible**, verdict MATCH. This is a clean result but the tasks are easy; it establishes the plumbing works end-to-end, not that the harness lifts hard problems.

**M7 hard set — 90% (9/10) vs single_shot 80% (8/10), a +10% one-task lift.** *Honest bound, stated plainly:* N=10 is tiny, the gain is a single task, and on this set **`flat_n == verified_inference`** — meaning the lift came from best-of-N sampling plus oracle selection, **not** from escalation or search cost. This does **not** prove escalation/search is load-bearing; it could be sampling noise. A larger held-out set (N≥100) is required before that claim is anything but a hypothesis. Note also this compares the harness against a single shot of *the same 14B model*, not against a frontier proprietary system.

**Curated hard lane — 110/100 tasks admitted, difficulty-screened (2026-07-09).** Every task passed `task_curator` soundness gates; the screen against the trained 14B reads **44% single-shot at temp 0 (49 saturate / 61 headroom)** — the N≥100 instrument above now exists. Artifacts: `tasks/curated/hard_v2.jsonl`, `E:\local-model-run\difficulty_screen_hard_v2_110.json`.

**HumanEval pass@1 (greedy, own harness) — 82.9% (136/164, 2026-07-09).** First public-suite number. Runner falsified first: canonical solutions score 164/164 through the same executor. One deterministic sample per task, temp 0, fence-stripping extraction, tree-killed sandboxed execution. *Bound:* this is OUR harness's number; it is not comparable to Qwen's published HumanEval figures (different prompting/extraction). The only honest comparison is the same-harness base-model run (in flight). Artifact: `E:\local-model-run\humaneval_flywheel14b.json`.

**32B — two separate configs, both true.** At seq_len 2048 / all-targets the 32B **OOMs** on the float32 upcast: it does not fit 24GB. At **seq_len 256 it PASSES** — 2 steps, loss 3.619, **peak 21.24 GB / 25.76 total**. The apparent contradiction ("does not fit" vs "passes") is two different configurations, not a discrepancy. On 24GB the 32B remains aspirational without WSL2 + fast-Linux bitsandbytes or a larger card.

**Perception probe — +20% (conserving 100% vs naive 80%), by-construction bound.** On a 20-sample grid-encoding contrast, the criterion-conserving encoder decoded 100% and the naive coarse encoder 80%. This validates the transpile-conservation principle empirically — but the naive encoder was *designed* to lose the criterion, so part of the lift is by construction. It is a single signal domain (grid), n=20; it validates the principle, not a behavioral discovery, and does not yet generalize across color/sound/art.

**Flexible-generalization marker — COPY-ONLY (the strong "workspace-loaded" claim is REFUTED).** The stronger, non-by-construction test asks whether *one* conserving encoding supports *many* functions. It does not: over 20 scenes the model scored locate **100%**, but nearest **20%**, count **10%**, quadrant **5%** — 1/4 functions handled → **COPY-ONLY**. The transpiled signal is a readable *lookup* carrier, not a perception engine: the model reads it and answers direct lookups, but cannot reason flexibly over it. This fails the workspace paper's own flexible-generalization marker. Notably, **the harness's own measurement layer caught the overclaim** — the +20% "PERCEPTION" verdict did not survive the stronger marker. That is the thesis (verification refutes inflated claims) working on our own work.

**Verification hardening — SOUND on the corpora tested.** Transitive witness: **0/7 false-accepts, 0 over-rejects**; the strawman outcome-only witness caught 7/7 and a depth-limited variant only 2/7, isolating the closure property as the thing doing the work. Adversarial closure: SOUND across 7 crafted attacks — with the honest caveat that 7 attacks make no claim of exhaustiveness. Proof-cache fix: agent-cache-hit **0% → 100%** after stripping volatile per-turn headers at the key site. Wiki freshness: a false-fresh hole (source_ref non-uniqueness) was found by a 5-agent audit, fixed, and regression-tested — fixing one drift mode, not all of them.

**Hardware envelope, measured:** 24GB GPU VRAM (~22GB idle-free); C: ~105GB free (near full); E: ~859GB free (the run drive). Test suite: 292 passing at the state-cursor snapshot (the code-inventory pass counts 268 test functions; the difference is granularity, not disagreement — some tests carry multiple assertions).

---

## 5. Research provenance

The research lane is receipt-sealed. A two-stage funnel (scout shortlists by title-novelty signal, deep-fetch extracts mechanisms from the linked papers) drove **8 harness-lane arXiv queries + 7 broad-domain queries across 15 domains**, each with a sha256 seal, sampling ~45 June-2026 preprints and cataloging a 24-paper high-collision subset. A separate 19-paper deep-dive ran the adversarial novelty audit.

**The honest verdict: no breakthrough.** All five competing candidate architectures surveyed are **strong-synthesis** — genuine, unpublished *composition* of known modules, not a new verification primitive. That is the truth of the contribution, not a limitation to be argued away. Field-adjusted, roughly **1.5 of 5 headline claims are pre-empted** by current arXiv:

- **Proof-Addressed Memory — ~half pre-empted.** GroundedCache (2605.27494) pre-empts the genus (criterion-gated cache + re-witness on hit). The surviving, defensible move is the *keying inversion*: we key on an **oracle-certified fact**, not the query/prompt/model, with **no learned judge**. Novelty shrank from "a new kind of cache" to "a specific addressing scheme" — stated as such.
- **Transitive Witness — the surviving frontier.** Not pre-empted. The **closure property** (criterion conserved along the whole path; `UNVERIFIABLE` the moment any ancestor drifts) is the center of gravity; no prior art touches re-witnessing closure. This is where the real novelty lives.
- **Witnessed Transform — now table stakes.** SEVerA's FGGM (call → check → gate) is the per-stage shape. Do not pitch it as novel.
- **Flywheel economics + Verified-Wiki freshness — partly folded in.** Recurrence motivation is pre-empted by 2512.21309 (~30% request recurrence) and 2504.13171 (sleep-time precompute); wiki freshness partly folds into GroundedCache version-validity.

**The workspace/perception thread.** The `boot.py` hydration packet is, functionally, an externalized global workspace — small, broadcast, selectively read — the same shape as the workspace-theory papers describe. "Perception lands in the workspace" is framed as a *buildable behavioral test* (flexible-use lift vs rote extraction), with a five-marker signature (flexible generalization, selectivity, verbal report, directed modulation, precedence). Markers 1–4 are behaviorally clean; **marker 5 (precedence) is weakest** without interpretability access and remains design-only.

**Functional-access boundary — Block A / P split, no phenomenal claim.** The workspace-signature design draws an explicit metaphysical boundary: it measures **functional access** (what the system can flexibly use and report on) and makes **no claim of phenomenal experience**. The behavioral markers are gated on the perception result; the design stops at what is measurable and says so.

Every arm's receipts reproduced 100% across the 8- and 10-task suites; pass rates ran 80–100% by oracle difficulty; no false-accepts in the test corpus. Sweep breadth is prospective, not complete: 7 of ~60 subreddits sampled (~12%), the rest crawlable — no silent cap, but coverage is a promise, not a measurement.

---

## 6. Roadmap

Ranked by what would actually move the thesis, hardest-earning first.

1. **A harder, larger M7 for a conclusive lift — instrument BUILT (2026-07-09), run pending.** The curated lane holds 110 hash-verified tasks, every one admitted through `task_curator` soundness gates (reference-passes, oracle-can-fail, leak, behavioral dedup). The difficulty screen against the trained 14B (`ollama` identity, honest model_ref) reads **44% single-shot at temp 0: 49 saturate, 61 headroom** — real statistical room at last. What remains is the matched-budget ablation run itself; until it runs, "the harness lifts" stays a hypothesis.
2. **Close the composition gap — Transitive Witness, full.** Today every receipt is an island: `validate_chain` only checks `prev_hash` equality and never re-witnesses. Extend the witness from kernel to an adversarial false-accept corpus and wire closure over real `ProofEnvelope` citation edges. This is the surviving-novelty frontier *and* the honest gap; closing it is the highest-leverage research move.
3. **Full 32B CPT.** seq_len 256 fits (21.24 GB); the path to real training is activation-CPU-offload (a DeepSpeed config is staged but unsmoked) or WSL2 + fast-Linux bitsandbytes. Resolve whether 32B is trainable on 24GB or genuinely needs a larger card.
4. **Diagnose COPY-ONLY, then the workspace markers.** The flexible-generalization marker returned COPY-ONLY (lookup, not reasoning). The immediate diagnostic (`run_encoding_sweep.py`, built) sweeps labels vs reasoning-friendly (label+decoded-coords) vs raw-coords to separate *format bottleneck* from *model-limited*. If a reasoning-friendly encoding recovers flexible use, that is a real tooling fix; if not, the model simply can't do the spatial reasoning. Only then extend to the remaining behavioral markers.
5. **Wire perception into the loop.** `transpile.py` / `perception_probe.py` are deployed but not yet feeding the core reconcile — and given COPY-ONLY, the honest precondition is a representation the model can *reason over*, not merely copy. Multi-domain proof (color/sound/art) is needed before the +20% generalizes.
6. **Serving traffic: F1 + F2.** The Messages facade (per-turn receipts) plus prefix canonicalization for the receipt cache, to drive real agent traffic — the payoff the proof-cache fix is waiting on.
7. **Field mechanisms to adopt:** adversarial verifier-can-fail corpus (2606.09682), process-level per-node re-check, paraconsistent glut/gap degradation (2507.09751), epoch-boundary criterion versioning (2606.26294).
8. **The superapp — one interoperable surface.** [SUPERAPP.md](SUPERAPP.md) is the unification spec (showcase shell + packaged app + companion routing + training lane + projected world). Increment 1 (the shell binds every number to receipts, falsifiers fired live) shipped 2026-07-09; increments 2–5 follow the ladder in the spec.

---

## 7. Honest state

What is genuinely done: the 14B CPT (loss 2.18 → 0.035); the 42-module harness with M0–M7 stages present and 268/292 tests passing; the verification-hardening corpora sound on the cases tested; the proof-cache and wiki-freshness fixes with regression tests; the receipt-sealed research sweep and its novelty audit.

What is **not** done, and would be theater to claim otherwise:

- **The harness lift is not proven.** +10% on N=10, one task, `flat_n == verified_inference`. This does not establish that escalation, search, or the receipt chain earns its keep. It is honest to call it a suggestive single data point and dishonest to call it a validated result.
- **Criterion-conservation does not compose end-to-end.** Chains check `prev_hash` equality only; they never re-witness. Every receipt is currently an island. The whole "compositional witness" story is a design with a kernel, not a shipped closure.
- **No frontier comparison exists.** M7 measures the harness against a single shot of the *same 14B*. There is no head-to-head against Claude, GPT-4, or any frontier system — so "beats frontier single-shot" remains the thesis, unmeasured.
- **32B is aspirational on 24GB.** It fits only at seq_len 256; full CPT is unproven.
- **Perception +20% is partly by construction** (the naive encoder was built to lose the criterion), single-domain, n=20. It validates transpile-conservation, not a behavioral discovery. The stronger flexible-generalization marker returned **COPY-ONLY** (1/4 functions) — the transpiled signal is a lookup carrier, not workspace-loaded. The consciousness-adjacent thread gets an honest **negative**, not a discovery.
- **The proof-cache pays off only under real traffic.** Empirical hit rate on current agent traffic was 0% before the fix; the fix is verified in isolation, but the payoff needs F1 client traffic to materialize.
- **Adversarial and wiki-drift corpora are non-exhaustive.** 7 attacks, one drift mode fixed — no enumeration of all tampering or drift modes is claimed.
- **Stale artifacts to distrust:** older STATE entries claiming "149 passing" (actual: 292) and resume-point instructions describing WSL2 setup as pending (it is complete). Treat those as superseded.

The shape of the project is a rigorous, honestly-bounded composition over known parts. The plumbing is real and reproducible; the headline claim — verified inference on a local model beating a frontier single shot — is a well-instrumented hypothesis with the falsifiers already written, not yet a demonstrated result. That distinction is the point.
