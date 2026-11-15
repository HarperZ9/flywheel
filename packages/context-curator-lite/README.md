<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/HarperZ9/context-curator-lite/main/docs/art/hero-dark.svg">
  <img src="https://raw.githubusercontent.com/HarperZ9/context-curator-lite/main/docs/art/hero-light.svg" alt="context-curator-lite: Builds token-efficient context bundles with redaction and source refs. Bundles of fine lines carry the work through 4 stations, extract, redact, bundle and hash, along a sweeping path into a bright core." width="100%">
</picture>

# context-curator-lite

Builds token-efficient context bundles with redaction and source refs.

```
context-curator-lite --root . --out-dir ./artifacts --telos-envelope
```

[![version: 0.2.0](https://img.shields.io/badge/version-0.2.0-e6e1d6?style=flat-square&labelColor=1a1712)](https://github.com/HarperZ9/context-curator-lite/releases/latest)
[![CI](https://github.com/HarperZ9/context-curator-lite/actions/workflows/ci.yml/badge.svg)](https://github.com/HarperZ9/context-curator-lite/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-MIT-e6e1d6?style=flat-square&labelColor=1a1712)](https://github.com/HarperZ9/context-curator-lite/blob/main/LICENSE)
![python 3.10+](https://img.shields.io/badge/python-3.10%2B-e6e1d6?style=flat-square&labelColor=1a1712)

Context Curator Lite extracts planning fragments from local text files, applies
heuristic redaction, and emits compact context bundles for agent session
continuity. It can also emit Project Telos context envelopes for receipt-chained
large-workspace handoffs.

## See it work, step by step

The [animated explainer](https://harperz9.github.io/repo-explainers/context-curator-lite.html)
walks through two sample files from a working session: keyword classification, scrubbing, the four-file bundle with its manifest checks, and the Telos envelope whose source refs point back to the originals. Every value on it is output from this repository. Its
source is [docs/explainer/index.html](docs/explainer/index.html).

## Walkthrough

Install it, run it once, then use the main feature. Each command below is real, and so is its output.

1. **Install.** Install from a checkout. Python 3.10 or newer.

   ```text
   $ git clone https://github.com/HarperZ9/context-curator-lite.git && cd context-curator-lite
   $ python -m pip install -e ".[test]"
   ```

2. **Scrub before it is stored.** Personal data and secrets are removed from text before curation.

   ```text
   >>> scrub("reach me at jane@example.com token=ghp_AAAA...A")
   reach me at <email> <redacted-secret>
   ```

3. **Curate a project.** Curate a project's notes and sessions into a bundle with a Telos envelope.

   ```text
   $ context-curator-lite --root ./proj --out-dir ./artifacts --telos-envelope
   "source_files_scanned": 2
   "raw_keyword_matches": 5
   "curated_records": 4
   "counts": {"next-action": 2, "blocker": 1, "idea": 1}
   "absolute_paths_included": false
   "raw_transcripts_copied": false
   ```

## Why it matters

Large codebases cannot be pushed into a model as raw text forever. This tool
keeps context small, reviewable, and replayable by preserving source references,
content hashes, and expansion commands instead of only compressed prose.

## Try it

```bash
(
  set -eu
  wheel="context_curator_lite-0.2.0-py3-none-any.whl"
  curl -fL -o "$wheel" \
    https://github.com/HarperZ9/context-curator-lite/releases/download/v0.2.0/context_curator_lite-0.2.0-py3-none-any.whl
  python - "$wheel" <<'PY'
from pathlib import Path
import hashlib
import sys
expected = "e0323946afe9a075c4916759c70280987e57813d5fc6126cfdcbbfdeb6cf1556"
actual = hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest()
if actual != expected:
    raise SystemExit(f"wheel sha256 mismatch: {actual}")
PY
  python -m pip install "./$wheel"
)
context-curator-lite --root . --out-dir ./artifacts --telos-envelope
```

## What to test first

- Run a local context bundle over a small repo.
- Inspect `curated-session-context-manifest.json`.
- Generate `project-telos-context-envelope.json` with `--telos-envelope`.

## Current status

Python package and CLI for local context preparation. Redaction is heuristic and
the generated bundle still requires human review before sharing.

## Existing technical notes

> Extract planning fragments and apply heuristic redaction to trim model context.

[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![version](https://img.shields.io/badge/version-0.2.0-informational.svg)
[![CI](https://github.com/HarperZ9/context-curator-lite/actions/workflows/ci.yml/badge.svg)](https://github.com/HarperZ9/context-curator-lite/actions/workflows/ci.yml)
![deps: none](https://img.shields.io/badge/deps-none-success.svg)
[![part of: AI-accountability toolkit](https://img.shields.io/badge/part_of-AI--accountability_toolkit-7a5cff.svg)](https://harperz9.github.io)

`context-curator-lite` extracts planning-like fragments from local text files,
redacts secret-shaped values heuristically, and emits a compact context bundle
for session continuity.

It can also emit a Project Telos context envelope for large-workspace agent
work. The compact summary stays reviewable and token-efficient, while each item
keeps source refs, content hashes, and expansion commands so future agents can
replay the context from the original files instead of trusting compressed prose.

The utility is lightweight by design. It helps a human prepare bounded context;
it is not a security boundary or a replacement for review before sharing.
Generated bundles use relative source references and root hashes instead of
absolute local paths.

## Install

`context-curator-lite` is not published on PyPI. Install the published v0.2.0 wheel from GitHub Releases after checking the asset hash:

```bash
(
  set -eu
  wheel="context_curator_lite-0.2.0-py3-none-any.whl"
  curl -fL -o "$wheel" \
    https://github.com/HarperZ9/context-curator-lite/releases/download/v0.2.0/context_curator_lite-0.2.0-py3-none-any.whl
  python - "$wheel" <<'PY'
from pathlib import Path
import hashlib
import sys
expected = "e0323946afe9a075c4916759c70280987e57813d5fc6126cfdcbbfdeb6cf1556"
actual = hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest()
if actual != expected:
    raise SystemExit(f"wheel sha256 mismatch: {actual}")
PY
  python -m pip install "./$wheel"
)
```

Release asset checks for v0.2.0:

- wheel: `e0323946afe9a075c4916759c70280987e57813d5fc6126cfdcbbfdeb6cf1556`
- sdist: `50bd0fa1fbb7efd34880c9538650b40647aab3f9ceb622aae8dec0b45f5c8958`

For source development, clone the repository and install it editable:

```bash
git clone https://github.com/HarperZ9/context-curator-lite.git
cd context-curator-lite
python -m pip install -e ".[test]"
python -m pytest
```

## Usage

```bash
context-curator-lite --root . --out-dir ./artifacts
context-curator-lite --root . --out-dir ./artifacts --limit 120 --per-file-limit 8
context-curator-lite --root . --out-dir ./artifacts --telos-envelope
```

Each run writes three files into `--out-dir`: a dated Markdown summary, a dated
JSONL bundle, and `curated-session-context-manifest.json` (also echoed to
stdout). See [USAGE.md](USAGE.md) for the full CLI/Python reference, worked
examples, and expected output. A runnable demo lives in
[`examples/demo.py`](examples/demo.py).

With `--telos-envelope`, the run also writes
`project-telos-context-envelope.json` using the
`project-telos.context-envelope/v1` shape. The envelope is designed for the
Gather -> Index -> Forum -> Crucible -> Telos workflow: it avoids absolute
paths, does not copy raw transcripts, marks hidden payloads as disabled, and
records that test evidence is unverifiable unless a downstream tool attaches
that receipt.

## Notes

- It is an agent-assisted tool and should be used with human review of the
  generated context.
- Redaction is heuristic and not a security boundary.
- Absolute root paths are omitted from generated bundles by default.

## Release Notes

- 0.2.0: Project Telos context-envelope export for receipt-chained large-context work.
- 0.1.0: initial package extraction and CLI.

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
