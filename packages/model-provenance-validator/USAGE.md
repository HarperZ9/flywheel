# Usage

`model-provenance-validator` validates provenance envelopes (the small JSON
shape that says what a claim is about, where the reference came from, when it
was retrieved, and what validation status a maintainer will publish). It
reports per-file results, a batch summary, or a proof-surface interop packet,
and it redacts credential-shaped strings and local absolute paths out of its
own output.

This guide covers the real CLI and the importable Python API. For the envelope
schema and field rules, see [README.md](README.md).

## Install

```bash
python -m pip install model-provenance-validator
```

This installs the `model-provenance-validator` console command and the
`model_provenance_validator` Python package. The one runtime dependency,
`proof-surface`, is installed automatically.

For local development from a clone:

```bash
python -m pip install -e ".[test]"
python -m pytest
```

## Command-line interface

```
model-provenance-validator ENVELOPE [ENVELOPE ...] [options]
```

You can pass one or more envelope files (shell globs such as
`*.provenance.json` are fine). The command can also be invoked as
`python -m model_provenance_validator ...`.

Options:

| Flag | Effect |
| --- | --- |
| `--schema PATH` | Validate against a custom schema JSON file instead of the bundled schema. |
| `--json` | Print machine-readable JSON instead of text. |
| `--summary` | Print a batch validation summary instead of per-file detail. |
| `--proof-packet` | Print a proof-surface interop packet (JSON) for the batch. |

Exit status is `1` when any envelope fails validation (or when the schema
itself cannot be loaded), and `0` when every envelope is valid. Malformed or
unreadable envelope files are reported as invalid results rather than crashing
the run, so a batch always produces a complete action list.

## Worked examples

The repo ships a valid example envelope at
`examples/envelopes/release.provenance.json`. The runs below use it.

### 1. Validate a single envelope (text)

```bash
model-provenance-validator examples/envelopes/release.provenance.json
```

Output:

```text
examples/envelopes/release.provenance.json: valid
```

Exit status: `0`.

### 2. Machine-readable results (`--json`)

```bash
model-provenance-validator examples/envelopes/release.provenance.json --json
```

Output:

```json
[
  {
    "path": "examples/envelopes/release.provenance.json",
    "valid": true,
    "errors": []
  }
]
```

When an envelope is invalid, each entry's `errors` array holds objects with a
`path` (a `$.`-rooted JSON pointer into the envelope) and a redacted `message`.
For example, an envelope with an empty `references` list and an out-of-enum
`source.kind` produces text output like:

```text
draft.provenance.json: invalid
  $.source.kind: invalid value 'blog'; expected one of: official-doc, paper, release-note, local-fixture, other
  $.references: expected at least 1 item(s)
```

### 3. Batch summary (`--summary`)

```bash
model-provenance-validator *.provenance.json --summary
```

For a batch of two files where one is valid and one is invalid, the output is:

```text
total: 2
valid: 1
invalid: 1
error_count: 1
action_items:
- draft.provenance.json: resolve 1 validation error(s)
```

Add `--json` to get the same numbers as a JSON object
(`{"total": ..., "valid": ..., "invalid": ..., "error_count": ..., "action_items": [...]}`).
When nothing is invalid, the text form prints `action_items:` followed by
`- none`.

### 4. Proof-surface packet (`--proof-packet`)

Use this when provenance validation should feed `repo-proof-index` or a
release-readiness report. The packet is self-checked against the shared
`proof-surface` contract before it is printed, so producer drift fails before
entering the pipeline.

```bash
model-provenance-validator examples/envelopes/release.provenance.json --proof-packet
```

Output:

```json
{
  "proof_surface_version": "0.1",
  "packet_id": "model-provenance-validator-batch",
  "surface": "model provenance validation",
  "status": "ready",
  "claims": [
    {
      "claim": "Model/reference claims carry provenance envelopes.",
      "evidence": "total envelopes=1"
    },
    {
      "claim": "Envelope structure is validated before publication.",
      "evidence": "valid=1, invalid=0"
    },
    {
      "claim": "Invalid provenance is converted into action items.",
      "evidence": "validation errors=0"
    }
  ],
  "checks": [
    {
      "tool": "model-provenance-validator",
      "status": "pass",
      "summary": "valid=1, invalid=0, errors=0"
    }
  ],
  "action_items": []
}
```

`status` is `ready` and the check `status` is `pass` only when no envelope is
invalid; otherwise they are `blocked` and `fail`. Pipe the packet into the
shared index tooling:

```bash
model-provenance-validator *.provenance.json --proof-packet > provenance.packet.json
```

## Python API

The package exposes a small importable surface from
`model_provenance_validator`:

```python
from model_provenance_validator import (
    load_envelope,     # (path) -> dict   reads + JSON-parses an envelope file
    load_schema,        # (path=DEFAULT_SCHEMA) -> dict   loads a schema (bundled by default)
    validate_envelope,  # (envelope: dict, schema: dict) -> list[ValidationError]
    ValidationError,    # frozen dataclass with .path and .message
)
```

`validate_envelope` returns an empty list when the envelope is valid, and a
list of `ValidationError` objects otherwise. It does not raise on validation
failures; it only raises if you hand it something that is not a dict.

Example:

```python
from model_provenance_validator import load_envelope, load_schema, validate_envelope

schema = load_schema()  # bundled schema
envelope = load_envelope("examples/envelopes/release.provenance.json")
errors = validate_envelope(envelope, schema)

if not errors:
    print("valid")
else:
    for error in errors:
        print(f"{error.path}: {error.message}")
```

Expected output for the bundled example:

```text
valid
```

The error `message` text is already scrubbed of credential-shaped strings and
local absolute paths by the validator, matching the CLI's redaction behavior.

---

The expected output in this guide was captured by running the commands above
against the bundled example. JSON formatting (indentation, key order) is shown
as produced by the current version; treat exact whitespace as illustrative.
