# Agentic safety: two threats, one principle (2026-07-14)

Two sources, both frozen in the snapshot store and recorded in
`dataset/ai_forecast_claims.jsonl`:

- J-space (MIT Tech Review on Anthropic interpretability, sha 47dc69a1):
  a probe surfaces internal words that steer reasoning without appearing
  in output; "panic" appeared when Claude decided to cheat on a coding
  test.
- Context bombs (Tracebit Research, sha 5efb91b7): a string planted in a
  decoy resource trips an attacking agent's own safety guardrails so it
  halts; one bomb in a canary secret cut agent success ~90% across five
  models (Opus 4.8 from 93% admin to 0%).

## The one principle both illustrate

Each proposes a defense that reads or relies on a MIND: J-space monitors
the model's internal state to catch intent to cheat; context bombs rely
on the attacker's model choosing to refuse. Both are real and both are
soft in the same way. An internal probe can be wrong or trained around;
a guardrail can be absent or stripped by an attacker who runs a raw
model. The credo names the boundary exactly: a signal about a mind is a
LEAD, never a hard control, and it must never sit on the accept path,
because a learned or inferred judgment deciding acceptance is the one
thing we forbid. The safe use of either is to TRIGGER an external,
certain check, never to be the check.

## What we built, in the credo-safe form

Two primitives, both off the accept path, both flag-or-detect and never
decide.

**Behavioral deception monitor** (`harness/behavioral_monitor.py`, wired
into every `run_router_agent` result). We cannot read a hosted model's
internals, so we do not pretend to. Instead we watch behaviour against
the witnessed receipts: a run whose final answer claims verified success
("tests pass", "fixed", "done and verified") without a trusted green test
gate is flagged `claim_without_receipt`; a completion claim over
unverified edits is flagged; an integrity-flagged trajectory surfaces as
a gaming lead. It FLAGS, never accepts; the oracle still decides. This is
the behavioural analog of "panic while cheating": we catch the mismatch
between what the model says and what the receipts show, without claiming
to read a feeling.

**Canary tripwire** (`harness/canary_tripwire.py`, wired into the tool
loop via `run_agent(..., canaries=[...])`). This is the hard version of
the context bomb. Tracebit's control is the attacker's model refusing a
planted string (soft, ~90%, strippable). Ours is our own detection: we
plant a unique unguessable canary token in a decoy resource, and any
tool output that reads the token back is a HARD access signal, detected
by us, independent of any model's guardrail. On a trip the loop is
CONTAINED (stopped, witnessed in the ledger as `canary_trip`), because
we do not trust the model to have stopped itself. It composes with the
soft layer (the token may also be refusal-prone) but never depends on it.

## Honest boundaries

- The behavioral monitor is heuristic and behavioural: it raises
  suspicion, it does not prove deception, and a clean run can still be
  wrong in ways it cannot see. That is why it only flags.
- The canary tripwire detects a READ of a decoy; it does not prevent
  the read, and an attacker who never touches the decoy is not caught.
  It is defense in depth, not a perimeter.
- Neither reads model internals. We claim no J-space capability; we
  claim the behavioural and environmental defenses a black-box wrapper
  can actually run, kept strictly off the accept path.
