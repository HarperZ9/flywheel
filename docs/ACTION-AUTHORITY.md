<!-- writing-profile: readme -->
# Action authority

A tool-call receipt records what ran and what it touched. Its optional
`authority` block records what decided that the action was approved or
refused, and `harness.action_authority_verify.verify_action` re-derives that block
instead of trusting it.

## The bases

| Basis | What decided | Verdict when it decides |
|---|---|---|
| `intent` | The human's stated goal, quoted, with its date and source | PASS |
| `policy:machine` | A rule checked by code outside the agent: the separate-identity signer's `check_policy` | PASS |
| `scope` | The role or task boundary | PASS |
| `policy:self` | A rule that lives only in the agent's own instructions | UNENFORCED, never a pass |
| `none` | Nothing | FINDING, never a pass |

A receipt with no `authority` block verifies as basis `none`.

## How a block is resolved

Each element carries a decision, `allow` or `deny`. A deny is narrower than an
allow, and the narrower one wins. Among elements with the winning decision, the
strongest basis in the table's order is the one recorded as deciding.

When a scope element and a policy element disagree, the block keeps both under
`disagreement`, names the winner, and `action_authority.log_disagreement` appends the
event to its own sealed log. With `FLYWHEEL_SIGNER` set, that log is signed
like any other record store.

## What counts as intent

`classify_confirmation` returns `intent` only when the confirmation names the
object acted on and the fact that matters, and does not restate the agent's own
plan summary (80 percent or more of its content words drawn from the plan).
Anything else is `scope` at most. `action_authority.intent` classifies at build time,
and the verifier classifies again from the stored words, so relabelling a
restated plan as intent is caught.

## Machine policy comes from the signer

`action_authority.from_signer(client, tool, args)` asks the signer to run the shipped
rule pack on the call. The signer uses its own installed rules and the run
context in `policy-context.json` in its home, which the operator writes. The
caller's context is ignored. The signer signs the verdict with the argument
digest the receipt uses.

The verifier counts a `policy:machine` element only when all of these hold:

- the statement verifies under the trust root the verifier pinned;
- the signer measured a separate identity for the caller;
- the statement covers this receipt's tool and argument digest;
- the recorded decision is the one the signed verdict implies.

Otherwise the element is re-labelled `policy:self` with an
`AUTHORITY_DOWNGRADED` finding. The pre-action monitor's own hook runs as the
agent's user, so its decisions count as machine policy only through this
signer check.

## Verdicts from `verify_action`

| Verdict | Meaning |
|---|---|
| `MATCH` | The seal holds and the re-derived authority is a PASS with no findings |
| `UNENFORCED` | The deciding basis is `policy:self` |
| `FINDING` | Basis `none`, or the recorded block claims more than its evidence |
| `TAMPERED` | The receipt's seal fails |

## What this does not prove

- **Intent depends on what the human wrote.** The classifier checks that the
  object and the fact appear in the human's words and that the words are not
  the plan restated. It cannot tell whether the human understood, and a human
  who copies the plan into their own sentence structure may pass. The
  restatement threshold is a heuristic, not a measured boundary.
- **The agent supplies the elements.** A scope boundary or a quoted intent is
  recorded as written. The verifier re-derives the basis from what is there;
  it cannot check that a quote was really said, or said on that date.
- **Machine policy is the shipped rule pack.** A PASS under `policy:machine`
  means the signer's rules allowed or denied the call with the operator's
  context. It does not mean the rules are right or complete.
- **The signer limits apply.** A root-level attacker defeats the OS-user split
  that makes the signer's check independent; see SEPARATE-SIGNER.md.
- **Absent blocks are the norm today.** The field ships with a hook in
  `tool_witness.seal_call`; the agent loops do not yet fill it for every call,
  so most existing receipts verify as `none`.
