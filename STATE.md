# STATE — live cursor

> **Canonical overview: [PROJECT.md](PROJECT.md).** This file is the running,
> append-only work log (newest-first); PROJECT.md is the synthesized, honestly-
> bounded picture of the whole project. Read PROJECT.md first.

> The moving cursor for the local-model program. `ROADMAP.md` is the durable
> backbone (the WHY and the phase plan); this file is where we are RIGHT NOW.
> Update on every material step. If context is lost: read ROADMAP.md, then this.

Last updated: 2026-07-06

## 2026-07-07 (cont.) — week-lane increments #2/#4/#7-prereq shipped

- **dataset receipt** (`dataset/receipt.py`): re-derivable corpus -> shards ->
  checkpoint chain, privacy invariant held (paths as sha256 only, falsifier
  asserts no leak). **REAL receipt derived for checkpoint-2020** (17,997 files
  / 0 missing / 8 shards / adapter sealed, round-trip MATCH), written beside
  the adapter on E: + committed copy in tasks/research/. Marked RETROACTIVE in
  the receipt itself (pack+checkpoint seal what trained; corpus layer is
  as-of-derivation — future runs seal at pack time).
- **knowledge_monitor** (`harness/knowledge_monitor.py`): standing observation
  over the verified base; subscriptions fire on verdict TRANSITIONS only
  (drift twice fires once; recovery fires; steady state never re-fires);
  read-only query API (concepts / kind / tier / last-verdict / neighbors).
- **task_curator** (`harness/task_curator.py`): admission gates for the
  N>=100 hard-set lane (reference_passes, oracle_can_fail via return-None
  stub, deterministic, no_solution_leak, edge_coverage>=4, dedup); JSONL
  registry with per-row hashes that refuse to load tampered. DOGFOOD: the
  existing 18-task benchmark screened 15/18 clean — 3 easy tasks fail only
  the new edge_coverage bar; ALL 18 pass oracle_can_fail + no leak, so the
  M7 sets carry no vacuous tests.
- **hard-set lane: 17/100 admitted, registry verified dup-free.** Batch 1
  (10) + batch 2 (9 of 10; the gates caught MY OWN count_islands test bug and
  a flatten_nested id collision). The id+hash dedup then proved too weak (3
  semantic dups admitted, culled): text similarity was measured and REJECTED
  as a fix (disguised rewrite jaccard 0.07 < legit decode/encode 0.27); the
  gate is now BEHAVIORAL and BIDIRECTIONAL (equivalent iff each solution
  passes the other's hidden tests; one-way = subsumption, admitted —
  search_rotated > binary_search is the noted case). Full sweep: 0 dups.
  Soundness-admitted ONLY; difficulty screening vs the served 14B comes later.
- **GGUF/Ollama packaging BLOCKED on operator review**: the pipeline script is
  ready (scratchpad ship_gguf.sh: llama.cpp clone/build, f16 convert,
  streaming export-lora merge — 15GB RAM box, quantize Q4_K_M, deterministic
  smoke, hash manifest) but the sandbox denied cloning/building an external
  repo (llama.cpp) without operator approval. Needs a green light or a manual
  run.
- Session slice green: 57 tests across the five new organs + collaborators.
- Remaining month-lane (gated, named): GGUF/Ollama packaging (toolchain not
  yet installed in WSL; checkpoint + 948G disk ready), actual 100-task
  curation through the gates, N>=100 matched-budget ablation (decides the
  uplift question; publish whatever it says, including zero).

## 2026-07-07 — GROUNDING CLOSURE SHIPPED (the ranked #1 increment)

- **transitive-witness closure is ON the critical path** (`harness/grounding.py`
  + `run_loop(grounding_recheck=True, grounding_workdirs=...)`): cited
  grounding resolved transitively from the envelope store, each ancestor
  re-witnessed in its own oracle environment, closure folded, acceptance gated
  on the transitive verdict, grounding stage sealed into the chain.
- **The 3-arm falsifier FIRED end-to-end on real envelopes**
  (`tests/test_grounding_closure.py`, 7 tests): tampered A -> DRIFT; B citing
  A -> UNVERIFIABLE (gap not glut), refused despite its own oracle passing,
  never sealed into the store; independent C -> MATCH (localization). Positive
  control: healthy grounding conserves MATCH. Fail-closed: missing envelope or
  missing oracle environment -> UNVERIFIABLE (never assumed MATCH, never a
  wrong-workdir fake re-run). Behavior-change proof: pre-wire path ACCEPTS the
  same poisoned setup; wired path refuses. No capability claim beyond that.
- **FLAGSHIP-PLAN.md added** (7-category ranked plan from the workflow sweep,
  run wf_643cfd70-9cb): harness #1 (shipped above), then dataset receipt ->
  knowledge monitor -> N>=100 curation lane -> packaging; compiler/creative
  parked; uplift deliberately last. M7 +10% stays quarantined as UNEARNED.
- Collaborator slice green (39 tests: grounding, m1, transitive, chain,
  adversarial corpus).

## 2026-07-06 (latest) — accountability benchmark category + flagship plan

- **accountability_bench committed** (`harness/accountability_bench.py` + 5
  falsifiers): a NEW benchmark CATEGORY scoring accountability, not capability.
  7 dimensions, each an aggregation over an existing tested module
  (re-checkability, externalization, adversarial soundness, no-regression,
  invariant fidelity, null-space honesty, provenance). Credibility test:
  strawman (unaccountable system) scores 0.0 vs harness 1.0 — the benchmark can
  FAIL. The 1.0 is near-tautological (self-authored axes) and the receipt says
  so; the value is scoring OTHER systems on axes they ignore. Deliberately NO
  capability/uplift axis (the uplift is unearned).
- **Flagship-establishment workflow** (7 categories): first run died mid-flight
  after 5/7 assessments (saved to scratchpad `flagship_assessments_partial.json`);
  resumed from journal `wf_643cfd70-9cb` for harness + compiler-pl + Rank.
  Landed maturities (honest): second-brain=demo, creative=demo,
  uplift-engine=demo, dataset-trainer=demo, local-models=kernel (no shipped
  artifact yet; increment = GGUF-quantize the 14B adapter + Ollama Modelfile).

## 2026-07-06 (late) — superproject, cross-domain series, ABLATION NEGATIVE

Branch at 58 commits (~390 tests). Since the M7 run:
- **ABLATION NEGATIVE (load-bearing).** The M7 hard-set +10% lift (single 80% ->
  verified 90%) DID NOT REPRODUCE. `scripts/run_ablation.py`: single 80% /
  verified-external 80% / verified-self 80% = **+0%**. The +10% was 1 task of 10, no
  CI, inside noise. "Verification raises capability" is **UNEARNED** (single-shot
  saturates at 80%; 7/10 model-written self-tests broke). Needs a harder set
  (single < 80%), larger N, a CI. `verified_lift` relabeled 1.125x -> 1.0 in asymmetry.py.
- **Superproject** (`superproject.py` + `SUPERPROJECT.md`): 11 flagships = 5 MCP-live
  spine (gather/crucible/index/forum/telos, doctors MATCH) + 6 declared (emet,
  accountable-surface, learn, proof-surface, coherence-membrane, studio-engine); +
  build-* bricks. Organs <-> flagships as peers (MCP = optional edge); spine closed.
- **Cross-domain mechanism series** (cross_domain, silhouette, inversion_flywheel,
  fluid_router, valve_flywheel, backflow, turbulence): the reconcile primitive across
  fields = REACH not law (self-labeled; audit retired the "unification" + the composed
  "amplitude" as a defined score not a launch variable). turbulence: re-checkability
  breaks at +Lyapunov, conserve the invariant not the trajectory. silhouette:
  access/phenomenal = permanent null-space floor. No consciousness claim.
- **asymmetry catalog** completed (4 amplifiers + 7 gates, 9 domains, grounded calls).
- **externalization** earned for VERIFICATION (non-self-authored check catches cheats
  self-authorship accepts; domain-general 5/5 + 7 fields), NOT for capability.
- **Process:** committed a red fluid-router test once (caught + fixed in the open, gated
  commits after). Two corrections landed from ground truth: flagship count (5 -> 11) and
  the ablation negative — both against the project's own preferred story.

## 2026-07-06 — research intake + verified second brain (Fable 5 session)

Continued from the paused OpenCode/glm-5.2 session. On-disk suite confirmed
**149 -> 241 passing** (the "137" in older notes was stale; +9 scout calibration,
+10 wiki, +5 intake, +7 audit-fix, +6 feeds, +10 research-theses, +7 transpile,
+8 proof-cache, +11 transitive-witness, +13 adversarial-corpus, +3 transitive-
integration, +3 prompt-canonical). Under git (genesis 7a99c68). New work:

- **Current arXiv sweep + honest novelty audit (2026-07-06).** 8 sealed
  gather_arxiv queries (~45 June-2026 preprints) + a 19-paper deep-dive reading
  each abstract adversarially. Verdict: ~1.5 of 5 headline claims eroded.
  PROOF-ADDRESSED MEMORY ~half pre-empted by GroundedCache (2605.27494 publishes
  criterion-gated reuse + re-witness-on-hit + USR); the prompt+model-absent
  oracle-fact keying with NO learned judge survives. WITNESSED-TRANSFORM now
  table-stakes (SEVerA FGGM). FLYWHEEL economics pre-empted (2512.21309,
  2504.13171). **TRANSITIVE WITNESS untouched by all 19 — the defensible center
  of gravity, and it was unbuilt.** Full audit in
  `tasks/research/ARXIV_FIELD_VERDICT_20260706.md` + `arxiv_sweep_20260706.json`.
- **Built TRANSITIVE WITNESS (the frontier).** `harness/transitive_witness.py`
  (+`test_transitive_witness.py`, 11): compositional criterion-conservation over
  a dependency DAG — MATCH conserved only along a fully-MATCH path; upstream DRIFT
  gaps downstream-dependents while independents hold (localization proven);
  paraconsistent glut/gap (2507.09751); no-receipt-never-MATCH adversarial gate
  (2606.09682); process-level per-node re-check (2508.16665).
- **Adversarial false-accept corpus (the credibility gate).**
  `harness/adversarial_corpus.py` (+`test_adversarial_corpus.py`, 13). Crafted DAG
  attacks (drifted-ancestor, deep-drift depth-evasion, cycle-laundering, dangling
  grounding, no-receipt, glut-launder, unverifiable-ancestor) + controls. The real
  closure scores **0/7 false-accepts, 0 over-rejects (SOUND)**; anti-theatrical
  proof: the outcome-only strawman is caught 7/7 and the depth-limited strawman
  2/7 (only the multi-hop attacks) — the refutation path provably executes,
  resolving the crucible "refutations never execute" weakness. Honest scope: a
  sound, adversarially-gated kernel; not a breakthrough.
- **Transitive witness wired over REAL envelopes** (+`test_transitive_integration.py`,
  3). `verify_frontier(envelopes, rewitness)` folds the closure over live
  ProofEnvelope citation edges (run_loop stamps `retrieved`). End-to-end
  falsifier: a 2-task citation chain (B cites A) + independent C — tamper A's
  verified result -> A re-witnesses DRIFT -> B gaps UNVERIFIABLE -> C holds MATCH.
  Closes the kernel->production gap (no longer a synthetic-node demo).
- **F2 fix: prompt canonicalization** (`cache.canonical_prompt`,
  +`test_prompt_canonical.py`, 4). Strips volatile decorations (attribution
  headers, req/session/trace ids, timestamps, co-author trailers) at the cache
  KEY site only (provenance prompt_hash untouched). Fixes the 0%-agent-cache-hit:
  a volatile-header-only change now HITS; a semantic body change still MISSES.

- **Architecture synthesis (11-agent workflow) → Proof-Addressed Memory kernel.**
  Mapped the whole corpus+codebase, generated 5 competing unifying architectures,
  adjudicated for genuine novelty. Honest verdict: NONE a breakthrough, all
  strong-synthesis. Winner built: `harness/proof_cache.py` (+`test_proof_cache.py`,
  8) — keys the verified-result cache on the oracle-certified FACT (prompt+model
  ABSENT), justified by C2 (acceptance is oracle-gated, prompt-independent). Fixes
  the F2 0%-agent-cache-hit bug. Wired into run_loop as OPT-IN (`proof_addressed`,
  default off): model-invariance is right for SERVING, wrong for M7 A/B eval, so
  eval leaves it off. A proof-hit is re-witnessed (C2 preserved), scope-gated by
  PROMPT_INDEPENDENT={pytest,stub}. Falsifier caught a real key bug (PytestOracle
  augments cmd with --junitxml). Full synthesis + roadmap in
  `tasks/research/ARCHITECTURE_20260706.md` (next: #2 Transitive Witness =
  compositional criterion-conservation).
- **14B CPT resumed** from checkpoint-1850 (the run died on a host restart at
  step 1881/2020, loss 0.394). Relaunched MODEL_SIZE=14B --resume in screen
  cpt14b; ~170 steps (~2.5 hr) to finish 2 epochs, then M7 eval unblocked.

- **Scout calibration fix (self-recursive, on real data).** Dogfooding the
  operator's real X reposts through `scout` classified ALL 13 as NOISE/
  INSPIRATION — a reproducible perception bug. Two root causes found + fixed with
  a falsifier (`tests/test_scout_calibration.py`, 9 tests): (B1) relevance was
  `hits/word_count` — length-fragile, the SAME thread flipped ACTIONABLE<->NOISE
  on verbosity; replaced with coverage-saturation `hits/(hits+K)`. (B2) vocab
  matched as substrings ("merge" in "emergent"); replaced with word-boundary
  matching. Post-fix the feed reads 2 actionable / 6 inspiration / 5 noise.
- **`harness/intake.py`** (+`test_intake.py`, 5) — curated feed (X reposts /
  gather / reading list) -> `scout.rank` -> `synthesize_feed` -> `evolve.
  meta_cycle`, with a content-addressed digest receipt. Exposes `.research_feed`
  so ONE intake drives both evolve and `flywheel.spin(research_feed=...)`.
- **`harness/wiki.py`** (+`test_wiki.py`, 10) — the verified second brain.
  Composes index_wiki's commit-pinned code pages + corpus nodes (scout-
  classified); links DERIVED from shared concepts (not hand-typed); every node
  content-sealed; `verify()` returns MATCH / DRIFT / UNVERIFIABLE — the freshness
  verdict Obsidian cannot produce. Built real base: 525 nodes (512 code + 13
  reposts), 379 derived links. Adversarial audit (5-agent workflow) found a
  false-fresh HOLE (freshness keyed by non-unique source_ref); fixed (id-keyed +
  ambiguous_ref -> UNVERIFIABLE) + regression `test_audit_fixes.py` (8).
- **`flywheel.research_feed_from_catalog`** — the glue the audit flagged missing:
  a catalog now actually reaches `flywheel.spin`. Live spin on the real feed:
  cache hit 0%->100%, avg_oracle 1.0->0.
- **Primary-source dive**: read leopardracer's "second brain" article (the real
  data behind the repost) via authenticated browser -> `tasks/research/
  second_brain_primary_source.md` (method + where verified beats it + build gaps).
- Artifacts: `tasks/research/x_reposts_20260706.json` (corpus),
  `x_reposts_digest.json` (receipt), `second_brain_primary_source.md`.
- **Research firehose ingested** (YouTube + ~60-subreddit list + 2 articles).
  Reached primary sources via authenticated browser + a 5-agent dive workflow
  (NVIDIA OpenShell/Verified-Skills/RL doctrine, Anthropic GWT video + workshops,
  shadcn, Ollama-compat). New durable capability `harness/feeds.py`
  (+`test_feeds.py`, 6) — normalizes any scrape → scout catalog with dedup,
  provenance, and the operator's ~60-sub → Telos-domain map; `coverage()` logs
  sampled-vs-remaining (7/60 sampled, no silent cap). Theses poured back as
  `tests/test_research_theses.py` (10): T1 Global-Workspace=boot-packet
  (Anthropic video), T2 criticality/edge-of-chaos (complexsystems+MAP-Elites+AWG),
  T3 deny-by-default policy = hashed receipt (NVIDIA OpenShell). Build brief +
  provenance in `tasks/research/THESES_20260706.md` and `reddit_scrape_20260706.json`.
  Finding: title-only scout under-classifies → two-stage funnel (scout shortlist
  → deep-fetch mechanism). Top build candidates: F1 Anthropic `/v1/messages`
  facade + receipt-per-turn (category capture), F2 prefix-canonicalize the cache
  (real bug: agent header → 0% hit rate).
- **Git: DONE.** Repo initialized (genesis 7a99c68); work lands on
  `feat/proof-addressed-memory`. `.gitignore` excludes secrets, E: run assets,
  and the proprietary corpus manifest.

## Expansion round (2026-07-06, model-independent, while the 14B trains)

Research-flagged mechanisms built to falsifier-gated completion (each composes
with the spine; 292 tests green, incl. +7 code-extraction). Includes the full build-brief F1-F8 (F1
Messages-API facade + receipt-per-turn `messages_api.py`; F5 detached HMAC
signature + trust-card `trustcard.py`) and architecture theses #4 provenance-keyed
flywheel (`cache.knowledge_hash`) + #5 correlation-steered compute
(`budget_control.py`):
- **criterion-versioning** (`transitive_witness.staleness_report`) — DRIFT vs
  REBASELINE (Red Queen 2606.26294).
- **verifier calibration** (`calibration.py`) — who verifies the verifier; a
  false-accept -> untrustworthy; `require_calibrated` gates the accept path (F3).
- **failure-corpus flywheel** (`failure_corpus.py`) — rejections become durable
  known-bads that grow the calibration set + catch verifier weakening (F4).
- **M7 runner + reconstructable scorecard** (`scripts/run_m7_eval.py`, `eval.py`
  F8) — measures HARNESS LIFT (verified vs single-shot of the same model); pinned-
  baseline deltas; dry-run proven. Fires when the adapter lands.
- **witnessed wiki write-back** (`wiki.propose_write`, F6) — refuses ungrounded/
  absent/drifted (hallucinated) writes; the unattended-second-brain guard.
- **session ingestion** (`feeds.normalize_sessions`, F7) — session history into
  the verified corpus via scout -> intake -> wiki.

Deferred as genuinely sprawl (need a real scenario/equivalence, no gap today):
region-caching, determinism-hardening (oracle path already deterministic).

## GPU endgame
- **14B CPT COMPLETE (2026-07-06): DONE rc=0, 2020/2020, 2 epochs, train_loss
  2.18 -> 0.035.** Final adapter at checkpoint-2020 (LoRA r=16, all-targets).
  GPU released.
- **M7 eval RAN on the trained 14B (2026-07-06): 100% pass (8/8) all arms,
  receipts 100% reproducible, verdict MATCH.** Scorecard:
  `tasks/research/m7_scorecard_20260706.json`. Two harness bugs found + fixed en
  route (NOT a bad model): (1) served instruct model wraps code in markdown fences
  -> `harness/extract.py` strips them in ServeProposer; (2) oracle `python -m
  pytest` exited rc=127 (WSL has only python3; training venv lacked pytest) ->
  finisher installs pytest + prepends venv to PATH.
  **HONEST READ:** the pipeline is validated end-to-end on a real trained model
  (propose -> extract -> verify -> witness -> accept, every receipt re-checkable),
  but single_shot already saturates at 100% on these 8 easy tasks, so there is NO
  HEADROOM to measure verified_inference's LIFT (it costs 4x oracle calls for the
  same 100%). Measuring the lift the thesis predicts requires a HARDER held-out
  slice where single_shot < 100%. That is the honest next benchmark step.
- **HARD M7 (10-task frontier set, `tasks_hard.py`) — THE LIFT IS REAL, measured
  (2026-07-06):** single_shot **80% (8/10)** -> verified_inference **90% (9/10)**;
  no_search 80% -> flat_n 90%. Oracle-gated best-of-N recovers a task greedy
  fails. Scorecard `m7_hard_scorecard_20260706.json`, verdict MATCH.
  **HONEST BOUNDS (no overclaim):** N=10 (tiny), the lift is ONE task (+10%), and
  verified_inference == flat_n — so the gain is best-of-N sampling + oracle
  SELECTION, NOT the escalation/search machinery (4x oracle cost, no measured
  benefit over flat best-of-N here). Larger/harder set needed before conclusive;
  but the direction is validated: verification-guided sampling lifts a capable-
  but-inconsistent model above its own single-shot.
- **Perception thread opened** (`workspace_perception_20260706.md`): the
  transformer-circuits workspace/J-space paper is the measurable INTERNAL analog
  of boot.py's EXTERNAL workspace; the transpiler delivers perception IFF the
  transpiled signal becomes workspace-loaded (flexible use) — behaviorally
  testable here.
- **Perception MEASURED (2026-07-06):** `perception_probe.py` (5 falsifiers) +
  `run_perception_probe.py` on the trained 14B: **conserving encoding 100% locate
  accuracy vs naive 80%, +20% lift, verdict PERCEPTION** (N=20). The model reads
  the transpile carrier perfectly (perception is usable) AND criterion-conservation
  is load-bearing (+20% over the lossy encoding). HONEST BOUND: partly by-
  construction (naive was designed to lose the criterion) — a clean validation of
  transpile-conservation, NOT a discovery. Scorecard committed.
- **Functional-access-marker layer DESIGNED** (`workspace_signature_design_
  20260706.md`): the honest consciousness-adjacent seam. Measures the workspace
  paper's 5 behavioral markers as ACCESS/FUNCTIONAL correlates — never phenomenal
  experience (Block's A/P split is the hard boundary; interpretation is framework-
  relative: GWT/illusionism say yes, IIT/biological-naturalism say no). boot.py =
  global broadcast; reconcile loop = higher-order monitor — two functional theories'
  architectures already instantiated by engineering. NO composite "consciousness
  score" (that would be theater). Next build: the flexible-generalization marker.
- **Flexible-generalization marker: COPY-ONLY (2026-07-06) — the strong claim is
  REFUTED.** One conserving encoding, four functions: locate **100%**, nearest
  **20%**, count_left **10%**, quadrant **5%** -> 1/4 handled -> COPY-ONLY. The
  model READS the transpiled carrier and does direct lookup perfectly, but CANNOT
  reason flexibly over it (distance/count/region all fail). So the transpiled
  signal is COPYABLE, NOT workspace-loaded — it fails the workspace paper's own
  flexible-generalization marker. **The earlier +20% "PERCEPTION" was by-
  construction (naive threw away the answer); the stronger, non-by-construction
  marker shows the transpiler is a readable LOOKUP carrier, not a perception
  engine.** No functional-access marker passes; the consciousness-adjacent thread
  gets an honest NEGATIVE, not a breakthrough. Notably, the harness's OWN
  measurement layer caught our overclaim — the thesis (verification refutes
  inflated claims) working on our own work.
- **Encoding sweep — the weak point DIAGNOSED + integrated (2026-07-06).** labels
  **0.20** -> reasoning **0.30** -> raw coords **0.467** mean over 3 spatial-
  reasoning functions (n=20). Two real things: the opaque grid-label FORMAT is a
  major bottleneck (raw coords >2x labels) AND the model has a spatial-reasoning
  ceiling (~0.47 even with ideal coords). **Native fix integrated:**
  `transpile.grid_metric_form` (compact label + decoded metric coords) — the
  reasoning-conserving form; principle refined to *conserve the criterion the
  DOWNSTREAM TASK needs* (lookup->label, reasoning->metric). perception_probe now
  composes onto it. Scorecard committed.
- **Finding -> tooling seam:** COPY-ONLY exposes that the grid-label encoding is a
  lookup format, not a reasoning-friendly one (the model can't compute over labels
  without decoded coordinates). The real next build is a reasoning-friendly
  transpile mode (expose decoded coords alongside labels) + re-run the marker —
  turning the negative into the next capability. Scorecard committed.
- (history) 14B CPT resumed from checkpoint-1850; watcher caught the DONE marker.
- M7 endgame: `bash scripts/finish_and_eval.sh` (done, above).
- **32B QLoRA smoke PASSES on the single 4090 (2026-07-06): seq_len 256, peak
  21.24 GB / 25.76 total (1.8 GB free), 2 steps, loss 3.619, DONE rc=0**, adapter
  at `checkpoints/phase2-linux-qlora-cpt-32b-smoke/checkpoint-2`. Corrects the
  prior "32B does not fit" — that was at seq_len 2048 (activation memory); the
  planner's seq_len-256 prediction is confirmed. No DeepSpeed offload needed; the
  seq_len reduction alone gets the 32.9B model under the 24 GB ceiling.
  **Democratization result: a 32B is QLoRA-trainable on commodity HW at short
  context.** (Full 32B CPT at seq_len 256 is now a viable follow-up run.)

## Layer B harness — M1 done (structural)

M1 (minimal witnessed loop) built and falsifier-proven (HARNESS-ROADMAP.md M1).
3/3 falsifier tests pass. The falsifier caught 2 real design flaws before
promotion: (a) non-deterministic oracle hashing (pytest's `N passed in X.XXs`
timing line broke the receipt chain → fixed via `--junitxml` canonical hashing),
(b) shared-workdir test interference (→ fixed via isolated tmp_path workdirs).

- `harness/task.py` — Task IR + loader (workdir-isolated).
- `harness/proposer.py` — Proposer adapter: StubProposer / ServeProposer (M0
  serve.py) / EnterpriseProposer (OpenAI-compatible). Model-agnostic boundary.
- `harness/envelope.py` — ProofEnvelope (HARNESS.md §proof-envelope receipt).
- `harness/oracle.py` — Oracle adapter: PytestOracle (deterministic canonical
  hash via junitxml) + StubOracle. M2 promotes SeedOracle (aleph/seed) +
  SandboxedOracle (behavior-transform) as new subclasses, same Protocol.
- `harness/witness.py` — canonical re-run → MATCH/DRIFT/UNVERIFIABLE.
- `harness/loop.py` — run_loop: retrieve → propose → verify → envelope → witness.
- `tasks/example_pass/` — held-out task with real pytest oracle (3 tests).
- `tests/test_m1_falsifier.py` — golden/failing/corrupted: 3/3 pass.

**Boot stage (Layer-1 hydration) — built + falsifier-proven + end-to-end smoke:**
- `harness/boot.py` — BootPacket (aligned to context-envelope/v1 shape) +
  `boot()` composer (system/workspace/goals/decisions slots) +
  `verify_boot()` freshness gate (root_hash drift → DRIFT) +
  `hydrate_prompt()` (injects compact `[ground]` header into the prompt).
- Minimum-token via lossless-by-ref: model gets shape + digests + expansion
  cmds, not raw bytes. Budget-enforced.
- Wired into `harness/loop.py` (retrieve → hydrate → propose) and
  `harness/envelope.py` (new `injected_context` field carries the boot receipt
  so every verdict can distinguish grounded-failure from starvation-failure).
- `tests/test_boot.py` — 9/9 pass (determinism, freshness-collapse, missing/
  empty→UNVERIFIABLE, budget ceiling, summary extraction, hydrate, receipt).
- End-to-end smoke (`scripts/smoke_boot_integration.py`): real project tree →
  MATCH, 40 files, ~1492 tokens (under 1500 budget), envelope carries receipt.
- Full suite: 15/15 green (boot + M1 + conformance).

**Policy / admission gate (Layered authorization) — built + falsifier-proven:**
- `harness/policy.py` — `Decision` (ALLOW/BLOCK/ESCALATE/TRANSFORM) +
  `PolicyResult` + `PolicyLayer` protocol + `gate()` chain (server→tool→call,
  first non-ALLOW wins) + `CallShellPolicy` (deny tokens + allowed-roots) +
  `ToolCapabilityPolicy` (static capability shape) + `default_harness_gate()`.
- Wired into `harness/loop.py`: gate runs BEFORE the oracle handler. Blocked
  call → `oracle=None`, `verdict="BLOCKED"`, admission record in envelope, NO
  verification verdict (handler never ran). Closes the arbitrary-shell hole.
- `harness/envelope.py`: new `admission` field — admission (policy) is
  orthogonal to verification (oracle/witness) and to grounding (boot), per the
  loop_ledger "separate admission from verification" contract.
- Trace hygiene: `PolicyResult.to_trace()` carries args_hash + reason_code +
  policy_id + boundary, NEVER raw args/cmd/paths/secrets.
- `tests/test_policy.py` — 6/6 pass (blocked=decision-not-failure, args_hash
  not raw args, allowed-runs-normally, workdir-escape, capability-set, unit).
- Full suite: 21/21 green. Composes with behavior-transform.io (policy
  decides whether; behavior-transform receipts what ran). ESCALATE/TRANSFORM
  decisions are stubbed in the enum; the decisive BLOCK path is proven.

**M2 spanning receipt chain (the spine) — built + falsifier-proven:**
- `harness/chain.py` — `StageReceipt` (hash-linked, content-hashed excluding
  prev_hash) + `validate_chain()` (walks links; broken link → UNVERIFIABLE) +
  `append_stage()` / `chain_to_dicts()` / `chain_from_dicts()`.
- Wired into `harness/loop.py`: every stage (boot, propose, policy, verify,
  accept) appends a receipt; the envelope carries `chain: list[dict]`. BLOCKED
  paths emit a partial chain (boot+propose+policy); full paths carry all five.
- Tamper-evidence boundary (honest): links self-verify (non-terminal tamper →
  UNVERIFIABLE); terminal-receipt tamper shifts head_hash, caught by the
  envelope's `content_hash` anchor. Combined: tamper any stage → never accepted.
- `tests/test_chain.py` — 11 tests (clean=_MATCH, empty=UNVERIFIABLE,
  parametrized non-terminal tamper, terminal-head-shift, envelope anchor,
  dict roundtrip, fake-receipt injection, loop integration + tamper).
- **Full harness suite: 41/41 green.** Six contract layers proven: M1 loop,
  boot grounding, policy admission, oracle conformance, M5 cache, M2 chain.

**M3 diversified best-of-N + correlation detector + voice-cap gate — built:**
- `harness/search.py` — `best_of_n()` (sample k at varied temps, verify each,
  accept first PASS) + `jaccard()`/`max_pairwise_correlation()` (near-identical
  detection) + voice-cap verdict logic.
- Voice-cap (§8 trap): no-pass + correlated (jaccard ≥ 0.85) → UNVERIFIABLE
  (wrong-attractor suspected, refuse confident FAIL); no-pass + diverse →
  honest FAIL. pass@k rescue: diversity finds PASS among wrongs.
- `tests/test_search.py` — 6/6 (diversity-rescue PASS, correlated→UNVERIFIABLE,
  diverse→FAIL, never-confident-wrong, correlation detector, temp coverage).
- **Full harness suite: 47/47 green.** Seven contract layers proven.
- NOTE: best_of_n is a proven standalone capability; wiring it as run_loop's
  multi-candidate search mode (chain branches per candidate) is the follow-up.

**M4 tiered escalation (cheap -> expensive gating) — built:**
- `harness/escalation.py` — `CompileOracle` (py_compile syntax tier, no
  execution — the cheap dense-signal prune) + `EscalationOracle` (tiered
  fast-fail; first failing tier stops escalation; only terminal tier ACCEPTS).
- C2 invariant proven: compile-pass + test-fail → NOT accepted (no dense-reward
  override of the terminal oracle). Compute saving proven: compile-fail → the
  expensive test tier is never called (CountingOracle.calls == 0).
- `tests/test_escalation.py` — 6/6 (accept, C2-override-refused, prune-saves-
  compute, compile-fail-verdict, single-tier=plain-oracle, real-pytest e2e).
- **Full harness suite: 53/53 green.** Eight contract layers proven: M1 loop,
  boot, policy, conformance, M5 cache, M2 chain, M3 search, M4 escalation.
- M0–M5 roadmap milestones all built. Remaining: M6 (verifier-guided search /
  MCTS-lite), M7 (eval), plus mem-layer (32B-fit) + M3-into-run_loop wiring.

**MEM-LAYER planner (memory subsystem decision core) — built:**
- `harness/membudget.py` — `ModelProfile` + `estimate_vram()` (4-bit weights +
  fp32 embedding head + LoRA + optimizer + activation peak + overhead) +
  `recommend()` (max native seq_len / offload strategy). Calibrated ±~20%
  against observed smokes; falsifier checks FIT-DECISIONS not exact GB.
- `tests/test_membudget.py` — 8/8 (retrodicts 14B-fits / 32B-OOMs, weights
  dominate 32B, recommender strategies, smaller-card push, determinism,
  seq_len→activation scaling).
- **Planner verdict on the 32B:** weights (~19 GB 4-bit) dominate; even at
  seq_len 256 native the 32B is at the 24 GB ceiling. To keep seq_len 2048 the
  32B needs **activation-CPU-offload** (keep 4-bit weights on GPU, offload
  forward activations to CPU, fetch in backward) — lighter than ZeRO-3 (which
  offloads weights and conflicts with 4-bit). This is the action layer; it
  needs GPU smoke, queued after the 14B CPT frees the card.
- **Full harness suite: 61/61 green.** Nine contract/probing layers proven.

**M6 verifier-guided search (MCTS-lite) — built:**
- `harness/mcts.py` — `SearchNode` + `ucb1()` (exploit+explore balance) +
  `verifier_guided_search()` (select-via-UCB → repair-expand → dense-evaluate →
  backprop-visits). DenseResult/DenseOracle/RepairProposer protocols.
- Dense cheap-oracle reward (fraction of tests passing) guides the repair tree;
  finds solutions beyond the model's single-shot distribution. Binary-only
  signal → no gradient → no improvement (honest scoping, falsifier-proven).
- `tests/test_mcts.py` — 6/6 (dense-finds-solution, dense-beats-random-best-of-N,
  binary-no-gradient, UCB unvisited=inf, UCB exploit/explore balance, root-solved).
- **MEM-LAYER action pre-staged:** `configs/ds_32b_actoffload.json` (DeepSpeed
  ZeRO-stage-0 + cpu_checkpointing, KEEPS 4-bit weights on GPU, offloads forward
  activations to CPU) + `--deepspeed` hook in qlora_cpt.py. UNSMOKED — smoke
  after 14B CPT frees the GPU. Fallback if cpu_checkpointing doesn't engage
  with 4-bit: lower seq_len (planner shows 32B fits native at ~256).
- **Full harness suite: 67/67 green.** Ten layers proven. M0–M6 COMPLETE.
  Remaining: M7 (eval framework vs frontier — needs trained model), action-layer
  smoke (post-CPT), M3-into-run_loop wiring.

**M7 eval framework (the publishable result) — built:**
- `harness/eval.py` — `ArmConfig` (single_shot / verified_inference / flat_n /
  no_search) + `run_arm()` (composes M1 oracle + M3 best_of_n by arm config) +
  `run_eval()` (each arm × each task → aggregate) + `compare()` (the
  whole-program verdict: MATCH if harness >= baseline, DRIFT if baseline wins).
- Honest by construction: `compare()` returns DRIFT when single_shot wins
  (falsifier-proven — the framework isn't rigged to make the harness win).
  Metrics: pass_rate, avg_oracle_calls (budget), receipt_reproducibility (100%
  by construction — every accept re-checkable).
- `tests/test_eval.py` — 7/7 (harness-rescues-weak, no-artificial-advantage,
  compare→MATCH, compare→DRIFT, receipts-100%, budget-honest, aggregation).
- **Full harness suite: 74/74 green. ALL ROADMAP MILESTONES M0–M7 BUILT.**
- What remains for a real publishable result: run M7 on a held-out task set
  with the TRAINED 14B (CPT ~51% done, loss 2.18→0.44, ~15hr to go) vs a
  frontier single-shot, at matched budget. The framework is ready; the run
  awaits the trained model. Plus the 32B offload smoke (post-CPT).

**Extensions (self-recursive improvement, while CPT trains):**
- **M3 wired into run_loop (search mode):** `run_loop(search=ArmConfig)` runs
  best-of-N and emits a "search" chain stage carrying ALL k candidates (linear
  chain preserved; corrupting any candidate entry → chain collapses). The
  primary API now does verified-inference, unblocking M7's verified_inference
  arm. `tests/test_search_integration.py` — 5/5.
- **AWG option-diversity selector (causal-entropic-forces inspired):** pulled
  Wissner-Gross's work through gather→forum→crucible. Crucible: 3/3 UNVERIFIABLE
  (no falsification condition on conceptual grounding → labeled "inspired by").
  The falsifiable extension became `awg_ucb()` in mcts.py — exploit+explore+
  option-diversity bonus (frontier distance), `d=0` recovers standard UCB as
  the M7 ablation hook. `tests/test_mcts.py` AWG cases — 3/3.
- **Full harness suite: 82/82 green.** The harness composes end-to-end now
  (boot → policy → search → chain → cache) and the option-diversity heuristic
  is measurable, not metaphorical.

**Held-out oracle task set (M7 benchmark fuel) — built:**
- `harness/tasks_lib.py` — `TaskSpec` + `REGISTRY` (8 held-out code tasks:
  easy/medium/hard spread — add, max_of_three, is_palindrome, count_vowels,
  dedupe_order, second_largest, fizzbuzz, flatten_one) + `materialize()` /
  `materialize_all()` + `validate_spec()` / `validate_registry()` (curator:
  every reference solution must pass its own hidden tests — rejects broken
  benchmark tasks).
- Each task has hidden pytest tests INCLUDING edge cases (empty/None/negatives/
  ties/dups) so the oracle discriminates fragile solutions, not just happy-path.
- `tests/test_tasks_lib.py` — 20/20 (benchmark integrity: all refs pass their
  tests; wrong/no-op solutions fail; materialize→load_task roundtrip; difficulty
  spread; edge-case coverage). Falsifier caught a path bug in validate_spec
  (solution written outside the oracle workdir) — fixed via load_task.
- **Full harness suite: 102/102 green.** M7 now has real fuel: a varied,
  self-validating task set to measure pass rate across a distribution.

**Research-derived extensions (depth-following: AWG → EvoMap → Starace/Paradigma → Carroll → Qwythos):**
- **CLI runner** (`harness/cli.py`) — dogfooding: `py -m harness.cli <task_dir>
  [--search] [--boot] [--cache] [--serve URL]`. Emits structured verdict +
  chain. `tests/test_cli.py` 3/3.
- **`python_executor` dense oracle** (`harness/exec_oracle.py`) — pulled from the
  Qwythos-9B tool-harness (their 7/7 with python_executor + web_search = our
  verified_inference thesis in miniature). Runs candidate code, matches stdout;
  M6 verifier-guided search now climbs REAL quantitative tasks. `tests/test_exec_oracle.py` 6/6.
- **`REASONING_TEMPS = [0.5,0.7,0.9,1.1]`** (`harness/search.py`) — Qwythos card
  documents reasoning-model degeneration at T≤0.3 (repetition loops); our
  DEFAULT_TEMPS included T=0 (harmful for reasoning models). REASONING_TEMPS
  avoids it; selectable in best-of-N.
- **Validations (no new code):** Qwythos's closed-book over-commit = the
  confabulation pattern (pxpipe/Fable) → validates abstention-at-proposal.
  EvoMap Capsule≈our envelope; GDI scoring = our cache-eviction gap. Starace's
  swe-bench/mle-bench = our M7 eval lineage. Carroll/SFI complexity grounds the
  emergence thesis. Paradigma "Flywheel" = our M5 cache compounding frame.
- **Full harness suite: 111/111 green.** Reddit AMA (AWG, Jul 4) + r/accelerate
  were anti-bot gated — not pulled; would need a different access path.

**Self-recursive + acceleration layer (the flywheel):**
- `harness/scout.py` — the "sly fox": consumes a gather catalog, assesses each
  source for FALSIFIABLE harness-relevance (the crucible discipline at scale),
  ranks ACTIONABLE > INSPIRATION > NOISE, emits a feed of build candidates.
- `harness/telemetry.py` — the algorithmic-efficiency loop: aggregates RunSignals
  into an EfficiencyProfile + GROUNDED improvement insights (cache hit rate,
  oracle dominance, over-sampling). Cache-hit runs report actual-this-turn cost
  (0), not stored budget.
- `harness/evolve.py` — the meta-loop: composes scout + telemetry feeds into one
  ranked pipeline; config+falsifiable candidates = AUTO-APPLY (falsifier-gated
  self-tune); code changes = GATED (never auto-applied — no automating confusion).
- `harness/flywheel.py` — THE ENGINE. Turns the meta-cycle, emits the momentum
  trace. Proven accelerating: turn 0 cold (0% cache hit, full cost) -> turn 1+
  hot (100% hit, ~0 cost). The substrate Project Telos is built around.
- `harness/kernel_oracle.py` — KernelBench-Mega verification (compile -> single-
  kernel gate -> correctness -> speedup[GPU-gated]). scaling01/Arledge tweets
  validated: "better harnesses" + "autoresearch" = the moat; multi-kernel
  pipelines fail the genuine-megakernel gate.
- **Full harness suite: 137/137 green (~120s).** Self-recursive loops (research,
  efficiency, meta) + the flywheel engine + kernel verification all falsifier-proven.

M1 ran with StubProposer (no GPU). Swapping to the local model is a config
change (ServeProposer), gated on the WSL2 reboot. The chain mechanics are
proven; the real-model run on a substantial held-out slice is the remaining
step for full CRUCIBLE_MATCH promotion.

Repurposing map (existing repos → harness gaps), from index.map of C:\dev:
- `aleph/seed` (C++23) → native oracle (M2 SeedOracle). [high confidence]
- `state/behavior-transform` → sandbox for every oracle (M2 SandboxedOracle). [high]
- `public/emet` + `aleph/sofer` → witness/receipt spine (M2 chain). [high]
- `public/pubscan/quantalang` (= buildlang) → compiler IR + codegen template. [moderate]
- `_private-clones/aurora` → LSP over task IR (human-language editing lane). [moderate]
- `protected/reverse-engineering/.../WARDEN` → property/proof oracle (M4). [low]
- `aleph/kun` → credential isolation inside the sandbox. [high]

## Phase: 2 (QLoRA CPT) — pivoted host from Windows native → WSL2 Ubuntu

## Where we actually are
- **Phases 0 + 1 DONE** (despite older STATE entries saying otherwise):
  - torch 2.6.0+cu124 + transformers 5.12.1 + peft 0.19.1 + accelerate 1.14.0
    + trl 1.7.0 + bitsandbytes 0.49.2 installed in Windows venv at
    `E:\local-model-run\venv`.
  - Corpus curated (17,997 files / 211.3 MB), tokenized, and packed:
    9 shards at `E:\local-model-run\data\packed\` = **66.2M tokens**.
  - **32B base model downloaded** (14 safetensors shards, ~62 GB) at
    `E:\local-model-run\models\Qwen2.5-Coder-32B-Instruct\`.
  - 14B model also present (used for the working smoke).
  - Tokenizer identity verified (14B == 32B tokenizer.json sha256).

- **Phase 2 on Windows — smoke PASSED on 14B, BLOCKED on the native path:**
  - 14B smoke completed 2026-07-04 05:56: train_loss 2.18, 2 steps,
    **131 s/step**, 4m22s total. Proves the code path is correct.
  - 32B path hits Windows-specific deadlocks that the source already carries
    workarounds for (grad-checkpoint dedup at qlora_cpt.py:100-105,
    `ensure_trainer_state` fallback at qlora_cpt.py:137-168, eager-attn escape
    hatch at qlora_cpt.py:209-212).
  - Root Windows limits: `expandable_segments` unsupported on Windows
    (confirmed in phase2-full.log), bitsandbytes runs via a Windows fork with
    known backward-pass reentrant deadlocks at step 0.

## Why the pivot to WSL2 Ubuntu
- Native bitsandbytes (no Windows fork), native `expandable_segments`,
  optional flash-attention-2. Expected 2-3× throughput vs the 131 s/step
  Windows baseline. Same 4090, same model bytes — just a working CUDA stack.
- All large assets (62 GB 32B, packed shards, HF cache) stay on `E:` and are
  readable from WSL via `/mnt/e/`. **No re-download.**
- Only the venv is rebuilt (Linux-native wheels). Linux venv at `~/venv-lm`.

## In flight / blocker (this session)
- **WSL2 FULLY UNBLOCKED (2026-07-04).** Root cause was NOT firmware/BIOS — it
  was **Fast Startup** (`HiberbootEnabled=1`) turning "Shut down" into a
  hibernation-resume that never let CBS finalize the staged VirtualMachine
  Platform feature. A true Restart (Start→Power→Restart) bypasses Fast Startup,
  lets CBS finalize VMP, and WSL2 comes up. (Earlier "BIOS" diagnosis was wrong;
  `HyperVisorPresent=True` proved firmware virt was on all along.)
- **Ubuntu-24.04 registered** (`wsl --install -d Ubuntu-24.04 --no-launch`, no
  admin needed once VMP landed). GPU passthrough confirmed: RTX 4090, 24564 MiB,
  driver 610.62. Python 3.12.3.
- **Linux venv built** at `/root/venv-lm`: torch 2.6.0+cu124, transformers
  5.12.1, peft 0.19.1, accelerate 1.14.0, trl 1.7.0, bitsandbytes 0.49.2,
  sentencepiece 0.2.1. Sanity import passes; `cuda? True`; VRAM free=24.1GB.
  (Setup needed `python3-dev` added — triton JIT compile requires Python.h;
  fixed in `scripts/wsl_setup.sh`.)
- Assets visible from `/mnt/e`: 32B model, packed corpus (8 shards = 66.2M tok),
  HF cache. Shard count is 8 (earlier "9" counted a non-shard file).
- **Linux smokes run (2026-07-04):**
  - **14B @ seq_len 2048, all-targets: PASSES.** train_loss 2.18 (identical to
    Windows — reproducible). ~87 s/step (vs 131 Windows, −34%). peak VRAM
    **21.04 GB**, 0.43 GB headroom. Smoke checkpoint written. **Fits, barely.**
  - **32B @ seq_len 2048, all-targets: FAILS.** Model loads (771 weights,
    4m16s via /mnt/e) but OOMs at `prepare_model_for_kbit_training` (float32
    upcast) → `CUDA driver error: device not ready`. GPU confirmed clear
    afterward (710 MiB used) → genuine VRAM ceiling, not transient.
  - **Hardware verdict: 32B at the target config does NOT fit a single 4090.**
    The 14B fits at 21 GB. Operator decision required: 14B-now-working vs
    reduced 32B config (lower seq_len / attn-only LoRA) vs 32B+CPU-offload.
- **14B CPT LAUNCHED (2026-07-04 20:24 UTC), detached screen `cpt14b`.** Full
  run on 66.2M-token corpus, seq_len 2048, r=16 all-targets, ~87 s/step →
  ~49 hr for 2 epochs. Checkpoints every 50 steps to
  `E:\local-model-run\checkpoints\phase2-linux-qlora-cpt-14b\`, resumable.
  Log: `E:\local-model-run\logs\phase2-linux-14b-full.log`. Survives session
  via `screen` in WSL. GPU track busy; CPU-side harness build proceeds in
  parallel.
  - **WSL dataloader fix (2026-07-04):** full run crashed on
    `OSError: [Errno 95] Operation not supported` — dataloader workers bind a
    Unix socket for IPC, which the /mnt/e (NTFS/9p) TMPDIR rejects. Fixed:
    `dataloader_num_workers=0` in qlora_cpt.py build_args (data is memmap'd
    shards; loading is trivial vs the 87 s/step GPU compute). Relaunch is
    training cleanly: step 0/2020, GPU 100% util @ 19.2 GB.
- **32B path = secondary goal (democratize capability onto commodity HW).**
  The upcast fix got it past model-prep; it OOMs in `loss.backward()`. Needs
  the memory layer (sequence chunking first, then offload orchestrator) —
  build CPU-side now, smoke after the 14B CPT frees the GPU.

## Resume point (next human action)
1. **Operator**: open an elevated PowerShell and run
   `wsl --install -d Ubuntu-24.04 --no-launch`, then reboot.
2. After reboot, ping the assistant. It will:
   a. Verify distro registered + non-interactive exec + `nvidia-smi` (GPU
      passthrough via the Windows 610.62 driver — should work out of the box).
   b. Run `bash /mnt/c/dev/local-model/scripts/wsl_setup.sh` inside Ubuntu
      (apt deps + Linux venv + pinned ML stack + sanity import).
   c. Verify `/mnt/e/local-model-run` assets visible.
   d. **14B smoke in Linux** (cheap stack validation, compare to 131 s/step).
   e. **32B smoke in Linux** (the real VRAM-envelope gate for the target model).
   f. If 32B smoke clean → `bash /mnt/c/dev/local-model/scripts/run_phase2_linux.sh`
      for the full run (resumable, logged to `E:\local-model-run\logs\`).

## Linux scripts staged (not yet executed)
- `scripts/wsl_setup.sh` — apt + venv + pinned ML stack + sanity.
- `scripts/run_phase2_linux.sh` — Linux launcher; reuses /mnt/e assets,
  writes Linux-tagged checkpoints + logs to avoid colliding with Windows ones.
  Passes all paths via CLI so qlora_cpt.py Windows defaults stay untouched.

## Decisions locked
- **Base model: `Qwen/Qwen2.5-Coder-32B-Instruct`** (Apache-2.0, ~62 GB bf16,
  ~18 GB in 4-bit). Target proposer. 14B kept as the smoke/prototype asset.
- **Run drive: E:.** HF_HOME + pip cache + tmp + checkpoints on E:.
  Venv on Linux native FS (`~/venv-lm`) for fast imports.
- **Tokenizer/pack format:** flat uint32 token stream, documents separated by
  `<|endoftext|>`, packed to seq_len 4096, trained at seq_len 2048.
- **No source path ever enters training text or logs** (invariant).

## Done (cumulative)
- E: run root scaffolded; corpus manifest valid + operator-curated.
- Safety gate restored in `corpus_manifest.py` (failed CLOSED; verified to
  reproduce the exact 17,997-file corpus).
- Windows venv: full ML stack installed and import-verified.
- 32B + 14B weights downloaded; tokenizer hash match verified.
- Corpus tokenized + packed: 9 shards, 66.2M tokens.
- Phase 2 training code (`train/qlora_cpt.py`) hardened against the three
  Windows deadlock modes (grad-ckpt dedup, trainer_state fallback, eager attn).
- 14B Windows smoke PASSED (train_loss 2.18) — code path proven correct.
- Linux scripts staged for the WSL2 pivot.

## Next (in order, after WSL2 distro is registered)
1. Run `wsl_setup.sh` inside Ubuntu → Linux venv with pinned stack.
2. 14B smoke in Linux (stack validation vs 131 s/step Windows baseline).
3. 32B smoke in Linux (the real gate).
4. Full Phase 2 QLoRA CPT on 32B (resumable, logged).
5. Phase 3 — SFT on oracle pairs (docstring→impl, test→impl, etc.).
6. Phase 4 — verified-inference harness (crucible/index/gather/forum).
7. Phase 5 — oracle-backed eval: system vs single-shot frontier, with receipts.

## Invariants (never violate)
- Nothing large on C:. Safety gate never narrowed. Corpus source identifiers
  stay proprietary (only aggregate stats leave the repo). No receipt, no accept.
- Windows native path is frozen at "14B smoke passed"; all new Phase 2 work
  happens in WSL2. Windows checkpoints/logs preserved as-is for reference.
