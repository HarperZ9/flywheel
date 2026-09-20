# Flywheel 1.0.0: overview, feature set, and walkthrough

Flywheel 1.0.0 is released: `flywheel-verify` 1.0.0 on PyPI and a Windows desktop
installer on the GitHub release. This document is the code-grounded overview: what
Flywheel is, the full feature set, and an install-to-first-verdict walkthrough. Claims
are bound to the code; items marked proposed or fast-follow are roadmap, not shipped
behavior.

## What Flywheel is

Flywheel is a self-hostable, model-agnostic AI workstation and coding harness. It runs a
task with any model, local or frontier, routes one prompt across roughly twenty endpoints
behind a drop-in OpenAI-compatible surface, runs a gated coding agent over your own
folders, serves local models for offline work, and drives a native desktop app. It is
built to stand with the coding harnesses people use every day and to compete on features,
not to be a niche eval tool.

Its distinctive backbone is re-derivable verification. The rule the code enforces is "no
receipt, no accept" and "no learned model on the accept path": only a real oracle, a test
runner or a data-only certificate checker, can accept a result, and each accepted answer
carries a proof receipt a third party re-runs to reproduce the verdict offline. Every
other harness gives you an answer; Flywheel gives you the answer and the receipt.

The enduring aim under the product is model capability and task-and-reasoning uplift. The
verified-inference loop, the local model, multi-provider routing, and an internal
candidate model are the mechanisms pointed at that aim. The honest state today: on the
shipped benchmark the verified loop shows no measured accuracy uplift over single-shot
(the interval includes zero), so the demonstrated value right now is the re-derivable
receipt and the containment, and uplift is the direction the mechanisms are built toward,
not a result claimed.

## Full feature set

Grouped by domain. Each line is bound to code. Items marked proposed or fast-follow are
not shipped 1.0.0 behavior.

### Verified-inference engine core
- Propose-verify-witness loop with per-stage hash-chained receipts; acceptance requires
  oracle PASS and witness MATCH (harness/loop.py).
- Four-way verdict PASS / FAIL / UNDECIDED / UNVERIFIABLE with candidate / harness /
  environment attribution, so an unrunnable check is not read as a failure
  (harness/verdict.py).
- Best-of-N search, proof-addressed cache, and a verified pool that banks only
  oracle-accepted claims (harness/loop.py).

### Verification and oracles
- The oracle is the sole acceptor; no learned model sits on the accept path
  (harness/oracle.py).
- PytestOracle runs model-written code in an allowlisted, tree-killable subprocess; the
  canonical hash is over junit outcomes, and an all-skipped green exit is refused as a
  non-pass (harness/oracle.py).
- Domain routing denies by default: an unregistered domain returns UNVERIFIABLE. Today:
  code (pytest), math (Lean), ml (a measurement gate) (harness/oracle_registry.py).
- Data-only certificate checkers that never execute the certificate, with scope
  envelope, instance binding, and a mechanically derived does-not-prove line
  (harness/certificates/).

### Proof, witness, provenance
- Each accepted answer emits an in-toto Statement in a DSSE envelope, with a verdict-free
  subject-digest and a verdict-bound claim-digest; the fixture set is signed so tampering
  moves the digest (harness/envelope.py).
- Independent re-check re-runs the recorded oracle command and recomputes the hash:
  MATCH, DRIFT, or UNVERIFIABLE (harness/witness.py).
- ed25519 receipt signing, Merkle chains, a transparency log, and external anchoring via
  OpenTimestamps and a Zenodo DOI (harness/receipt_sign.py, harness/merkle.py).
- A behavioral provenance probe that flags when an endpoint's outputs match a known
  alternative better than the claimed model (harness/served_model_provenance.py).

### Coding agent and gated tools
- A real edit-test-repair agent with acceptance-criteria gating, a canary tripwire that
  contains a run on a decoy-resource read, a per-run byte-witness chain, and HMAC-signed
  per-tool receipts (harness/local_loop.py).
- A gated sandbox: default-deny writes and exec, path-traversal-safe reads that re-confine
  symlinks, a destructive-command denylist, and strict all-or-nothing diff apply
  (harness/local_tools.py). Runnable on any model endpoint (relay lane).

### Model-agnostic: frontier, all providers, and local
- One roster of about twenty endpoints, all feeding the same oracle, witness, and receipt
  path: OpenAI-compatible providers, native Anthropic and Gemini, subscription CLIs,
  OpenCode, and local serve / Ollama / vLLM. The provider registry includes codex, claude,
  gemini, deepseek, glm, openrouter, and an abliteration endpoint
  (harness/endpoint_registry.py, harness/endpoints.py).
- The gateway exposes OpenAI-compatible /v1/chat/completions and /v1/models, routes to any
  named provider, and rides an x_receipt extension. Credential presence only: it never
  reads or returns a key value, and it records served_model to catch a silent model swap
  (harness/gateway.py). Native Anthropic Messages-API facade with per-turn receipts
  (harness/messages_api.py).
- A local offline tier fails over between a local served model (deterministic on seed and
  prompt) and Ollama, health-gated and streaming, speaking only to localhost
  (harness/local_agent.py, harness/serve.py).

### Selection and escalation
- Cheapest-first routing: cache, then local verified selection, then escalation to a
  costlier tier. Escalation is a thresholded-confidence verdict, never a learned
  difficulty prediction, and every decision is appended to a ledger (harness/companion.py).

### Gateway superapp
- One stdlib HTTP origin with zero external dependencies serving the shell plus dozens of
  API routes: endpoint-health roster, a root-hashed world-state and receipts ledger with a
  Merkle root and offline inclusion proofs, governance tiers, the lane roster, agent
  operations, memory, plugins, a parity matrix, and training status. Built-in falsifiers:
  killing the local server flips the tier unhealthy; touching a cataloged receipt moves the
  root hash (harness/gateway.py).

### Lane layer
- A roster of standalone MCP engine lanes, each resolved across installed package, source
  checkout, bundled, or http, with live health probes grading LIVE / STALE / DECLARED /
  MISSING (harness/lanes.py, harness/lanes_registry.py). Lanes and roles: gather (research
  intake), crucible (falsifiable verification), index (workspace map and symbol graph),
  forum (witnessed causal ledger and routing), learn (accountable learning), telos
  (creative engine and five-tool workflow), local-model (proposer plus verified inference),
  writing (author workspace), relay (coding agent), plexus (capability discovery and
  auto-wiring), mneme (memory recall with ranking receipts), calibrate-pro (display
  calibration), canon (provider-neutral memory bank), bulletin (agent correspondence
  board), accountable-surface (witnessed perception and gated effectors).
- Native in 1.0.1: chorus (re-derivable discourse digest) and articulate (writing-quality
  and AI-tell detector and editor) are registered lanes, and a compose pipeline chains
  gather, chorus, and crucible into one claim-verification bundle (harness/compose_claim.py).

### Research intake, code intelligence, learning, memory
- Research intake: crawl and normalize sources, rank ACTIONABLE / INSPIRATION / NOISE by
  falsifiable mechanism, synthesize with provenance receipts (gather lane).
- Code intelligence: workspace map, symbol graph, BM25 retrieval, repo map, drift-checked
  verified wiki (index lane).
- Learning: spaced repetition, a codebase-to-lesson academy pipeline, deterministic Manim
  lesson rendering (learn lane).
- Memory and continuity: accountable recall with re-derivable ranking receipts and drift
  verdicts, a provider-neutral memory bank, a local second-brain (mneme and canon lanes).

### Creative studio, actuation, governance, interop
- Creative studio: deterministic seeded pipelines with per-stage receipts for image, film,
  and raster work, a parametric typeface forge, and a seeded sound studio (telos lane).
  This is the one place color is the subject of the work.
- Accountable actuation: witnessed perception, an operator-grant pre-execution gate,
  self-verifying effectors, and a tamper-evident journal; browser and native control with
  credential-shaped fields refused before policy is consulted (accountable-surface lane).
- Governance and interop: TADR tiered governance receipts, a standards registry, incident
  simulation, accountability benchmarks, and cross-harness bridges (ACP, LSP, DAP, and a
  METR Inspect bridge).

### Desktop workstation
- A native Flutter client that is a thin renderer over the local engine at
  http://127.0.0.1:8799, reimplementing no engine logic. Wired destinations across work,
  chat, code, evidence, and advanced groups: chat with the Rowan assistant on any model
  with a per-turn receipt and verdict pill; Compare (one prompt, two live model threads);
  Companion (cheapest honest source, labeled verified / consensus / escalated); a Code IDE
  with LSP go-to-definition and a docked gated agent; Lint and Scan surfaces that print
  coverage denominators; an Approvals inbox showing the exact operation JSON before approve
  or reject; Receipts and a root-hashed World with offline inclusion-proof walking; a
  generative Studio; Relay for phone-driven runs; and read-only Train and Uplift views
  where a lift whose interval includes zero renders as an honest null.

### Internal candidate model (proposed / experimental, off the accept path)
- A candidate-aware classifier/encoder/decoder for repeated bounded decisions: routing,
  tool ranking, context relevance, and escalation, meant to avoid full text generation for
  those decisions and to abstain under uncertainty (harness/classifier_model.py,
  train/classifier_encoder.py). Three arms exist and are tested: a stdlib hashed-feature
  CPU ranker, an optional neural encoder, and decoder comparators.
- How it is meant to help the engine: as a pre-accept proposer aid it can rank
  candidates before the oracle runs, route each task to the cheapest adequate tier,
  pre-rank intake and recall, and triage lint findings. It stays off the accept path by
  design, because a model that both proposes and accepts makes verification circular. So it
  is a system-uplift accelerator across every lane while the oracle stays the sole
  acceptor.
- Honest state: a negative result so far. Automatic selection is disabled and the shipped
  classifier abstains; in controlled experiments deterministic rules beat the frozen
  classifiers. It is built and instrumented; it has not yet demonstrated that it
  strengthens the engine.

## Install-to-first-verdict walkthrough

1. Install the engine. `pip install flywheel-verify`. Stdlib-only core, no compiled
   dependencies.
2. Install the desktop app (optional). Run the Windows installer from the GitHub release.
   The app carries a bundled engine, launches it on start, and polls liveness. Every step
   below also works from the CLI and the gateway API.
3. Start the gateway. It listens at http://127.0.0.1:8799 and serves the shell and the API.
   The app auto-starts it; from the CLI, start the flywheel gateway process. Confirm it is
   live from the endpoint-health roster or the World view.
4. Pick a model or endpoint. `GET /v1/models` lists local serve, Ollama, and hosted
   providers (OpenAI-compatible, Anthropic, Gemini, subscription CLIs). Hosted providers
   show credential presence only, by environment-variable name, never a value. For a fully
   offline run, point at a local served model or an installed Ollama model.
5. Run a task. `POST /v1/chat/completions` with a model name routes to that provider through
   the same accept path and records served_model. For a gated coding task use the local
   agent or the relay lane; reads are free, writes and exec are opt-in.
6. Run through a lane. `flywheel lanes` probes the roster and grades each LIVE / STALE /
   DECLARED / MISSING. A code task routes to the pytest oracle; a claim with no registered
   domain oracle returns UNVERIFIABLE.
7. Get a receipt. An accepted answer emits a proof envelope carrying the oracle command,
   the oracle output hash, and the signed fixture set. In the API it rides the x_receipt
   extension; in the app it is the Receipts view and the verdict pill.
8. Verify it. Hand the receipt to the witness: it re-runs the recorded oracle command and
   recomputes the hash to return MATCH, DRIFT, or UNVERIFIABLE. A third party reproduces
   the verdict without your machine; for a cataloged receipt you can walk its Merkle
   inclusion proof offline in the World view.

## Honest state

- Released: `flywheel-verify` on PyPI (Trusted Publishing, attested) and a Windows
  installer attached to the GitHub release, which passed a clean-runner installed
  acceptance. 1.0.1 adds the chorus and articulate lanes and the compose pipeline natively.
- On the shipped benchmark the verified loop shows no measured accuracy uplift over
  single-shot; the interval includes zero. The demonstrated value is the re-derivable
  receipt and the containment, and capability uplift is the direction the mechanisms aim
  at. It is not a demonstrated result yet.
- The internal classifier is experimental, abstains today, and stays off the accept path
  by design.
- A receipt proves a check reproduces. It does not prove the answer is true of the world.
- This is an independent project, built in the open, with the honest nulls left in.
