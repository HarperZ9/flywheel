# Reviewer independence: when a second reader pays

A second checker that reads the same evidence as the first repeats the first
one's errors. `harness.reviewer_independence` measures how much evidence the
two share and says whether adding the second reader buys a catch.

## The rule

Three numbers decide it:

- `p`: the share of known lies the first checker clears, measured on its own
  evidence (its miss rate on a planted set);
- `acc`: how often the second reader is right on evidence of its own;
- `rho`: the share of the second reader's evidence that the first already read.

The second reader catches `p * acc * (1 - rho)` of the lies read. It pays when
that reaches a floor, 0.05 by default, so the stop point is
`rho* = 1 - 0.05 / (p * acc)`. The rule comes from the society lane, where the
base evidence policy measured `p` at 0.247 and the formula sat within 0.01 of
the measured catch in every arm. At `acc` 0.8 that puts the stop point near
three quarters. With a better first look (`p` 0.103) it drops to about 0.4, and
a reader sharing half the evidence catches 0.033 of lies read, under the floor.
Improving the first checker's evidence lowers the value of any second reader.

## Use it

```python
from harness.reviewer_independence import run
receipt = run({"first": first_ids, "second": second_ids},
              {"p": {"k": 25, "n": 100}, "acc": 0.8})
receipt.verdict   # PASS, FAIL or UNVERIFIABLE
```

Evidence ids are any stable name for one piece of evidence: a file sha256, a
URL, a record id. `p` and `acc` take a number or a `{"k", "n"}` count; a count
gives Wilson 95% bounds and the verdict uses them.

| Verdict | Code | Meaning |
|---|---|---|
| PASS | `second_reader_pays` | the catch's lower bound reaches the floor |
| FAIL | `second_reader_redundant` | the catch's upper bound is under the floor |
| UNVERIFIABLE | `interval_straddles_floor` | more measurements of `p` or `acc` would decide it |
| UNVERIFIABLE | `no_rates`, `malformed` | an input is missing or out of range |

The reason line gives the overlap, the stop point and the catch interval. From
the shell: `python -m harness.reviewer_independence case.json`, where the file
holds `subject` and `spec`; exit 0 on PASS, 1 on FAIL, 2 otherwise.

## Limits

Overlap counts shared ids, so two readers that read different copies of the
same source under different ids look independent. Errors can also correlate
through a shared model family or a shared prompt with no shared evidence; that
is a separate measurement on the false-accept corpus (H143). The formula
assumes the second reader's own evidence errs independently of the first
checker's misses.
