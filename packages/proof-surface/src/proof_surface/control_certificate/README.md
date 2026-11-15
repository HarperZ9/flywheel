# control-certificate -- wedge #10

A **stability/feasibility-claim -> proof packet**. Grounded in dogfood passes
0112 (Lyapunov stability certificate) and 0113 (constrained-MPC feasibility),
scoped in by the operator's robotics and cybernetics lane. Cybernetics is the
program's thesis in feedback-loop vocabulary; this wedge makes the loop's
central promise -- "this controller is stable" -- carry re-checkable proof.

A `system` (plant + regime) claims a declared `certificate` (`lyapunov`,
`ranking-function`, `contraction-metric`, or `mpc-feasibility`), proven by
witnessed `conditions` (each a real residual within tolerance) **and**
falsified by a required `negative_fixture` that **must violate** the
certificate.

## The load-bearing gates

`_gates.py` enforces three rules:

1. The `negative_fixture` provably violates the certificate
   (`violates_certificate == true` **and** `residual > tolerance`). A
   stability "check" that cannot fail on a known-unstable system has no
   discriminating power -- **a verifier that cannot fail on a known-bad input
   is not a verifier.**
2. **Kind completeness**: a certificate kind must witness all of its defining
   conditions (`lyapunov` needs `positive-definite` + `decrease`;
   `mpc-feasibility` needs `recursive-feasibility` + `constraint-satisfaction`;
   `ranking-function` needs `well-founded` + `decrease`; `contraction-metric`
   needs `contraction`). A kind without its conditions witnessed is an
   assertion, not a certificate.
3. **Sim-to-real boundary**: `hardware_validity_claim` requires a hardware (or
   hybrid) regime AND hardware evidence references. Verified in simulation is
   never presented as verified on hardware.

The verdict is `MATCH` iff every witnessed condition holds within tolerance,
`DRIFT` if any fails, `UNVERIFIABLE` if nothing was witnessed.

Decrease is not constancy: a conserved quantity belongs to the `conservation`
wedge (#9); this wedge covers directional conditions (a potential strictly
decreases, a feasible set stays reachable). Domain-general: controller
stability, program termination via ranking functions, iterative-solver
convergence, MPC feasibility.

## Contract additions from the lane handoff

- `certificate.provenance` (`synthesized` / `verified` / `author-asserted`,
  optional `provenance_ref`): the certificate's own origin is disclosed and
  never conflated -- an author-asserted candidate is a different evidence
  class than an independently verified one. The builder defaults to
  `author-asserted` (fail-closed: never an upgrade).
- `trajectory` (`log_sha256`, `samples`, optional `description`): the packet
  binds the certificate check to the hashed executed trajectory log. Without
  the binding there is nothing the verdict is a verdict OF.

## Prior art (the fence)

The composed artifact -- a sealed, offline-re-verifiable receipt binding an
executed trajectory to a declared certificate with its own provenance, plus
negative fixtures proving the checker can fail -- is unclaimed in the
2024-2026 verified-control literature (verified 2026-07-02 by a 3-researcher
grounding pass). Nearest neighbors, each one level short:

- Certified Control (arXiv 2104.06178): per-decision runtime certificates,
  not per-run archived or offline re-verifiable.
- ModelPlex (FMSD 2016): provably correct runtime monitors; no sealed
  re-checkable artifact.
- Dynamic neural-certificate verification (arXiv 2507.11987): online
  monitoring, not sealed offline receipts.
- ROVER (arXiv 2511.17781): STL trace evaluation without sealed provenance or
  negative fixtures.
- Ethical Black Box (arXiv 2205.06564): flight-recorder logging; no invariant
  binding or re-verification.
- Tamper-evident logging (arXiv 2509.03821): seals bytes, not invariants.
- Fossil 2.0 (arXiv 2311.09793): certificate synthesis, not run receipts.

## Demo

`examples/control_certificate/demo.py` synthesizes a real discrete Lyapunov
certificate (P = Q + A^T P A fixed-point iteration, provenance `synthesized`),
measures the decrease residual over simulated trajectories, and shows the
stable loop PASS (MATCH) while the destabilized loop under the SAME
certificate FAILS (DRIFT). Every residual is computed, never hand-entered.

## Use

```bash
telos-proof control-certificate --input claim.json --claim "..." --scope "..." --out ./artifacts
# or: python -m proof_surface.control_certificate --input claim.json ...
```

`claim.json`: `{sources, system, certificate, witnesses, negative_fixture,
sim_to_real[, uncertainty]}`. Emits `packet.json`, `report.md`, crucible
`thesis`/`measurements`, an optional peer assessment, and a content-addressed
`bundle.json`.
