# Certified Commons (CC-1): the epistemic training environment

**Status:** DESIGN, operator review pending
**Date:** 2026-07-25
**Provenance:** three-architecture adversarial design panel (22 agents, 18 lens
critiques, run `wf_6d20aac7-bb5`), grounded by a domain research sweep (run
`wf_0393907f-7b1`) and a repo/essay/reference sweep (run `wf_88625103-a58`).
Full panel synthesis: [records/2026-07-25-cc1-panel-synthesis.md](../records/2026-07-25-cc1-panel-synthesis.md).
Research synthesis: [records/2026-07-25-epistemic-infra-research.md](../records/2026-07-25-epistemic-infra-research.md).

---

## 1. Mission and posture

A model uplift and discovery engine for the world. Local models are the
subject; epistemology is the method. The training signal is verification
(external oracles, re-derivable receipts), not preference reward and not
ethics rules. Ethics never sit in the accept path; criteria do: explicit,
versioned, hash-pinned, forkable, contestable. A verified receipt is the
neutral ground on which previously opposed interests can share facts without
sharing values.

Posture is non-competitive and non-volatile. No comparison framing on public
surfaces. The claim register is the one the discourse rewards: benchmarks
with intervals and evidence files, honest nulls, no predictions reported as
discoveries.

The essay "Pick the Lock for Everyone" binds this design as ethos and
vocabulary, never as biography. Its constraint: capability distributed by
construction: inspectable, forkable, runnable on machines people already
own, unable to be re-locked, including by the author.

## 2. The two bars, co-equal, converging

The operator's ruling (2026-07-25): both bars are focuses, each serving its
own group, and they coalesce later.

- **Bar U (uplift):** preregistered, control-armed, interval-bounded model
  improvement from verified reward, published whatever it says, including
  the null. Serves the people improving models.
- **Bar R (reproducibility):** a criterion-pinned corpus of receipts any
  stranger re-derives offline: no GPU, no network, no account, no trust in
  the author. Serves everyone who must rely on results they did not produce.

**Convergence commitment:** the reproduction tiers are the bridge. T0
(offline replay of every certificate, digest, signature, and the headline
table) ships first. T1 (eval replay on any CUDA box) and T2 (full training
replay from a pinned lockfile) then carry Bar U itself into Bar R: the
uplift claim stops being "the operator's box says so" and becomes a
communally re-derived fact. Endpoint: the experiment is the commons.

Two further bars ride along, preregistered with the rest: developmental
retention (verified knowledge kept over time, probed on isomorphic
perturbations to separate derivation from memorization) and entropy and
diversity preservation under training (measured on the guard-OFF arm;
collapse is a recoverable incident with a recovery receipt, never a lost
run).

## 3. Principles carried into mechanism

From the essay synthesis, the principles that bind this design, each with
its mechanical expression:

1. The candidate touches something capable of saying no: deterministic
   checkers the proposer did not author; model confidence is invisible on
   verdict surfaces.
2. Criteria cannot silently change after a miss: criterion objects are
   hash-pinned into receipts; a criterion edit is a recorded CRITERION_AMENDED
   event with downstream invalidation.
3. Append-only, repair on top: failed runs become regression cases; the
   ledger never rewrites; latest verified state reads first, history one
   click deep.
4. UNVERIFIABLE is a first-class verdict; the gap is part of the record.
5. One-way valve: only receipted, re-witnessed experience feeds training
   (developmental.curate is the existing gate).
6. Receipts certify lineage, not virtue: process manifests with roles,
   never quality badges.
7. Both records kept: verified successes preserved with the same
   durability as failures.
8. Effect over intent: verification judges what shipped; every record is
   legible standalone, years later, author unavailable.
9. Verification throughput is a first-class budget: metered, displayed,
   capped by the human.
10. Exit rights: local-first, offline-capable, open formats, no account,
    no telemetry gate, Apache-2.0 on everything load-bearing for
    verification.
11. Anti-deskilling: receipts state what they do NOT prove; surfaces show
    what a check did not cover.
12. Doubt answers with records, never friction: "why was this accepted?"
    is the cheapest action in the app.

Forgiving circumstances, engineered: strict truth, gentle consequences.
Verdicts never lie; the process never punishes exploration into collapse.
Interrupted runs resume; failures are recorded events, not corrupted state;
entropy is preserved by mechanism, not hope. Friction is structural and
applies to the path; shame is punitive and applies to the person. This design
uses the first and never the second.

### 3a. Qualifications restored from the canonical master

The public edition of the essay is a trim of a 21,208-word master. The trim
dropped fences that the master states explicitly. A dropped qualification is
how an honest argument becomes an overclaim, so the load-bearing ones are
restored here and bind the design. Source:
[records/2026-07-25-canonical-master-delta.md](../records/2026-07-25-canonical-master-delta.md).

1. **The flywheel has a ceiling, and importing is not contamination.**
   Recirculation makes existing experience more useful; it cannot create
   coverage the system never encountered. New coverage comes from outside the
   line. Stated alone, the one-way valve implies a closed loop and makes the
   system's asymptote look like a virtue. Consequence: the external intake
   path (gather, human-gated into the registry) is load-bearing, not a
   concession, and the system publishes its coverage ceiling alongside any
   improvement curve.
2. **Throughput asymmetry nullifies, it does not merely cost.** A metered
   budget still permits emitting more than can be checked. The master's
   position is refusal, not measurement: a system producing more claims per
   hour than its checkers can adjudicate has degraded its own output even
   where individual outputs are correct.
3. **Weights are not morally cursed.** Foundation models used and disclosed
   are legitimate. Provenance surfaces must never render as clean versus
   dirty; a purity tier is the robe with better typography. The adapter
   layer's `trainable` vs `evaluatable_only` is a capability tier and the
   renderer must present it as one.
4. **UNVERIFIABLE must say why.** A bare UNVERIFIABLE is unactionable and
   indistinguishable from "we did not look." Typed reason codes are required,
   distinguishing at least: confounded, no witness available, outside the
   criterion's domain of applicability, lane absent.
5. **A permanent record must not function as a permanent sentence.** Append-only
   plus redemption without erasure. Neither the public edition alone (which
   licenses a permanent adverse weight) nor the master alone (which licenses
   forgetting) is the author's position. The design owes a stated policy for
   how age, repair, and subsequent verified behaviour weight a past failure in
   later decisions. Recorded as an open design question, not yet answered.
6. **A criterion carries a domain of applicability.** "A poem has no kernel."
   Verification machinery is fenced out of aesthetic and interpretive domains,
   where tooling may disclose process but must not issue a verdict. The
   criterion object carries the fence and the renderer refuses to display a
   verdict outside it. This is the self-limitation most likely to be lost to
   drift, because a general assessor slides into quality judgment by default.
7. **Independence that offloads its cost is not independence.** A fork that
   leaves the verification burden behind has moved the ledger rather than
   carried it. This sharpens the already-named cross-fork residual risk into a
   design question.
8. **Retaining only failures misrepresents base rates.** Keeping both records
   is a statistical requirement, not only a fairness norm, which makes it
   enforceable.
9. **The witness locates failure; it never computes worth.** Verdict counts are
   not a quality score. Reinforces the standing refusal of any trust score.
10. **Human gate decisions are the least instrumented node in the accept path.**
    A gate decision should emit a justification with the same evidentiary
    standing as a checker verdict. Recorded as not-yet-covered.

Also absent from the public edition and adopted as framing: sourcehood
without self-origination (responsibility attaches to the node an action passed
through; an agent whose decisions cannot be queried, contested, and corrected
has been built as weather, and logging alone does not fix that), and deception
modelled as input control (editing another party's picture of reality without
permission, which unifies poisoned tool results and selectively curated
reviewer context under one rule).

## 4. Architecture summary

The spine: a criterion-pinned verification environment whose receipts a
stranger re-derives offline, with the training run as its first and most
demanding consumer. The flagship oracle family is construction
certificates: pure data checkers (witness graphs, codebooks, tensor
decompositions) that never execute candidate code. That single choice
closes the stranger-RCE security flaw, makes verification cost negligible,
and makes offline verifiability real.

Layers (full component tables with line budgets in the panel synthesis):

- **Layer 0, seam repairs (Phase 0):** a shared four-way Verdict type
  (PASS, FAIL, UNDECIDED, UNVERIFIABLE) with execution and attribution
  enums; Oracle Protocol widened (the old `passed` property raises on
  non-binary verdicts so every call site surfaces); `run_env` deny-by-default
  allowlist, argv not shell, session isolation; gateway bearer token, Host
  allowlist, Content-Type enforcement; CI matrix (3 OSes) with clean-clone
  network-disabled verify, 300-line gate burn-down, orphan check, and an
  AST no-execution scan over every checker module.
- **Layer 1, criteria and checkers (Phase 1):** criterion spec + registry
  (versioned incumbents, named invalidation, conjunctive-only decision
  rules for reward eligibility); CertificateOracle base (data-only, exact
  integer arithmetic, coverage block); Zarankiewicz and constant-weight
  checkers + parameterized generators with a difficulty knob; independent
  reimplementations wired to held_out (disagreement is UNDECIDED, never a
  majority side); an adapter wrapping the existing exact-Fraction matmul
  oracle; oracle QA that precedes training (planted exploits, mutation
  classes, Wilson-bound false-accept rates; no QA card, no reward
  eligibility).
- **Layer 2, receipts and ledger (Phase 1):** receipt v2 (section 5),
  vendored stdlib Ed25519 verify-only, hash chain with RFC 6962 inclusion
  and consistency proofs, signed tree heads to an external anchor, contest
  channel (signed counter-receipts; open contests are a published series),
  bundle pack/verify, `flywheel why`.
- **Layer 3, cost and amortization (Phase 2, instrument not headline):**
  multi-denominator cost meter with a user-held budget (estimate, cap that
  halts, live meter, cancel that still emits an INCOMPLETE receipt);
  scope-bound audit-once lifts and certify-fast-against-slow with
  epsilon-rate forced re-verification. A lift transfers cost, never tier.
  Replay and transfer series never pool.
- **Layer 4, model adapters (Phase 2): bolt-on, first class.** Discovery
  ladder (GGUF header, Ollama show, HF config, /v1/models, measured-only)
  with per-field metadata_source; effective context by measurement;
  cache-aware stable-prefix prompting with measured hit rate in the
  denominator; tool-call dialect probing; a signed AdapterCard with
  three-valued determinism and trainable vs evaluatable_only. Any model
  runs; only carded, trainable models produce claim-admissible receipts.
- **Layer 5, the science (Phase 1):** preregistration with an external
  anchor on freeze day; control arms as code that raises; uplift_stats
  (seed-spread-primary intervals, cluster bootstrap, permutation tests,
  power analysis) validated on synthetic data before the freeze.
- **Layer 6, training (`train/`, torch allowed):** reward_gate (receipt
  written, signed, chained, committed BEFORE reward returns; commit failure
  returns the UNDECIDED sentinel); TRL GRPOTrainer optimizer with Dr.GRPO
  advantages, DAPO clip-higher and overlong punishment, difficulty
  resampling, KL leash; rollout audit (sampler-trainer logprob divergence
  with a preregistered abort threshold, actual-tensor advantage agreement);
  entropy guard (torch reimplementation of reheater math with a DETACHED
  self-distillation target, hysteresis, nats, canonicalized diversity;
  stdlib reheater.py retained as the CPU parity oracle); classical search
  baseline (arm G, and the source of unpublished incumbents).
- **Layer 7, surfaces and distribution:** CLI verbs (verify, why, contest,
  criterion, oracle qa, adapter probe, bench prereg/run, pack, budget);
  desktop receipt-v2 renderer (fourth verdict as a word and a shape, never
  a fourth color; does_not_prove rendered; budget surface); verifiers and
  OpenEnv environment packages with a pack/env split (hidden tests as
  salted commitments); reproduce scripts (minutes on a laptop).

**Training loop corrections adopted from the panel (previously wrong in
live code):** one temperature per group with fresh seeds per step
(budget_schedule leaves the training path; its multi-temperature grid stays
on selection and eval); UNDECIDED gets advantage exactly 0.0, loss-masked,
counted; candidate-attributable execution failure is FAIL;
harness-attributable failure is dropped and written to an exclusion ledger.

## 5. Receipt schema v2 (the fields that are cheap now, expensive later)

Canonical JSON, sorted keys, no floats in hashed fields. Two digests:
content_digest (the stranger-re-derivable subset, verdict included) and
attested_digest (the signed full body; signed_over fixed in code, never
read from the receipt). receipt_id = H(content_digest, run_nonce,
ledger_seq).

Load-bearing fields, beyond the obvious:

- CRITERION: id, version, sha256, parent hash, change_reason, decision
  rule (conjunctive required for reward), objective mapping as data,
  license id.
- ORACLE: checker source hash, runtime hash, toolchain pin,
  execution_isolation (signed), **executes_candidate_code** (the stranger's
  filter), oracle_qa_card_hash (absent means not reward-eligible),
  held_out agreement, determinism reruns.
- TIER: evidence_kind is NOMINAL (formal, constructive, computational,
  empirical, adjudicated); cross-kind comparison is a validation error;
  input tier multiset carried in full, never min()'d; specificational
  inputs recorded separately so human judgment is never floored.
- RAW OUTPUT: raw stdout/stderr sha256 hashed from the subprocess stream
  before any Python reads it; model_readout: false is structural. (The one
  measured 2026 case of trusting a model's readout inflated a result 4.3x.)
- DENOMINATOR (mandatory, no defaults): attempts, oracle calls, hits,
  undecided, unverifiable, parse failures, tokens, cache hits, tasks
  proposed and filtered, filter id and hash, **filter_is_learned** (a
  learned curriculum proposer is visible, never invisible).
- NOVELTY: verdict in {REDISCOVERY, NOT_FOUND_IN_CORPUS, UNKNOWN}. "NOVEL"
  is not a legal value; NOT_FOUND_IN_CORPUS names its corpus. (8 of 13
  "solved" Erdos problems in the 2026 record were rediscoveries.)
- DOES_NOT_PROVE: required, non-empty, mechanically derived floor plus
  free text. The receipt names its own limits.
- INVALIDATION: typed reason codes; downstream records append, never
  mutate.
- SIGNATURE: Ed25519 exportable, HMAC local-only and stripped at pack
  time.
- No trust_score field exists anywhere. Only trust_recompute_cmd.
- Negative, null, UNDECIDED, and INCOMPLETE receipts are first-class and
  spendable.

RL extension wraps this with estimator config, per-rollout verdict and
advantage audit fields, sampler-trainer divergence, entropy and reheat
trace, arm id, prereg hash, and exclusion ledger ref.

## 6. Proof protocol (Bar U)

Primary metric: mean normalized objective ratio against the operator's own
search incumbent (arm G), on sealed held-out generated instances,
instance-level split within regime; parameter-regime extrapolation is a
separate secondary. No success metric on any family where the frozen base
scores zero (elicitation vs expansion is unresolved in the literature; the
design does not bet on capability creation).

Arms: A oracle-reward RL; B random reward matched per step to A's realized
trajectory with A's difficulty schedule replayed; C shuffled oracle
(marginal preserved, pairing destroyed); D frozen base at identical budget
(+ D_E non-Qwen frozen base); E non-Qwen replication of A; F
rejection-sampling SFT on developmental.curate output at matched budget;
G classical annealer at equal wall clock; H memorization probe against the
registry. Plus a compute-matched inference contrast (post-RL greedy vs
pre-RL best-of-N).

Claim rule, frozen before the first scored run: uplift is claimed only if
A-D, A-B, A-C, and A-F all exclude zero AND arm E reproduces the sign.
G and H are reporting obligations, not claim conditions: a valid and an
irrelevant uplift can coexist, and both publish. Any failure publishes as
a null with the same intervals, receipts, and prereg hash. A wide null is
the modal outcome at three seeds; the preregistered power analysis will
say so before the run.

Preregistered and externally anchored before the first scored run:
criterion hashes and the frozen held-out seed split; the exact primary
metric expression; all arms including B's matching algorithm; the analysis
script validated on synthetic data with known coverage; power analysis and
MDE; the stopping rule as a fixed budget (never "until significant"); the
claim rule verbatim; the compute-contingency ladder (which arm is cut
first if budget fails, with stated consequence); the entropy floor derived
from the OFF arm; abort thresholds; the multiplicity hierarchy; the QA
gate bounds.

## 7. Lane roles

- **crucible:** verdict authority and receipt mint; sealed held-out
  assessments; ProofMeasure carries objective and coverage beside the
  boolean; UNVERIFIABLE already first-class.
- **forum:** ledger of record; rollout harness with tiered executors; the
  only path to a human-adjudicated annotation; human gates are the
  verification-gated-improvement mechanism that public sentiment licenses.
- **learn:** curriculum engine (difficulty filter with mandatory
  denominator fields) and calibration (predict-then-observe, Brier as a
  receipt field and Bar U secondary, not a reward term).
- **index:** scope bounds, INPUT_MUTATED events, named invalidation from
  checker source hash to dependent receipts.
- **gather:** evidence intake with grounding check; proposes incumbents
  into staging only; a forum human gate promotes to the registry (a
  model-assisted extraction pipeline must not touch the accept path).
- **telos:** the export format; a bundle is a self-contained proof packet;
  propose-verify-promote is the certificate lifecycle.
- **lanes.py:** provisioning and honest degradation; an absent verifier
  lane degrades to UNVERIFIABLE, never a fake pass.

## 8. Deliberately not built (yet)

- No instance proposer (generators with a difficulty knob only; a stranger
  regenerates the instance set from a seed).
- No Lean 4 tier yet: the elaborator executes arbitrary code (#eval,
  native_decide, @[extern]) and a multi-gigabyte cache breaks the offline
  claim. The proof_checker slot is declared and empty; harness/lean_oracle.py
  already audits correctly and is promoted when Phase 3 isolation and a
  per-platform sidecar pin exist.
- No allocator or price mechanism; cost is metered and budgeted, not
  optimized.
- No falling-marginal-cost headline until earned on novel input closures.
- No consensus or quorum anywhere near reward (votes propose, proofs
  dispose; CONSENSUS_PASS maps to UNDECIDED at mint time).
- No calibration reward term (degenerate optimum; gated form needs its own
  ablation).
- No hosted-provider training (hosted endpoints are evaluatable_only).
- No zkML, no TEEs, no trust score, ever.

## 9. Residual risks and honest unknowns

Carried verbatim from the panel: elicitation vs expansion stays unresolved
and this design sharpens it; the classical baseline may simply win (both
facts would publish); five-condition conjunction at three seeds has low
power; key custody on a single-operator box is policy, not architecture,
and every receipt says so; invalidation rates have no principled setting
(the drill measures them); verifier QA bounds only imagined mutations;
Bar R's human evidence cannot be self-generated (CI is a mechanical
stranger); construction certificates generalize weakly and a reader may
fairly ask whether they transfer; cross-fork criterion reconciliation is
unsolved; Windows toolchain risk (WSL2/Linux is Phase 1 scope, not
contingency); selective publication is detectable only as rollback, not as
absence; several line estimates will be wrong on the low side.

## 10. Milestones

- **Phase 0, ground (weeks 1-2):** CI, license split (Apache-2.0 for
  harness, criteria, checkers, verifier, bundles, adapters; FSL only where
  not load-bearing for verification), verdict.py, Oracle widening, run_env
  allowlist, gateway auth. Gate: one existing orphan chain
  (matmul_oracle -> rl_from_oracle.collect -> receipt -> verify -> MATCH)
  end-to-end behind one command in one week, using only code that exists.
  If that fails, the plan is disproven cheaply.
- **Phase 1, first proof (weeks 3-8):** criteria, two certificate
  families + generators + independent checkers + matmul adapter, oracle
  QA live, receipts + Ed25519 + ledger + bundle + contest, why + desktop
  receipt renderer + budget surface, base-rate survey, preregistration,
  reward gate + TRL optimizer + rollout audit + entropy guard + search
  baseline. 7B pilot (arms A, B, D, G, H; dress rehearsal, explicitly not
  the claim). First stranger trial in week 4.
- **Phase 2, hardening (weeks 9-11):** families 3-4, cost meter +
  amortization + invalidation drill, full adapter layer with six carded
  heterogeneous backends, main 14B run (all arms, three seeds, bursting to
  rented CUDA; remote nodes never sign), retention probe, entropy ON/OFF
  ablation.
- **Phase 3, world (weeks 12-13):** bundle hardening, pack/env split, STH
  external anchoring, key rotation, verifiers + OpenEnv publication, PyPI
  under a checked name, reproduce scripts, full publication including
  nulls, drifts, and open contests.

Desktop presentation work (onboarding, installer, bundled engine, naming
the Zentropy identity in the Windows runner) proceeds in the idle windows
of GPU-bound phases, per the operator's approach ruling, with the
receipt-v2 renderer and budget surface as the Phase 1 anchor.

## 11. Success, stated in the register the discourse rewards

Not "the model got smarter." The claims this program can honestly earn:

1. A corpus of criterion-pinned receipts any stranger re-derives offline,
   with contests counted and published (Bar R).
2. A preregistered, control-armed answer to whether verified reward lifts
   a local model on these families, whatever the answer is (Bar U).
3. Retention and entropy trajectories measured with controls (Bars 3-4).
4. The two bars coalescing: strangers re-deriving the uplift experiment
   itself (T1/T2), the evidence base becoming communal.
