# How it works

`learn` runs a study loop over the operator's own practice log. This page walks that loop one
step at a time: **plan**, **due**, **retrieval**, **predict-then-observe**, **self-explanation**,
**misconceptions**, **mastery-gate**, **witnessed receipt**. Each step reads what the operator
recorded and computes from it. Answers to a certified assessment stay with the operator.

## The loop, step by step

```
   ┌───────────────────────────────────────────────────────────────────┐
   │  1. plan       : declare a topic and its objectives                │
   │  2. due        : which objectives are overdue for review           │
   │  3. retrieval  : recall prompts from the operator's OWN material   │
   │  4. predict -> observe  : commit a prediction BEFORE seeing a render│
   │  5. self-explain : the operator's OWN explanation, graded honestly │
   │  6. misconceptions : what the operator keeps getting wrong          │
   │  7. mastery-gate : ready only if the operator's own attempts prove it│
   │  8. witnessed receipt : a hash-chained record of exactly this       │
   └───────────────────────────────────────────────────────────────────┘
```

### 1. Plan

```bash
node src/cli.mjs tutor plan mysession --topic "derivatives" --objectives "power-rule,chain-rule"
```

A session is a topic and a list of objectives, both named by the operator. `tutor/tutor.mjs`'s `newSession` creates
an empty practice log (`attempts: []`) tied to those objectives.

### 2. Due

```bash
node src/cli.mjs tutor due mysession --now 2026-06-30T00:00:00Z
```

`tutor/schedule.mjs` runs an SM-2-lite / Leitner ladder over the session's own recorded attempts.
A fresh objective is due at once; one answered right several times in a row is due further
out. `due()` is a pure function of the practice log and an explicit `now`, so the same log and
the same `--now` always give the same schedule.

### 3. Retrieval

`tutor/retrieval.mjs`'s `clozePrompts` takes claims the operator's own draft already asserted
(via `assist()`, which cites the draft's own claims) and blanks out a salient term, so the operator has
to recall it from memory. Every prompt carries its `source`, so the operator can check the
answer after attempting recall. `interleave()` mixes objectives into a seeded, deterministic
study order, the interleaving-practice technique.

### 4. Predict, then observe

```bash
node src/cli.mjs tutor predict mysession --objective power-rule --prompt "what will this look like?" --prediction "a straight line"
```

`tutor/predict.mjs`'s `recordPrediction` stores the operator's own prediction as a **pending**
attempt (`correct: null`), before they see any rendered aid. After the operator compares
the prediction with what they observed, `scorePrediction` records the verdict. Until then
`recordAttempt` counts the `null` as an open attempt.

### 5. Self-explanation

`tutor/explain.mjs` wraps the operator's own explanation of a concept into a crucible thesis
(reusing the same `assist()` pillar as retrieval) and buckets the returned MATCH/DRIFT/UNVERIFIABLE
verdicts into grounded/shaky/unverifiable. This checks the operator's explanation against sources
they themselves cited, and the wording of the explanation stays the operator's.

### 6. Misconceptions

```bash
node src/cli.mjs tutor misconceptions mysession
```

`tutor/misconception.mjs` aggregates the operator's own wrong attempts, ranked by count, so the
next study session spends time on the objectives where the operator's own record shows the
most misses.

### 7. Mastery-gate

```bash
node src/cli.mjs tutor mastery mysession
```

`tutor/tutor.mjs`'s `mastery()` reports `ready` per objective and overall, computed from
`session.attempts` only: at least `minAttempts` recorded attempts and at least `threshold`
accuracy. Scored attempts are the only input, so a render (`recordVisualization`) or a pending
prediction leaves the verdict where it was; `doctor.mjs` re-checks that rule on every run.

### 8. Witnessed receipt

```bash
node src/cli.mjs tutor study mysession --now 2026-06-30T00:00:00Z
node src/cli.mjs tutor study-receipt mysession --now 2026-06-30T00:00:00Z
```

`tutor/study.mjs` composes steps 2 to 7 into one `studyPlan`, and `studyReceipt` hash-chains the
underlying practice log (via the same `Ledger` the credential engine uses) into a tamper-evident
record. The receipt shows the study happened as recorded. It carries what `studyPlan` computed
and the operator's own recorded practice.

### 9. Receipt re-verification

```bash
node src/cli.mjs tutor receipt mysession
node src/cli.mjs tutor reverify mysession
```

`tutor/reverify.mjs` recomputes an emitted receipt's own evidence instead of trusting its stored
booleans. The hash chain over the witnessed practice entries must recompute (a break is typed
`CHAIN_BROKEN` with the offending entry's seq and hash) and the stored mastery verdict must
re-derive from the recorded attempts under the recorded policy (a divergence is typed
`VERDICT_MISMATCH`). A receipt without chain evidence is `UNVERIFIED`, never verified. A clean
re-check exits 0 with a witnessed summary digest; any failure exits 1.

---

## Fail-closed, the same way the rest of Project Telos is

When a render fails (`LEARN_TELOS_CMD` unset, the engine offline, a bad output),
`interop/telos.mjs` returns `UNVERIFIABLE` at once, tagged `provenance: "aid"`. Aid renders,
verified or otherwise, live in their own channel, apart from the graded receipt channels
(`humanAssessments`, `manualSubmissions`, `witnessedAutoSubmissions`).

The credential engine applies the same rule to course logistics: it denies an undeclared step
kind, and it halts at every `assess` step and waits for the operator before running the next
step. `learn doctor` re-derives these rules at runtime on every run.

See also: [Architecture](ARCHITECTURE.md) for the organs and modules, and
[Enterprise Readiness](ENTERPRISE-READINESS.md) for the operational contract.
