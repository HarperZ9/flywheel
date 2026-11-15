<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/HarperZ9/public-surface-sweeper/main/docs/art/hero-dark.svg">
  <img src="https://raw.githubusercontent.com/HarperZ9/public-surface-sweeper/main/docs/art/hero-light.svg" alt="public-surface-sweeper: Check a repo public surface for missing files and secret-shaped values. Lines arrive from one side at a toothed ring around a bright core; most pass through and a few stop at the ring with a short cross mark." width="100%">
</picture>

# public-surface-sweeper

Check a repo public surface for missing files and secret-shaped values.

```
python -m pip install -e ".[test]"
```

[![version: 0.1.3](https://img.shields.io/badge/version-0.1.3-e6e1d6?style=flat-square&labelColor=1a1712)](https://github.com/HarperZ9/public-surface-sweeper/releases/latest)
[![CI](https://github.com/HarperZ9/public-surface-sweeper/actions/workflows/ci.yml/badge.svg)](https://github.com/HarperZ9/public-surface-sweeper/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-MIT-e6e1d6?style=flat-square&labelColor=1a1712)](https://github.com/HarperZ9/public-surface-sweeper/blob/main/LICENSE)
![python 3.10+](https://img.shields.io/badge/python-3.10%2B-e6e1d6?style=flat-square&labelColor=1a1712)

Public Surface Sweeper audits public and developer delivery surfaces for
GitHub-facing repositories. It checks whether a repo explains itself clearly,
has runnable handoff material, carries release/status metadata, avoids
secret-shaped values, and can feed proof-surface evidence workflows.

## See it work, step by step

The [animated explainer](https://harperz9.github.io/repo-explainers/public-surface-sweeper.html)
walks through the bundled clean fixture, a copy with a missing license and a secret-shaped value, its score and action items, its proof packet, and the flags that decide what fails the run. Every value on it is output from this repository. Its
source is [docs/explainer/index.html](docs/explainer/index.html).

## Walkthrough

Install it, run it once, then use the main feature. Each command below is real, and so is its output.

1. **Install.** Install from a checkout. Python 3.10 or newer.

   ```text
   $ git clone https://github.com/HarperZ9/public-surface-sweeper && cd public-surface-sweeper
   $ python -m pip install -e ".[test]"
   ```

2. **First run: a clean repository.** Sweep the bundled clean example.

   ```text
   $ public-surface-sweeper examples/clean-repo --summary
   score: 100
   status: ready
   total_findings: 0
   errors: 0
   warnings: 0
   action_items:
   - none
   ```

3. **A repository with a problem.** Sweep a repository that carries a finding. The sweep blocks it.

   ```text
   $ public-surface-sweeper ./repo
   ERROR LICENSE required-file: missing required file: LICENSE
   ERROR notes.txt:1 aws-access-key: AWS access key shaped value
   ```

4. **A proof packet.** Write the result as a packet another tool can check.

   ```text
   $ public-surface-sweeper ./repo --proof-packet
   "surface": "repo public release surface"
   "status": "blocked"
   Required public release files are visible.   required-file findings=1
   Secret-shaped values are surfaced before publication.   secret-shaped findings=1
   Public text hygiene is checkable.   em-dash findings=0
   Public and developer delivery are inspectable.   delivery findings=0
   check: public-surface-sweeper  fail  score=50, findings=2
   ```

## Why it matters

Small public repos often fail on simple delivery details: missing license,
unclear README, accidental credential-shaped strings, or unreviewed release
claims. This tool makes those checks quick and repeatable.

## Try it

```bash
python -m pip install -e ".[test]"
public-surface-sweeper examples/clean-repo
python -m pytest
```

## What to test first

- Run the clean fixture and expect `No findings.`
- Run `public-surface-sweeper . --summary`.
- Emit a proof packet with `--proof-packet`.

## Current status

Python package and CLI. It checks public clarity, developer handoff material,
workspace-scale delivery drift, and secret-shaped values; it is not a full
security scanner or certification tool.

## Existing technical notes

> Audit public and developer delivery surfaces before a repository asks for trust.

[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![version](https://img.shields.io/badge/version-0.1.3-informational.svg)
[![CI](https://github.com/HarperZ9/public-surface-sweeper/actions/workflows/ci.yml/badge.svg)](https://github.com/HarperZ9/public-surface-sweeper/actions/workflows/ci.yml)
[![part of: AI-accountability toolkit](https://img.shields.io/badge/part_of-AI--accountability_toolkit-7a5cff.svg)](https://harperz9.github.io)

Use it before a repository asks a user, customer, reviewer, investor, or future
maintainer to trust what it says.

It is intentionally narrow: a release-hygiene gate, not a full security scanner
or certification tool.

## Install

Download the reviewed wheel or source archive from a GitHub Release, then
install the local artifact:

```bash
python -m pip install ./public_surface_sweeper-0.1.3-py3-none-any.whl
```

## For developers

For local development:

```bash
python -m pip install -e ".[test]"
python -m pytest
```

## Usage

See [USAGE.md](USAGE.md) for an install line, the full CLI and Python API,
worked examples, and expected output.

```bash
public-surface-sweeper .
public-surface-sweeper . --json
public-surface-sweeper . --summary
public-surface-sweeper . --summary --json
public-surface-sweeper . --proof-packet
public-surface-sweeper . --fail-on warning
public-surface-sweeper path/to/workspace --workspace --json
```

The command exits with status `1` when error-level findings are present.
In workspace mode, the command also exits with status `1` when discovery is
empty or unverifiable, so a zero-repository matrix does not pass as a clean
portfolio gate.

Use `--fail-on warning` to fail on warnings and errors, or `--fail-on none` to
print findings without failing the process.

Run the bundled clean fixture:

```bash
public-surface-sweeper examples/clean-repo
```

Expected output:

```text
No findings.
```

Scan every GitHub-facing repository under a workspace root:

```bash
public-surface-sweeper path/to/workspace --workspace
```

Workspace mode discovers local repositories with GitHub remotes, deduplicates
multiple checkouts of the same remote, runs the single-repo sweep against each
one's forward-facing delivery surface, and emits a delivery matrix with
separate public, developer, and boundary verdicts. The matrix is public-safe by
default: it includes repository names, GitHub slugs, relative paths, scores,
counts, and action items, but not absolute local paths, raw secret values,
network calls, or filesystem writes.

Discovery reads local Git metadata only. It recognizes standard `.git/config`
repositories and linked Git worktree `.git` files whose `gitdir:` pointer leads
to a Git worktree metadata directory with a matching backpointer and common-dir
relationship. Unvalidated external Git metadata, including symlinked `.git`
markers, is reported as `UNVERIFIABLE` before config is read. If a workspace
contains no Git repositories, no GitHub-facing remotes, or unreadable Git
metadata, the matrix reports `workspace_status` and `coverage.empty_reason`
instead of treating an empty result as success.

## What it checks

A sweep walks one repository and applies every rule below to what it finds
on disk. The order matters at the end, where two filters remove candidate
findings that another rule has already accounted for.

![Eight stages of a single sweep: root, skip list, readable, punctuation, required, contract, credentials, filters. The walk starts at the repository root and covers everything under it. Twenty five directory names are never entered, among them the virtual environment, the build output and the caches. A file is read only if it decodes as UTF-8, holds no null byte, and is under a megabyte. An em dash anywhere in a scanned file is an error rather than a note. Four files have to be present at the root by name. Five further rules ask whether the release surface is inspectable at all: a changelog, funding metadata, agent instructions, usage docs and a workflow. Five known credential shapes are matched by their own patterns, then a generic name-equals-value rule catches the rest. Two filters drop candidates before they are counted: a span a provider rule already claimed, and a value that reads as a placeholder. Three outcomes: ready, needs polish, and blocked.](docs/art/sweep-lane.svg)

The workspace mode runs that same sweep across every GitHub-facing checkout
under a root, then reduces each repository to three verdicts and takes the
worst of them.

![Eight stages of the workspace matrix: walk, git metadata, remote, duplicates, surface, public, developer, status. Every directory under the given root is walked once, skipping the same build and cache names the single sweep skips. A repository is recognized by a readable Git config, either from a normal `.git` directory or a linked worktree `.git` file. Only a remote that parses as a GitHub slug is kept, so a local-only checkout is passed over with coverage recorded. When two checkouts share a slug the shallower path wins, and a mirror directory loses on purpose. Each surviving repository is scanned across its named files, its workflows and its docs, rather than its whole tree. Six rules decide the public verdict. Four more decide the developer verdict. The overall status is the worst of the three verdicts rather than an average, so one drift or unreadable metadata is enough.](docs/art/matrix-lane.svg)

Required project files:

- `README.md`
- `LICENSE`
- `AUTHORS.md`
- `CONTRIBUTING.md`

Text hygiene:

- em dash characters in public-facing text

README delivery:

- public value, status, or use-case section
- developer entry point and workflow section
- runnable command block
- substantive non-badge visual asset

Forward-facing repository delivery:

- changelog or release notes for public status
- GitHub funding metadata for sponsor-button support
- `AGENTS.md` or equivalent agent/developer instructions
- standalone `USAGE.md` or docs usage guide
- GitHub workflow evidence under `.github/workflows/`

Workspace delivery:

- GitHub-facing repository discovery from local `.git/config` remotes and
  validated linked worktree `.git` files
- duplicate-checkout deduplication by GitHub remote
- local wrapper repository traversal for workspaces that contain nested repos
- explicit empty and unreadable-metadata coverage in workspace matrices
- fast delivery-surface scanning instead of full source-tree scanning
- public/developer delivery verdicts per repository
- normalized contract rules for receipt chains and dashboards
- release-readiness counts across a whole local portfolio
- JSON output suitable for receipt chains and dashboard ingestion

Secret-shaped values:

- private key block markers
- GitHub token shaped values
- OpenAI key shaped values
- AWS access key shaped values
- Slack token shaped values
- generic credential assignments such as `token: <value>`, `api_key=<value>`,
  `client_secret=<value>`, and `password=<value>` when the value is not an
  obvious placeholder

![Ten of the rules a sweep applies, one to a row, each with its severity and what it had to read. Five errors cover missing required files, an em dash, a PEM private key header, a GitHub token prefix, and an AWS access key identifier. Four warnings cover a README without a substantive image, a README without all three developer entry points, absent funding metadata, and an absent workflow file. The generic credential assignment row is accented, because it is the one rule whose match can still be dropped: by a provider rule that already claimed the same span, or by a value that reads as a placeholder.](docs/art/rule-severity.svg)

The scanner skips common cache, build, virtualenv, dependency, and local
agent-tool state directories such as `.superpowers` and `.telos`.
It also skips binary files and text files larger than 1 MB.
Secret-shaped labels and placeholders such as `YOUR_API_KEY_HERE`, `redacted`,
or `example-token-placeholder` are ignored so findings stay value-focused.
Delivery findings are warning-level by default so existing repos can be migrated
without blocking secret and required-file gates.

## Example text output

```text
ERROR LICENSE required-file: missing required file: LICENSE
ERROR README.md:12 em-dash: replace em dash with plain punctuation
```

## Example JSON output

```json
[
  {
    "path": "LICENSE",
    "line": 0,
    "rule": "required-file",
    "severity": "error",
    "message": "missing required file: LICENSE"
  }
]
```

## Example summary output

```text
score: 75
status: blocked
total_findings: 1
errors: 1
warnings: 0
action_items:
- LICENSE: missing required file: LICENSE
```

Summary mode is the fastest handoff format for release reviews. It gives a
bounded readiness score, a status, finding counts, and the first actionable
items to fix before publishing or showing the repository to a reviewer.

## Proof-surface packet output

Use `--proof-packet` when the scan result should feed `repo-proof-index` or a
release-readiness report. The packet follows the shared proof-surface interop
shape: claims, checks, and action items in one JSON object. The generated packet
is self-checked before printing so producer drift fails before entering the
pipeline.

```bash
public-surface-sweeper . --proof-packet > public-surface.packet.json
repo-proof-index public-surface.packet.json --summary
```

## What it does not do

- It does not perform exploit testing.
- It does not audit dependencies for vulnerabilities.
- It does not validate whether a credential is real.
- It does not certify that a repository is safe, compliant, or trustworthy.
- It does not replace a security review.

## Release-readiness use

`public-surface-sweeper` is the first point in a proof-surface pipeline:

```text
repo public surface -> hygiene findings -> proof index -> release-readiness report
```

Its job is to catch basic public-surface defects before a repository asks users,
clients, employers, or reviewers to trust it.

---
**Zain Dana Harper** - small tools with explicit edges.
[Portfolio](https://harperz9.github.io) · [HarperZ9](https://github.com/HarperZ9)
<sub>Built with Claude Code; reviewed, tested, and owned by me.</sub>

---

Built by **[Zain Dana Harper](https://harperz9.github.io)** in Seattle: evidence-first tools that leave a re-checkable artifact behind. The full workbench is at [Project Telos](https://harperz9.github.io).
