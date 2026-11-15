# V3 — decisions of record

The decisions that frame the persona drift adapter, continuing the log in
F0-DECISIONS.md, F1-DECISIONS.md, R0-DECISIONS.md, R1-DECISIONS.md,
R2-DECISIONS.md, and V2-DECISIONS.md, and recorded in the same shape the
`adr-decision` kind captures. Each is accepted unless marked otherwise.

V3 is the second verify band. It writes nothing. It ships one read-only adapter:

- `src/canon/persona_thesis.py` — the persona-as-crucible-thesis drift adapter.
  `persona_thesis` frames a `synthesized-persona-l3` record as a crucible thesis
  of two model-free, pool-derived basis claims; `thesis_payload` serializes it to
  the shape the injected engine consumes; `assess_persona` runs the injected
  crucible assessor and interprets its counts into a headline `DriftVerdict`
  (MATCH / DRIFT / UNVERIFIABLE).

## D-43 — persona drift is measured from the basis, model-free, never re-synthesized
**Status:** accepted (this build, 2026-08-29).
**Context:** a `synthesized-persona-l3` record is a synthesis claim: its text is
the faithful summary of the source memories named in `data.source_ids`, produced
by an extractor under a criterion. Judging whether the text is faithful means
re-running the synthesis, which needs the model that produced it. canon has no
model (that is mneme's L3 extractor), so it cannot verify faithfulness directly.
**Decision:** canon measures persona drift structurally, from the pool alone, on
two axes it can re-derive without a model: basis-present (every `source_id`
resolves to a record in the pool) and basis-current (no `source_id` is superseded
by a newer record in the pool). It never re-runs synthesis. A source that
vanished, or that has a newer version, means the persona rests on a basis that
changed, so it should be re-synthesized. Both axes are clock-free: presence is set
membership, supersession is the structural `temporal.supersedes` pointer, neither
reads a wall clock.
**Consequence:** the measurement is re-derivable and model-free, the same
discipline crucible holds for its verdict step. canon reports drift it can prove
from state, not a judgment it would have to guess.

## D-44 — the crucible assessor is an injected seam, not an import
**Status:** accepted (this build).
**Context:** the drift verdict engine is crucible, which lives in another repo
(`public/crucible`). canon is self-contained and stdlib-only. Importing crucible
would take a runtime dependency on another tree and break that invariant, the
same bind V2's writing gate faced with the STE linter (D-38).
**Decision:** the adapter defines the seam and the caller wires the engine, the
injection shape F1 used for the store handle (D-9) and V2 used for the checker
(D-38). canon owns three things: the `CrucibleAssessor` callable's shape (the
thesis payload in, an assessment mapping with int `match`/`drift`/`unverifiable`
counts out), the `thesis_payload` serialization, and the verdict interpretation.
The caller supplies the real engine, building crucible claims and measurements
from the payload and returning `crucible.assess(...)[0].to_dict()`.
**Consequence:** canon stays dependency-free and the adapter is provable with a
fake assessor that mirrors crucible's honesty ladder. The real engine and canon
agree on the verdict by construction, because canon reads the exact counts
`Assessment.to_dict()` emits.

## D-45 — the strict basis tolerance encodes integer-zero as 0.5
**Status:** accepted (this build).
**Context:** a deviation on either axis is an integer count of eroded sources
(missing, or superseded). canon wants any erosion to drift: zero eroded is a
match, one or more is a drift. crucible's ladder rejects a tolerance that is not
finite and positive as untrusted (UNVERIFIABLE, fail closed), so a literal zero
tolerance cannot express "no erosion allowed."
**Decision:** `BASIS_TOLERANCE = 0.5`. With crucible's margin,
`(tolerance - deviation) / tolerance`, a deviation of 0 gives margin 1.0 (MATCH)
and a deviation of 1 gives margin -1.0 (DRIFT). Because the deviation is always a
whole number, 0.5 is the exact bound "fewer than one eroded," which is integer
zero, expressed as the largest sub-integer positive value crucible will trust.
**Consequence:** the strict "no erosion" rule rides on crucible's real
positive-tolerance model with no special case. The severity of a drift does not
scale with the count; any erosion at all is a drift, which is the right signal for
a reconcile loop that must decide fast-forward against conflict.

## D-46 — a proven drift outranks an honest null in the headline
**Status:** accepted (this build).
**Context:** a persona can have one axis that is measurable and drifted and
another that is unmeasurable. The reconcile loop V4 will build wants a single
headline verdict from the two-axis thesis.
**Decision:** `assess_persona` reads crucible's counts and folds them in order:
any `drift` reads DRIFT; else any `unverifiable` reads UNVERIFIABLE (fail closed);
else MATCH. A proven drift is never softened by an honest null elsewhere. The
counts are read by direct index (`result["drift"]`, `result["unverifiable"]`,
`result["match"]`), the same fail-closed discipline V2 used for `score["hard"]`
(D-39): an assessment mapping without those keys is a wiring fault the caller
must see, not a silent MATCH.
**Consequence:** the headline never certifies a persona that has any provable
drift, and never green-lights on a malformed assessment. The full breakdown rides
along on the `DriftVerdict` for a caller that wants it.

## D-47 — an empty basis is UNVERIFIABLE, not MATCH
**Status:** accepted (this build).
**Context:** a persona may declare no `source_ids` at all. The `source_ids` list
is structurally valid empty (the validator requires a list, not a non-empty one),
so this is a constructible record, not a malformed one.
**Decision:** with no basis, there is nothing to measure. Both axes carry a
`deviation` of None, which crucible's ladder reads as UNVERIFIABLE (an unmeasured
axis is never a match). canon does not invent a zero deviation for an empty basis,
which would falsely certify a persona it cannot ground.
**Consequence:** canon never reports MATCH for a persona whose basis it cannot
check. The honest null is preserved end to end, from canon's measurement through
crucible's verdict.

## D-48 — the surface-drift-as-thesis bridge is scoped out (honest null)
**Status:** accepted (this build).
**Context:** the phase plan names "persona/render drift as a crucible thesis." V3
could also reframe V2's rendered-surface drift (`drift.py`) as a crucible thesis,
for one uniform witnessed verdict across both axes.
**Decision:** V3 ships only the persona adapter. The V3 to V4 hard edge requires
the reconcile loop's fast-forward-against-conflict decision to consume an external
witnessed verdict rather than a self-report, and that requirement bites on the
axis where drift is a judgment: persona and content faithfulness. Rendered-surface
drift is already objective in V2's `drift.py`, a sha256 equality of the region
interior, not a self-report. Reframing a byte comparison as a crucible thesis adds
no external-witness value V2 lacks.
**Consequence:** V3 is one focused module. Surface drift stays V2's byte-level
gate; persona drift is the piece that needed an external witness, and it has one.
The render-as-thesis bridge is recorded here as a deliberate scope-out, not an
omission.

## D-49 — the basis is a set: duplicate source ids are deduped
**Status:** accepted (this build, folded from the V3 audit).
**Context:** a persona's `data.source_ids` is a list, and a synthesis extractor
could name the same memory twice. The first cut counted occurrences: `["a", "a"]`
against an empty pool reported a basis-present deviation of two for one distinct
absent source, and titled the claim "all 2 source memories are present." That
inflated number is handed to crucible and sealed into the thesis, so canon would
witness a count it cannot justify.
**Decision:** the basis is a set. `persona_thesis` dedupes `source_ids`
order-preserving (`dict.fromkeys`) before it counts, so `n`, the missing count,
and the superseded count are all over distinct sources. This aligns the
measurement with D-43 (presence is set membership) and with `_pool_ids`, which
already returns a set.
**Consequence:** the deviation canon seals is the true count of distinct eroded
sources. The strict 0.5 tolerance already kept the headline from flipping on the
inflated number (any positive count drifts), so this corrects the sealed
measurement, not the verdict. A regression test pins both axes and the
all-present case.

## D-50 — the documented caller-wiring is corrected and verified out-of-suite
**Status:** accepted (this build, folded from the V3 audit).
**Context:** the seam (D-44) keeps canon from importing crucible, so the real
wiring lives only as a caller recipe in the test docstring. The first cut wrote
`assess.assess(th, by_id, clock=clock)`. But `crucible/__init__.py` binds the
name `assess` to the assess function (`from crucible.assess import ..., assess,
...`), which shadows the `crucible.assess` submodule, so the documented call
raises AttributeError. The submodule-qualified `claim.`, `thesis.`, and
`verdict.` references worked because those names are not rebound, so `assess` was
the sole shadowed reference.
**Decision:** the docstring uses crucible's top-level exports uniformly
(`from crucible import Measurement, assess, make_claim, make_thesis`), which
removes the shadowing trap at its root. The corrected wiring is verified three
ways: a line-by-line read of crucible's `claim`, `thesis`, `verdict`, and
`assess` sources; the V3 audit's independent end-to-end run; and an out-of-suite
execution of the literal wiring against crucible 1.2.0 in this build, which
reproduced MATCH (all present), DRIFT (a missing or superseded source), and
UNVERIFIABLE (an empty basis), the exact counts canon's fake ladder yields.
**Consequence:** the published caller-recipe runs. canon's suite still does not
import crucible, so the cross-engine agreement (D-44) is not gated in-suite: it is
an honest null, discharged by the out-of-suite receipt above and re-runnable by
anyone with both trees present. canon's own side (measurement, payload, count
fold) stays proven by the injected fake.

## Recorded audit
Three adversarial lenses (contract faithfulness, drift-measurement correctness,
fail-closed and totality discipline) plus a synthesizer read the V3 adapter
against the real crucible contract. Verdict: fix-then-ship. Two findings were
confirmed and folded in TDD-style: the documented wiring's AttributeError (D-50)
and the duplicate-source double-count (D-49, a RED test written first, watched
fail, then fixed). One finding was rejected: bare-id source matching reads as
consistent with mneme's memory-resolution convention, and the proposed
cross-scope id-collision exploit needs an unrealizable collision, so no
scope-qualified key was added.
