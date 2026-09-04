# Reproduce the Form 1040 check

A published demo of a frontier model filled out a Form 1040 for a taxable
income of $36,700 and reported a tax of $4,165.50. The rate schedule gives that
figure. The form requires the tax table, which charges tax on the $36,725
midpoint of a $50-wide row and rounds half up, giving $4,169. Both numbers are
arithmetically correct, so no amount of rereading the arithmetic finds the
error. What was wrong is which source got to decide.

Three runs, from this directory. Each produces a different outcome, and the
exit code is the interface a harness branches on.

## The answer as filed

```bash
flywheel check-output --contract form-1040.contract.json --answer answer-as-filed.json --allow-commands
```

```
FAIL  1 of 2 fields confirmed
  FAIL          tax: the value disagrees with irs-2025-tax-table-single
  PASS          taxable_income: the answer cites the return
  next: tax: consult irs-2025-tax-table-single and take the value it gives, rather than deriving one that should match it
```

Exit 1. Note what the `next` line does not contain. The report never carries the
authoritative value, because an attempt that copied the right number out of its
own failure report would pass the check while learning the opposite lesson.

## The answer after consulting the table

```bash
flywheel check-output --contract form-1040.contract.json --answer answer-from-the-table.json --allow-commands
```

```
PASS  2 of 2 fields confirmed
  PASS          taxable_income: the answer cites the return
  PASS          tax: the value agrees with irs-2025-tax-table-single
```

Exit 0.

## The same correct answer, with nothing allowed to check it

```bash
flywheel check-output --contract form-1040.contract.json --answer answer-from-the-table.json
```

```
UNVERIFIABLE  1 of 2 fields confirmed
  UNVERIFIABLE  tax: irs-2025-tax-table-single could not decide: PermissionError: command authorities are not granted for this run, so this field is unchecked rather than confirmed
  PASS          taxable_income: the answer cites the return
  next: tax: irs-2025-tax-table-single was not available to the checker, so this field is unchecked rather than wrong
```

Exit 3. The value is the same value that passed a moment ago. Without
`--allow-commands` no program ran, so nothing confirmed it, and the report says
so rather than reporting a pass. This is the direction every failure in the
mechanism leans: a check nobody could run must not read as a check that passed.

## From a source checkout

`python ../../scripts/run_output_check.py` takes the same flags as
`flywheel check-output`.

## What is here

| File | What it is |
| --- | --- |
| `form-1040.contract.json` | Two fields and the authority for each. |
| `answer-as-filed.json` | The demo's figures. |
| `answer-from-the-table.json` | The same return with the tax the form requires. |
| `tax_table.py` | The checker program. Reads the answer on stdin, writes the value on stdout, exits 3 for an input it does not cover. |

`tax_table.py` models one rule over two brackets and declines outside them. It
is not a tax authority and nothing here is filing advice. It exists so the
example runs end to end without a network.

Full reference: [docs/OUTPUT-VALIDATION.md](../../docs/OUTPUT-VALIDATION.md).
