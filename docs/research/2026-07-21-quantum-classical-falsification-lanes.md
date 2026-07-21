# Quantum--classical falsification lanes

Version: 1.0
Last updated: 2026-07-21
Author: QCR research documentation
Status: operational research map; not an empirical result

## Decision boundary

This checkpoint turns low-energy, tabletop quantum--classical gravity questions
into falsifiable computations. It does **not** solve quantum gravity, establish a
theory of everything, select an ultraviolet completion, or directly probe Planck
energy or Planck length.

The [verified Reddit comment](https://www.reddit.com/r/accelerate/comments/1v1t248/comment/oysna5w/)
contains a 2031 collider / Planck / ToE scenario. It is a speculative planning
prompt, not experimental evidence, a forecast, or a basis for priority-setting.

“Planck-mass-scale” is a parameter regime for an object mass; it can still be a
weak-field, low-energy experiment. Direct Planck-energy or Planck-length probes
would be a distinct ultraviolet program and are outside this work.

Every receipt records these **orthogonal** fields; none substitutes for another:

| Field | Allowed values | Meaning |
|---|---|---|
| `evidence_state` | `verified`, `inferred`, `unverifiable` | Whether a source, test, or deterministic receipt supports the assertion. `unverifiable` is fail-closed. |
| `scope_state` | `model-bound`, `empirical-bound` | Whether the result applies only to an implemented model or to a controlled empirical result. |
| `controversy_state` | `undisputed`, `disputed` | Whether relevant technical interpretation is contested. |

Thus a reproduced calculation can be `verified + model-bound + disputed`; that
does not become empirical validation.

## Competing low-energy model classes

| Class | Bounded prediction / discriminator | Boundary |
|---|---|---|
| QG-EFT | A local quantized weak gravitational field can create a nonlocal branch phase and a nonzero two-branch entanglement invariant. | A positive result needs exclusion of other quantum channels; it does not choose an ultraviolet theory. |
| CM-local | A strictly local classical-information mediator cannot entangle initially separable systems; specified measurement-feedback realizations require accompanying noise. | Excludes only the stated classical-channel model, not every theory labelled classical gravity. |
| CG+QFT-AH | Aziz--Howl propose a fourth-order, same-matter-field contribution in a classical gravitational background. | The carrier/interpretation and amplitude completeness are disputed; it is not benchmark truth. |
| CG+QFT-factorized | Complete number-preserving evolution in a prescribed classical potential may factorize. | The Gundhi--Infantino--Bassi counterclaim is a current, disputed preprint result. |
| CG+QFT-cross-talk | Same-field propagation and projection can create a conditional signal; distinct noninterconverting fields or a barrier should suppress it. | This is a quantum-matter nuisance/channel, not evidence that classical gravitational degrees of freedom carry quantum information. |
| NL-pair | A direct Newtonian position-pair potential entangles and can reproduce a static phase. | It is a separate nonlocal model, not a local-mediator demonstration. |
| CG-stochastic/collapse | A specified stochastic sourcing/noise law can add decoherence, diffusion, or heating. | “Classical gravity” without a kernel and noise spectrum is not a predictive null. |

## Observables, confounders, and common oracles

Use a reconstructed branch determinant/concurrence or a validated witness, the
local-phase-invariant loop phase, joint parameter slopes, cross-propagator and
barrier/binding response, leakage/success probability, and a force--noise/PPT
boundary. Visibility alone is not an entanglement certificate.

| Confounder class | Examples | Required control / record |
|---|---|---|
| Electromagnetic / surface | residual charge, multipoles, patch fields, magnetic gradients, Casimir--Polder forces | Vary geometry, material, charge state, field orientation, and screen; propagate uncertainty into the loop phase. |
| Hidden quantum channel | shared phonons, photons/electronics, support modes, tunnelling, same-field propagation, preparation entanglement | Independent preparation, field/species separation, barrier and detuning controls; retain leakage sectors. |
| Environment / geometry | gas and thermal decoherence, vibration, blackbody gradients, branch overlap, spreading, timing and distance error | Independently measured kernels; no-gravity controls; report approximation ratios and reject invalid regimes. |
| Readout / statistics | crosstalk, drift, loss, postselection, unequal branches, scan multiplicity | CPTP readout model, preregistered witness, uncertainty interval, and success probability. |
| Theory systematics | static/RWA choices, truncation, regularization, backaction, identical versus distinct fields, source law | Make each an explicit switch; report residuals and nested-limit comparisons. |

Shared deterministic oracles are: O2 pure-state separability (and mixed-state
PPT where applicable); O3 local-phase gauge invariance; O4 complete-sector
closure, trace preservation, and declared leakage; O5 factorization across
particle/field representations; O6 null/asymptotic limits; O7 causality versus
static-limit separation; O8 Kafri covariance/PPT; O9 Yant--Blencowe
nonrelativistic regression; and O10 witness consistency under nuisance injection.
Dimension/validity checks (O1) gate every model before interpretation.

### Current TaskSpec boundary

The two executable physics specs are
[`branch_entanglement_invariants`](../../harness/tasks_physics.py) and
[`projected_sector_audit`](../../harness/tasks_physics.py); their focused
regression coverage is in
[`tests/test_tasks_physics.py`](../../tests/test_tasks_physics.py). They use the
existing `TaskSpec` materialization API, `materialize(spec, dest_dir)`, and the
normal harness execution path--there is no new endpoint.

- `branch_entanglement_invariants` requires
  `branch_invariants(a00, a01, a10, a11)` and returns exactly
  `(norm2, determinant_magnitude, concurrence)`.
- `projected_sector_audit` requires
  `audit_projected_sector(amplitudes, indices)` and returns exactly
  `(full_norm2, success_probability, leakage_probability,
  conditional_concurrence)`. `indices` are the four distinct, ordered in-range
  positions mapping to `(a00, a01, a10, a11)`.

Run their focused repository gate with:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest tests/test_tasks_physics.py -q -p no:cacheprovider
```

The specs implement only algebraic audits of a **supplied** vector:

- branch invariants: `norm2 = sum(abs(ai)**2)`, normalized determinant magnitude,
  and concurrence, with finite/nonzero validation and scale/local-phase checks;
- projected-sector audit: four distinct ordered indices map to
  `(a00, a01, a10, a11)` and return full norm, sector success, leakage, and
  conditional concurrence, rejecting invalid, non-finite, or zero vectors/sectors.

They presently exercise only O2/O3 and selected/complement bookkeeping. They may
verify supplied-vector accounting and model-bound conditional entanglement, but
they do **not** satisfy O4 physical closure and cannot certify physical amplitude
or channel completeness. That claim requires a source-grounded amplitude
enumerator, explicit included/excluded-channel manifest, all final sectors
through a controlled cutoff, and a receipt showing selected probability plus
declared leakage exhausts the full state within tolerance.

### Lane 1 readiness: BLOCKED before a physical closure calculation

No physical fourth-order closure run is authorized by the current vector tasks.
Before execution, primary-source derivation and technical review must populate
and approve this canonical manifest; the blanks are intentional and no values or
model choices are implied here.

```yaml
schema: qcr.amplitude-closure-manifest/v1
source:
  primary_source_versions_and_hashes: []
model:
  hamiltonian_or_action_terms: []
  field_and_species_choice: null
  initial_state: null
  basis_and_final_sectors: []
  included_channels: []
  excluded_channels_and_justification: []
perturbation:
  convention_and_order: null
evolution:
  evolution_method_or_integrator: null
  projection_definition: null
  cutoff_sequence_and_convergence_rule: null
oracles:
  O1_dimension_and_validity_predicate: null
  O2_separability_predicate: null
  O3_local_phase_gauge_predicate: null
  O4_trace_closure_predicate: null
  O5_factorization_predicate: null
  O6_null_and_asymptotic_predicate: null
  explicit_tolerances: {}
outputs:
  amplitude_tables: null
  full_and_projected_density_matrices: null
  leakage_and_success_records: null
  convergence_records: null
  receipt_schema_and_hashes: null
```

The lane remains `BLOCKED` until every field is source-derived, the declared
sectors/channels are reviewable, and the O1--O6 predicates and tolerances can be
run deterministically. A populated manifest is a prerequisite, not a conclusion.

## Ranked falsifiable lanes

| Rank and lane | Minimum model | Required artifact | Falsification criterion | Stop criterion |
|---|---|---|---|---|
| 1. Fourth-order amplitude closure | Finite 1-D modes; two branches/object; `N=1`, then smallest `N=2`; prescribed classical potential; same/distinct fields and optional barrier. | Basis/Hamiltonian manifest, order-by-order amplitude tables, full and projected states, leakage/success, determinant/negativity, convergence plot, machine-readable record. | In the implemented assumptions, falsify AH if complete converged evolution cancels the projected term and gives zero invariant to tolerance; falsify matched factorization if a non-postselected invariant survives all amplitudes and unitarity checks; falsify cross-talk diagnosis if it survives distinct fields with zero cross propagator. | Stop at any unresolved non-unitarity, cutoff nonconvergence, undeclared channel, or projection without leakage accounting. |
| 2. Scaling-manifold identifiability | QG-EFT, CG+QFT-AH, and CM-local/noise surfaces over bounded `(M,t,d,Δx,R,m_c)` with EM, decoherence, geometry, and readout nuisance. | Versioned parameter schema, raw sweep, sensitivity/Fisher matrix, blinded recovery coverage, failure atlas. | Reject only a preregistered joint prediction surface after nuisance marginalization. | Stop if the nuisance-marginalized surface is rank-deficient or required lever arms violate approximation domains. |
| 3. Species/barrier/binding separator | Green-function or tight-binding propagation; same/distinct fields, barrier, and binding-gap switches; unchanged mass geometry. | Propagator norm, AH-like contribution, gravitational phase, leakage, and suppression ratios. | Reject cross-talk if its term does not track/vanish with the cross propagator; reject a pure leading-gravity account if the invariant tracks permeability at fixed geometry; test Tang suppression only in its stated regime. | Stop if a switch changes mass geometry or another quantum channel cannot be bounded independently. |
| 4. Witness and nuisance robustness | Four-dimensional branch density matrix with calibrated local noise, loss, and readout; map to Bose witness and Yant--Blencowe visibility. | Witness map, adversarial nuisance suite, confidence evaluator, robustness margin. | Reject an analysis if an in-bounds nuisance produces its acceptance statistic from a separable state or its confidence set contains PPT states. | Stop a visibility-only protocol unless a validated state model makes visibility an entanglement monotone over the allowed nuisance set. |
| 5. Yant--Blencowe QFT-to-NR regression | Truncated 1-D harmonic basis for the paper's weakly relativistic coherent-state and branch-action calculation. | Cutoff convergence, corrected crossing times, variance/visibility curves, mixed-action invariant, NR comparison. | Reject the implementation if it fails NR convergence, corrected retiming, physical probability/visibility bounds, or the paper-regime sign/order regression. | Stop if cutoff or validity-window convergence is absent; it is a model regression, not experiment design. |
| 6. Classical-channel force--noise boundary | Two coupled Gaussian oscillators; Kafri master equation, noise matrix, covariance evolution, and PPT test. | Coupling/noise phase diagram, heating/decoherence prediction, positivity/PPT residuals. | Reject a specified CM-local channel if it entangles separable Gaussian inputs at its claimed noise point or violates complete positivity. | Stop before generalizing from this measurement-feedback realization to all classical gravity; an experimental exclusion also needs independent bounds on noise and hidden quantum channels. |

### Lane 2 parameter-schema readiness: BLOCKED

The symbols used by Lane 2 have fixed dimensional meanings, while each model must
declare its precise geometric convention:

| Symbol | Unit | Required semantic |
|---|---:|---|
| `M` | kg | Total mass of the test object used by the model. |
| `t` | s | Interaction/evolution duration under the stated Hamiltonian or approximation. |
| `d` | m | Declared inter-object or branch-reference separation used in the model. |
| `Δx` | m | Declared branch displacement. |
| `R` | m | Object radius or declared density-profile length scale. |
| `m_c` | kg | Constituent-mass parameter where a constituent model uses one; not silently interchangeable with `M`. |

Before a sweep, the following versioned schema must be populated from primary
sources and reviewed. It deliberately supplies no numeric range, prior, or
sampling choice:

```yaml
schema: qcr.scaling-manifold-parameters/v1
model_id: null
primary_source_versions_and_hashes: []
parameters:
  M: {unit: kg, semantic: null, bounds: null, prior: null}
  t: {unit: s, semantic: null, bounds: null, prior: null}
  d: {unit: m, semantic: null, bounds: null, prior: null}
  delta_x: {unit: m, semantic: null, bounds: null, prior: null}
  R: {unit: m, semantic: null, bounds: null, prior: null}
  m_c: {unit: kg, semantic: null, bounds: null, prior: null}
sampling_plan: null
nuisance_covariance: null
validity_predicates: []
observable_definition: null
falsification_threshold: null
```

Lane 2 remains `BLOCKED` until this schema records model-specific bounds, priors,
sampling plan, nuisance covariance, validity predicates, observable definition,
and source hashes. No identifiability conclusion is permitted before then.

**Binding expansion stop:** do not enter ultraviolet/Planck-length models until at
least one low-energy model pair has a complete forward model, identifiable
observable after nuisance treatment, deterministic oracle, and an explicit control
that breaks its main degeneracy.

## Existing-tool routing and exclusions

| Surface | QCR role | Explicit exclusion |
|---|---|---|
| Physics `TaskSpec` + curator | Candidate code plus hidden deterministic invariants and admission checks. | Not a physical completeness certificate or theory selector. |
| Local-model gateway | Existing task execution/model route. | No new endpoint, service, or invented model receipt. |
| Forum | Ledger-only `external:qcr-local-model` campaign/status and receipt pointers. | External `done` is harness-reported, not Forum-verified; no model call is required. |
| Mneme | Source-bound facts, provenance/drift, portable deterministic keyword recall. | Vector/hybrid recall is not independently reproducible without the same embedder. |
| Crucible | Recompute/classify `MATCH`, `DRIFT`, or fail-closed `UNVERIFIABLE`; seal and recheck measurements. | No source re-certification merely from Mneme export; rows without a replay descriptor are `not replayable`. |
| Science bench | Separately gathered claim/measurement evidence intake. | Not a substitute for deterministic code-oracle results or literature truth. |
| Conjecture Forge + Lean | Bounded linear-natural-number side lemmas in the existing `omega` grammar. | Not a Hilbert-space/complex-amplitude theorem generator. |
| Tension ledger | Compare two sourced estimates of the same quantity. | Never a quantum-versus-classical theory score. |

Models may propose implementations; deterministic oracles and Crucible classify
receipts. The dry run must retain exact commits, commands/results, endpoint state
if present, receipt hashes, and all three claim-state fields. A missing local
endpoint blocks model execution but does not invalidate deterministic oracle runs.

## Evidence ledger

Evidence grades describe support for the stated source/model, not settlement of
the overall question.

| Source | Evidence grade and use |
|---|---|
| [Bose et al., 1707.06050](https://arxiv.org/abs/1707.06050) | High, peer-reviewed primary theory: stated BMV protocol, witness, phase, and nuisance assumptions. |
| [Marletto--Vedral, 1707.06036](https://arxiv.org/abs/1707.06036) | High, peer-reviewed primary framework within local-only-mediator premises. |
| [Aziz--Howl, 2510.19714](https://arxiv.org/abs/2510.19714) | High that the peer-reviewed calculation/claim was made; **disputed** for amplitude interpretation/completeness. |
| [Yant--Blencowe, 2503.20855](https://arxiv.org/abs/2503.20855) | Moderate, model-specific primary preprint and thought experiment; regression target only. |
| [Quantum Gravity Phenomenology Roadmap, 2312.00409](https://arxiv.org/abs/2312.00409) | Methodological guidance for explicit models, systematics, and reusable simulations; not direct BMV evidence. |
| [Kafri--Taylor--Milburn, 1401.0946](https://arxiv.org/abs/1401.0946) | High, peer-reviewed measurement-feedback classical-channel realization; not universal classical-gravity coverage. |
| [Gundhi--Infantino--Bassi, 2604.19696](https://arxiv.org/abs/2604.19696) | Current direct technical critique, preprint and **disputed**, for complete-amplitude/factorization claims. |
| [Tang et al., 2512.13675](https://arxiv.org/abs/2512.13675) | Current binding/localization analysis, preprint and **disputed**; test only within stated approximation. |
| [Vidal--Iyer, 2607.03429](https://arxiv.org/abs/2607.03429) | Current direct technical analysis, preprint and **disputed**, for same-field cross-propagation, leakage, and barrier controls. |

The operative first result is therefore a complete, trace-aware amplitude-closure
calculation with same/distinct-field and full/projected-sector switches--not a
benchmark based on a disputed formula and not a claim that quantum gravity is
solved.
