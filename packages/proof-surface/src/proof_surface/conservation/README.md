# conservation — wedge #9

A **transformation-conserves-an-invariant → proof packet**. Harvested from the
convergence of dogfood passes 0105 / 0106 / 0107 (mass-conservation,
stoichiometric invariant, reaction-network corpus).

A claimed `transformation` is asserted to conserve a declared `invariant`, proven
by independent `witnesses` (an exact `algebraic` residual and/or a `numeric` drift
bound, each within its tolerance) **and** falsified by a required
`negative_fixture` that **must break** the invariant.

## The load-bearing gate
`_gates.py` enforces that the `negative_fixture` provably breaks the invariant
(`breaks_invariant == true` **and** `drift > tolerance`). A conservation "check"
whose negative fixture cannot break has no discriminating power — **a verifier
that cannot fail on a known-bad input is not a verifier.** The verdict is `MATCH`
iff every witness conserves within tolerance, `DRIFT` if any exceeds it.

Domain-general: the same shape covers mass/energy balance, refactor-preserves-
total, RL reward-shaping-preserves-return, and optimization reformulation-
preserves-objective.

## Use

```bash
telos-proof conservation --input claim.json --claim "..." --scope "..." --out ./artifacts
# or: python -m proof_surface.conservation --input claim.json ...
```

`claim.json`: `{sources, transformation, invariant, witnesses, negative_fixture[, uncertainty]}`.
Emits `packet.json`, `report.md`, crucible `thesis`/`measurements`, an optional
peer assessment, and a content-addressed `bundle.json`.
