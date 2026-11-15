<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/HarperZ9/proof-surface-report/main/docs/art/hero-dark.svg">
  <img src="https://raw.githubusercontent.com/HarperZ9/proof-surface-report/main/docs/art/hero-light.svg" alt="proof-surface-report: Render proof packets and receipts into reviewer-facing Markdown. A fan of ruled sheets drawn in fine lines, the top sheet lit by a bright core." width="100%">
</picture>

# proof-surface-report

Render proof packets and receipts into reviewer-facing Markdown.

```
python -m pip install -e .
```

[![CI](https://github.com/HarperZ9/proof-surface-report/actions/workflows/ci.yml/badge.svg)](https://github.com/HarperZ9/proof-surface-report/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-MIT-e6e1d6?style=flat-square&labelColor=1a1712)](https://github.com/HarperZ9/proof-surface-report/blob/main/LICENSE)
![python 3.10+](https://img.shields.io/badge/python-3.10%2B-e6e1d6?style=flat-square&labelColor=1a1712)

Proof Surface Report turns proof-surface packets and compatible receipt files
into a readable Markdown handoff. It validates input shape and rejects language
that would overstate the output as approval, certification, or compliance.

## See it work, step by step

The [animated explainer](https://harperz9.github.io/repo-explainers/proof-surface-report.html)
walks through the bundled packet and witness receipt rendered into one Markdown handoff, and the guards that refuse a certified title, an approved claim and a TRUSTED verdict. Every value on it is output from this repository. Its
source is [docs/explainer/index.html](docs/explainer/index.html).

## Walkthrough

Install it, run it once, then use the main feature. Each command below is real, and so is its output.

1. **Install.** Install the proof-surface contract, then this package. Python 3.10 or newer.

   ```text
   $ pip install git+https://github.com/HarperZ9/proof-surface.git
   $ git clone https://github.com/HarperZ9/proof-surface-report && cd proof-surface-report
   $ pip install .
   ```

2. **First run: render a report.** Render a packet and a receipt into one report.

   ```text
   $ proof-surface-report examples/public-surface.packet.json examples/emet.receipt.json
   # Proof Surface Handoff Report
   This report summarizes proof-surface artifacts. It is an evidence handoff,
   not a certification, safety verdict, or authority claim.
   | Packets | 1 |  | Witness receipts | 1 |  | Aggregate status | needs-polish |
   ### Claims
   - Public text hygiene is checkable. Evidence: em-dash findings=1
   ### Action Items
   - README.md:14: replace em dash with plain punctuation
   ## Witness Receipt: emet-verify-example-7d26e03c2a4f13b0
   | Verdict | MATCH |
   ```

3. **An inflated title is refused.** A title that claims more than the evidence shows is refused.

   ```text
   $ proof-surface-report examples/public-surface.packet.json --title "Certified release review"
   error: report title validation failed: $.title contains authority-shaped wording: certified
   ```

## Why it matters

Receipts are useful only when reviewers can read them quickly. This tool keeps
the report grounded in evidence while preventing handoff text from becoming a
false authority claim.

## Try it

```bash
python -m pip install -e .
proof-surface-report examples/public-surface.packet.json examples/emet.receipt.json
python -m pytest -q
```

## What to test first

- Render the bundled example packet and receipt.
- Override the title with `--title` and confirm language checks still apply.
- Run the tests before changing report wording or validation rules.

## Current status

Small Python adapter with a CLI and synthetic examples. It is a reviewer handoff
renderer, not a release approval system.

## Existing technical notes

> Render proof-surface packets and receipts as reviewer-facing Markdown; rejects authority-shaped language on output.

[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![version](https://img.shields.io/badge/version-0.1.0-informational.svg)
[![CI](https://github.com/HarperZ9/proof-surface-report/actions/workflows/ci.yml/badge.svg)](https://github.com/HarperZ9/proof-surface-report/actions/workflows/ci.yml)
[![part of: AI-accountability toolkit](https://img.shields.io/badge/part_of-AI--accountability_toolkit-7a5cff.svg)](https://harperz9.github.io)

`proof-surface-report` is a small Python adapter. Its only runtime dependency
is the shared [`proof-surface`](https://github.com/HarperZ9/proof-surface)
contract package, which it uses to validate artifacts; beyond that it relies
solely on the Python standard library. It validates two neutral artifact shapes
and renders reviewer-facing Markdown:

- a **proof-surface packet** (`proof_surface_version: "0.1"`): a surface, a
  status, factual claims with evidence, tool checks, and action items.
- an **EMET witness receipt**: a verdict plus witness facts (implementation,
  spec version, self-hash, check), subjects with digests, and run evidence.

The output is an **evidence handoff**, not a certification, trust verdict,
safety decision, or compliance finding. To keep it that way, the renderer
rejects authority-shaped wording (for example "certified", "approved",
"safe to release", "compliant") anywhere it appears in artifact text or in the
report title, and it rejects unknown fields and ungoverned receipt verdicts.

It is part of the EMET suite. EMET is the umbrella brand; this leaf is named
descriptively for what it does.

## Install

The package uses a `src/` layout. Its single runtime dependency is the
`proof-surface` contract package, which is distributed from git:

```bash
pip install git+https://github.com/HarperZ9/proof-surface.git
pip install .
```

This installs a `proof-surface-report` console script.

For local development without installing, put the package on the path with
`PYTHONPATH=src` (the `proof-surface` package must still be importable).

## Usage

As a console script:

```bash
proof-surface-report examples/public-surface.packet.json examples/provenance.packet.json examples/emet.receipt.json
```

As a module (development checkout):

```bash
PYTHONPATH=src python -m proof_surface_report examples/public-surface.packet.json examples/emet.receipt.json
```

Override the report title (still language-checked):

```bash
proof-surface-report --title "Release Surface Handoff" examples/public-surface.packet.json
```

The report is written to stdout. On validation or IO error the tool prints an
`error:` line to stderr and exits non-zero.

For a step-by-step walkthrough with worked examples and expected output, see
[USAGE.md](USAGE.md).

## Examples

The `examples/` directory contains synthetic, public artifacts:

- `public-surface.packet.json` -- a public-release surface packet.
- `provenance.packet.json` -- a model-provenance packet.
- `emet.receipt.json` -- an EMET witness receipt.

Keep claims factual and evidence-backed. Do not phrase them as approval,
certification, compliance, or release safety; such phrasing is rejected before
rendering.

## Development

```bash
PYTHONPATH=src python -m pytest -q
```

## Provenance

This adapter was extracted as a standalone tool from an internal reporting
project. It shares no code with that project's reporting core; its only runtime
dependency is the shared `proof-surface` contract package, and otherwise it uses
only the Python standard library.

## License

[MIT](LICENSE)

---
**Zain Dana Harper** -- small tools with explicit edges.
[Portfolio](https://harperz9.github.io) · [HarperZ9](https://github.com/HarperZ9)
<sub>Built with Claude Code; reviewed, tested, and owned by me.</sub>

## For developers

Keep the public README, package metadata, and examples aligned with current behavior. Before opening a PR or pushing a release, run the local package verification path.

```bash
python -m pip install -e ".[test]"
python -m pytest
```

See [AGENTS.md](AGENTS.md) for the repo-specific operating boundary and
[CHANGELOG.md](CHANGELOG.md) for current delivery status.

---

Built by **[Zain Dana Harper](https://harperz9.github.io)** in Seattle: evidence-first tools that leave a re-checkable artifact behind. The full workbench is at [Project Telos](https://harperz9.github.io).
