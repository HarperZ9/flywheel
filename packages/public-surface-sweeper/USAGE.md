# Usage Guide

`public-surface-sweeper` audits public and developer delivery surfaces for
GitHub-facing repositories. It checks required project files, public-facing
text, README clarity, release/status metadata, developer handoff material,
workflow evidence, and secret-shaped values. It is a delivery gate, not a
vulnerability scanner.

This guide covers the real CLI and the importable Python API. Every flag,
command, and function shown here exists in the current source.

## Install

Download the reviewed wheel or source archive from a GitHub Release, then
install the local artifact:

```bash
python -m pip install ./public_surface_sweeper-0.1.3-py3-none-any.whl
```

For local development from a clone:

```bash
python -m pip install -e ".[test]"
python -m pytest
```

Requires Python 3.10+.

## Command line

The console script is `public-surface-sweeper`. You can also invoke it as a
module with `python -m public_surface_sweeper`.

```
public-surface-sweeper [ROOT] [--json] [--summary] [--proof-packet] [--workspace] [--fail-on {none,warning,error}]
```

- `ROOT` - repository root to scan. Optional; defaults to `.`.
- `--json` - print findings as a JSON array.
- `--summary` - print a release-readiness summary instead of individual findings.
- `--summary --json` - print the summary as a JSON object.
- `--proof-packet` - print a proof-surface interop packet as JSON.
- `--workspace` - discover GitHub-facing repos under `ROOT` and print a
  delivery matrix.
- `--fail-on {none,warning,error}` - minimum severity that returns a failing
  exit code. Default is `error`.

The process exits `1` when findings at or above the `--fail-on` threshold are
present, otherwise `0`. Required-file, punctuation, and secret-shaped findings
are errors. README and forward-facing delivery contract findings are warnings.

In workspace mode, the process exits `1` when any repository is `DRIFT` or
`UNVERIFIABLE`, when Git metadata is unreadable, or when discovery is empty.
Use `--fail-on none` for report-only workspace output. Workspace mode reads
local Git metadata to identify GitHub remotes, including normal `.git/config`
repositories and linked Git worktree `.git` files that validate against Git
backpointer and common-dir metadata. Unvalidated external Git metadata and
symlinked `.git` markers are reported as `UNVERIFIABLE` before config is read.
It then deduplicates multiple local checkouts of the same remote. It traverses
local-only wrapper repositories so nested GitHub repos are still found, then
scans each repository's forward-facing delivery surface instead of its full
source tree. It does not call the network, validate credentials, include
absolute paths, or write files.
Local agent-tool state such as `.superpowers` and `.telos` is excluded from
the scan so generated planning receipts do not drown out the public surface.

## Python API

```python
from pathlib import Path
from public_surface_sweeper.sweeper import (
    scan,
    summarize_findings,
    format_text,
    format_summary,
    proof_surface_packet,
)

findings = scan(Path("examples/clean-repo"))   # list[Finding]
summary = summarize_findings(findings)          # SweepSummary
print(format_text(findings))                    # human-readable text
print(format_summary(summary))                  # human-readable summary
packet = proof_surface_packet(Path("."), findings)  # dict (proof-surface shape)
```

`scan(root)` returns a sorted `list[Finding]`. Each `Finding` has the fields
`path`, `line`, `rule`, `severity`, and `message`. `summarize_findings`
returns a `SweepSummary` with `score`, `status`, `total_findings`, `errors`,
`warnings`, and `action_items`.

Workspace delivery matrix:

```python
from pathlib import Path
from public_surface_sweeper.workspace import (
    build_delivery_matrix,
    discover_forward_facing_repos,
)

repos = discover_forward_facing_repos([Path("path/to/workspace")])
matrix = build_delivery_matrix([Path("path/to/workspace")])
print(matrix["counts"])
```

## Worked examples

The expected output below was produced by running the commands against the
bundled `examples/clean-repo` fixture and a small repository that is missing
two required files and contains an em dash and a GitHub-token-shaped value.

### 1. Scan a clean repository

```bash
public-surface-sweeper examples/clean-repo
```

Expected output:

```text
No findings.
```

Exit code: `0`.

### 2. Scan a repository with problems (text)

Given a repo missing `AUTHORS.md` and `CONTRIBUTING.md`, with an em dash on
line 2 of `README.md` and a GitHub-token-shaped value on line 3:

```bash
public-surface-sweeper ./my-repo
```

Expected output:

```text
ERROR AUTHORS.md required-file: missing required file: AUTHORS.md
ERROR CONTRIBUTING.md required-file: missing required file: CONTRIBUTING.md
ERROR README.md:2 em-dash: replace em dash with plain punctuation
ERROR README.md:3 github-token: GitHub token shaped value
```

Exit code: `1`.

### 3. Release-readiness summary

```bash
public-surface-sweeper ./my-repo --summary
```

Expected output:

```text
score: 0
status: blocked
total_findings: 4
errors: 4
warnings: 0
action_items:
- AUTHORS.md: missing required file: AUTHORS.md
- CONTRIBUTING.md: missing required file: CONTRIBUTING.md
- README.md:2: replace em dash with plain punctuation
- README.md:3: GitHub token shaped value
```

The same data as a JSON object:

```bash
public-surface-sweeper examples/clean-repo --summary --json
```

Expected output:

```json
{
  "score": 100,
  "status": "ready",
  "total_findings": 0,
  "errors": 0,
  "warnings": 0,
  "action_items": []
}
```

### 4. Proof-surface packet for a pipeline

```bash
public-surface-sweeper ./my-repo --proof-packet > public-surface.packet.json
```

Expected output (for the problem repo above):

```json
{
  "proof_surface_version": "0.1",
  "packet_id": "public-surface-sweeper-my-repo",
  "surface": "my-repo public release surface",
  "status": "blocked",
  "claims": [
    {
      "claim": "Required public release files are visible.",
      "evidence": "required-file findings=2"
    },
    {
      "claim": "Secret-shaped values are surfaced before publication.",
      "evidence": "secret-shaped findings=1"
    },
    {
      "claim": "Public text hygiene is checkable.",
      "evidence": "em-dash findings=1"
    },
    {
      "claim": "Public and developer delivery are inspectable.",
      "evidence": "delivery findings=0"
    }
  ],
  "checks": [
    {
      "tool": "public-surface-sweeper",
      "status": "fail",
      "summary": "score=0, findings=4"
    }
  ],
  "action_items": [
    "AUTHORS.md: missing required file: AUTHORS.md",
    "CONTRIBUTING.md: missing required file: CONTRIBUTING.md",
    "README.md:2: replace em dash with plain punctuation",
    "README.md:3: GitHub token shaped value"
  ]
}
```

The generated packet is self-validated before printing. If validation fails,
the command writes an error to stderr and exits `1`.

### 5. Workspace delivery matrix

```bash
public-surface-sweeper path/to/workspace --workspace --json
```

Expected output shape:

```json
{
  "schema": "public-surface-sweeper.delivery-matrix/v1",
  "repository_count": 2,
  "counts": {
    "MATCH": 1,
    "DRIFT": 1,
    "UNVERIFIABLE": 0
  },
  "workspace_status": "DRIFT",
  "coverage": {
    "root_count": 1,
    "git_repository_count": 2,
    "github_repository_count": 2,
    "unknown_repository_count": 0,
    "empty_reason": null,
    "diagnostics": []
  },
  "privacy_boundary": {
    "absolute_paths_included": false,
    "raw_secret_values_included": false,
    "network_calls_performed": false,
    "filesystem_writes_performed": false
  },
  "repositories": [
    {
      "name": "ready-tool",
      "path": "ready-tool",
      "remote": "HarperZ9/ready-tool",
      "status": "MATCH",
      "score": 100,
      "public_delivery": "MATCH",
      "developer_delivery": "MATCH",
      "boundary": "MATCH",
      "findings": {
        "total": 0,
        "errors": 0,
        "warnings": 0,
        "rules": {},
        "action_items": []
      }
    }
  ]
}
```

The `public_delivery` verdict covers public value, required release files,
README visual assets, public text hygiene, changelog or release notes, and
funding metadata. The `developer_delivery` verdict covers developer entry
points, workflow notes, runnable commands, agent instructions, standalone usage
docs, and CI/workflow evidence. The `boundary` verdict covers secret-shaped
values in the delivery surface. Use normal single-repo mode when you need a
full source-tree secret-shaped value sweep.

If workspace discovery finds no Git repositories, the JSON contains
`workspace_status: "EMPTY"` and `coverage.empty_reason:
"no_git_repositories"`. If it finds only local repositories with no GitHub
remote, the empty reason is `"no_github_repositories"`. If a `.git` file points
to a missing, unreadable, or unvalidated Git directory, or if `.git` is a
symlink, `workspace_status` becomes `"UNVERIFIABLE"` and
`coverage.diagnostics` lists a relative path plus reason.

## Exit codes

- `0` - no findings at or above the `--fail-on` threshold.
- `1` - findings at or above the threshold, or a proof-packet that failed
  internal validation. In workspace mode, this also means at least one
  repository is `DRIFT` or `UNVERIFIABLE`, Git metadata is unreadable, or
  discovery is empty.

Use `--fail-on none` to print findings without failing the process (useful in
report-only mode), or `--fail-on warning` to also fail on warnings.
