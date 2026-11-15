# Test diffs

`articulate code test-diff` answers one question about a code change: do its
Python tests check less than they did before? It reads the test files as text.
No test is imported or run.

```bash
articulate code test-diff main HEAD                # two commits in the current repository
articulate code test-diff BASE HEAD --repo path/to/repo --json
articulate code test-diff --before old_test.py --after new_test.py --path tests/test_x.py
```

## What it reports

| Rule | The change |
|---|---|
| `assertion-deleted` | a test keeps its name and loses checks |
| `assertion-weakened` | a check is replaced by a weaker form, such as `assert x == 4` becoming `assert x` |
| `assertion-made-conditional` | a check moves under an `if`, so it may not run |
| `skip-added`, `xfail-added` | a new `skip`, `skipif` or `xfail` on a test or a module |
| `tolerance-widened` | a wider `approx` tolerance |
| `raises-widened` | a broader expected exception |
| `exception-swallowed` | a broad `except` around the step under test |
| `test-deleted` | a test is gone and its checks appear nowhere else in the change |
| `test-uncollected` | a test is renamed to a name pytest does not collect |
| `assert-true`, `self-compare`, `snapshot-self`, `mock-only`, `mock-called-only`, `no-assertion` | a new or edited test whose checks pass whatever the code does |

Each row has a tier. A `finding` has no explanation in the change. A `declared`
row carries a reason the author wrote: a declared test change, a comment on the
changed line, or a skip tied to a platform or a missing dependency. The reason
is shown and is not checked. An `advisory` row is a weakening that the change
may explain, because it also edits source or adds other tests. Only findings
are counted.

## Output and exit status

The text report lists one line per row with the file and line. `--json` gives
the same rows with `status` (`clean`, `findings` or `unverifiable`), counts by
rule, a digest of the inputs and a digest of the rows, so two runs on one
change can be compared.

The command reports and does not gate. It exits 0 whatever it finds and 2 on a
usage or git error. A caller that wants a gate reads `status` from the JSON.

`--declared concept.json` takes a JSON list of test ids, or an object with a
`declared_test_changes` list, and moves the matching findings to `declared`.

## Limits

- A clean report means the change did not weaken the tests in the forms this
  command reads. It says nothing about whether the tests are good.
- A check moved into a fixture, into another file, or more than one helper
  call deep reads as deleted.
- One test split into several smaller ones is not detected.
- Python only. Test files in other languages are listed as `unverifiable`.

## In CI

A workflow step can run it on a pull request and print the rows:

```yaml
- run: |
    base=$(git merge-base "$BASE_SHA" "$HEAD_SHA")
    articulate code test-diff "$base" "$HEAD_SHA" --json > test-diff.json
```

Keep a control beside it: a planted weakened test that the step must report.
`tests/test_code_testdiff_control.py` in this package is one.
