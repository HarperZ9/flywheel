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
- `UNIT` says which unit the value has to be in. A dose of 600 is correct in
  milligrams and a thousandfold overdose in micrograms.
- `BOUND` says whether the value is permitted. A perfectly computed figure above
  a ceiling is still an error, and no comparison of numbers reaches it.

Two more keys matter on a field. `criticality` is `advisory`, `standard`, or
`critical`, and it decides what an unconfirmed field blocks rather than changing
any verdict. `method` names how the value had to be produced, and it is checked
before the value: an answer that used a different method fails even when the two
methods happen to agree.

An authority's `kind` is how the value gets produced:

- `citation` decides nothing.
- `table` looks the value up in a JSON file that shipped with the task.
- `command` runs a program that is not the one being checked. This is the kind
  with teeth, because independence from the producer is the entire point.

## When the domain already decides

For a financial, medical, or legal answer, name a pack and use its templates.
The pack supplies the authority kind, the criticality, and the method mandate.
The document supplies what the pack cannot know: the field name and the source.

```json
{"pack": "medicine",
 "fields": [{"use": "dose", "name": "dose", "source": "formulary:2026-03"},
            {"use": "maximum", "name": "dose", "source": "formulary:max-daily"}]}
```

A pack ships no domain data. There is no formulary in it, no rate table, no
court calendar. Every authority is still yours to supply, and a critical field
with nothing behind it comes back unchecked, which holds the answer. Run
`flywheel packs` to see what each one declares and what it refuses to decide.

Three domains ship, and the defect reaches many more. Water treatment reads a
dosing table. A grid study reads an ampacity table with a correction applied.
An emissions report reads a global warming potential that changed between
assessment reports. For a domain that does not ship here, write the pack as a
document and point at it:

```bash
flywheel packs plant/water-treatment.pack.json
```

```json
{"schema": "flywheel.domain-pack-declaration/v1",
 "name": "water-treatment",
 "describes": "coagulant dose, disinfectant residual, contact time",
 "caution": "This pack holds no treatment data and decides no limit.",
 "templates": {
   "dose": {"authority": "TABLE", "method": "plant-jar-test-table",
            "catches": "a dose computed from turbidity where the plant tables it"}}}
```

The path works anywhere a pack name works. A declaration may not carry a value,
so a `maximum`, a `rate`, a `limit`, or a `table` inside it is refused: that
would be a pack deciding the thing the authority is supposed to decide. Every
template has to say what it catches, because one that cannot is a template no
reviewer can argue with. A declaration may not take a shipped pack's name
either, or a reader could not tell which one decided their contract.
`examples/output-validation/water-treatment.pack.json` is a worked one.

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

## Whether it may ship

The verdict says whether the values are confirmed. The report's `release` line
answers the narrower question of whether the answer may go to the reader:

- `RELEASE`. Everything passed.
- `RELEASE_WITH_CAVEAT`. Something is unconfirmed and nothing critical is. Send
  it, and say what is unconfirmed.
- `HOLD`. A field disagreed, or a critical field went unchecked. The `blocking`
  list names the fields responsible. Do not send it.

`--strict` puts that on the exit code, so a held answer exits `1` where the
verdict alone would have exited `3`. Use it from a script that cannot carry a
caveat in its head.

## When the answer lives in a document

`--answer` takes `.md`, `.tex`, and `.pdf` as well as `.json`. It reads a
fenced block tagged `flywheel-answer`, a `flywheelanswer` environment, or the
JSON stream a Flywheel PDF carries. Tag the block when you write the document,
because an untagged memo with several code blocks makes the reader guess.

Prose is never mined. A sentence stating the number is not a field, and asking
the check to read one would be asking it to guess.

`--report review.pdf` writes the report back into a document. The suffix picks
the format from `.txt`, `.md`, `.tex`, `.pdf`, and `.json`. The PDF is
byte-identical across runs and carries the answer it vouches for inside it.

## When you want a proof

```bash
flywheel check-output --contract c.json --answer a.json \
  --lean Answer.lean --verify-lean
```

This emits the check as a Lean 4 file and runs the kernel on it. Deterministic
obligations become theorems closed `by decide`. Anything an outside authority
decided becomes a named axiom, because a subprocess's word is not a kernel's.
The last line of the file prints the axiom list, and that list is what to read:

- named axioms are what the result rests on, and each one is a source you can
  go and check
- `sorryAx` means an obligation did not close, and the run is a `FAIL`
- no axioms at all is the strongest result available

Without `--verify-lean` the file is written and nothing runs it. Without Lean
installed the proof is `UNVERIFIABLE`, and it is never a `PASS`.

The proof says the answer is internally consistent and names what it rests on.
It does not say those sources are right. Report it that way.

## Across a task, a goal, a session

Add `--scope task|goal|session --subject <id>` to append the check to a
validation ledger. The end-of-session question is what went out unverified over
the whole run, and it cannot be answered from the last check alone. Without a
scope, subject, or `--ledger`, nothing is written.

The roll-up takes the worst entry, never the latest. A session whose last check
passed is not a clean session if something went out held in the middle of it.

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

A lane that declares a contract gets the check on its accept path:

```python
result = run_loop(task, proposer, oracle,
                  output_contract=contract, output_authorities=authorities)
```

An oracle answers whether the code did what the task asked. It has no opinion
about which source decides the numbers that code produced, so a candidate can
pass every test and still be held. A held answer does not accept and writes no
envelope.
