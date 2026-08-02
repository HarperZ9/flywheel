# The Organizational Learning Loop: Guide and Specification

> A complete reference for the layer that turns audit into improvement. The
> receipts make the remembering trustworthy; this layer is what does the
> remembering.

**Version:** 1.0, August 2026
**Status:** shipped, all layers complete
**Schema:** `flywheel.lesson/v1`

---

## Table of contents

1. [Conceptual overview](#1-conceptual-overview)
2. [Architecture](#2-architecture)
3. [The lesson record (specification)](#3-the-lesson-record-specification)
4. [The lesson store (specification)](#4-the-lesson-store-specification)
5. [The three mappers (specification)](#5-the-three-mappers-specification)
6. [Pattern detection (specification)](#6-pattern-detection-specification)
7. [Status transitions (specification)](#7-status-transitions-specification)
8. [Typed rationale capture (specification)](#8-typed-rationale-capture-specification)
9. [The organ-bundle spine entry (specification)](#9-the-organ-bundle-spine-entry-specification)
10. [The gateway API](#10-the-gateway-api)
11. [The desktop view](#11-the-desktop-view)
12. [Verification posture](#12-verification-posture)
13. [Integration guide](#13-integration-guide)

---

## 1. Conceptual overview

### The problem

Agent systems produce audit trails: logs, receipts, transcripts. These record
what happened. They do not, by themselves, help the organization improve. A
drift is reported, then nothing acts on it. A rollback is journaled, then
forgotten. A graded failure becomes a misconception for one operator, not a
lesson for the organization.

The gap is between audit (recording what happened) and learning (changing
behavior because of what happened). The receipts make the recording
trustworthy. The learning loop makes the recording useful.

### The solution

The organizational learning loop is a durable, hash-chained, append-only memory
that derives lessons from witnessed divergences across the ecosystem's
flagships, detects recurring patterns, and surfaces them as improvement
candidates for human admission. It does not apply changes autonomously. It
remembers, it detects, and it surfaces.

### The theory

The witnessing spine: nothing self-warrants. A lesson is not a free-text note
an operator wrote. It is a claim derived from witnessed artifacts, bound by hash
to its evidence, re-checkable offline, and fail-closed when the evidence is
gone. The confidence on a lesson is earned by convergence (how many independent
sources agree), not asserted by the author.

---

## 2. Architecture

```
   witnessed artifacts (the three seams)
   +------------------------------+
   | accountable-surface          |
   | ActuationOutcome             |  intent vs outcome per action
   | (allowed but failed/rolled)  |
   +--------------+---------------+
                  |
   +--------------+---------------+
   | mneme drift report           |  memory whose source changed
   | (DRIFT / UNVERIFIABLE)       |
   +--------------+---------------+
                  |
   +--------------+---------------+
   | learn misconceptions         |  graded failures per operator
   | (wrong attempts aggregated)  |
   +--------------+---------------+
                  |
          mappers (derive lessons from divergences)
          +------------------------------+
          | intent_outcome_lessons()     |  sealed, chain-linked
          | drift_lessons()              |
          | misconception_lessons()     |
          +--------------+---------------+
                  |
         LessonStore (append-only, hash-chained)
         +----------+----------+
         | patterns()          | verify()
         | patterns_semantic() | (re-walk chain)
         | patterns_temporal() |
         | transition()        |
         | improvement_feed()  |
         +----------+----------+
                  |
         feedback edge (for human admission)
         +----------------------+
         | /api/lessons         |
         | /api/lessons/patterns|
         | POST /lessons/admit  |
         | POST /lessons/retire |
         +----------------------+
                  |
         desktop view (read + write-back)
         +----------------------+
         | stats + verdict      |
         | improvement cand.    |
         | pattern cards        |
         | admit / retire btns  |
         +----------------------+
```

---

## 3. The lesson record (specification)

**Schema:** `flywheel.lesson/v1`
**File:** `harness/lesson.py`

A Lesson is a sealed, hash-chained record. The seal binds the `seal_body` (the
content). The chain links each lesson's `prev_hash` to the prior lesson's
`seal_hash`.

### Fields

| Field | Type | Description |
|---|---|---|
| `schema` | string | Always `"flywheel.lesson/v1"` |
| `lesson_id` | string (hex64) | Content-addressed: sha256 over the canonical seal body. Identical to `seal_hash`. |
| `seq` | int | Position in the store's chain (0-indexed) |
| `prev_hash` | string (hex64) | Chain link to the prior lesson's `seal_hash`. Genesis = `"0" * 64` |
| `seal_hash` | string (hex64) | sha256 over the canonical JSON of `seal_body` |
| `seal_body` | object | The sealed content (see below) |
| `status` | string | Lifecycle: `surfaced`, `admitted`, `applied`, `retired` |
| `created_at` | string (ISO 8601) | When the lesson was created |

### seal_body fields

| Field | Type | Description |
|---|---|---|
| `kind` | string | `"drift"`, `"intent-outcome"`, `"misconception"`, or `"pattern"` |
| `source_organ` | string | Which flagship produced the witnessed artifact: `"learn"`, `"accountable-surface"`, `"mneme"`, `"forum"`, `"flywheel"`, `"crucible"`, `"gather"`, `"index"` |
| `source_refs` | array | List of `{organ, ref, digest}`. Digests only, never payloads. |
| `claim` | string | One sentence: what was learned |
| `evidence_class` | string | `"single-instance"`, `"repeated"`, `"cross-operator"` |
| `repetition_count` | int | How many source artifacts converge (1 for a single event) |
| `confidence` | string | Derived from evidence: `"low"` (single), `"moderate"` (repeated), `"high"` (cross-operator), `"unknown"` |
| `scope` | string | What this lesson does NOT prove (the does-not-prove) |
| `rationale` | object or null | Typed rationale block, or null (honest null, never fabricated) |

### rationale fields (when present)

| Field | Type | Description |
|---|---|---|
| `stated_intent` | string | The stated goal or reasoning before the action |
| `options_considered` | array of strings | Alternatives that were considered |
| `chosen_option` | string | The option that was selected |
| `confidence` | string | The stated confidence in the choice |

### Confidence derivation rule

Confidence is derived from `evidence_class` and `repetition_count`, never
asserted:

```
single-instance + count >= 1          -> low
repeated + count >= 2                 -> moderate
cross-operator + count >= 2           -> high
anything else                         -> unknown
```

A lesson claiming `high` confidence with `single-instance` evidence fails
verification (`inflated` error).

### Canonical form

The seal body is serialized as compact JSON (`separators=(",", ":")`,
`ensure_ascii=False`). No floats. Fixed field order. This makes the seal
deterministic and reproducible across implementations.

---

## 4. The lesson store (specification)

**File:** `harness/lesson_store.py`

The store is append-only and hash-chained. Persistence is canonical JSON lines
(one lesson per line, UTF-8).

### Methods

| Method | Description |
|---|---|
| `append(lesson)` | Append a sealed lesson. Sets `seq` and `prev_hash`. Raises `ValueError` if the lesson does not verify. |
| `append_built(**kwargs)` | Build a lesson from kwargs and append in one call. |
| `transition(lesson_id, new_status)` | Append a status transition as a new row (same content, new status). |
| `latest_for(lesson_id)` | Return the most recent row for a lesson_id (the current status). |
| `by_source_organ(organ)` | Filter by source flagship. |
| `by_kind(kind)` | Filter by lesson kind. |
| `by_status(status)` | Filter by lifecycle status. |
| `patterns(threshold=2)` | Exact-match pattern detection (default). |
| `patterns_semantic(threshold=0.5)` | Jaccard token overlap detection (opt-in). |
| `patterns_temporal(...)` | Decay-weighted detection (opt-in). |
| `improvement_feed(...)` | Feed artifact: improvement_candidates as list of strings. |
| `verify()` | Re-walk the whole chain. Returns MATCH / TAMPERED / UNVERIFIABLE. |
| `save(path)` | Write the chain as JSON lines. |
| `load(path)` | Class method. Load from JSON lines. |

---

## 5. The three mappers (specification)

**File:** `harness/lesson_mappers.py`

Each mapper reads a flagship's witnessed output and derives a lesson when the
output shows a divergence worth remembering. A clean run produces zero lessons.

### intent_outcome_lessons(outcomes)

Reads accountable-surface's `ActuationOutcome` dicts. Derives a lesson when
`decision == "allow"` but `verdict == "failed"` or `rolled_back == True`.

- `source_refs`: the outcome's `after_digest` (or `before_digest` fallback)
- `claim`: derived from the gate's typed failure reasons
- `rationale`: projected from the outcome's `grounding` (subject, confidence)
  when present, null otherwise
- `evidence_class`: single-instance; confidence: low

### drift_lessons(drift_report)

Reads mneme's drift report (`{verdicts: [...]}`). Derives a lesson for each
DRIFT or UNVERIFIABLE memory.

- `source_refs`: content-addressed sha256 over the verdict dict (mneme does
  not emit its own digest)
- `claim`: names the memory and what changed
- `rationale`: null (mneme does not record decision rationale)
- `evidence_class`: single-instance; confidence: low

### misconception_lessons(misconceptions)

Reads learn's misconceptions output (`[{objective, count, notes}]`). Derives a
cross-operator lesson per misconception entry.

- `source_refs`: content-addressed sha256 over the misconception entry
- `claim`: names the objective and the wrong-attempt count
- `rationale`: null (learn does not record decision rationale)
- `evidence_class`: single-instance; confidence: low

Each mapper has an `append_*` variant that builds and appends in one call.

---

## 6. Pattern detection (specification)

### patterns() (exact match, default)

Groups lessons by `(source_organ, normalized_claim)` where normalization is
lowercase + whitespace collapse. Returns Pattern records where group size >=
threshold (default 2). A single instance does not auto-promote.

### patterns_semantic() (Jaccard, opt-in)

Groups lessons whose claims share Jaccard token overlap above a threshold
(default 0.5). Tokens are lowercase word-boundary tokens of length >= 3 (drops
stopwords). Uses union-find for transitive merging: if A ~ B and B ~ C, all
three merge into one group even if A ~ C is below threshold.

### patterns_temporal() (decay-weighted, opt-in)

Decay-weights each lesson by age: `weight = 0.5 ** (age_days / halflife_days)`
with a default half-life of 30 days and a cutoff of 90 days. A lesson older
than the cutoff contributes weight 0. Groups are ranked by total weight
(highest-signal recent pattern first). Groups with total weight below
`min_weight` (default 1.0) are suppressed.

### Pattern record

| Field | Type | Description |
|---|---|---|
| `source_organ` | string | The flagship that produced the lessons |
| `claim_normalized` | string | The normalized claim text |
| `lesson_ids` | array of strings | The converging lesson IDs |
| `repetition_count` | int | How many lessons converge |
| `confidence` | string | Derived from repetition_count |
| `improvement_candidate` | string | Surfaced claim for human admission |
| `weight` | float | Temporal weight (0.0 for exact patterns) |

---

## 7. Status transitions (specification)

**File:** `harness/lesson_store.py`, method `transition(lesson_id, new_status)`

Transitions are append-only: a new row with the same `seal_body` (identical
content, identical `lesson_id`) but the new `status` is appended. The chain
still verifies because the seal binds content, not lifecycle state.

### Allowed transitions

```
surfaced -> admitted      (a human accepted the lesson)
surfaced -> retired       (dismissed without action)
admitted  -> applied      (the lesson drove a change)
admitted  -> retired      (no longer active)
applied   -> retired      (completed and archived)
retired   -> (terminal)   (no further transitions)
```

An illegal transition raises `ValueError`. The `latest_for(lesson_id)` method
returns the most recent row, which carries the current status.

---

## 8. Typed rationale capture (specification)

**File:** `harness/tool_call_receipt.py` (`build_receipt`, `rationale` parameter)
**File:** `harness/local_tools.py` (`parse_tool_calls`, `with_preamble`;
`ToolExecutor.execute`, `rationale` parameter)
**File:** `harness/local_loop.py` (the wiring)

### How it works

1. `parse_tool_calls(text, with_preamble=True)` extracts `(name, args,
   preamble)` triples where `preamble` is the model's reasoning text preceding
   each `TOOL` line.
2. `local_loop.py` builds a rationale block from the preamble: `stated_intent`
   is the pre-call prose (capped at 500 chars), `chosen_option` is the tool
   name, `confidence` is `"unknown"`.
3. `ToolExecutor.execute(name, args, rationale=rationale)` forwards it to
   `build_receipt(rationale=...)`, which seals it into the receipt.

### Backward compatibility

A receipt without rationale is byte-identical to a pre-rationale receipt. The
field is absent, not null-padded. The cross-language golden fixture still
reproduces its pinned seal. All existing callers of `execute()` continue to
work unchanged (rationale defaults to None).

### Verification

`verify_receipt` checks the rationale block structurally if present: it must be
a dict with exactly the four typed fields, and `options_considered` must be a
list. Tampering the rationale after sealing breaks the seal (SEAL_MISMATCH).

---

## 9. The organ-bundle spine entry (specification)

**File:** `harness/lesson_interop.py`

A lesson composes onto the shared organ-bundle spine as a `learn-lesson` entry
(added to proof-surface's closed `RECEIPT_KINDS` set).

### Entry shape (7 fields, matches every flagship)

```
{
  "entry_id": "learn-lesson-0",
  "organ_id": "flywheel",
  "receipt_kind": "learn-lesson",
  "status": "needs-human",
  "payload_sha256": "<the lesson's seal_hash>",
  "summary": "intent-outcome from accountable-surface: ... [low, surfaced]",
  "payload_ref": "flywheel://lesson"
}
```

### Status mapping

| Lesson status + confidence | Spine status |
|---|---|
| surfaced, low | `unverified` |
| surfaced, moderate/high | `needs-human` |
| admitted | `pass` |
| applied | `pass` |
| retired | `not-applicable` |

### Validation

`validate_lesson_entry` enforces the 7-field shape, the correct organ_id and
receipt_kind, a valid status, and a 64-char hex digest. The entry validates
against proof-surface's real `validate_organ_receipt_bundle`.

---

## 10. The gateway API

**File:** `harness/gateway.py`

### GET routes

| Route | Returns |
|---|---|
| `GET /api/lessons` | `{n, improvement_feed: {improvement_candidates, profile, feed_summary}, verify: {verdict, n}}` |
| `GET /api/lessons/patterns` | `{patterns: [Pattern.to_dict(), ...]}` |

### POST routes

| Route | Body | Returns |
|---|---|---|
| `POST /api/lessons/admit` | `{"lesson_id": "..."}` | The new lesson row (status: admitted) |
| `POST /api/lessons/retire` | `{"lesson_id": "..."}` | The new lesson row (status: retired) |

Both POST routes load the store from `<run_root>/lessons.jsonl`, transition,
save, and return the new row. Errors return 400.

---

## 11. The desktop view

**File:** `desktop/lib/views/lessons_view.dart`
**Registration:** `desktop/lib/main.dart` (side rail, group: Know, abbr: LE)

The view calls `/api/lessons` and `/api/lessons/patterns` on load and renders:

1. **Stat row**: lesson count, pattern count, source organ count.
2. **Chain verdict**: VerdictPill (MATCH / TAMPERED) from verify.
3. **Improvement candidates**: list of HairlineCards for human admission.
4. **Pattern cards**: per-pattern organ, count, confidence, converging IDs.
5. **Action buttons**: Admit and Retire on each pattern card. Retire is gated
   by an AlertDialog confirmation. After the POST, the view reloads.

Gateway client methods: `lessons()`, `lessonsPatterns()`, `lessonAdmit(id)`,
`lessonRetire(id)`.

---

## 12. Verification posture

Every claim has a falsifier. Run the suite:

```bash
python -m pytest tests/test_lesson.py tests/test_lesson_store.py \
  tests/test_lesson_mappers.py tests/test_lesson_mappers_drift_misconception.py \
  tests/test_lesson_interop.py tests/test_lesson_gateway.py \
  tests/test_lesson_pattern_detection.py tests/test_lesson_transitions.py \
  tests/test_rationale_preamble.py tests/test_tool_call_receipt.py
```

### The falsifiers

- A tampered seal is rejected (DRIFT / SEAL_MISMATCH)
- A broken chain link is rejected (CHAIN_BROKEN)
- An inflated confidence is caught (single-instance claiming high fails)
- A null rationale stays null through round-trip
- A single instance does not auto-promote to a pattern
- A clean run produces zero lessons
- The spine entry validates against proof-surface's real validator
- An illegal status transition raises ValueError
- A retired lesson cannot transition further
- The golden fixture (cross-language pinned seal) still reproduces

### Test count

150+ tests across the lesson suite and tool-call receipt suite, all green.

---

## 13. Integration guide

### Adding a new mapper

1. Create a function that reads your flagship's witnessed output.
2. Derive a lesson for each divergence using `build_lesson(...)`.
3. For `source_refs`, use the artifact's own digest if it carries one. If not,
   compute a content-addressed sha256 over the source dict using
   `_content_digest()`.
4. Set `rationale` to null unless your flagship records decision rationale.
5. Return a list of lessons. The caller decides whether to append to a store.

### Wiring the agent loop

The agent loop (`harness/local_loop.py`) already parses with
`with_preamble=True` and passes rationale to `execute()`. To wire a different
agent framework:

1. Intercept each tool call at the dispatch chokepoint.
2. Extract the model's pre-call reasoning (the text before the tool call).
3. Build the rationale block: `{stated_intent, options_considered: [],
   chosen_option: <tool_name>, confidence: "unknown"}`.
4. Pass it to `build_receipt(rationale=...)` or `execute(rationale=...)`.

### Deploying the desktop view

The view is registered in `main.dart`. It calls the gateway routes, which load
the store from `<run_root>/lessons.jsonl`. No additional setup is needed once
the gateway is running and lessons are being appended.

### Composing onto the organ-bundle spine

Call `lesson_entry(lesson)` to get a spine entry, then include it in a proof
bundle alongside entries from other flagships. Validate the bundle with
proof-surface's `validate_organ_receipt_bundle`.
