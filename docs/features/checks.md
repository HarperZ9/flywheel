# Deterministic checks: one library, one receipt

Some mistakes a model makes can be caught without a model. A number can be
recomputed from its inputs. A quote can be looked up in the page it cites. A
receipt can be checked against its schema, a program can be parsed, and a run
can be replayed against the order of steps it must follow. A verdict can be checked
for the checks it skipped, and a port can be compared with its original on every
fuzz input. `harness.checks`
puts these seven checks behind one call and one receipt, and search and the
pre-action monitor both use it.

```python
from harness.checks import run

receipt = run("recompute", 125, {"expr": "a ^ b", "inputs": {"a": 74, "b": 51}})
receipt.verdict   # "FAIL": 74 XOR 51 is 121
receipt.to_dict() # schema flywheel.check-receipt/v1
```

## The seven checks

| Kind | Subject | Spec | Fails when |
|---|---|---|---|
| `schema` | a JSON value | `schema`: type, required, properties, additionalProperties, enum, const, items, min and max bounds, pattern | the value breaks the schema; a bool never counts as an integer |
| `ast` | Python source | `require_defs`, `forbid_calls`, `forbid_imports`, `reward_hacking` (on by default) | the source does not parse, misses a definition, uses a forbidden call or import, or exits, skips or patches its way past tests |
| `fsm` | a list of events | `start`, `transitions`, `accept` | an event is not allowed in the current state, or the run stops outside a final state |
| `value_on_page` | the quoted value | `page`, `fold_case` | the value does not appear in the page; runs of whitespace are collapsed first, and 1070 also matches 1,070 |
| `recompute` | the claimed value | `expr`, `inputs`, `tolerance` | the claim differs from the recomputed value; the expression may use arithmetic, comparisons and abs, min, max, sum, len, round, int, float, sorted, and nothing else |
| `coverage` | `{"ran": {check_id: verdict}}` | `required`: the check ids a pass needs, the protected verifier among them | a required check did not run, or returned anything but PASS (FAIL, SKIPPED, a timeout, a partial-credit score) |
| `differential` | `{"outputs": [[input, output], ...]}` recorded from the candidate | `reference` (an expression over `x`, same evaluator as recompute), `inputs` (the fuzz set) | a fuzz input has no recorded output, or an output differs from the reference exactly; 3 and 3.0 differ |

Every receipt carries the verdict (PASS, FAIL or UNVERIFIABLE), a code, a
reason, the sha256 of the subject and of the spec, and a `does_not_prove` line.
A missing input (schema, page, expression or machine) gives UNVERIFIABLE. A
check that raises gives UNVERIFIABLE with code `check_error`. Both cases block a
pass.

## In search

Give search a list of checks and each candidate runs them before the visible
tests. A candidate that fails any check is rejected before its test run, and
the next candidate gets its turn.

```python
from harness.eval import ArmConfig
arm = ArmConfig(name="search", n_candidates=4,
                checks=[("ast", {"require_defs": ["solve"]})])
```

The receipt's search stage lists each candidate's check codes. An empty check
list leaves search exactly as it was.

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

The checks were measured on a corpus of 56 false accepts: cases a weaker check
let through, eight for each kind, each paired with a fixed twin that must pass.
Four of the 56 were observed in recorded runs, such as a twin task whose own
test asserted 74 XOR 51 = 125. Thirty-six were built from failure patterns
seen in Flywheel's runs and reports. The 16 coverage and differential items
were built from the reward audit in Terminal-RSI (arXiv 2610.22192, sections
2.1, 2.2 and 3.5): 48 of 4,352 audited trajectories passed every executed
scenario check and failed the terminal gate, and a Rust-to-C port passed its
wrapper test and failed exact-output fuzzing. No Flywheel run produced them. The corpus is
`tests/fixtures/checks/false_accepts_v1.json`, and
`scripts/build_false_accept_corpus.py` rebuilds it byte for byte.

| Measure | Bar | Result |
|---|---|---|
| False accepts caught, first 40 | at least 30 of 40 | 38 of 40 |
| Partial-check false accepts caught (2026-10-21) | at least 14 of 16 | 15 of 16 |
| False accepts caught, all | | 53 of 56 |
| False rejects on known-good items | 0 on at least 200 | 0 on 376 |

The known-good items are the 56 fixed twins, the 120 reference solutions of
the shipped hard task sets, 128 search traces built from the held-out rerun
records, 31 sentences quoted from a shipped doc, the rerun summaries
recomputed from their rows, and 40 of the checks' own receipts validated
against the receipt schema.

Each check has a paired mutation test: a weakened version of the check (for
example, the schema check with required fields ignored) must catch fewer of its
kind's false accepts, and an always-pass checker must catch zero.

## Limits

The three misses mark where these checks stop. The differential check sees the
fuzz inputs its spec names, so a port that breaks on the most negative integer
passes a fuzz set that leaves that integer out. A quote cut to drop a negation
still appears on the page, and a program that hard-codes the visible test's
answer still parses. A passing check shows structure or a matching value;
meaning needs a reader. Most of the corpus was built from known patterns, so
the catch rate covers the failures already named.
