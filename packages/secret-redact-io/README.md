<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/HarperZ9/secret-redact-io/main/docs/art/hero-dark.svg">
  <img src="https://raw.githubusercontent.com/HarperZ9/secret-redact-io/main/docs/art/hero-light.svg" alt="secret-redact-io: Guarded file, fetch and exec IO that strips secrets, hash-only receipts. Lines arrive from one side at a toothed ring around a bright core; most pass through and a few stop at the ring with a short cross mark." width="100%">
</picture>

# secret-redact-io

Guarded file, fetch and exec IO that strips secrets, hash-only receipts.

```
python -m pip install "secret-redact-io @ git+https://github.com/HarperZ9/secret-redact-io.git@v0.1.0"
```

[![version: 0.1.0](https://img.shields.io/badge/version-0.1.0-e6e1d6?style=flat-square&labelColor=1a1712)](https://github.com/HarperZ9/secret-redact-io/releases/latest)
[![license](https://img.shields.io/badge/license-MIT-e6e1d6?style=flat-square&labelColor=1a1712)](https://github.com/HarperZ9/secret-redact-io/blob/main/LICENSE)
![python 3.10+](https://img.shields.io/badge/python-3.10%2B-e6e1d6?style=flat-square&labelColor=1a1712)

Brand assets: `docs/art/` (hero, social preview) and `docs/brand/` (mark, lockups).

## See it work, step by step

The [animated explainer](https://harperz9.github.io/repo-explainers/secret-redact-io.html)
walks through the seven redaction rules, an in-memory redaction, guarded reads, dry-run writes and subprocess output, a receipt that holds no secret, and a credential in plain words that no rule can catch. Every value on it is output from this repository. Its
source is [docs/explainer/index.html](docs/explainer/index.html).

## Walkthrough

Install it, run it once, then use the main feature. Each command below is real, and so is its output.

1. **Install.** Install the pinned release from GitHub. Python 3.10 or newer; it is not on PyPI.

   ```text
   $ python -m pip install "secret-redact-io @ git+https://github.com/HarperZ9/secret-redact-io.git@v0.1.0"
   ```

2. **First run: redact text.** In Python, redact a token and a password before the text goes anywhere.

   ```text
   >>> policy.redact_text("token=ghp_bbbb...b\npassword=hunter2")
   token=[REDACTED:github_token] | password=[REDACTED:credential_field]
   counts: {'github_token': 1, 'credential_field': 1}
   total:  2
   ```

3. **Guard a write.** A guarded write in dry-run mode shows what it would write, redacted, and writes nothing.

   ```text
   >>> write_text_guarded(target, "api_key: ...", dry_run=True)
   text:     api_key: [REDACTED:credential_field]
   operation: write.dry_run
   written:  False
   file exists on disk: False
   ```

4. **Guard a command's output.** A guarded run redacts what the command prints.

   ```text
   >>> run_guarded(["python", "-c", "print('token=ghp_bbbb...b')"])
   returncode: 0
   stdout:     token=[REDACTED:github_token]
   redactions: {'github_token': 1}
   ```

## Why it matters

Agents need IO, but raw IO can leak credentials or private payloads into logs and model context. Secret Redact IO gives tools a small guarded boundary: outputs are redacted, receipts are hash-only, and the original secret-shaped values are not archived.

## What to test first

- Read a file that contains a fake token and confirm the returned text is redacted.
- Run the dry-run write path and inspect the receipt before anything is persisted.
- Execute a subprocess that prints a fake secret and confirm stdout is redacted.

## Technical framing

> Stdlib-only guarded file/fetch/subprocess IO: strips API keys, tokens, and PEM keys; emits hash-only receipts.

[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![version](https://img.shields.io/badge/version-0.1.0-informational.svg)
[![CI](https://github.com/HarperZ9/secret-redact-io/actions/workflows/tests.yml/badge.svg)](https://github.com/HarperZ9/secret-redact-io/actions/workflows/tests.yml)
![deps: none](https://img.shields.io/badge/deps-none-success.svg)
[![part of: AI-accountability toolkit](https://img.shields.io/badge/part_of-AI--accountability_toolkit-7a5cff.svg)](https://harperz9.github.io)

`secret-redact-io` is a small Python SDK and CLI for guarded IO. It wraps file
reads, file writes, HTTP fetches, and subprocess execution with redaction and
hash-only audit receipts.

The default posture is conservative:

- user-facing output is redacted before it is returned;
- guarded writes persist redacted content by default;
- receipts store byte counts, hashes, status metadata, and redaction counts;
- receipts do not archive raw input or raw secret values.

<p align="center"><img src="docs/art/guarded-lane.svg" alt="Eight stages from a guarded call to the caller, ending in redacted, untouched, or still leaking." width="100%"></p>

## Install

`secret-redact-io` is not currently published on PyPI. A bare
`python -m pip install secret-redact-io` will fail until a package registry
release exists.

For a pinned release install, use the GitHub release tag:

```bash
python -m pip install "secret-redact-io @ git+https://github.com/HarperZ9/secret-redact-io.git@v0.1.0"
```

For local examples and tests, use a source checkout:

```bash
git clone https://github.com/HarperZ9/secret-redact-io
cd secret-redact-io
python -m pip install -e ".[dev]"
```

## CLI

```bash
secret-redact-io read README.md --json
secret-redact-io write out.txt --content "note=hello" --dry-run --json
secret-redact-io fetch https://example.com --json
secret-redact-io exec --json -- python -c "print('hello')"
```

## Python API

```python
from secret_redact_io import read_text_guarded, run_guarded

read_result = read_text_guarded("README.md")
print(read_result.text)
print(read_result.receipt.to_json())

exec_result = run_guarded(["python", "-c", "print('hello')"])
print(exec_result.stdout)
```

## What a receipt records

<p align="center"><img src="docs/art/receipt-fields.svg" alt="The nine keys a guardrail receipt returns, one to a row, each with what fills it. Two are digests, over the input bytes and over the returned text. Three are counts: the length of the input, the length of what came back, and how many times each rule fired. Two are names: which operation ran, and what it acted on, trimmed to a path or a program name. One is a clock stamp. The last is metadata, and its row is accented, because the caller fills it and nothing redacts what goes in." width="100%"></p>

Nine keys, and seven of them are a hash, a count, or a name the tool trimmed itself. `target` keeps a path, a host and path, or a program name, and drops arguments and query strings before it is set. `metadata` is the exception: it holds what the caller handed over, and nothing redacts it.

## Usage

See [USAGE.md](USAGE.md) for an install line, the full CLI and Python API
surface, and worked examples with expected output. A runnable end-to-end
demo lives in [examples/demo.py](examples/demo.py).

## Boundary

This package is a public, self-contained guardrail utility. It does not include
credentials, secrets, or any deployment-specific configuration.

<p align="center"><img src="docs/art/blind-spots-lane.svg" alt="Eight stages across the honesty surface, ending in hash only, unmatched, or open field." width="100%"></p>

The policy is seven patterns and stays seven. Each one matches a shape, so a private key block, a key carrying a known prefix, or a value beside the word `password` is caught. A credential that reads as ordinary prose has no shape to match and survives the pass. That is the honest edge of the tool, and it is why the receipt reports which rules fired rather than claiming the text is clean.

---
**Zain Dana Harper** -- small tools with explicit edges.
[Portfolio](https://harperz9.github.io) · [HarperZ9](https://github.com/HarperZ9)
<sub>Built with Claude Code; reviewed, tested, and owned by me.</sub>

## For developers

Keep the public README, package metadata, and examples aligned with current behavior. Before opening a PR or pushing a release, run the local package verification path.

```bash
python -m pip install -e ".[dev]"
python -m pytest
python scripts/check_public_surface.py
python -m build
```

See [AGENTS.md](AGENTS.md) for the repo-specific operating boundary and
[CHANGELOG.md](CHANGELOG.md) for current delivery status.

---

Built by **[Zain Dana Harper](https://harperz9.github.io)** in Seattle: evidence-first tools that leave a re-checkable artifact behind. The full workbench is at [Project Telos](https://harperz9.github.io).
