<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/HarperZ9/agent-routing-kit/main/docs/art/hero-dark.svg">
  <img src="https://raw.githubusercontent.com/HarperZ9/agent-routing-kit/main/docs/art/hero-light.svg" alt="agent-routing-kit: Route agent tasks by capability, risk, and context budget. Lines arrive from one side at a toothed ring around a bright core; most pass through and a few stop at the ring with a short cross mark." width="100%">
</picture>

# agent-routing-kit

Route agent tasks by capability, risk, and context budget.

```
python -m pip install -e .
```

[![version: 0.1.0](https://img.shields.io/badge/version-0.1.0-e6e1d6?style=flat-square&labelColor=1a1712)](https://github.com/HarperZ9/agent-routing-kit/releases/latest)
[![CI](https://github.com/HarperZ9/agent-routing-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/HarperZ9/agent-routing-kit/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-MIT-e6e1d6?style=flat-square&labelColor=1a1712)](https://github.com/HarperZ9/agent-routing-kit/blob/main/LICENSE)
![python 3.9+](https://img.shields.io/badge/python-3.9%2B-e6e1d6?style=flat-square&labelColor=1a1712)

Agent Routing Kit is a deterministic routing helper for coding-agent workflows.
It scores a task against a small capability catalog, marks public/private risk,
and estimates context usage before a session spends tokens on the wrong lane.

## Why it matters

Large workspaces need explicit routing. A route summary and handoff receipt give
an agent enough shape to start in the right place without pulling private
assumptions or unbounded context into a public task.

## Try it

```bash
python -m pip install -e .
agent-route "write tests and docs for a small Python CLI" --json
python -m pytest
```

## What to test first

- Route a plain coding task and inspect the selected capability.
- Route a task with `--include-private` and compare omitted risk counts.
- Import `route_task` and `estimate_context` from Python.

## Current status

Public-safe Python package, CLI, and Codex skill extraction. It is advisory
routing, not an authorization or policy engine.

## Existing technical notes

> Deterministic task-routing and context-budget helpers -- explicit edges, no deps.

[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![python](https://img.shields.io/badge/python-3.9%2B-blue.svg)
![version](https://img.shields.io/badge/version-0.1.0-informational.svg)
[![CI](https://github.com/HarperZ9/agent-routing-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/HarperZ9/agent-routing-kit/actions/workflows/ci.yml)
![deps: none](https://img.shields.io/badge/deps-none-success.svg)
[![part of: AI-accountability toolkit](https://img.shields.io/badge/part_of-AI--accountability_toolkit-7a5cff.svg)](https://harperz9.github.io)

Agent Routing Kit is a tiny routing and context-budget utility for agentic
development work. It makes a task's likely lane visible before a model session
starts loading files, spending context, or crossing from public utility work
into private workflow assumptions.

This is the public-safe extraction of a larger private workspace pattern: make
capability routing explicit, keep context budgets visible, and separate
publishable utility code from private operational systems.

## What It Does

- Scores a task against a small capability catalog.
- Labels capabilities as `public`, `private`, or `restricted`.
- Excludes private/restricted lanes by default and reports omitted risk counts.
- Estimates context usage with a conservative token approximation.
- Emits concise Markdown or JSON handoff summaries.
- Ships as both a Python package and a Codex plugin skill.

It does not include private agent corpora, credentials, target data, live
operations, exploit logic, broker integrations, or proprietary project state.

## Install

```bash
python -m pip install -e .
```

## CLI

```bash
agent-route "write tests and docs for a small Python CLI" --json
agent-route "design a frontend dashboard" --include-private
```

## Python

```python
from agent_routing_kit import route_task, estimate_context

result = route_task("write docs and tests for a Python package")
budget = estimate_context("some model-bound context", max_tokens=8000)

print(result.to_markdown())
print(budget.status)
```

## Usage

See [USAGE.md](USAGE.md) for an install line, the full CLI flag set, the
importable API, and worked examples with their expected output. A runnable
end-to-end script lives in [`examples/demo.py`](examples/demo.py).

## Codex Plugin

The repo root is also a Codex plugin. The plugin provides a compact skill for:

- choosing a simple route for a coding task,
- splitting harmless utilities from larger private systems,
- checking context budget before loading files,
- preparing public-safe handoff summaries.

## Design Rules

- Prefer deterministic scoring over hidden model state.
- Keep private and restricted lanes out of default output.
- Show when private or restricted matches were omitted.
- Treat routing as advisory, not authority.
- Keep small tools independent enough to publish.
- Make claims testable.

## Contributors

- Zain Dana Harper - author and maintainer.
- Claude Code - AI coding contributor for implementation and packaging assistance.

The maintainer reviews and owns public release decisions, security posture, and
final claims.

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

---

Built by **[Zain Dana Harper](https://harperz9.github.io)** in Seattle: evidence-first tools that leave a re-checkable artifact behind. The full workbench is at [Project Telos](https://harperz9.github.io).
