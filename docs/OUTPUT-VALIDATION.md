# Checking an answer before it reaches a reader

An assistant that rechecks its own arithmetic gets the same wrong number twice.
Rereading the work confirms the method that produced it, which is exactly the
thing that needs testing.

A public example makes the shape clear. A frontier model's demo filled out a
Form 1040 for a taxable income of $36,700 and reported a tax of $4,165.50. The
rate schedule gives that figure. The form requires the tax table, which charges
tax on the $36,725 midpoint of a $50-wide row and rounds half up, giving $4,169.
Both numbers are arithmetically correct. The error is in which source got to
decide, and self-review does not reach it.

So the check runs against an authority instead of against the reasoning.

## Three outcomes

Two outcomes would be a lie. A value nobody was able to check is not the same
as a value that was checked and held.

| Outcome | What happened | Exit code |
| --- | --- | --- |
| `PASS` | The value agrees with its authority and the answer names it. | 0 |
| `FAIL` | The value disagrees with its authority. | 1 |
| `UNVERIFIABLE` | Nothing could confirm the value. | 3 |

`UNVERIFIABLE` covers a value that happens to be right but cites nothing, a
field the answer never stated, an input the authority does not cover, and an
authority that could not run. Each has a distinct reason code in the report.

The worst field decides the run. There is no majority and no average, because a
report that averaged one wrong field against four right ones would publish the
wrong one.

## Run it

```bash
flywheel check-output --contract task.contract.json --answer answer.json --allow-commands
```

Add `--json` for the machine-readable report, `--out report.json` to keep it.
From a source checkout, `python scripts/run_output_check.py` takes the same
flags.

A runnable version of the case above, with the contract, both answers, and the
checker program, is in
[examples/output-validation](../examples/output-validation/README.md).

## The contract

The contract lists every value a reader will act on and names what decides each
one. Writing it before the work starts is the useful part: a field nobody can
name a source for is a field about to be guessed at.

```json
{
  "fields": [
    {"name": "tax", "authority": "TABLE", "source": "irs-2025-tax-table-single",
     "describes": "Form 1040 line 16"},
    {"name": "filing_status", "authority": "CITED", "source": "the return"}
  ],
  "authorities": {
    "irs-2025-tax-table-single": {"kind": "command",
                                  "argv": ["python", "tax_table.py"]},
    "the return": {"kind": "citation"}
  }
}
```

`authority` says what has to happen for the field to count. `TABLE` and
`RECOMPUTE` both produce a value to compare against. `CITED` asks only that the
answer name where it looked, so it can never fail and never confirms a number.

`kind` says how the value gets produced:

- `citation` decides nothing.
- `table` looks the value up in a JSON file shipped alongside the contract.
  Relative paths resolve beside the contract, so a task and its checkers travel
  together.
- `command` runs a separate program. Independence from the producer is the point
  of the whole exercise, and a separate process is the plainest way to get it.

A contract with no fields is refused rather than passing, because it would exit
clean on any answer at all.

## The answer

Each field carries its value and the source it came from.

```json
{"taxable_income": {"value": 36700, "source": "the return"},
 "tax": {"value": 4169, "source": "irs-2025-tax-table-single"}}
```

Money comparison is exact by default. A tolerance has to be asked for per field,
because a default tolerance of a few cents would have passed the demo answer
above.

## The command protocol

A checker program reads the answer as JSON on stdin and writes
`{"value": ...}` as JSON on stdout.

| Exit | Meaning |
| --- | --- |
| 0 | The value on stdout decides this field. |
| 3 | This input is outside what the program covers. Decline it. |
| anything else | The program broke, and the field goes unchecked. |

Exit 3 exists so declining is not mistaken for a crash. A checker that guessed
outside its range would publish a fabrication with a check's authority behind
it, so declining is the correct behavior and it needs a way to say so.

The answer arrives on stdin, never in arguments, because arguments are readable
by every process on the machine.

## Command authorities are a grant

Running a program is an execution surface, so it stays off unless the caller
asks for it. Without `--allow-commands` a command authority does not run and its
field comes back `UNVERIFIABLE`, never `PASS`. Failing toward unverified is the
design throughout: a check nobody could run must not read as a check that
passed.

One authority that breaks does not discard the other fields. It becomes one
unchecked field, with the error text in its reason so the break stays visible.

## The retry loop

```python
from harness.validated_answer import run_validated, emission

result = run_validated(produce, contract, authorities, max_attempts=3)
out = emission(result)
```

`produce` receives `None` on the first attempt and the feedback block on every
attempt after. The loop stops for one of three reasons, and the result says
which:

- `validated`. The answer passed.
- `no-progress`. An attempt failed in a way an earlier attempt already failed.
- `attempts-exhausted`. The ceiling was reached.

Failure signatures are held as a set rather than compared to the previous
attempt, so an answer that oscillates between two wrong shapes is caught too.
A third attempt after a repeat is a reroll, not a retry, and buys a costlier way
to be wrong.

The feedback never carries the authoritative value. An attempt that copied the
right number out of its own failure report would pass the check while learning
the opposite lesson, so the report names the source and the retry has to go
there.

## Emitting an answer that never validated

It is returned, with the reason attached. Dropping it hides work the user paid
for. Emitting it clean is the failure the whole mechanism exists to prevent.

`emission` attaches a notice, the list of unresolved fields, and the verdict.
An unchecked answer says it is unchecked rather than reading as wrong, because
those are different facts and a reader who conflates them will discard something
correct or trust something unverified.
