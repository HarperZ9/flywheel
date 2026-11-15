# optimization_workflow — wedge #5

An **optimization run → proof packet**. Bind a problem (objective + constraints,
optionally a QUBO/encoding), an enumerated/searched candidate space, an **exact
baseline optimum**, and a **solver branch**, then derive the proof obligation:
*does the solver's best feasible objective match the exact baseline within
tolerance?*

- **Verdict** (shared crucible-faithful rule): `deviation = |solver_value − baseline_value|`; `MATCH` if within tolerance, `DRIFT` if beyond, `UNVERIFIABLE` if the branch did not complete. A **constraint violation is a `DRIFT`** regardless of value — an infeasible answer is not a valid optimum.
- **Honesty boundary** (`_boundary_gate.py`): a `hardware_execution_claim` is admissible only with a **COMPLETED `hardware` solver branch**; a `quantum_advantage_claim` requires a `hardware_execution_claim`. A toy/exact solve claims neither. Same no-overreach-without-disclosure gate as the visual calibration boundary and research `formal` block.

Quantum optimization is the lead demo (harvested from dogfood pass 0085/0086);
the primitive is domain-general — the same receipt covers LP/MILP, portfolio,
routing, and hyperparameter search. A future D-Wave / simulator / generic QUBO
adapter must reproduce these exact receipt fields against the baseline.

## Use

```bash
telos-proof optimization-workflow --input run.json --claim "..." --scope "..." --out ./artifacts
# or: python -m proof_surface.optimization_workflow --input run.json ...
```

`run.json`: `{sources, problem, candidate_space, baseline, solver[, boundary, uncertainty]}`.
Emits `packet.json`, `report.md`, crucible `thesis`/`measurements` for independent
re-derivation, a peer assessment (when crucible is installed), and a
content-addressed `bundle.json`.
