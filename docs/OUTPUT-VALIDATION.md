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

Tax is the example, not the scope. The same defect reaches doses, deadlines,
citations, and units. [CRITICAL-DOMAINS.md](CRITICAL-DOMAINS.md) covers the
domain packs for finance, medicine, and law.

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

## Criticality and the release decision

The verdict says whether the values are confirmed. A second question follows
from it and is not the same question: may this answer leave the building.

A field carries a criticality, `advisory` or `standard` or `critical`, and
`standard` is the default. Criticality never changes a verdict. What it decides
is what a non-PASS blocks, because an unchecked footnote and an unchecked dose
arrive as the same verdict and carry different risk.

| Release | When | What a caller does |
| --- | --- | --- |
| `RELEASE` | every field passed | send it |
| `RELEASE_WITH_CAVEAT` | something is unconfirmed, nothing critical | send it saying what is unconfirmed |
| `HOLD` | a field failed, or a critical field is short of PASS | do not send it |

The report carries `release` and a `blocking` list naming the fields that held
it. `--strict` puts that on the exit code for a caller that cannot carry a
caveat: a held answer exits 1 where the verdict alone would have exited 3.

## Run it

```bash
flywheel check-output --contract task.contract.json --answer answer.json --allow-commands
```

Add `--json` for the machine-readable report, `--out report.json` to keep it,
`--strict` to put the release decision on the exit code. From a source checkout,
`python scripts/run_output_check.py` takes the same flags.

A runnable version of the case above, with the contract, both answers, and the
checker program, is in
[examples/output-validation](../examples/output-validation/README.md).

## Documents in, documents out, and a proof

`--answer` also reads the answer out of the document it arrived in: a
`flywheel-answer` fence in Markdown, a `flywheelanswer` environment in LaTeX,
or the stream a Flywheel PDF carries. `--report review.pdf` writes the report
back out in whichever of `.txt`, `.md`, `.tex`, `.pdf`, or `.json` the suffix
names.

```bash
flywheel check-output --contract c.json --answer memo.md --report review.pdf
```

`--lean Answer.lean --verify-lean` emits the same check as a Lean 4 file and
hands it to the kernel. Deterministic obligations become theorems closed `by
decide`, every value an outside authority decided enters as a named axiom, and
`#print axioms confirmed` prints the whole trust surface in one line. The
report and the file are two readings of one answer built from different code,
so a kernel that refuses an obligation the report passed is the finding.
[PROOF-AND-FORMATS.md](PROOF-AND-FORMATS.md) covers all of it.

## The contract

The contract lists every value a reader will act on and names what decides each
one. Writing it before the work starts is the useful part: a field nobody can
name a source for is a field about to be guessed at.

```json
{
  "fields": [
    {"name": "tax", "authority": "TABLE", "source": "irs-2025-tax-table-single",
     "criticality": "critical", "method": "tax-table-lookup",
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

`authority` says what has to happen for the field to count:

| Kind | What it asks |
| --- | --- |
| `TABLE` | the value is what a source that supersedes any formula says |
| `RECOMPUTE` | an independent derivation gets the same value |
| `CITED` | the answer names where it looked, and nothing more |
| `UNIT` | the value is in the unit the source requires |
| `BOUND` | the value is inside what the source permits |

`UNIT` and `BOUND` are there because a right number can still be wrong. A dose
of 600 is correct in milligrams and a thousandfold overdose in micrograms, and a
perfectly computed 600 mg is still an error above a 500 mg ceiling. Neither
failure is reachable by comparing numbers.

`method` mandates how the value had to be produced, and it is checked before the
value. An answer that states a different method fails on `METHOD_MISMATCH` even
when the two methods happen to agree, because agreeing by luck this time is not
a check. An answer that states no method is `METHOD_UNSTATED`, which is
unverified rather than wrong.

`kind` says how the value gets produced:

- `citation` decides nothing.
- `table` looks the value up in a JSON file shipped alongside the contract.
  Relative paths resolve beside the contract, so a task and its checkers travel
  together.
- `command` runs a separate program. Independence from the producer is the point
  of the whole exercise, and a separate process is the plainest way to get it.

A contract with no fields is refused rather than passing, because it would exit
clean on any answer at all.

A contract may also name a domain pack and use its templates instead of
spelling out what the domain already decides. See
[CRITICAL-DOMAINS.md](CRITICAL-DOMAINS.md).

## The answer

Each field carries its value and the source it came from.

```json
{"taxable_income": {"value": 36700, "source": "the return"},
 "tax": {"value": 4169, "source": "irs-2025-tax-table-single",
         "method": "tax-table-lookup"}}
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

## In the harness loop

A task that declares a contract gets the check on the accept path, after the
oracle and the re-witness:

```python
result = run_loop(task, proposer, oracle,
                  output_contract=contract,
                  output_authorities=authorities,
                  validation_ledger=path)
```

`output_extract` pulls the answer out of the candidate when the task does not
emit JSON directly. The loop records at task scope under the task id, so a run
of many tasks leaves a ledger the goal and session scopes can roll up.

An oracle answers whether the code did what the task asked. It has no opinion
about whether the number that code produced came from the source that decides
it, so a candidate can pass every test and still hold. When the output stage
holds, `result.accepted` is false and no envelope is written. The gate is on
`HOLD` rather than on any non-PASS, so a contract author sets the strictness
through criticality rather than through the loop.

`result.output` carries the report. A lane with no contract behaves as it did
before, which is why this could go into the live loop without changing what
existing lanes do.

## Post-task, post-goal, post-session

One check answers one question about one answer. The accumulated question is the
one an operator asks at the end: across this task, this goal, this whole
session, what went out unverified.

Every check can append a line to a ledger, and the three scopes read the same
file.

```bash
flywheel check-output --contract c.json --answer a.json --scope goal --subject sprint-14
```

Without `--scope`, `--subject`, or `--ledger`, nothing is written. A command a
person runs to look at one answer should not accumulate a record of them.

```python
from harness.validation_ledger import outstanding, read_ledger, roll_up

roll_up(read_ledger(scope="session"))
outstanding(read_ledger(scope="session"))
```

The roll-up takes the worst entry, never the latest. A session whose last check
passed is not a clean session if something went out on hold in the middle of it.
`outstanding` returns the entries still short of a clean release, worst first,
which is the list an operator has to work through.

A torn last line is skipped rather than raising. A ledger written by a process
that was killed mid-write still answers the question about every entry before
it.

## Emitting an answer that never validated

It is returned, with the reason attached. Dropping it hides work the user paid
for. Emitting it clean is the failure the whole mechanism exists to prevent.

`emission` attaches a notice, the list of unresolved fields, and the verdict.
An unchecked answer says it is unchecked rather than reading as wrong, because
those are different facts and a reader who conflates them will discard something
correct or trust something unverified.
