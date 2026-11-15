# Recheck a failed task without confusing it with a broken receipt

This is a development compatibility exercise for the optional Flywheel reporter.
It checks a concrete boundary: a failed task can have intact evidence. It is not
a model evaluation, a regulatory assessment, or proof that the submitted actions
executed.

Use reviewed source revisions of both projects in a disposable Python environment.
The released packages may not include these development adapters. Record the two
commit IDs, Python version, operating system and package hashes with the result.
Install EMET from its checkout and Flywheel from the corresponding evaluation
integration checkout. The byte-witness path needs no model key or provider call.

## Exercise

From a directory outside both checkouts, run the following Python with the
Flywheel checkout path as its first argument. It uses the deliberately wrong
final-state example, writes to a new directory, and refuses to overwrite one.
Inspect the example before running it; it contains submitted synthetic JSON,
not executable agent actions.

```python
import json
from pathlib import Path
import subprocess
import sys
from emet import report, witness_receipt
from emet.reporters.flywheel import mint_receipt

source = Path(sys.argv[1]).resolve()
fixture = source / "examples/evaluation/incident-sim"
run = subprocess.run([
    sys.executable, "-m", "harness.cli_entry", "incident-sim",
    "--task", str(fixture / "task.json"),
    "--trace", str(fixture / "wrong-state-trace.json"),
], capture_output=True, timeout=30)
assert run.returncode == 1, "expected a checked task failure"
result = json.loads(run.stdout)
assert result["evaluation"]["overall"]["verdict"] == "DRIFT"
receipt, artifacts = mint_receipt(run.stdout)
assert receipt["verdict_record"] == []
out = Path("evaluation-review")
out.mkdir(exist_ok=False)
for name, raw in artifacts.items():
    (out / name).write_bytes(raw)
(out / "receipt.json").write_text(report.canonical(receipt), encoding="utf-8")
assert witness_receipt.check_receipt(
    receipt, base_dir=str(out), recompute=True)[0] == "RECEIPT_VALID"
print("Task: DRIFT; submitted report bytes: RECEIPT_VALID")
```


For final process-audit packet handoff, prefer `mint_packet_receipt(packet_bytes)`
and retain the returned commitment's `receipt_sha256` whole-receipt hash, or the
full commitment that contains it, separately. `receipt_id` is supplementary and
does not bind the whole handoff. The writer helper refuses to overwrite existing
outputs, but it does not provide independent storage.

Recheck the stored evidence with the installed command:

```text
emet check evaluation-review/receipt.json --recompute-from-paths
```

## Controls that must change the outcome

Keep the original artifacts and make separate copies of the review directory.
Run the same recheck command against each copy:

| Change in the copied directory | Required witness result | What this tests |
| --- | --- | --- |
| No change | `RECEIPT_VALID` | Both addressed artifacts can be rehashed |
| Add a newline to `flywheel-evaluation.json` | `RECEIPT_TAMPERED` | Exact raw bytes, including whitespace, matter |
| Remove `flywheel-evaluation.json` from the copy | `RECEIPT_UNVERIFIABLE` | Missing evidence cannot become a pass |
| Change `flywheel-record.json` | `RECEIPT_TAMPERED` | The metadata is also addressed |

The original task result stays `DRIFT` throughout. Re-minting a receipt around
edited evidence can produce a new intact receipt; that does not authenticate the
producer or make the edited claim true. Preserve the original receipt identity
and expected artifact hashes from a separately established source.

For another implementation, run the existing EMET JavaScript receipt checker
against the same receipt and subjects. Python and JavaScript share the same
author and specification; agreement is interoperability evidence, not independent
institutional assessment or independent ground truth.

## Useful feedback

Report the exact source revisions, platform, command, expected result, actual
result and smallest nonsensitive reproducer. Distinguish import compatibility,
artifact integrity, task-checker disagreement and missing observation. Do not
upload private logs, credentials, original user conversations or proprietary
task material to a public issue. A synthetic reproducer is preferable.

The separate Flywheel fixture suite checks supported Inspect producer behavior
and deliberate schema/fixture drift. This exercise does not replace that suite
or validate every tool in the wider portfolio.
