# Deterministic checks: one library, one receipt

Some mistakes a model makes can be caught without a model. A number can be
recomputed from its inputs. A quote can be looked up in the page it cites. A
receipt can be checked against its schema, a program can be parsed, and a run
can be replayed against the order of steps it must follow. `harness.checks`
puts these five checks behind one call and one receipt, and search and the
pre-action monitor both use it.

```python
from harness.checks import run

receipt = run("recompute", 125, {"expr": "a ^ b", "inputs": {"a": 74, "b": 51}})
receipt.verdict   # "FAIL": 74 XOR 51 is 121
receipt.to_dict() # schema flywheel.check-receipt/v1
```

## The five checks

| Kind | Subject | Spec | Fails when |
|---|---|---|---|
| `schema` | a JSON value | `schema`: type, required, properties, additionalProperties, enum, const, items, min and max bounds, pattern | the value breaks the schema; a bool never counts as an integer |
| `ast` | Python source | `require_defs`, `forbid_calls`, `forbid_imports`, `reward_hacking` (on by default) | the source does not parse, misses a definition, uses a forbidden call or import, or exits, skips or patches its way past tests |
| `fsm` | a list of events | `start`, `transitions`, `accept` | an event is not allowed in the current state, or the run stops outside a final state |
| `value_on_page` | the quoted value | `page`, `fold_case` | the value does not appear in the page; runs of whitespace are collapsed first, and 1070 also matches 1,070 |
| `recompute` | the claimed value | `expr`, `inputs`, `tolerance` | the claim differs from the recomputed value; the expression may use arithmetic, comparisons and abs, min, max, sum, len, round, int, float, sorted, and nothing else |

Every receipt carries the verdict (PASS, FAIL or UNVERIFIABLE), a code, a
reason, the sha256 of the subject and of the spec, and a `does_not_prove` line.
A missing input (no schema, no page, no expression, no machine) gives
UNVERIFIABLE. A check that raises gives UNVERIFIABLE with code `check_error`.
Neither case can pass.

## In search

Give search a list of checks and each candidate runs them before the visible
tests. A candidate that does not pass every check is rejected without a test
run, and the next candidate gets its turn.

```python
from harness.eval import ArmConfig
arm = ArmConfig(name="search", n_candidates=4,
                checks=[("ast", {"require_defs": ["solve"]})])
```

The receipt's search stage lists each candidate's check codes. With no checks
set, search runs as before.

## In the pre-action monitor

`monitor_layer0` turns per-tool rules into the monitor's layer-0 gate. A tool
call whose arguments fail a check is blocked, and the reason names the check,
its code and the first 16 hex digits of its receipt hash.

```python
from harness.checks.adopt import monitor_layer0
rules = {"write_file": [{"check": "schema", "arg": None,
                         "spec": {"schema": {"type": "object",
                                             "required": ["path", "content"]}}}]}
monitor = Monitor(home, layer0=monitor_layer0(rules))
```

An existing layer-0 gate can be passed as `inner`, and it runs first.

## Measured result

The checks were measured on a corpus of 40 false accepts: cases a weaker check
let through, eight for each kind, each paired with a fixed twin that must pass.
Four of the 40 were observed in recorded runs, such as a twin task whose own
test asserted 74 XOR 51 = 125. The other 36 were built from failure patterns
seen in Flywheel's runs and reports. The corpus is
`tests/fixtures/checks/false_accepts_v1.json`, and
`scripts/build_false_accept_corpus.py` rebuilds it byte for byte.

| Measure | Bar | Result |
|---|---|---|
| False accepts caught | at least 30 of 40 | 38 of 40 |
| False rejects on known-good items | 0 on at least 200 | 0 on 353 |

The known-good items are the 40 fixed twins, the 120 reference solutions of
the shipped hard task sets, 128 search traces built from the held-out rerun
records, 31 sentences quoted from a shipped doc, the rerun summaries
recomputed from their rows, and 40 of the checks' own receipts validated
against the receipt schema.

Each check has a paired mutation test: a weakened version of the check (for
example, the schema check with required fields ignored) must catch fewer of its
kind's false accepts, and an always-pass checker must catch none.

## Limits

The two misses show where these checks stop. A quote cut so that it drops a
negation still appears on the page, and a program that hard-codes the visible
test's answer still parses. A passing check shows structure or a matching
value. It does not show the subject is right in meaning. Most of the corpus
was built from known patterns, so the catch rate says the checks cover the
failures we have already named; it does not measure failures nobody has seen
yet.
