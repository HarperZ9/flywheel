# Introduction to learn

`learn` is a command-line study planner. You give it the objectives of a course, a
certification or a stack of notes, and record each practice attempt. It schedules reviews with
spaced repetition, builds recall prompts from your own drafts, counts the mistakes behind your
wrong answers, orders objectives by prerequisite, and combines all of it into one study plan.
A second engine handles course and certification logistics and stops at every graded step for you
to do yourself. It needs Node 20 or newer and has no dependencies.

```bash
npx -y @harperz9/learn@2.3.0 tutor plan mysession --topic "derivatives" --objectives "power-rule,chain-rule"
```

## Core concepts

- **Session.** A named unit of study (`tutor plan <id>`) with a topic and objectives. Objectives
  can be plain strings or `{id, text, requires}` objects; `requires` builds a concept map and a
  topological learning path, and an objective stays locked until its prerequisites are mastered.
- **Attempt.** One recorded practice answer (`tutor record`): objective, prompt, your answer,
  whether you were right, and optional feedback on what went wrong. Attempts are the only input
  the mastery gate ever reads.
- **Due.** The spaced-repetition view (`tutor due`). By default an SM-2-lite/Leitner ladder over
  your practice log; opt in per session to an FSRS-class per-item model (`--enable-fsrs`, grades
  0 to 4, `--use-fsrs --desired-retention 0.9`) that surfaces the item you are most likely to
  have forgotten. Either way, time is injected with `--now`, so schedules are deterministic.
- **Misconception.** An aggregation of your wrong attempts and feedback per objective, ranked by
  count, used to steer the next plan toward where you are weak.
- **Study plan.** `tutor study` composes due items, misconceptions, an interleaved practice
  order, prerequisite readiness, and the mastery verdict into one plan.
- **Mastery gate.** `tutor mastery` derives a readiness verdict per objective from your
  scored attempts, the gate's one input. Renders, schedules and predictions awaiting a score leave it as it is.
- **Receipt.** `tutor study-receipt` emits a witnessed, hash-chained record of the session.
  `tutor reverify` recomputes that record's own evidence: the chain must recompute and the
  verdict must re-derive. Failures are typed (`CHAIN_BROKEN`, `VERDICT_MISMATCH`), and a chainless
  receipt reports `UNVERIFIED`.
- **Workflow.** For the credential engine: a declarative JSON list of steps (`navigate`, `click`,
  `fill`, `waitFor`, `capture`, `submit`, `assess`, `complete`). `learn run` executes it and
  halts and waits for you at every `assess` step and at sensitive fills (credentials, payment
  details, CAPTCHA). It also halts at `submit` steps until you authorize witnessed automated
  submission, and at steps flagged `cost` or `irreversible` until you pass `--allow-cost`.

## Your first ten minutes

From a clone of the repository:

```bash
node --test              # the full suite should pass
node src/cli.mjs doctor  # every integrity line should read MATCH
```

Plan a session on something you are studying:

```bash
node src/cli.mjs tutor plan mysession --topic "derivatives" --objectives "power-rule,chain-rule"
# tutor plan mysession: 2 objective(s)
```

Record honest attempts, including a wrong one with feedback:

```bash
node src/cli.mjs tutor record mysession --objective power-rule \
  --prompt "d/dx x^3" --answer "3x^2" --correct true
node src/cli.mjs tutor record mysession --objective chain-rule \
  --prompt "d/dx sin(x^2)" --answer "cos(x^2)" --correct false --feedback "forgot inner derivative"
```

Ask for the plan:

```bash
node src/cli.mjs tutor study mysession --now 2026-06-30T00:00:00Z
# tutor study mysession: 0 due, 1 misconception(s), mastery not yet
#   order: power-rule, chain-rule
#   readiness: power-rule:unlocked, chain-rule:unlocked

node src/cli.mjs tutor misconceptions mysession
# tutor misconceptions mysession: 1 objective(s)
#   chain-rule (1x): forgot inner derivative
```

Emit a receipt and re-verify it from its own evidence:

```bash
node src/cli.mjs tutor study-receipt mysession --now 2026-06-30T00:00:00Z
# verified true, mastery not yet -> tutor/mysession.study-receipt.json
node src/cli.mjs tutor reverify mysession
# tutor reverify mysession: VERIFIED (1 receipt(s))
```

Optionally, run the credential engine against the bundled example and watch it halt at the graded
step, step 4, and wait for you:

```bash
node src/cli.mjs run examples/course.json --id run1
# run run1: halted-assess @step 4
node src/cli.mjs resume run1 --attest "completed Quiz 1 myself"
```

## Where to go next

- [HOW-IT-WORKS.md](HOW-IT-WORKS.md): the full study loop step by step, including retrieval
  practice, predict-then-observe, and self-explanation.
- [ARCHITECTURE.md](ARCHITECTURE.md): the witness/ledger/gate spine both engines are built from.
- [../USAGE.md](../USAGE.md): the complete CLI and MCP command reference.
- [ENTERPRISE-READINESS.md](ENTERPRISE-READINESS.md): using `learn` inside unattended agent
  workflows with context envelopes and action receipts.
- [smoke.md](smoke.md): an operator-run smoke test against a live LMS.
- The README's feature list covers the rest: proof-packet lessons
  (`tutor prooflesson`), self-explanation (`tutor explain`), predictions (`tutor predict` /
  `tutor score`), and the assist pillar (`learn assist`) that flags claims to verify in your own
  draft and leaves the writing to you.
