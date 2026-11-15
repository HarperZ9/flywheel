# Usage Guide

`proof-surface-report` reads one or more proof-surface JSON artifacts and writes
a single reviewer-facing Markdown report to **stdout**. It accepts two artifact
shapes:

- a **proof-surface packet** (`proof_surface_version: "0.1"`)
- an **EMET witness receipt** (an object with `receipt_id` and `verdict`)

Each input file is auto-detected by shape, validated against the shared
`proof-surface` contract, and swept for authority-shaped wording before
anything is rendered. The output is an evidence handoff, not a certification,
trust verdict, safety decision, or compliance finding.

## Install

```bash
pip install git+https://github.com/HarperZ9/proof-surface.git
pip install .
```

The `proof-surface` contract package is the only runtime dependency; the rest is
standard library. After install, a `proof-surface-report` console script is on
your `PATH`. For a development checkout you can skip the second `pip install`
and run with `PYTHONPATH=src` instead, as long as `proof-surface` is importable.

## Command line

```
proof-surface-report [--title TITLE] ARTIFACT [ARTIFACT ...]
```

| Argument            | Meaning                                                              |
| ------------------- | ------------------------------------------------------------------- |
| `ARTIFACT`          | One or more paths to packet/receipt JSON files (at least one).      |
| `--title TITLE`     | Markdown H1 title. Default: `Proof Surface Handoff Report`. The title is itself language-checked. |

Exit code is `0` on success. On a missing file, malformed JSON, failed contract
validation, or rejected (authority-shaped) wording, the tool prints a single
`error: ...` line to **stderr** and exits `1`.

## Example 1 -- render the bundled artifacts

Renders two packets and one witness receipt into a single report. (Run from the
repository root.)

```bash
proof-surface-report \
  examples/public-surface.packet.json \
  examples/provenance.packet.json \
  examples/emet.receipt.json
```

Expected output (verified against the bundled examples):

```markdown
# Proof Surface Handoff Report

This report summarizes proof-surface artifacts. It is an evidence handoff,
not a certification, safety verdict, or authority claim.

## Summary

| Field | Value |
| --- | --- |
| Packets | 2 |
| Witness receipts | 1 |
| Aggregate status | needs-polish |
| Claims | 6 |
| Checks | 2 |
| Action items | 1 |

## example repository public release surface

| Field | Value |
| --- | --- |
| Packet | public-surface-sweeper-example |
| Status | needs-polish |
| Source | `examples/public-surface.packet.json` |

### Claims

- Required public release files are visible. Evidence: required-file findings=0
- Secret-shaped values are surfaced before publication. Evidence: secret-shaped findings=0
- Public text hygiene is checkable. Evidence: em-dash findings=1

### Checks

- public-surface-sweeper: warn. score=90, findings=1

### Action Items

- README.md:14: replace em dash with plain punctuation
```

(The report continues with the provenance packet and the witness receipt
sections; truncated here for brevity.)

The **aggregate status** is the worst status across all packets, ranked
`blocked` > `needs-polish` > `unknown` > `ready`. Here `needs-polish` (from the
public-surface packet) outranks `ready` (from the provenance packet).

## Example 2 -- a development checkout, single packet

No install required; run the module directly with `PYTHONPATH=src`:

```bash
PYTHONPATH=src python -m proof_surface_report examples/provenance.packet.json
```

Expected output:

```markdown
# Proof Surface Handoff Report

This report summarizes proof-surface artifacts. It is an evidence handoff,
not a certification, safety verdict, or authority claim.

## Summary

| Field | Value |
| --- | --- |
| Packets | 1 |
| Witness receipts | 0 |
| Aggregate status | ready |
| Claims | 3 |
| Checks | 1 |
| Action items | 0 |

## model provenance validation

| Field | Value |
| --- | --- |
| Packet | model-provenance-validator-example |
| Status | ready |
| Source | `examples/provenance.packet.json` |

### Claims

- Model/reference claims carry provenance envelopes. Evidence: total envelopes=2
- Envelope structure is validated before publication. Evidence: valid=2, invalid=0
- Invalid provenance is converted into action items. Evidence: validation errors=0

### Checks

- model-provenance-validator: pass. valid=2, invalid=0, errors=0

### Action Items

- none
```

## Example 3 -- override the title

The `--title` flag sets the H1. It is itself checked for authority-shaped
wording.

```bash
proof-surface-report --title "Release Surface Handoff" examples/public-surface.packet.json
```

The first line of the report becomes:

```markdown
# Release Surface Handoff
```

A title that asserts authority is rejected before any rendering:

```bash
proof-surface-report --title "Certified Safe Report" examples/public-surface.packet.json
```

```text
error: report title validation failed: $.title contains authority-shaped wording: certified
```

(exit code `1`; nothing is written to stdout.)

## Example 4 -- using the API directly

`render_report` is the main entry point; it returns the report as a string and
raises `ValueError` (or an `OSError` / `json.JSONDecodeError`) on bad input.

```python
from pathlib import Path
from proof_surface_report import render_report

report = render_report(
    "Proof Surface Handoff Report",
    [Path("examples/public-surface.packet.json")],
)
print(report)
```

Public functions re-exported from the package (`from proof_surface_report import ...`):

| Function                                        | Purpose                                                        |
| ----------------------------------------------- | -------------------------------------------------------------- |
| `render_report(title, artifact_paths)`          | Validate artifacts and return the full Markdown report string. |
| `load_artifact(path)`                           | Load one file, returning `(kind, data)` where kind is `"packet"` or `"witness_receipt"`. |
| `validate_packet(path, data)`                   | Validate a packet dict; raise `ValueError` on failure.         |
| `validate_receipt(path, data)`                  | Validate a witness-receipt dict; raise `ValueError` on failure.|
| `reject_authority_language(value, path, issues)`| Append an issue if `value` contains authority-shaped wording.  |
| `main(argv=None)`                               | CLI entry; print report or `error:` line, return an exit code. |

## What gets rejected

Validation has two layers. The shared `proof-surface` contract enforces field
sets, the packet status enum, the version constant, and the closed
witness-verdict lattice (`MATCH`, `CORROBORATED`, `COHERENT`, `DRIFT`,
`UNVERIFIABLE`, `VIEW_DIFFERS_FROM_SOURCE`, `QUARANTINE_READ_PATH_DIVERGENCE`).
On top of that, this adapter sweeps reviewer-facing text (the report title,
packet surface/claims/evidence/check summaries/action items, and the receipt
notes and stdout verdict line) for authority-shaped wording such as
`certified`, `approved`, `authorized`, `compliant`, `trusted`, `safe to/for`,
`permitted`, and `allowed`. Any match aborts rendering with a non-zero exit.

The intent is to keep the report an evidence handoff: it summarizes claims and
checks, but it never asserts that something is approved, certified, safe, or
compliant.
