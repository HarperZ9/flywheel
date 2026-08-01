# The Organizational Learning Loop

> The layer above audit. Not "can I audit this decision?" but "can the
> organization get better at making decisions because the system remembers what
> worked, what failed, and why?"

## What this is

The ecosystem has always been able to record what happened: tool-call receipts
bind capability + args + output; forum's causal ledger chains cause to effect;
accountable-surface journals intent vs outcome per action; learn's graded ledger
tracks what an operator got wrong and when. Each of these stops at surfacing. A
drift is reported, then nothing acts on it. A rollback is journaled, then
forgotten. A graded failure becomes a misconception for one operator, not a
lesson for the organization.

The lesson loop is the layer that feeds forward. It derives lessons from
witnessed artifacts, stores them in a durable, hash-chained, append-only memory,
detects recurring patterns, and surfaces them as improvement candidates for
human admission. The receipts make the remembering trustworthy; this layer is
what does the remembering.

The theory is the witnessing spine: nothing self-warrants. A lesson is not a
free-text note an operator wrote; it is a claim derived from witnessed artifacts,
bound by hash to its evidence, re-checkable offline, and fail-closed when the
evidence is gone.

## The architecture

```
   witnessed artifacts (the three seams)
   ┌─────────────────────────────────────────────────────┐
   │ accountable-surface   mneme drift     learn ledger  │
   │ ActuationOutcome       drift verdict   misconceptions│
   │ (intent vs outcome)    (source drift)  (graded fail) │
   └──────────────┬──────────────┬──────────────┬─────────┘
                  │              │              │
          mappers (derive lessons from divergences)
          ┌───────┴──────────────┴──────────────┴────┐
          │ intent_outcome_lessons()  (shipped)      │
          │ drift_lessons()           (follow-up)    │
          │ misconception_lessons()   (follow-up)    │
          └──────────────────┬───────────────────────┘
                             │
                  LessonStore (append-only, hash-chained)
                  ┌──────────┴──────────┐
                  │ patterns()          │ verify()
                  │ improvement_feed()  │ (re-walk chain)
                  └──────────┬──────────┘
                             │
              feedback edge (for human admission)
              ┌──────────────┴──────────────┐
              │ /api/lessons                │
              │ /api/lessons/patterns       │
              │ improvement_candidates[]    │
              └─────────────────────────────┘
```

## The lesson record

A `Lesson` (`flywheel.lesson/v1`) is a sealed, hash-chained record. Each lesson
carries:

- **kind** : what class of witnessed event: `drift`, `intent-outcome`,
  `misconception`, `pattern`.
- **source_refs** : the witnessed artifacts this lesson derives from, as
  `{organ, ref, digest}`. Digests only, never payloads (same discipline as the
  organ-bundle spine).
- **claim** : one sentence: what was learned.
- **evidence_class** : how many artifacts converge: `single-instance`,
  `repeated`, `cross-operator`.
- **confidence** : derived from evidence, never asserted. Single-instance is
  low; repeated is moderate; cross-operator is high; uncheckable is unknown.
  This is the witnessing stamp: confidence is earned by convergence, not
  declared.
- **rationale** : an honest null by default, never fabricated. When present,
  the typed block `{stated_intent, options_considered, chosen_option,
  confidence}`.
- **status** : lifecycle: `surfaced -> admitted -> applied -> retired`.

The seal binds the seal body (the claim + its evidence refs). The chain links
each lesson's `prev_hash` to the prior lesson's `seal_hash`. A third party
re-walks the chain offline: `verify_lesson_chain` returns `MATCH` only if every
seal reproduces AND the chain links hold.

## The three source seams

| Seam | What it witnesses | Mapper status |
|---|---|---|
| accountable-surface `ActuationOutcome` | intent vs outcome per action (allowed but failed / rolled back) | **shipped** |
| mneme drift | a memory whose source changed under it | follow-up |
| learn misconceptions | graded failures aggregated per operator | follow-up |

The first mapper is proven end-to-end. It reads accountable-surface's
`ActuationOutcome`, derives a lesson when an allowed action failed or rolled
back (the intent-vs-outcome divergence), and seals it. A clean run produces zero
lessons: the absence is meaningful, not a gap.

## The feedback edge

The loop's feedback edge is `patterns()`: it groups lessons by
`(source_organ, normalized_claim)` and returns `Pattern` records where the
group size meets a threshold (default 2). A single instance does not auto-promote.
Each Pattern carries an `improvement_candidate` string in the same shape as
`telemetry.efficiency_feed`, so the learning loop and the efficiency loop feed
one admission pipeline.

The feedback edge surfaces candidates for human admission. It does not apply
changes. The `loop_ledger` contract and the workspace rule ("no production
deploy without an explicit yes") both hold.

## The honest-null rationale discipline

The "why did the agent do this?" layer requires capturing decision rationale.
Today the engine's session ledger records the conversation, and tool-call
receipts record capability + args + output, but neither carries a typed
rationale field. The lesson schema supports a rationale block, and the
intent-outcome mapper projects accountable-surface's `Grounding` into it when
present. When the grounding is absent, the rationale is `null` and stays `null`
through round-trip. A null rationale is honest, never filled with a guess.

Wiring typed rationale capture at the engine chokepoint (extending
`tool_call_receipt.py` with the optional rationale block) is a follow-up. The
lesson schema is ready for it.

## The organ-bundle spine

Lessons compose onto the shared organ-bundle spine as `learn-lesson` entries
(added to proof-surface's closed `RECEIPT_KINDS` set). The spine entry is the
7-field shape every flagship uses:

```
(entry_id, organ_id, receipt_kind, status, payload_sha256, summary, payload_ref)
```

A lesson bundle validates against proof-surface's
`validate_organ_receipt_bundle`, so a lesson composes into a cross-tool proof
bundle alongside crucible assessments, gather corpora, forum routes, index
envelopes, and learn receipts.

## What is built vs deferred

**Built (this layer):**
- The lesson record (`harness/lesson.py`): sealed, chain-linked, re-verifiable.
- The lesson store (`harness/lesson_store.py`): append-only, patterns, verify,
  persistence.
- The intent-outcome mapper (`harness/lesson_mappers.py`): reads
  accountable-surface, derives lessons from divergences.
- The spine entry (`harness/lesson_interop.py`): maps lessons to organ-bundle
  entries, validated against proof-surface.
- The gateway surface: `/api/lessons`, `/api/lessons/patterns`.
- The `learn-lesson` receipt kind in proof-surface.

**Deferred to follow-ups:**
- The drift mapper (mneme drift -> lesson).
- The misconception mapper (learn misconceptions -> cross-operator lesson).
- Typed rationale capture at the engine chokepoint.
- Sophisticated pattern detection (semantic clustering, temporal decay).
- A desktop view (`lessons_view.dart`).

## Verification

Every claim has a falsifier. Run the suite:

```bash
python -m pytest tests/test_lesson.py tests/test_lesson_store.py \
  tests/test_lesson_mappers.py tests/test_lesson_interop.py \
  tests/test_lesson_gateway.py
```

The falsifiers: a tampered seal is rejected (DRIFT); a broken chain link is
rejected (CHAIN_BROKEN); an inflated confidence is caught; a null rationale
stays null; a single instance does not auto-promote to a pattern; a clean run
produces zero lessons; the spine entry validates against proof-surface's real
validator.
