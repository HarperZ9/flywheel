---
name: check-output
description: Bind the values in an answer to the source that decides them before the answer reaches the user. Use when a task produces numbers, amounts, dates, identifiers, or citations that a reader will act on, and use it before handing back any calculation, form, report, or filing.
user-invocable: true
argument-hint: "[--allow-commands] [contract.json answer.json]"
---

# /check-output: bind the answer to what decides it

A model that rechecks its own arithmetic gets the same wrong number twice. The
case this was built from is public. A frontier demo filled out a Form 1040 and
read the tax off the rate schedule, giving $4,165.50, where the form requires
the tax table, which gives $4,169. Both figures are arithmetically correct. The
error was in which source got to decide, and no amount of rereading the work
would surface it.

So the check does not ask whether the reasoning holds. It asks what the
authority says, and whether the answer names it.

## The four steps

**Plan.** Before producing the answer, write down every value a reader will act
on and what decides each one. That list is the contract. A field nobody can
name a source for is a field you are about to guess at, and finding that out now
costs nothing.

**Produce.** Do the work. Put each value under a field name with the source that
decided it.

**Check.** Run the contract against the answer.

**Assess and retry.** Read the `next` block, go to the source it names, and
produce again. Two attempts that fail the same way means stop.

## Writing the contract

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

A field's `authority` is what has to happen for it to count:

- `TABLE` and `RECOMPUTE` produce a value to compare against. Use these for
  anything a reader will act on.
- `CITED` only asks that the answer name where it looked. It can never fail, so
  it never confirms a number. Use it for provenance, not for values.

An authority's `kind` is how the value gets produced:

- `citation` decides nothing.
- `table` looks the value up in a JSON file that shipped with the task.
- `command` runs a program that is not the one being checked. This is the kind
  with teeth, because independence from the producer is the entire point.

## The answer

Each field carries its value and the source it came from.

```json
{"taxable_income": {"value": 36700, "source": "the return"},
 "tax": {"value": 4169, "source": "irs-2025-tax-table-single"}}
```

## Running the check

```bash
flywheel check-output --contract task.contract.json --answer answer.json --allow-commands
```

From a flywheel checkout the same flags work on `python
scripts/run_output_check.py`. Add `--json` for the machine-readable report and
`--out report.json` to keep it.

Three exit codes, and they mean different things:

- `0` every field agrees with its authority and names it. Send the answer.
- `1` a field disagrees with its authority. The answer is wrong, and the report
  says which field.
- `3` nothing was able to confirm a field. The answer is unchecked, which is not
  the same as wrong, and it must not be sent as though it passed.

Exit `2` is a usage error from argparse. Fix the command rather than retrying
the task.

## Rules for the retry

**Go to the source, not to the report.** The report deliberately never carries
the authoritative value. An attempt that copied the right number out of its own
failure report would pass this check while learning the opposite lesson. Open
the table, run the program, read the page.

**Two failures the same way is the stop.** A third attempt is a reroll and buys
a more expensive way to be wrong. Say what remains unresolved instead.

**Grant commands deliberately.** Without `--allow-commands` a command authority
does not run and its field comes back unchecked. That is the safe direction and
it is not a pass. Only grant it for checker programs you can read.

**Do not edit the contract to make the answer pass.** Loosening a tolerance or
downgrading a field to `CITED` after seeing a failure removes the check rather
than satisfying it. If the contract is genuinely wrong, say so and say why.

## Reporting to the user

An answer that never validated still gets handed over, with the reason attached.
Dropping it hides work the user paid for. Sending it clean is the failure this
whole thing exists to prevent.

Say which fields were confirmed, which disagreed, and which nothing could check.
Keep the honest null: "the table covers incomes up to $48,475 and this one is
above it, so the tax is unchecked" is a useful sentence, and "verified" would
have been a false one.

## In Python

Inside a flywheel lane the same loop runs in process:

```python
from harness.validated_answer import run_validated, emission

result = run_validated(produce, contract, authorities)
out = emission(result)
```

`produce` is called with `None` on the first attempt and with the feedback block
on every attempt after. The loop stops on a pass, on a repeated failure
signature, or on running out of attempts, and `emission` attaches the notice.
