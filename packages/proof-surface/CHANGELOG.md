# Changelog

## Unreleased

- CI now checks the committed demo proof bundle on Ubuntu and on Windows with
  `core.autocrlf=true`. Its digests were resealed over the committed LF bytes
  and the bundle folder is pinned with `-text`; see `RESEAL.md`.
- Added a stdlib-only tracked public-surface gate and wired it into CI. It uses
  Git's tracked-file list, excludes caches, Git metadata, and build roots, and
  reports deterministic locations without echoing matched secret values. Every
  tracked file is scanned as bounded UTF-8 unless its suffix explicitly marks a
  known binary. Credential-shaped material is checked in source, tests, dotenv
  variants, credential files, and unknown text suffixes. Unreadable or oversized
  unclassified files fail closed. Machine paths, encoding corruption, unresolved
  template markers, unsupported private-tree references, and new or grown
  em-dash use fail closed on public prose. Existing v0.1 fixture paths and package
  README punctuation debt are count-bounded so the gate can burn down but not
  grow.
- Factored the ledger's duplicate-key and non-finite JSON rejection into one
  shared stdlib decoder and applied it to raw authorization receipt file and CLI
  entry points. Authorization v0.2 conformance now covers duplicate scope keys,
  escaped-equivalent keys, `NaN`, and positive and negative infinity. Dict-only
  validators remain structural APIs: callers must not permissively parse raw
  signed JSON before invoking them.
- Aligned the authorization v0.2 JSON Schema with the reference validator for
  trimmed nonempty strings, explicit-timezone RFC3339 timestamps, JSON boolean
  and integer edge cases, nonce shape, action budgets, and unknown fields. A
  checked-in 24-case negative parity corpus and every manifest fixture now run
  through both validators.

- Added the explicit authorization-receipt v0.2 inner contract while preserving
  v0.1 fixtures, validation, and `check_action` behavior. The v0.2 structure
  requires a stable receipt ID, a nonzero lowercase hexadecimal nonce with
  at least 128 bits, exact agent/action/target strings, issued and expiry times,
  a positive action budget, and a revocation flag. Unknown fields fail closed.
  `check_action_v2` checks exact identity, scope, time, revocation, and observed
  budget use. External signature trust and atomic consumption remain consumer
  obligations. Separate schema, conformance, and migration fixtures make the
  version boundary explicit.
- Added `tadr-classification` and `tadr-control` to the organ bundle's closed
  receipt-kind vocabulary. Bundle payload digests must now be nonzero 64-character
  lowercase SHA-256 values; existing kinds and nonzero legacy digests remain
  valid. The schema, validator, valid/invalid vectors, and manifest are pinned
  together.
- Added `telos-proof validate <document.json>` and the equivalent module command
  for authorization v0.1/v0.2 receipts and organ bundles. The command emits a
  typed JSON `MATCH` or `UNVERIFIABLE` result and fails closed on unknown input.

- Added `learn-lesson` to the organ-bundle `RECEIPT_KINDS` closed set: the
  receipt kind for the organizational learning loop. A lesson entry composes
  onto the same spine every flagship already rides, carrying the lesson's
  content-addressed seal hash as its `payload_sha256`. Backward-compatible
  (additive to the set); the kind-vocabulary test, the JSON schema enum, and the
  mixed-bundle fixture stay in lockstep.
- N-instance replication gate (dogfood 0145), one more optional disclosure field
  shared across the family and wired into `model_eval` and `ai4science` first:
  - `replication` (an object `{instances: [{instance_id, verdict, warnings?}],
    generalization_claim}`): a single-instance `MATCH` is never a
    generalization/scale claim. When `generalization_claim` is true the gate
    (shared helper `proof_surface._replication`) requires two or more instances
    AND every instance verdict `== MATCH`; a generalization claim with fewer
    than two instances, or with any non-`MATCH` instance, is rejected, and a
    malformed instance verdict enum is rejected. Per-instance warnings are
    preserved, never dropped. The field is optional; legacy packets without it
    validate unchanged. Covered by a dedicated gate test, wedge validator tests,
    and the family negative-fixture conformance gate.
- Family evidence gates (dogfood 0115/0117/0126), three optional disclosure
  fields that stay honest under scrutiny:
  - `declared_branches[]` (branch matrix, wired into `optimization_workflow`
    and `research_claim`): every declared branch is `EXECUTED` (and records the
    `MATCH`/`DRIFT`/`UNVERIFIABLE` verdict it earned) or `UNAVAILABLE_FENCED`
    (and carries non-empty `probe_evidence` of the fence). A fenced branch that
    claims a verdict is rejected, and a claim or decision reason that cites a
    fenced `branch_id` as support is rejected (a branch that did not run is not
    evidence).
  - `witness_tier` (wired into `research_claim`): declares the target verifier
    tier, the strongest tier that actually executed, and whether the target
    slot ran. Bound to the promotion ladder so a rung may not exceed the
    strongest executed tier; when the target slot did not execute the declared
    target tier may not be named as achieved.
  - `evidence_classes[]` (wired into `research_claim`): a closed vocabulary of
    evidence provenance. A fact-tier promotion (CRUCIBLE_MATCH and above)
    requires at least one class that is not `single-modality-derived`; evidence
    that is entirely single-modality caps the promotion at the hypothesis rung.
  - All three are optional; legacy packets without the fields validate
    unchanged. Off-ladder honesty rungs (UNVERIFIABLE, REFUTED) are never
    capped. Covered by dedicated tests and the family negative-fixture gate.
- Added wedge #11 `competition_attempt` (the SAIR competition/judge lane): a
  single competition attempt binds the challenge to a source-pinned
  `judge_repo` observation (repo ref, 40-hex head sha, observed file count,
  files digest), discloses hosted-model usage with the eval-attempt
  hermeticity rule verbatim, records how the answer was extracted (a non-boxed
  method must record an injection check; an unrendered template marker is
  rejected), and carries a closed certificate ladder (informal-model-output,
  machine-checked-proof, finite-counterexample, judge-verdict). A fenced layer
  must cite the probe that proved the fence and may not carry a pass/fail
  result; the overall verdict may only cite EXECUTED layers; `MATCH` is only
  derivable from an EXECUTED, passing judge verdict, so a passing verdict with
  zero executed layers is impossible by construction. Grounded in dogfood
  passes 0136/0137/0138/0139; routed through `telos-proof competition-attempt`
  and covered by the family negative-fixture conformance gate.

- eval_attempt hermeticity disclosure (dogfood 0137/0138, SAIR cluster):
  optional `attempt.external_model_calls` + `attempt.provider_receipt_ref`.
  When the attempt discloses its hosted-model usage the claim must be
  evidence-consistent: a hermetic claim (0 calls) citing a provider receipt is
  a contradiction; a nonzero count without a receipt reference is rejected
  (redacted evidence is admissible, absence is not); a receipt without a
  disclosed count is rejected as undisclosed external usage. Undisclosed
  legacy packets validate unchanged.

- Added wedge #10 `control_certificate` (the robotics/cybernetics lane): a
  stability, termination, or convergence claim carries a declared certificate
  (lyapunov, ranking-function, contraction-metric, mpc-feasibility), witnessed
  conditions with real residuals, a REQUIRED negative fixture that must
  violate the certificate, and an explicit sim-to-real boundary -- hardware
  validity is never claimable from simulation-only evidence, and a certificate
  kind missing its defining witnessed conditions is rejected as an assertion.
  Grounded in dogfood passes 0112/0113 and the operator's robotics directive;
  routed through `telos-proof control-certificate` and covered by the family
  negative-fixture conformance gate.

## 2026-07-01 - Flagship receipt kinds on the organ bundle spine

- Extended the closed `RECEIPT_KINDS` set of the `organ-receipt-bundle` contract
  with the five flagship kinds: `crucible-assessment`, `forum-route`,
  `index-context-envelope`, `gather-corpus`, `learn-receipt`. The JSON schema
  enum was updated in lockstep and a test pins the two artifacts together.
- Added a cross-tool conformance test module proving a mixed bundle (one entry
  of every flagship kind plus an existing organ kind, synthetic sha256 digests)
  validates with the stdlib-only validator, and that an entry claiming an
  unknown `receipt_kind` is still rejected: the set is extended, not opened.
- `ORGAN_BUNDLE_VERSION` stays `0.1`; validation behavior for existing kinds is
  unchanged.

## 2026-07-01 - 0.2.0 - Family hardening (post-integration)

- Typed `failure_labels` (the shared `_failure` vocabulary) are now accepted by
  ALL nine wedges, not just `agent_action`, per the rl-scaling receipt-spine note.
- `research_claim` gained a first-class `REFUTED` promotion rung and a refutation
  gate: a standing counterexample (a `refuted` attempt or `formal.counterexample_found`)
  forces `REFUTED` and outranks passing checks; a PASSED kernel replay with
  unresolved `sorry` holes is rejected.
- `eval_attempt` gained an auditability gate: a `correct` outcome with a latent
  (unavailable) reasoning trace and no `replay_ref` has no audit surface and is
  not scored `MATCH`.
- `_compute_lease` was promoted to the shared spine and wired onto `rollout_receipt`
  (paid GPU / cluster compute as an accountable external write); rollout now also
  enforces `$.verdicts.overall == $.verifier.verdict`.
- The negative-fixture conformance gate ("a verifier that cannot fail is not a
  verifier") now covers all nine wedges.

## 2026-07-01 - 0.2.0 - Proof-packet wedge family

- Added nine domain proof-packet wedges, each a validator + builder + report +
  CLI sharing one spine (crucible-faithful verdict rule, required decision
  summary, non-promotion boundary, content-addressed bundle, neutrality guards):
  `agent_action`, `visual_measurement`, `research_claim`, `model_eval`,
  `optimization_workflow`, `rollout_receipt`, `eval_attempt`, `ai4science`,
  `conservation`. All route through the unified `telos-proof <domain>` CLI.
- Each wedge enforces a domain honesty gate (no physical-calibration overclaim,
  contamination rejection, dependency-boundary and penalty-surrogate and
  fixture-match-is-not-encoding-soundness checks, reject-unmeasured-discovery,
  a negative fixture that must break, and a sufficient-not-necessary boundary).
- Added `proof_surface.trace_adapters`: OpenTelemetry and LangSmith/Langfuse
  trace normalizers plus evidence importers for MLflow, W&B (artifacts + Weave),
  Braintrust, Arize Phoenix, promptfoo, Helicone, DVC, and SLSA/in-toto, each
  declaring the non-inferable proof-layer gap, with an enforced coverage registry.
- Harvested from the `telos/docs/research/dogfood` program (through pass 0111)
  and the `rl-scaling-receipt-spine` and `mycology-network-intelligence` notes.
- Bumped version to 0.2.0. Base contracts (packets, receipts, gates, ledgers,
  delegation chains, witness receipts) are unchanged and remain the stable core.

## 2026-06-29 - Forward Delivery Contract

- Added `AGENTS.md`, `CHANGELOG.md`, a delivery regression test, and
  `project-docs/specs/SPEC-proof-surface-forward-delivery.md`.
- Updated CI to current Node 24-era GitHub Actions majors for Python setup and
  checkout.
- Added package repository, issues, and homepage metadata.
- Normalized forward-facing punctuation for public-surface scanner
  compatibility.
- Kept schemas, validators, conformance vectors, decision helpers, and verdict
  behavior unchanged.

## Current Status

- Runtime: Python 3.10+ with stdlib-only core validators.
- Surfaces: Python API, JSON schemas, conformance vectors, examples, and usage
  guide.
- Verification: pytest suite plus the root forward delivery contract.
