<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/HarperZ9/model-provenance-validator/main/docs/art/hero-dark.svg">
  <img src="https://raw.githubusercontent.com/HarperZ9/model-provenance-validator/main/docs/art/hero-light.svg" alt="model-provenance-validator: Validate model and release claims against small provenance envelopes. A chain of small linked squares, each holding a few ruled lines, winds inward to a bright core." width="100%">
</picture>

# model-provenance-validator

Validate model and release claims against small provenance envelopes.

```
python -m pip install -e ".[test]"
```

[![version: 0.1.1](https://img.shields.io/badge/version-0.1.1-e6e1d6?style=flat-square&labelColor=1a1712)](https://pypi.org/project/model-provenance-validator/)
[![CI](https://github.com/HarperZ9/model-provenance-validator/actions/workflows/ci.yml/badge.svg)](https://github.com/HarperZ9/model-provenance-validator/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-MIT-e6e1d6?style=flat-square&labelColor=1a1712)](https://github.com/HarperZ9/model-provenance-validator/blob/main/LICENSE)
![python 3.10+](https://img.shields.io/badge/python-3.10%2B-e6e1d6?style=flat-square&labelColor=1a1712)

Model Provenance Validator checks the JSON envelope that says what a claim is
about, where its source came from, when it was retrieved, and what validation
status can be published. It redacts credential-shaped values from its own output.

## See it work, step by step

The [animated explainer](https://harperz9.github.io/repo-explainers/model-provenance-validator.html)
walks through the bundled envelope validated, the invalid fixture's four errors with their paths, a refused status word, and a batch summary and proof packet. Every value on it is output from this repository. Its
source is [docs/explainer/index.html](docs/explainer/index.html).

## Walkthrough

Install it, run it once, then use the main feature. Each command below is real, and so is its output.

1. **Install.** Install from PyPI and clone for the examples. Python 3.10 or newer.

   ```text
   $ python -m pip install model-provenance-validator
   $ git clone https://github.com/HarperZ9/model-provenance-validator && cd model-provenance-validator
   ```

2. **First run: a valid envelope.** Validate the bundled release envelope.

   ```text
   $ model-provenance-validator examples/envelopes/release.provenance.json
   examples/envelopes/release.provenance.json: valid
   ```

3. **An invalid envelope.** Each problem is named.

   ```text
   $ model-provenance-validator tests/fixtures/invalid.json
   tests/fixtures/invalid.json: invalid
     $.subject: expected non-empty string
     $.source.kind: invalid value 'unknown-kind'; expected one of: official-doc, paper, release-note, local-fixture, other
     $.references: expected at least 1 item(s)
     $.validation.extra: unexpected field
   ```

4. **A proof packet.** Write the result as a packet.

   ```text
   $ model-provenance-validator examples/envelopes/release.provenance.json --proof-packet
   "surface": "model provenance validation"
   "status": "ready"
   "claims": envelopes=1; valid=1, invalid=0; validation errors=0
   "checks": [{"tool": "model-provenance-validator", "status": "pass", "summary": "valid=1, invalid=0, errors=0"}]
   "action_items": []
   ```

## Why it matters

Model cards, README claims, release notes, and agent reports become fragile when
source references are informal. This tool makes the reference shape explicit
enough to validate, summarize, and hand off.

## Try it

```bash
python -m pip install -e ".[test]"
model-provenance-validator examples/envelopes/release.provenance.json
python -m pytest
```

## What to test first

- Validate `examples/envelopes/release.provenance.json`.
- Run `model-provenance-validator *.provenance.json --summary --json`.
- Emit a proof packet with `--proof-packet`.

## Current status

Python package and CLI with proof-surface integration. It validates envelope
shape and report hygiene; it does not certify the underlying claim.

## Existing technical notes

> Validate provenance envelopes; redact secret-shaped values out of its own output.

[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![version](https://img.shields.io/badge/version-0.1.1-informational.svg)
[![CI](https://github.com/HarperZ9/model-provenance-validator/actions/workflows/ci.yml/badge.svg)](https://github.com/HarperZ9/model-provenance-validator/actions/workflows/ci.yml)
[![part of: AI-accountability toolkit](https://img.shields.io/badge/part_of-AI--accountability_toolkit-7a5cff.svg)](https://harperz9.github.io)

`model-provenance-validator` keeps model and release claims attached to small,
checkable provenance envelopes. It validates the JSON shape that says what the
claim is about, where the reference came from, when it was retrieved, and what
validation status a maintainer is willing to publish.

The package includes a small schema validator for the envelope shape used by
the CLI. Its one runtime dependency is `proof-surface`, the shared package that
owns the proof-surface packet contract emitted by `--proof-packet`.

Use it when a README, report, model-card note, release packet, or AI workflow
claim needs a source reference before the claim is repeated publicly.

## Install

```bash
python -m pip install model-provenance-validator
```

For local development:

```bash
python -m pip install -e ".[test]"
python -m pytest
```

## Usage

See [USAGE.md](USAGE.md) for an install line, the full CLI/API surface, and
worked examples with expected output.

```bash
model-provenance-validator envelope.json
model-provenance-validator envelope.json --json
model-provenance-validator *.provenance.json --summary
model-provenance-validator *.provenance.json --summary --json
model-provenance-validator *.provenance.json --proof-packet
model-provenance-validator *.provenance.json
```

The command exits with status `1` when any envelope fails validation. Malformed
or unreadable envelope files are reported as invalid results so batch runs can
continue and produce a complete action list. Result paths are printed relative
to the current directory when possible, and validation messages redact
credential-shaped strings and local absolute paths.

Use a custom schema:

```bash
model-provenance-validator envelope.json --schema schema.json
```

Run the bundled example:

```bash
model-provenance-validator examples/envelopes/release.provenance.json
```

![Eight stages of validating one provenance envelope: envelope, root shape, subject and source, references, calendar check, validation block, scrub, and exit code. An envelope is a single JSON object with five required fields. The root refuses unexpected fields by naming them rather than ignoring them, and the same rule applies to every nested object at every depth. Subject says which claim the envelope is about; source says what kind of thing it came from, drawn from five kinds: official documentation, a paper, a release note, a local fixture, or other. References must carry at least one entry, and each entry needs a name, a locator, and a retrieval date. The date is checked twice: once against the ten-character pattern and once against the calendar, so a well-shaped date that never existed is still an error. The validation block carries a status of verified, partial, or unknown. Every message is scrubbed before it is printed. A batch exits zero only when nothing in it was invalid. Three outcomes: valid, invalid, and no schema.](docs/art/envelope-lane.svg)

## Envelope shape

Required top-level fields:

- `envelope_version`
- `subject`
- `source`
- `references`
- `validation`

Allowed `source.kind` values:

- `official-doc`
- `paper`
- `release-note`
- `local-fixture`
- `other`

Allowed `validation.status` values:

- `verified`
- `partial`
- `unknown`

Each `references[].retrieved_at` value must use `YYYY-MM-DD` date shape and be
a valid calendar date.

## Minimal valid envelope

```json
{
  "envelope_version": "1",
  "subject": "public-surface-sweeper README claim",
  "source": {
    "name": "public-surface-sweeper README",
    "kind": "release-note"
  },
  "references": [
    {
      "name": "Repository README",
      "locator": "https://github.com/HarperZ9/public-surface-sweeper",
      "retrieved_at": "2026-06-13"
    }
  ],
  "validation": {
    "status": "verified",
    "notes": "Claim checked against the public README surface."
  }
}
```

## Example text output

```text
release.provenance.json: valid
draft.provenance.json: invalid
  $.references: expected at least 1 item(s)
```

## Example JSON output

```json
[
  {
    "path": "release.provenance.json",
    "valid": true,
    "errors": []
  }
]
```

## Example summary output

```text
total: 3
valid: 2
invalid: 1
error_count: 1
action_items:
- draft.provenance.json: resolve 1 validation error(s)
```

![Eight stages of a batch run: batch, per file, tally, action items, status, packet, self-check, and handoff. One command takes many envelope files. A file that cannot be read, or that is not JSON, becomes a single error attached to the root rather than a crash, so it still counts toward the tally. The tally records four numbers: total, valid, invalid, and the total error count. Action items are one line per invalid file, capped at the first eight, so a large broken batch produces a readable list rather than a wall. Status is ready when nothing was invalid and blocked otherwise. The packet carries three claims and one check. Before printing, the packet is validated against the shared proof-surface contract, and a packet that fails that check is written to standard error rather than standard output. The result is readable by the proof index without this tool present. Three outcomes: ready, blocked, and not printed.](docs/art/packet-lane.svg)

## Proof-surface packet output

Use `--proof-packet` when provenance validation should feed `repo-proof-index`
or a release-readiness report. The packet follows the shared proof-surface
interop shape: claims, checks, and action items in one JSON object. The generated
packet is self-checked before printing so producer drift fails before entering
the pipeline.

```bash
model-provenance-validator *.provenance.json --proof-packet > provenance.packet.json
repo-proof-index provenance.packet.json --summary
```

## What it validates

- required fields;
- JSON object and array shape;
- non-empty string fields where required;
- exact constants such as `envelope_version: "1"`;
- enum values for source kind and validation status;
- string pattern constraints such as `references[].retrieved_at`;
- calendar-date validation for `references[].retrieved_at`;
- unexpected fields when `additionalProperties` is false.

![Eleven redaction rules, one to a row, with what each shape becomes and why it is on the list. A null byte becomes a space, and it is replaced first so nothing downstream can be split by it. A private key block is redacted from its opening line to its closing line, the only rule that spans more than one line. Cloud access key ids are matched by two prefixes and sixteen uppercase characters. Three token prefixes are matched by shape, each requiring twenty characters or more so that a short lookalike is left alone. The accented row is the named-secret rule: bearer, token, api key, password or secret in any case, followed by a colon or an equals sign, which is the only rule that catches a secret whose shape nobody has catalogued in advance. Two path rules remove drive-letter paths and six absolute prefixes below the root, with the second written so that a URL path is not swept up. Whitespace is collapsed after redaction, never before, which is a real gap: a token broken across two lines matches no prefix rule and survives, and the row says so. Messages over two hundred and forty characters are cut at two hundred and thirty-seven and closed with an ellipsis, and because truncation runs last, a long message is redacted before any of it is discarded.](docs/art/redaction-rules.svg)

## What it does not do

- It does not fetch the referenced source.
- It does not decide whether the underlying claim is true.
- It does not prove a model is safe.
- It does not certify provenance.
- It does not replace human review of the referenced material.

## Release-readiness use

`model-provenance-validator` is the provenance-envelope point in a proof-surface
pipeline:

```text
claim -> source reference -> provenance envelope -> validation result -> proof index
```

Its job is to keep model/reference claims from floating without a source,
retrieval date, and validation status.

---
**Zain Dana Harper** -- small tools with explicit edges.
[Portfolio](https://harperz9.github.io) | [HarperZ9](https://github.com/HarperZ9)
<sub>Built with Claude Code; reviewed, tested, and owned by me.</sub>

## For developers

Keep the public README, package metadata, and examples aligned with current behavior. Before opening a PR or pushing a release, run the local package verification path.

```bash
python -m pip install -e ".[test]"
python -m pytest
```

---

Built by **[Zain Dana Harper](https://harperz9.github.io)** in Seattle: evidence-first tools that leave a re-checkable artifact behind. The full workbench is at [Project Telos](https://harperz9.github.io).
