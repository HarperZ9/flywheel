# A spent budget is inconclusive

A check that runs out of search budget or time has covered part of what a pass
needs. It found no counterexample in that part and never looked at the rest.
Flywheel records that as inconclusive, never as a pass. The rule follows a
pattern in formal verification tools that prove a binary correct down to its
system calls: each one documents what its proof leaves out, and a run that
exhausts its budget reports inconclusive.

## Certificate checks

Every certificate check returns a `Coverage` record with a `stop_reason`:
`complete`, `bound`, `budget` or `timeout`.

| check says | stop reason | verdict |
|---|---|---|
| valid | `complete` | PASS |
| valid | `bound` (a declared limit, such as a stated sample size) | PASS, with the bound in coverage and no `SEARCH_SPACE_ENUMERATED` scope code |
| valid | `budget` or `timeout` | UNDECIDED, reason `BUDGET_EXHAUSTED` |
| invalid | any | FAIL: a counterexample found before the budget ran out is still a counterexample |

The excerpt of an UNDECIDED result names the stop reason and the enumerated
fraction. The verdict enters the output hash, so an inconclusive result and a
pass on the same certificate never share a digest. The base class applies the
rule, so no certificate family has to remember it. The `Coverage` record now
lives in `harness/certificates/coverage.py` and is still importable from
`harness.certificates.base`.

## buildc byte-witness packets

`harness/buildc_receipt_bridge.py` turns a buildc receipt into a byte-witness
packet. Each packet now carries a `scope` block:

- `checked`: the steps the bridge ran, in order: `receipt_bytes_hashed`,
  `export_bytes_hashed`, `source_digest_read_from_receipt`,
  `buildc_receipt_verify_ran`, `buildc_receipt_verify_exit_zero`. A step that is
  absent did not run.
- `inconclusive`: true when `buildc receipt verify` timed out (exit 124).

A timed-out verify gives failure code `buildc_verification_budget_exhausted`
and `verification.budget_exhausted: true`, with verdict UNVERIFIABLE. The
bridge's own vocabulary (MATCH, DRIFT, UNVERIFIABLE) has no UNDECIDED; a timeout
used to share the generic `buildc_verification_failed` code with a crash.
