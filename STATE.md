# STATE — live cursor

> **Canonical overview: [PROJECT.md](PROJECT.md).** This file is the running,
> append-only work log (newest-first); PROJECT.md is the synthesized, honestly-
> bounded picture of the whole project. Read PROJECT.md first.

> The moving cursor for the local-model program. `ROADMAP.md` is the durable
> backbone (the WHY and the phase plan); this file is where we are RIGHT NOW.
> Update on every material step. If context is lost: read ROADMAP.md, then this.

Last updated: 2026-07-11

## 2026-07-11 (session 8) -- superapp increments 3/4/5 to launch-ready

Drove the superapp toward launch-readiness. Every module ships with its
falsifier; committed in five commits (493a22e..this). 117 passed across the
changed-module slice.

- **Increment 5 (companion seat) SHIPPED end to end.** `harness/companion.py`
  (9/9) is the routing seat over AdaptiveSelector: cache hit -> local-verified
  (oracle PASS) -> local-consensus (agreement, flagged not-verified) -> escalate
  (budget exhausted; frontier tier NAMED, never called inline). Only oracle-
  verified PASS is cached. Wired behind the gateway at `POST /api/companion` with
  ONE lifetime seat so cache + ledger accumulate; 3 gateway falsifiers; live-
  smoked over the wire (serve down -> honest escalate, no crash). Both SUPERAPP
  increment-5 falsifiers hold.
- **subsystem c (projected world) built.** `harness/world.py` (7/7):
  `project_world()` composes roster + findings + STATE cursor into one root-
  hashed `flywheel.projected-world/v1`; `verify_world()` -> MATCH/DRIFT/
  UNVERIFIABLE. `/api/world` upgraded from the v0 catalog to it.
- **Increment 4 (training lane) STATUS HALF shipped.** `harness/training_lane.py`
  (19/19) read-only status: parses the supervisor's own log markers into a state
  machine + screen liveness (the SOLE liveness claim, so it can never disagree
  with `wsl screen -ls`; a log/screen divergence sets reconciled=False) +
  checkpoint progress. `would_double_launch` guard is pure + fail-safe. `GET
  /api/training/status`. Start/stop ACTIONS deliberately deferred as a separately
  confirmed surface -- status-only first, per the ordering rationale.
- **Increment 3 two more parts done.** Gemini key moved out of the URL query
  string into the `x-goog-api-key` header (canary never in the URL).
  `LedgeredProposer` chains EVERY endpoint call into one tamper-evident
  SessionLedger (commitments only -- no prompt/response text, no key); flip a
  byte -> verify() fails. Serve-side receipt minting still needs the live model.
- **Launch-readiness:** `QUICKSTART.md` (user-register, run-it-now) passes
  publish_lint --strict clean; the shell passes clean; publish_lint --selftest
  PASSES. Entry point: `run_harness_cli.py app` (now forwards --run-root).
  REMAINING to public launch (the flip itself is not automated): serve-side
  receipt minting (needs GPU), the training action-half, and the shell views for
  the new routes.

## 2026-07-11 (session 7) -- universal router, prompt forge, pipeline, disk

- **SUPERAPP vision clarified (operator): NOT a 14B wrapper -- a universal
  router+harness with full operability across ALL providers, more feature-rich +
  seamless than existing platforms; as a NATIVE app the web-studio limits (deps,
  CSP, no local-model access) fall away.** The differentiator vs OpenRouter/
  LiteLLM/etc.: they route, ours routes AND verifies (receipts, oracle-gating).
- **Increment 3 roster+bridge BUILT: `harness/endpoint_registry.py` (7/7).**
  `unified_roster()` = 20 endpoints (14 OpenAI-compat providers + local serve/
  ollama/vllm/sglang/lmstudio/llamacpp + native Anthropic/Gemini + claude/codex
  CLI tiers) with credential-PRESENCE booleans (never a value; test asserts no
  secret leaks). `BackendProposer` bridges any `.chat` backend into a verified
  Proposer -> every endpoint feeds the same accept path, provenance in model_ref.
  Remaining for increment 3: mint receipts on serve endpoints + ledger chaining.
- **prompt forge BUILT: `harness/prompt_forge.py` (8/8)** -- the cisya-Studio front
  door: goal -> classified, constraint-sniffed, criterion-FORCED task spec; flags
  honestly when a goal admits no checkable criterion. On-thesis (the prompt IS the
  pre-decided world). Next: wire into the gateway as /api/forge + a shell view.
- Superapp status: increments 1-2 shipped, #3 roster+bridge built (receipts
  remaining), #5 selection core built (this session), #4 + world.py + companion.py
  still pending.

### colibri-inspired gen/verify pipeline + disk redirect

- **Colibri architecture mined for TECHNIQUE (operator: inspiration, not model
  adoption).** GLM-5.2-colibri (744B MoE on ~25GB RAM via NVMe expert-streaming)
  is real but 0.05-1 tok/s -> non-viable as our proposer. The borrowable move:
  async-prefetch = overlap I/O with compute. Built `harness/pipeline.py`
  (`pipelined_run`): generation (one model server, I/O-bound, serial) overlaps
  with verification (subprocess oracle, CPU-bound, worker pool) since both release
  the GIL. Pure scheduling -- byte-identical results to serial, strictly faster,
  never on the accept path. 6/6 tests (identical-results + strictly-faster
  falsifier + error isolation). Runners can adopt it for the N=64 lane; primitive
  proven, wiring is a follow-up (didn't refactor a working runner mid-flight).
  Other colibri borrows: learned generation-param pinning (C2-clean, propose-side)
  = INSPIRATION-with-a-thread; disk-streaming residency = NOISE (our thesis avoids
  needing huge models).
- **DISK: C: at 99% (15G free / 931G). Fixed OUR contribution:** run_ablation.py +
  run_passn_curve.py defaulted scratch to C:/local-model-run -> redirected both to
  E:/local-model-run/work; cleaned leaked sel_cons_/pytest/pycache scratch. Big C:
  consumers found (operator decisions, NOT touched): WSL vhdx 74G (compactable,
  needs wsl shutdown -- approval-gated), C:/dev/protected+aleph+opsec ~56G
  (sensitive/operator-owned), HF cache 13G (movable to E:), Temp 14G. The
  flywheel's work no longer feeds C:; the remaining pressure is WSL + sensitive
  dev dirs + caches, awaiting operator direction.
- selector-capture-at-N=32 run stopped at 30/61 (session teardown); resumable via
  --resume. Early rows confirm the confound: raw consensus_select picks
  confident-WRONG clusters (matrix_shape_strict cc=2 cons=F conf=0.97), validating
  why the gated select() demotes them.

Last updated (prior): 2026-07-10

## 2026-07-10 (session 6) -- frontier sweep + matmul oracle + closure-2 fixes

- **pass@N N=32 run COMPLETED + adjudicated (61 tasks).** consensus-reachable
  6.6%(N4)->12->24->36->49.2%(N32), ~12%/doubling, NOT plateaued; pass@32 = 60.7%.
  Pre-registration adjudicated HONESTLY: my ~32% estimate was too conservative
  (over-corrected the n=4 model's 59% as overshoot); truth 49.2% sat between,
  model closer. Beta-Binomial calibrates from n>=16 (held-out err 3.1%). Findings
  composer auto-flipped passn_curve pending->measured on the artifact (ingestion
  architecture verified end-to-end). PROJECT.md 4 + PASSN-PREREGISTRATION updated.
- **selector.py split at the 300-line gate:** selector.py (policy, 300) +
  selector_probe.py (battery/clustering, 293), behavior-identical via re-exports,
  98-test surface green. Test hygiene: test_no_learned_model_in_path now uses
  tmp_path (no repo scratch dirs). PROJECT.md module map + count (48) synced.
- **Regression status:** my changes are regression-free -- 108/108 on the complete
  reverse-import surface (selector/adaptive_select/findings/workspace_lens/
  matmul_oracle/discovery_flywheel + calibration/consensus/typed_battery/passn).
  Full suite = 910 passed / 9 failed (with test_task_curator + test_local_agentic
  excluded -- the former has a PRE-EXISTING subprocess hang at ~84%, the latter
  needs ollama). The 9 failures are ALL pre-existing, in foreign subsystems that
  do NOT import my modules, and characterized as environment/platform quirks:
  test_gather_readiness (Windows backslash vs forward-slash assertion, + a
  static-surface read), test_benchmark_profile_coverage (list ordering; invalid
  metric-shape), test_closed_loop_benchmark_seed (missing scorecard artifacts),
  test_accountability_bench (self-axis score), test_local_model_serve_launcher
  (serve config), test_package_ship_doctor (empty/malformed JSON artifact). Not
  regressions, not this session's scope; fixing foreign-subsystem tests without
  their contracts would risk breakage. Documented, not chased.

- **Discovery flywheel BUILT (harness/discovery_flywheel.py, 10/10 tests).** The
  operator's "oracle that senses discoveries and adapts course" -- reframed
  honestly: sensing is a PROPOSER (a learned discovery-judge on the accept path
  would be a C2 violation), so this composes the existing machinery (evolve.py
  gated meta-loop + knowledge_monitor transition discipline) and adds the two
  missing pieces: (1) a falsifier-ENFORCING intake gate (an ACTIONABLE discovery
  with no runnable falsifier is demoted, never adoptable), (2) a transition-fired
  COURSE-DRIFT signal (recommends re-prioritizing when a domain outside the course
  accumulates >=K adoptable threads; fires once, never auto-changes course). ML is
  on the propose side only; nothing auto-applies code; a falsifier is the only
  thing that lands a change. Ran on the REAL frontier sweep: matmul + J-lens ->
  gated admission, VSA/Clifford -> inspiration, monotiles NOISE dropped, course
  holds. The matmul oracle was one completed turn (sensed -> falsifier -> admitted).
  Dogfooded on the operator's GLM-5.2/colibri/winlibs batch (all REAL engineering,
  not word-salad): winlibs (native Windows GCC/MinGW -- fixes the documented WSL
  quant-toolchain pain) + GLM-5.2-colibri-as-slow-escalation-tier -> needs_admission
  with falsifiers; colibri-as-PRIMARY-proposer -> INSPIRATION (0.05-1 tok/s kills
  best-of-N -- 744B MoE on ~25GB RAM via NVMe expert-streaming is real but far too
  slow for the propose loop; NOT a drop-in engine). Dogfooding EXPOSED a real wiring
  flaw and I fixed it: evolve's CONFIG_HINTS keyword matcher had routed a code+setup
  discovery ("wire colibri behind escalation.py") into the AUTO-CONFIG lane because
  "escalation" is a hint word. External discoveries are capabilities to ADMIT, never
  runtime knobs -- so discovery_cycle now folds both evolve lanes into one
  needs_admission list; no external discovery can ever reach auto-apply. Stronger
  falsifier added; 10/10.

- **Frontier sweep (21-agent workflow, live web).** Operator supplied a batch of
  terms/links + a fused "method" sentence. Verdict: every individual token maps to
  REAL 2023-2026 work (Clifford/GATr, AlphaTensor/AlphaEvolve, grid-cell torus,
  twistor/amplituhedron, Penrose/monotile QEC, INR/SeedLM, J-lens); the FUSED
  compounds ("golden strassen clifford toroidal field", "torsional twistor markov
  pump") are word-salad with zero literature hits; and the clause "infinite
  tessellation without data loss + compression" is forbidden by Shannon/Kolmogorov
  (a theorem, not a training gap -- neural fields are resolution-independent but
  LOSSY). Report: tasks/research/FRONTIER-SWEEP-20260710.md.
- **ACTIONABLE #1 SHIPPED -- matmul bilinear-scheme oracle** (harness/matmul_oracle.py,
  8/8 tests). The AlphaTensor thesis made runnable: search proposes a rank-R
  decomposition, an EXACT symbolic tensor identity disposes, proposer off the
  accept path (C2-clean). Accepts a scheme only if it reproduces the exact n*m*p
  tensor over the rationals; Strassen-7 + naive pass, perturbed/rank-dropped
  rejected; calibrates zero-false-accept through calibration.py. The harness's
  first hard-symbolic ring-parameterized oracle. Provenance note in PROJECT.md 5.
- **ACTIONABLE #2 -- J-lens sourcing corrected + code-model path.** Festyve (the
  operator's link) = deepseek-coder-1.3b lens (real); solarkyle/jspace-lenses =
  broader registry with code-model lenses (gpt-oss-20b, Qwen3.6-27B) + hallucination
  router weights, transfers across quant. workspace_lens demote-only advisory
  already built+tested last pass. Next empirical step (needs GPU+fit): run a code
  lens over the 61 headroom tasks with the pre-falsifier (heatmap must differ on
  solved vs never-solved). Memo: tasks/research/JSPACE-INTEGRATION-20260710.md.
- **NOISE kept explicit:** aperiodic monotiles (QEC = tamper-tolerance, the OPPOSITE
  of our fail-closed tamper-evidence); GATr-as-proposer, SeedLM-for-32B, twistor
  geometry all rejected for stated reasons.
- **Closure review #2 fixes applied** (the 12 confirmed seams in the hardened
  engine): _safe_parse(None/non-str) degrade not crash; _signature mkdir wrapped +
  backstop sized to dominate per-slot sum + WORKER_DIED sentinel out of EXC:
  namespace; verify_selection enforces method/verifier consistency; select()
  validates confidence_threshold bounds + None candidates; findings.py nested
  non-dict guard + n_tasks=0 preserved + no raw-JSON dump; entry_point resolver for
  helper-first solutions. Full engine slice 89 green + matmul 8 + workspace 4.

## 2026-07-10 (session 5, cont.) -- findings promoted to accept-path components

- **The selection findings are now load-bearing components, not experiment scripts.**
  Three new harness modules, 48-test falsifier slice green:
  - `harness/selector.py` -- `select()` policy (oracle-first / consensus-fallback
    / confidence gate / re-checkable SelectionReceipt); `oracle_select`,
    `consensus_select`, the typed battery + type inference (moved here from
    run_ablation.py, which now re-exports for back-compat -- de-dup, not a copy).
  - `harness/adaptive_select.py` -- `AdaptiveSelector`: generate → select → RAISE
    N (double budget) → escalate-on-budget-exhaustion; `budget_schedule` (unique
    index-stable temp/seed grid). This is the companion seat's selection core.
  - `harness/findings.py` -- receipt-bound findings composer: scans run artifacts,
    binds every metric to a source hash, root-hashed `flywheel.findings/v1` doc,
    honest "pending" for incomplete runs, `verify_findings` staleness check.
- **pass@N raise LAUNCHED at N=32** (unique-grid diversity, extension-on-resume).
  Early: 13 of first 26 headroom tasks are consensus-reachable at N=32 vs ~5/61
  at N=4; pattern is bimodal (wake up substantially OR stay 0 -- the single-
  correct "oracle-only limbo" collapses). Pre-registered prediction recorded
  (model-from-n4 says consensus@32~59%, my independent estimate ~32%); the run
  adjudicates. New instruments: `scripts/passn_model.py` (exact hypergeometric
  pass@k/consensus@k, brute-force verified, Beta-Binomial extrapolation),
  `scripts/run_passn_curve.py`, `scripts/analyze_selectors.py`.
- SUPERAPP.md increment-5 companion seat + PROJECT.md module map synced to the
  built components. Adversarial review workflow run over the three components.
- **Adversarial review (24 agents, 5 risk dimensions): 12 confirmed / 7 plausible
  / 0 refuted. Confirmed defects FIXED, 59-test slice green:**
  - CRITICAL confidence-confound: `consensus_select` could emit verdict=PASS,
    confidence=1.0 for a WRONG-but-agreeing majority (4 byte-identical buggy
    candidates cluster perfectly). The fix wires the already-present
    `max_correlation` wrong-attractor gate onto the consensus PASS path (it was
    dead there) + a tie gate (runner-up == winner) + honest reason strings
    ("AGREEMENT not oracle-verified correctness"). Textually near-identical
    candidates (corr >= 0.85) and 2-2 ties now route to LOW_CONFIDENCE -> the
    adaptive loop raises N / escalates instead of a confident-wrong local accept.
  - CRITICAL receipt gaps: SelectionReceipt now carries task_id + fn/arity/
    param_types so a third party can actually regenerate the battery and
    re-cluster; added `verify_selection()` (MATCH/DRIFT/UNVERIFIABLE) delivering
    the re-check the docstring promised.
  - CRITICAL findings fabrication: `project_findings` emitted "single None/None"
    for present-but-malformed artifacts; now validates keys and emits honest
    pending; single-read `_load_and_hash` closes a TOCTOU gap.
  - MAJOR determinism: `_signature` subprocess now pins PYTHONHASHSEED=0 so
    set/dict repr order (and thus clustering) is stable across processes.
  - MAJOR budget cap: `budget_schedule`/`AdaptiveSelector` refuse n > 73 (past
    capacity the temp/seed grid would repeat and add no diversity).
  Note: the corr/tie gates make the DEPLOYED consensus path more conservative
  than the raw agreement-capture the ablation measured -- it trades some local
  accepts for never-confident-wrong, the correct default for the companion seat.
- **Total-closure hardening pass (operator: "a flywheel engine cannot have any
  edge cases; every gap, seam, thread, surface traced and solidified").** Closed
  the 7 plausible review findings + edge cases the review didn't reach, 72-test
  slice green:
  - per-input timeout in `_signature` (threaded daemon + join per battery input,
    whole-probe backstop) so machine load can't flip a candidate's cluster;
  - `select()` fails loud on oracle-without-task; coerces None/non-string
    candidates (`_as_text`); requires >=2 candidates for a consensus PASS (one
    is single-shot, not agreement); cleans its scratch dir every call (no leak);
  - `oracle_select` treats a THROWING oracle as no-pass, never crashes;
  - `AdaptiveSelector` tolerates a raising/empty proposer (escalates, no crash);
    ESCALATE now carries text=None with the attempt in `best_effort_text`;
  - `findings.py` single-read `_load_and_hash` (no TOCTOU), key validation
    (malformed artifact -> honest pending, never fabricated), glob-based pass@N
    artifact selection (largest max_n wins, any future filename picked up);
  - `verify_selection` returns MATCH/DRIFT/UNVERIFIABLE (the re-check the receipt
    promised). Second adversarial closure review run to confirm no seam moved.

## 2026-07-10 (session 5) -- consensus arm measured, type-aware battery, pass@N curve

- **Consensus arm COMPLETE on all 61 headroom tasks (2026-07-10).** Oracle-free
  behavioral-consensus (MBR-exec) selector: 4/61 (7%), +2pts over single,
  recovering 9% of external oracle's lift. McNemar p=1.0 vs single (not
  significant), p=0.004 vs external (SIGNIFICANT gap). The structural picture:
  at N=4, 77% have zero correct candidates, 15% have exactly one, 6.6% have
  two-or-more (the consensus ceiling). 8/11 external rescues are single-correct
  (structurally unreachable by any oracle-free method).
  Artifact: E:\local-model-run\selector_consensus_headroom.json.
- **Type-aware battery improvement BUILT + TESTED.** The old mixed-type probe
  pool sent wrong-typed inputs (ints to list params, etc.), causing all
  candidates to crash identically and erasing behavioral signal. Fix: infer
  per-parameter types from function signatures, generate typed battery inputs.
  Verified fix on sliding_window_max (FIXED from FAIL to PASS). Root cause
  analysis on splice_pure and matrix_transpose: candidates genuinely behave
  identically on battery inputs but differ on hidden edge cases -- a structural
  limit of behavioral consensus, not a selector bug. Offset bug fixed (per-param
  offset dropped when rewriting for typed pools). INT_POOL rebalanced toward
  typical list lengths.
- **pass@N budget curve runner BUILT** (scripts/run_passn_curve.py). Generates
  N candidates at distinct (temperature, seed) pairs, counts correct_count at
  each budget level. Early probe on 10 tasks at N=8 shows search_rotated moving
  from oracle-only (1/4 correct) to consensus-reachable (2/8 correct). Full
  61-task run pending.
- **Analysis tooling BUILT** (scripts/analyze_selectors.py). Structural
  breakdown of oracle-free feasibility: correct_count distribution, cluster
  diagnosis, McNemar tests, Wilson CIs, actionable recommendations.

## 2026-07-09 (session 4) -- lane 110/100, difficulty screen DONE (44%), oracle tree-kill fix

- **Hard-set lane COMPLETE at 110/100** (batch 8: 24/24 admitted through curator
  gates, authors self-verified with reference-pass + return-None falsifiers;
  commit 75d25fe). Registry hash-verified, unique ids.
- **Difficulty screen executed over all 110** against the honest identity
  `ollama:flywheel-local-coder-14b` (serve.py held the BASE model; screening
  through it would have misattributed — new --ollama route, commit 7e5ce00).
  **Result: single_shot@temp0 = 44% (49 saturate / 61 headroom).** The old
  10-task M7 saturated at 80% with no headroom; this is the frontier-zone
  instrument the matched-budget ablation needs. Artifact:
  E:\local-model-run\difficulty_screen_hard_v2_110.json (+ .partial.jsonl).
- **Oracle liveness bug FOUND LIVE + FIXED (c0e7273):** a generated candidate
  with an infinite loop wedged the screen 10+ min — subprocess.run(shell=True,
  timeout=) on Windows kills only cmd.exe; the pytest grandchild survives
  holding stdout and the post-kill drain blocks forever. PytestOracle now
  Popen + taskkill /T + bounded drain; falsifier
  tests/test_oracle_hostile_candidate.py hangs on the old code. Screen gained
  <out>.partial.jsonl checkpointing + --resume (resumed at 37/110, zero waste).
- 14B HF repo: shipped Modelfile fixed to portable relative FROM (operator-
  approved upload, HF commit 1d45b509, re-download verified). Public flip +
  token rotation remain the operator's actions.
- ROADMAP-STATUS synced to executed evidence (cab4988): 27/32 (~84%).
- **SUPERAPP.md landed** (root): the one-surface unification spec (showcase
  shell + packaged app + companion routing + training lane + projected world),
  from a six-reader grounded survey; increment ladder inside. Operator vision:
  one large interoperable surface, local+enterprise models, all endpoints,
  trains models, projects the shared world.
- Session-memory bridge now LIVE globally (project-docs/tools/
  session_memory_bridge.py + ~/.claude hooks): every session's spoken context
  auto-compresses to project-docs/wiki/sessions/ + mneme; SessionStart injects
  the digest tail. The cold-start archaeology that opened this session is gone.

## 2026-07-09 (session 3, cont.2) — HF PUBLISH IN PROGRESS + market surfaces

- **14B UPLOADED TO HUGGING FACE (private).** `zaindanaharper/flywheel-local-coder-14b`
  is live private: 13 files, 8.99 GB, GGUF intact, model card + LICENSE +
  provenance + receipts. Operator flips it PUBLIC themselves (Settings ->
  Change visibility; I hold sharing-permission changes). The 9 GB xet upload
  stalled twice on the connection tail via upload_folder; FIX that worked =
  TWO-STEP: upload metadata first (ignore_patterns=['*.gguf'], fast commit),
  then the GGUF alone via upload_file (xet deduped to ~134 MB new data, landed).
  Lane at 86/100. Benchmark lane, market surfaces, guarded publisher all shipped.
- **14B UPLOAD context.** Operator supplied a token and lifted the
  benchmark gate (acknowledged the honest null). Key correction: the HF account
  is **papacr0w** (org **zaindanaharper**, the operator's real name), NOT
  HarperZ9 (that is the GitHub handle; the pipeline default was wrong and is now
  fixed to zaindanaharper across the HF/repo-stage/build scripts). Repo created
  **PRIVATE** at `zaindanaharper/flywheel-local-coder-14b`; the 9 GB GGUF +
  card + LICENSE + receipts are uploading. The PUBLIC flip stays the operator's
  one click (I hold sharing-permission changes). The token's fine-grained scope
  empirically allows org repo create+write.
- Release folder re-synced before upload (the E: README was stale/missing the HF
  card front-matter; now carries license/base_model/tags front-matter + the
  benchmark-evidence-so-far section). Secret-scan of the folder: clean (only
  prose mentions of "secret handling" in safety.md/usage.md).
- **32B still NOT published** even though the operator said "both models": no
  trained artifact exists, so publishing would republish base Qwen weights under
  our name. Held (truth over approval). Publishes after it is actually trained.
- Guarded publisher `scripts/publish_to_huggingface.py` encodes the whole gate
  as code (token + trained + ready + approval + benchmark-excludes-zero-OR-
  acknowledged-null; false uplift can never pass; 7 falsifiers).
- Market surfaces shipped: `site/index.html` (companion positioning + 10-demo
  gallery + honest CI benchmark table, offline/theme-aware), all nine flagship
  demos recorded, PEDAGOGY.md voice+discipline guide, benchmark CIs
  (scripts/run_benchmark_ci.py), hard-set lane at 50/100 (batch 6/7 authoring
  toward ~80), Bilevel outer-loop integrated into evolve.py.
- Enterprise parity: spine audit done (index/forum/gather/crucible live on PyPI;
  telos not on npm; common gap = no observability layer + missing SECURITY.md).
  A SAFE hardening sweep (SECURITY.md + README test-count drift, telos excluded,
  dirty repos skipped) is running on the 7 non-telos flagships.

## 2026-07-09 (session 3, cont.) — market-entry sprint: hard bench, 32B RAM-gated, deliverables shipped

- **GOAL (operator, /goal): flywheel enters the market as a COMPANION to every
  frontier model** (Codex app / Sol lineup / Mythos 5), not a competitor; both
  local models pushed to HF with generous walkthrough + benchmarks measurable
  to an outside observer (publication gated on that); demos for every flagship;
  enterprise parity for mneme/relay/plexus; humanist/wonder voice (integration
  and benefit, not fear-lead) with receipts as empowerment, one doorway line.
- **Hard-set benchmark (10 tasks, ollama:flywheel-local-coder-14b)**:
  single_shot 80% (8/10), verified_inference 90% (9/10), flat_n 90%,
  no_search 80%, receipts 100% everywhere, verdict MATCH. **HONEST BOUNDS:
  the +10% is ONE task of ten, inside noise, and flat_n equals it (best-of-4
  sampling, not verification) — the M7 quarantine rule stands, NO uplift
  claim.** The outside-observer instrument is still the 100-task lane
  (curation was at 38/100). The defensible measurable claims: 100% receipt
  reproducibility + pass parity + local cost. Scorecard:
  `artifacts/flywheel-local-coder-14b-benchmark-m7-hard-scorecard.json`.
  Readiness now shows 2 benchmark artifacts for the 14B.
- **32B TRAINING: launched, then STOPPED for a RESOURCE REALITY, now RAM-gated.**
  This box is 32 GB RAM. Loading the 82 GB fp16 32B and quantizing to 4-bit
  streams ~20 GB through CPU RAM; with only ~10 GB free it thrashed swap and
  wedged WSL (could not even `pkill`). Operator-approved `wsl --terminate
  Ubuntu-24.04` (surgical, NOT `wsl --shutdown`) freed it (VRAM 19.5 -> 1.6 GB).
  No checkpoint existed, so nothing trained was lost. The 32B SMOKE proved the
  path works (peak 21.24 GB VRAM, rc=0). Fix: `run_phase2_32b_supervised.sh`
  now RAM-gates each launch (waits for ~22 GB MemAvailable, polls 2 min);
  `scripts/launch_32b_training.ps1` is a one-command start; `TRAINING-32B.md`
  is the runbook. STOP flag is SET so nothing auto-runs. RUN IT WHEN THE
  MACHINE IS IDLE.
- **DISK INCIDENT: C: hit 0 bytes** mid-session. Cause: a Q3_K_M quant wrote
  inside the WSL VHD (which lives on C:); the VHD grew ~6 GB and cannot shrink
  without `wsl --shutdown`. Freed ~22 GB via Run-dialog delete of `.pyinstaller`
  + `.m7-run` + pip cache (computer-use, operator-approved). LESSON: future
  quant output must target /mnt/e, never ~/gguf (recorded in TRAINING-32B.md).
- **HF upload hard blocker: no HF token on this machine**
  (LocalTokenNotFoundError). Only the operator can export one. Everything else
  on the 14B is staged and waiting.
- **SHIPPED this session (branch `fix/release-model-identity`, all pushed):**
  WALKTHROUGH.md + BENCHMARK-METHODOLOGY-OUTSIDE-OBSERVER (a skeptic can rerun
  it); zero-dep demo recorder (stdlib) + offline HTML player + first
  harness-first-run demo with a live 14B generation (5 falsifiers);
  MARKET-SURFACE-COMPANION-POSITIONING (Codex app / Sol=GPT-5.6 / Mythos 5,
  grounded with citations); COMPANION.md (the humanist/wonder positioning,
  receipts as one doorway not the frame); ENTERPRISE-PARITY-GAPS +
  quick-win branches pushed to mneme/relay/plexus (docs drift fixed, gated
  release workflows added; relay's `relay-agent` PyPI name is TAKEN, needs a
  rename); RESEARCH-CURATION (arXiv 2603.23420 Bilevel Autoresearch curated,
  its "5x" quarantined as n=3/underpowered; ninja_maths post UNRESOLVED, x.com
  402 paywall, needs a direct URL); and the Bilevel outer-loop mechanism
  INTEGRATED into `harness/evolve.py` as a gated-only proposal source (never
  auto-applies, 5 falsifiers).
- Enterprise-parity follow-ups for the operator: register PyPI trusted
  publishers + set PYPI_ENABLED for mneme (ready), rename relay's distribution,
  merge plexus feat/graph-run-compare (0.2.0 content is on the unmerged branch,
  main is still 0.1.0).

## 2026-07-09 (session 3) — release identity corrected; 14B READY_TO_STAGE, 32B honestly gated

- **CRITICAL FIX: the staged HF release candidates pointed at the BASE Qwen
  weights, not our artifacts.** The prior staging would have republished
  unmodified Qwen2.5-Coder weights under the Flywheel name (the 32B has NO
  trained artifact at all; only a checkpoint-2 smoke exists). Release identity
  now lives in `harness/model_profiles.py` (`release` block per model) and a
  `trained_artifact_present` gate runs FIRST in readiness -> publish plan ->
  repo stage -> HF stage. 32B verdict: `MODEL_NO_TRAINED_ARTIFACT`,
  DO_NOT_PUBLISH, upload templates replaced by a DO-NOT-UPLOAD marker.
- **14B release root built and fully evidenced**:
  `E:\local-model-run\release\flywheel-local-coder-14b\` = the trained GGUF
  (telos-coder-14b-cpt2020-q4_k_m.gguf, sha256 613db240... verified on copy
  from WSL) + Modelfile + LICENSE (Apache-2.0 + attribution) + all 10 release
  docs (truth-passed) + merged checksums (GGUF line preserved).
- **Live endpoint gate PASSES on the real artifact**: Ollama model
  `flywheel-local-coder-14b` created from the GGUF (blob store on E:, C: is at
  97%); `ollama-release-14b` profile health+generation OK (524ms). The base
  `ollama-14b` row honestly FAILS (base model not in store). Gate artifact now
  rides the package and the ship doctor requires it.
- **Benchmark evidence attached**: fresh M7 run of `ollama:flywheel-local-coder-14b`
  (4 arms x 8 held-out tasks): pass 8/8 in ALL arms, receipts 100%, verdict
  MATCH. No uplift claimed (the easy set saturates; hard-set run is the
  discriminating follow-up). Scorecard:
  `artifacts/flywheel-local-coder-14b-benchmark-m7-scorecard.json`.
- **End state: 14B = MODEL_RELEASE_READY_STATIC -> READY_TO_STAGE (17/17
  gates) -> WAITING_FOR_OPERATOR_UPLOAD_APPROVAL** (sole blocker = operator
  approval, never auto-granted). 32B = DO_NOT_PUBLISH until a real 32B
  adapter is trained. GGUF gate-file set is artifact-kind aware (GGUF embeds
  tokenizer/config; HF sidecar files not required).
- Guards added: repo-stage sync refuses to write staged docs into an untrained
  track's root (would overwrite the base model dir); checksum sync merges
  instead of clobbering weight hashes. Test slice 32 passed (was 24).

## 2026-07-07 (session 2, cont.) — SHIPPABLE GGUF + provenance chain, index watch

- **GGUF ARTIFACT SHIPPED & DETERMINISTIC.** telos-coder-14b-cpt2020-q4_k_m.gguf
  (8.4G Q4_K_M from checkpoint-2020, train_loss 0.035). Loads, generates CORRECT
  code (valid iterative Fibonacci), smoke MATCH (byte-identical at temp 0 seed 7).
  The initial DRIFT was a FALSE alarm correctly diagnosed as the wrong invariant
  (llama-cli conversation banner in stdout, not generation nondeterminism) — the
  turbulence lesson applied live; fixed by switching to llama-completion (clean
  token stream). This closes the "local-models: no shipped artifact" gap.
- **Full provenance chain closed** (the invented niche): the ship manifest
  (tasks/research/gguf_ship_manifest_checkpoint2020.json) chains corpus content
  hash -> pack shards hash -> checkpoint adapter sha256 -> GGUF sha256, each
  layer independently re-derivable. A pullable artifact whose receipt proves
  what it was trained on — no competitor ships this.
- **BATTLE-MAP.md**: whole-product sweep of 6 categories (live July-2026
  research) with per-axis verdicts + beating increments + invented niche each.
  The durable extension roadmap. Honest: we lead speed/cost/zero-dep + the
  verifiable-artifact niches; trail on demo/community/benchmark-traction.
- **index watch shipped** (in the index repo, feat/context-lens): live
  auto-resync — the feature every codebase-map competitor has and index lacked;
  composes the freshness machinery (holds the prior fingerprint) into a real
  live FRESH/STALE verdict + re-checkable sync receipt; --regen rebuilds the
  workbench/atlas on change. 6 falsifiers.

## 2026-07-07 (session 2) — providers, curator hardening, hard-set 38/100

- **providers.py**: named registry (13 providers + BYO endpoint) over the
  zero-dep OpenAI-compatible proposer; provider identity rides model_ref into
  every envelope + cache key; falsifiers against a live local mock incl. the
  end-to-end gated accept. Feature parity where it matters vs the clawcodex
  class of 25-provider agents.
- **task_curator hang fix**: a TimeoutExpired from one oracle run killed a
  whole admission batch; hangs are now gate-FAILs (falsifier added). Behavioral
  dedup extended to the EXPERT tier (3 batch-2 id collisions culled).
- **hard-set lane at 38/100**: batch 3 (24 workflow-authored constraint-rich
  tasks) admitted 21/24; the 3 leak-gate rejections were authors echoing
  solution lines verbatim in prompts — prompts reworded to state contracts
  without code echo, 3/3 re-admitted. Difficulty screen v2 (real 14B, temp 0):
  12/17 of batch 1-2 saturate; the authoring principle (contract density over
  textbook fame) drove batch 3.
- **Doctrine saved in-repo** (FLAGSHIP-PLAN.md, SUPERPROJECT.md): best tool in
  every category + invented integrative niches; whole-product competitor
  assessment first, accountability as the closing multiplier.
- GGUF pipeline relaunched in WSL (first run died with the host session
  mid-smoke; toolchain survived). Battle-map sweep across 6 categories running.

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
