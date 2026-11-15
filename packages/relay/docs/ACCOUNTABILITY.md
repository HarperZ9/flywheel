# Accountability: a run you can re-verify

Most coding agents hand you a run that finished. relay hands you a run a stranger
can re-verify was not faked. Every relay run is a hash-chained, tamper-evident
trajectory carrying per-turn receipts, and the guarantees below are computed over
that record, offline, by anyone.

This is the accountability axis. It is orthogonal to the capability and adoption
axis, and relay does not claim to solve more tasks than the agents it is compared
to below. It claims something they do not offer: when relay says a task is done,
you can re-derive that it is, and catch it when it is not.

## What you get

| Guarantee | relay | omp | Prime Agent | Hermes | aider | Cline |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Re-derivable per-turn receipts | ✓ | · | · | · | · | · |
| Tamper-evident hash-chained ledger | ✓ | · | · | · | · | · |
| Reward-hacking accept gate (a green check is refused if the grader was edited) | ✓ | · | · | · | · | · |
| Intent and claimed-history audit | ✓ | · | · | · | · | · |
| Claim grounding (the final answer is checked against the ledger) | ✓ | · | · | · | · | · |
| Portable offline certificate, verified with zero dependencies | ✓ | · | · | · | · | · |
| Verified best-of-N (the winner is chosen by proof, not a judge) | ✓ | · | · | · | · | · |
| First-bad-edit bisection over the witnessed edit set | ✓ | · | · | · | · | · |

`✓` = shipped and covered by tests in this repo. `·` = not offered as a public
feature as of 2026-08-27, per each project's public documentation. This table is
the accountability axis only; corrections are welcome via an issue. On the axis
these tables usually measure, the agents above lead: omp on edit efficiency, Prime
Agent on raw capability, Hermes on adoption, Cline on IDE integration, aider on
simplicity. relay is built on a different axis, and the point is that the two
compose: you can run a capable agent and still keep a run you can prove.

## Verify it yourself

Every guarantee is a command, not a claim.

```bash
# See a run as a hash-chained trajectory. Flip one byte and one edge snaps red.
relay --agent "fix the bug" --root . --save run.jsonl
relay --view run.jsonl

# Emit a proof-carrying certificate, then verify it offline with zero dependencies
# (no model, no re-execution). Editing the grader to make the tests pass is REFUTED.
relay --agent "fix the bug" --root . --check "pytest -q" --cert run.rvc
python verify_cert.py run.rvc          # ALLOW / UNVERIFIABLE / REFUTED

# Run the goal N times and keep the VERIFIED winner. A run that made the tests pass
# by editing the grader ranks below an honest run that scored higher.
relay --agent "fix the bug" --root . --best-of 8 --check "pytest -q" --save selection.jsonl

# Localize the first edit that broke the tests, by replaying the witnessed edit set
# against the check. The model is never re-run.
relay --bisect run.jsonl --root <clean-checkout> --check "pytest -q"
```

## The honest nulls

Accountability is a measurement, and every measurement here states its limit.

- The certificate proves re-derivable correctness, not authorship. Python's
  standard library has no asymmetric signature, so an `.rvc` says the recorded run
  holds, not who produced it. A detached signature or a transparency log binds the
  who; the re-derivation core needs no key.
- Claim grounding uses a rule-based extractor. It classifies test-verdict and
  file-change claims and grounds those; a claim it cannot parse degrades to
  `unclassified`, counted against the run, never a silent pass.
- Verified best-of-N is decisive only when a runnable acceptance check exists. With
  no check it ranks accountability, not capability.
- Bisection needs the pre-run tree state and a deterministic check, and it assumes
  the failure is monotonic in the edit prefix, which is git-bisect's own assumption.
