# Field-adjusted novelty audit — our harness vs. current arXiv (2026-07-06)

> Receipt-backed sweep (8 sealed gather_arxiv queries, ~45 June-2026 preprints) +
> a 19-paper deep-dive that read each abstract and adversarially tested whether
> the field already published our moves. Honest verdict first. Our novelty
> shrank; the truth of by-how-much is the deliverable.

## How much eroded: ~1.5 of 5 headline claims

| Claim | Verdict vs. current literature |
|---|---|
| **A — Proof-Addressed Memory** | **~half pre-empted.** `2605.27494 (GroundedCache)` publishes the genus: safe answer-cache reuse gated by re-checkable criteria, re-validate-on-hit, a source-version freshness gate (= our wiki DRIFT), and the USR metric. Stop pitching "criterion-gated cache with re-witness on hit" as new. **Survives:** keying on the oracle-certified FACT with PROMPT and MODEL absent, with NO learned judge in the accept path — every published cache keys on query/prompt similarity; GroundedCache's safety *depends* on it and its support gate is exactly the LLM-judge our C2 forbids. The inversion is defensible. It is now "a specific addressing scheme," not "a new kind of cache." |
| **B — Transitive Witness** | **NOT pre-empted. The defensible center of gravity.** No paper in the sweep touches the re-witnessing closure (criterion CONSERVED along a path; UNVERIFIABLE-on-ancestor-drift). `SEVerA`/`Red Queen Gödel` evolve the criterion (opposite direction); `PROV-AGENT` publishes only the *descriptive* citation DAG. B is novel strictly as the closure property, never as graph-tracking. |
| **C — Witnessed Transform** | **Now table stakes.** `SEVerA`'s FGGM (call → check against a named criterion → gate emit) is the same per-stage shape. Do not pitch C as novel. |
| **D — Flywheel economics** | **Motivation pre-empted.** `2512.21309` (~30% request recurrence) and `2504.13171` (sleep-time precompute) publish the amortization thesis. Cite them as prior art, not fresh observation. |
| **E — Verified Wiki freshness** | Partly folded into GroundedCache's version-validity gate; the sealed-node + derived-link composition survives. |

## Taxonomy: we sit OUTSIDE the survey's spanning set (not in an empty cell)

`2508.16665 (Trust but Verify)` catalogs **learned, soft-scoring reward-model
verifiers that rank decode-time candidates**. Our composition is orthogonal on
every axis: deterministic external oracle (not learned), discrete
MATCH/DRIFT/UNVERIFIABLE (not a soft score), serve-time re-checkable from a
persisted receipt (not one-shot at decode), amortizing cost (every verifier they
catalog *adds* per-query cost). The survey defines the region we deliberately sit
outside — stronger positioning than "unoccupied cell." The one axis to import:
**process-vs-outcome** (we are outcome-only; per-node re-check is how B is built).

## Mechanisms adopted from the sweep (ranked)

1. **Adversarial verifier-can-fail corpus + false-accept count as headline metric**
   (`2606.09682` AutoMegaKernel: 6,091 unsafe proposals, 0 false-accepts; `2605.27494` USR).
   Attacks the theatrical-MATCH weakness our own crucible notes flag. **Highest ROI.**
   Seeded here as the no-receipt gate; the full corpus is the next build.
2. **Process-level (per-node) re-check** (`2508.16665`) — built into transitive_witness:
   each node carries its own re-witness verdict, folded over the cone.
3. **Paraconsistent glut/gap degradation** (`2507.09751`) — built: GLUT=DRIFT (own
   claim refuted), GAP=UNVERIFIABLE (grounding unconfirmable); a descendant of a
   glut becomes a gap, not a glut, so one drift never collapses the DAG.
4. **Epoch-boundary criterion versioning** (`2606.26294`) — NOT yet built: split
   "ancestor drifted" from "criterion intentionally upgraded (re-baseline)".
5. **Region-caching via prototype bounds** (`2212.01346`) — NOT yet built: upgrade
   A from exact-fact hits to MATCH + a proven local bound over a neighborhood of
   oracle-inputs, widening flywheel hit-rate without weakening the gate.
6. Runner-up: fixed-shape reduction schedule (`2601.17768`) to pin oracle
   re-execution determinism so DRIFT means real drift, not float jitter.

## Built this pass: Transitive Witness kernel

`harness/transitive_witness.py` (+`test_transitive_witness.py`, 11). The closure:
a node is MATCH only along a fully-MATCH dependency path; an upstream DRIFT gaps
every downstream-dependent node while independents keep their verdict
(localization, proven by `dependents_of` + the sibling-holds-the-line test).
Cycles/dangling grounding → UNVERIFIABLE; no receipt → never MATCH. Honest scope:
this is the kernel. It is NOT a breakthrough until it survives a full adversarial
false-accept corpus (mechanism #1) — that is the next gate, and it is the thing
that would make B credible rather than theatrical.

## The actionable truth

The defensible center of gravity moved **from the cache (A) to the closure
property (B)** — and B is now built as a kernel where before it was only a
roadmap line. Next: (a) the adversarial false-accept corpus for B; (b) wire the
closure over real ProofEnvelope citation edges (`from_envelopes`, drafted);
(c) criterion-versioning (#4) to separate drift from intentional re-baseline.
