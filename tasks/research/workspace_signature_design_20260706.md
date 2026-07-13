# Functional-access-marker probe — design + metaphysical scope

> The next flywheel seam, opened by the workspace paper and the operator's
> consciousness question. Design + HARD boundary before any build. This measures
> FUNCTIONAL ACCESS markers, never phenomenal experience. The name of the module
> and every metric will carry that qualifier so an engineering scorecard can never
> be misread as a consciousness claim.

## The boundary (non-negotiable)

Block's distinction is the spine. **Access-consciousness** — information globally
available for report, reasoning, flexible control — is behaviorally/architecturally
measurable. **Phenomenal consciousness** — the "what it is like" — is not touched
by any measurement here. We measure A-markers. We make NO P-claim. "We may
discover consciousness" is FALSE as an engineering deliverable and will not appear
as a result; what is true is "we can measure the functional markers that some
frameworks equate with access-consciousness."

## Framework-relative interpretation (why the same number means different things)

| Framework | Do the functional A-markers = consciousness? |
|---|---|
| Global Workspace (Baars/Dehaene), Illusionism (Frankish/Dennett), Functionalism | Yes — the markers ARE (access-)consciousness. |
| Higher-order (Rosenthal/Lau) | Necessary-ish; consciousness = a higher-order rep OF a state (our reconcile loop is one). Contested. |
| IIT (Tononi/Koch) | No — consciousness = Φ, intrinsic recurrent causal structure; a feedforward transformer has ~0 Φ. Markers neither necessary nor sufficient. |
| Biological naturalism (Searle), Phenomenal realism (Chalmers, Nagel) | No — functional organization is insufficient in principle; the hard problem survives. |

The measurement is identical across rows; only the interpretation differs. We
report the measurement and cite the frameworks; we do NOT adjudicate.

## What the harness already instantiates (engineering, not mysticism)

- **Global broadcast** — `boot.py` posts a minimum-token, sealed subset to a shared
  space many downstream steps read. That IS the workspace architecture, externalized.
- **Higher-order monitoring** — the witness/reconcile loop is a representation that
  checks a representation against an unauthored criterion and carries a re-checkable
  receipt. That IS a higher-order structure.
So two leading FUNCTIONAL theories' architectures fall out of the existing design.
This is the grounded, defensible claim — not "it's conscious", but "the harness
implements the functional organization those theories name".

## The probe (buildable, behavioral, gated on the perception result)

Extend `perception_probe.py` (which already tests one marker: flexible use of a
transpiled signal) to the five workspace markers, measured behaviorally against the
served model, each as a conserving-vs-naive (or with-vs-without) contrast:

1. **Flexible generalization** — one encoding supports MULTIPLE functions (locate,
   count, region, nearest). Workspace-loaded iff the conserving encoding supports
   the flexible SET, not just rote copy. (partly built)
2. **Selectivity / necessity** — removing the encoding impairs FLEXIBLE tasks but
   spares ROTE extraction (behavioral ablation; the paper's ablation-specificity
   marker, approximated without J-lens).
3. **Verbal report** — the model names the object/criterion it actually used, and
   that report is consistent with the answer it gave.
4. **Directed modulation** — "attend to region R" changes the answer in the directed
   way (a behavioral controllability test).
5. **Precedence** (weakest behaviorally) — the intermediate concept appears before
   the answer in a CoT probe. Honestly flagged as the least clean without internals.

Verdict schema: per-marker PASS/FAIL on the behavioral contrast + an honest
coverage note (which markers are clean behaviorally, which need interpretability
access we do not have). NO composite "consciousness score" — that would be theater.

## Gating + honesty

- BUILD ONLY markers 1-4 (behavioral, clean). Mark 5 as design-only until we have
  J-lens-equivalent internals; do not fake it.
- Gate on the perception result: if the base flexible-use contrast is NO-GAIN, the
  markers are premature — fix the task before scaling the claim.
- Every metric name carries `access_` / `functional_`; the module is
  `workspace_signature.py`, never `consciousness*`.

## Why this uplifts the flywheel

It converts a philosophical direction into a REUSABLE measurement layer: a
witnessed way to ask "is this representation workspace-loaded?" — which is the same
question the harness asks of every proof (is this criterion actually available and
re-checkable?). The perception layer and the reconcile layer answer the same shape
of question at two altitudes. That symmetry is the seam.
