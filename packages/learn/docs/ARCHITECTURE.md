# Architecture

`learn` is two engines sharing one accountability spine. This page maps the organs, the verbs
between them, and where the integrity line actually lives in the code, not just in prose.

## The one shape underneath both engines

Every capability in `learn`, credential logistics and the teach-you loop alike, is built from the
same three primitives:

```
witness   ──  content-addressed hashing of what actually happened (sha256hex, observe)
ledger    ──  a hash-chained, tamper-evident append log (Ledger.append / .verify)
gate      ──  default-deny decision over a step (decide -> allow | deny | needs-human)
```

Nothing in `learn` records a fact without a witness, nothing accumulates state outside a ledger,
and nothing graded proceeds without passing the gate. This is the same shape the rest of Project
Telos uses: perceive, recover an invariant, check it, emit a verdict you can re-derive rather than
take on trust. Here the "artifact" is a study session or a course run, and the invariant is "did
the operator's own work satisfy the threshold," never a guess the tool supplies for them.

## The credential engine

```
workflow (declarative steps)
      │
      ▼
gate.decide(step)  ──►  deny (undeclared kind, nothing actuated)
      │                 needs-human (assess, sensitive fill, submit or cost step without a grant)
      ▼
actuate (FakeDriver | NativeDriver)
      │
      ▼
witness (before/after snapshot digest)  ──►  ledger.append
      │
      ▼
receipt (json + markdown + html: logistics vs. human assessment vs. aid visualizations)
```

- `workflow/schema.mjs`: the declarative step schema. `STEP_KINDS` is the engine's global
  allowlist; a step outside it is denied before it ever reaches a driver.
- `accountability/gate.mjs`: `decide(step, {sealedKinds, autoSubmit, allowCost})`. `assess`
  always returns `needs-human`, unconditionally. A `submit` proceeds automatically only under
  "witnessed-auto" submission, and a step flagged `cost` or `irreversible` only with `allowCost`
  (`--allow-cost` on that invocation); a submit that costs needs both. Otherwise it halts too.
  `assess` is never gated by either grant; it always halts.
- `runtime/runner.mjs`: `run`/`resume`. Walks workflow steps, asks the gate first, actuates only
  on `allow`, snapshots before/after every actuated step, and witnesses the digest into the
  ledger. A `deny` or `needs-human` decision stops the loop immediately; nothing after that point
  is actuated.
- `actuation/`: `FakeDriver` (deterministic, offline, used by every test and by `doctor`) and
  `NativeDriver` (real browser control via `native-control`, used only for the operator-run smoke
  in `docs/smoke.md`).
- `adapters/`: a `Source`-style seam (`getAdapter(name)`) so each course platform's
  "how do I read the completion certificate" logic stays isolated from the runner. Shipped:
  `generic` (config-driven) and an LMS pack (Coursera, Udemy, LinkedIn Learning, edX, Credly,
  Microsoft Learn, NonprofitReady, and a generic self-paced fallback). No adapter contains grading
  logic; they only read what already happened.
- `receipt/receipt.mjs`: folds the ledger into three structurally separate channels
  (`humanAssessments`, `manualSubmissions` / `witnessedAutoSubmissions`, `aidVisualizations`), so a
  render can never be filed as if it were graded human work.

## The tutor / learning loop

```
tutor.newSession(topic, objectives)
      │
      ▼
tutor.recordAttempt   ──  the operator's OWN answer to a practice prompt, scored true/false
      │
      ├──► schedule.due            (spaced repetition: what's due for review, most-overdue first)
      ├──► misconception.misconceptions  (ranked aggregation of the operator's own wrong attempts)
      ├──► retrieval.clozePrompts / interleave  (blanked recall prompts from the operator's OWN
      │                                          assist-extracted claims; deterministic mixed order)
      ├──► predict.recordPrediction / scorePrediction  (predict-then-observe, pending until scored)
      ├──► explain.explanationThesis / gradeExplanation  (self-explanation via crucible MATCH/DRIFT)
      └──► map.normalizeObjectives / learningPath / readiness  (prerequisite gating)
      │
      ▼
tutor.mastery(session)  ──  ready iff EVERY objective has >= minAttempts and >= threshold accuracy,
      │                     computed ONLY from session.attempts (never a render, never a pending
      │                     prediction, never a visualization)
      ▼
study.studyPlan / studyReceipt  ──  composes all of the above into one plan and one witnessed,
                                     hash-chained study record
```

- `tutor/tutor.mjs`: the session shape and the mastery-gate itself. `recordAttempt` is the only
  way an attempt enters the log, and it always coerces `correct` to a boolean (`!!correct`), so a
  `null`/pending value can never be silently read as true.
- `tutor/schedule.mjs`: an SM-2-lite / Leitner ladder over `session.attempts`. Pure function of
  the practice log and an explicit `now`; no wall clock, no hidden state.
- `tutor/misconception.mjs`: aggregates wrong attempts (`correct === false`) per objective, ranked
  by count. It surfaces nothing the operator did not already see; it never fabricates a "correct
  answer" field.
- `tutor/retrieval.mjs`: `clozePrompts` blanks a salient span out of a claim the operator's own
  `assist()` already extracted, carrying a `source` so the operator can check themselves
  afterward. `interleave` is a seeded (mulberry32), deterministic shuffle, never `Math.random`.
- `tutor/predict.mjs`: `recordPrediction` stores the operator's prediction as a pending attempt
  (`correct: null`); `scorePrediction` requires an explicit index and throws rather than silently
  no-op-ing on an already-scored or invalid attempt.
- `tutor/explain.mjs`: wraps the operator's own explanation into a crucible thesis (via
  `assist` + `toCrucibleThesis`) and buckets the returned MATCH/DRIFT/UNVERIFIABLE verdicts into
  grounded/shaky/unverifiable. It supplies no answer key; the falsification field stays for
  crucible or the operator to fill in.
- `tutor/map.mjs`: normalizes objectives (plain string or `{id, text, requires}`), computes a
  topological `learningPath`, and gates `readiness` on whether every prerequisite is itself
  mastered (reading `mastery()`'s own `ready` flag, adding no new judgment about correctness).
- `tutor/study.mjs`: the orchestrator. Composes `due`, `misconceptions`, `interleave`, `readiness`,
  and `mastery` into one `studyPlan`, and `studyReceipt` hash-chains the practice log underneath it
  into a witnessed, tamper-evident record.
- `tutor/tutorstore.mjs`: session persistence (load/save by id), so a study session survives across
  CLI invocations without a database dependency.

## The visualization bridge (aid, never graded)

```
concept  ──►  toTelosSceneSpec (pure, no I/O)  ──►  telosRender (spawns LEARN_TELOS_CMD)  ──►
      render result, always tagged provenance:"aid"
      │
      ▼
toAidLedgerEntry  ──  kind:"aid-visualization", structurally distinct from every graded-channel kind
      │
      ▼
recordVisualization(session, ...)  ──  attached to the study log, NEVER read by mastery()
```

`interop/telos.mjs` delegates rendering to an external telos engine process over
`LEARN_TELOS_CMD`. It never imports telos internals and never chooses the render profile; it asks
over a process boundary and is fail-closed: no command configured returns `UNVERIFIABLE`
immediately, never a guess dressed as a pass. Every render carries `provenance: "aid"` all the way
into the ledger and the receipt, so it can never be misread as a graded answer or a human
assessment.

## Where the integrity line actually lives in code

The rule ("no learning-aid capability may produce, hint, or auto-fill an answer to a graded
assessment; `mastery()` is a function of the operator's own practice only") is enforced at these
concrete points, each with a falsifiable test:

1. `accountability/gate.mjs`: `decide` returns `needs-human` for `assess` unconditionally; no
   flag, mode, or caller argument can move it to `allow`.
2. `runtime/runner.mjs`: a `needs-human` or `deny` decision halts the loop before any actuation for
   that step; `doctor.mjs` asserts this halts with zero driver actions.
3. `tutor/tutor.mjs`: `mastery()` reads only `session.attempts`; recording a visualization or a
   pending prediction changes `session.visualizations` or the attempt count, never the accuracy of
   an already-scored objective.
4. `tutor/predict.mjs`: a pending prediction is `correct: null`, coerced to `false` by
   `recordAttempt`'s own boolean cast; it is never silently counted as correct.
5. `receipt/receipt.mjs`: aid visualizations are filed under `aidVisualizations`, structurally
   separate from `humanAssessments`, `manualSubmissions`, and `witnessedAutoSubmissions`.
6. `doctor.mjs`: re-runs checks 1 to 5 at runtime and reports `MATCH`/`DEGRADED`, so a future change
   that weakens any of them fails loudly instead of silently.

## Peer composition

`learn` composes with `gather` (source receipts feed the assist pillar's citations), `crucible`
(measured claim evaluation powers self-explanation grading), and the `telos` engine (renders
learning aids over a process boundary). None of these are imported as internals; each is a clean
seam that defaults to absent (fail-closed) rather than a hard dependency, so `learn` stands alone
with zero external packages while still composing with the rest of Project Telos when those tools
are present.

See also: [How it works](HOW-IT-WORKS.md) for the study loop walked step by step, and
[Enterprise Readiness](ENTERPRISE-READINESS.md) for the operational contract.
