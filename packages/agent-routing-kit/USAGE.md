# Usage Guide

`agent-routing-kit` is a zero-dependency Python package and CLI that scores a
task against a small capability catalog, hides private/restricted lanes by
default (reporting how many were omitted), and estimates a conservative context
budget for the task text.

- Requires Python 3.9+.
- No third-party dependencies.

## Install

From a clone of the repository:

```bash
python -m pip install -e .
```

This installs the importable package `agent_routing_kit` and the console script
`agent-route` (entry point `agent_routing_kit.cli:main`).

You can also run the CLI without installing the console script, straight from
`src/`:

```bash
PYTHONPATH=src python -m agent_routing_kit "your task text"
```

## CLI

```
agent-route TASK [--include-private] [--max-results N] [--max-context N] [--json]
```

| Flag | Default | Effect |
| --- | --- | --- |
| `TASK` (positional) | required | Task text to route. |
| `--include-private` | off | Include `private`/`restricted` labels in the route instead of omitting them. |
| `--max-results N` | `3` | Maximum number of route matches to return. |
| `--max-context N` | `8000` | Token budget the task text is measured against. |
| `--json` | off | Emit a JSON object (`{"route": ..., "context": ...}`) instead of Markdown. |

By default the CLI prints a Markdown route followed by a one-line context
summary. With `--json` it prints `route.to_dict()` and `context.to_dict()`.

## Python API

```python
from agent_routing_kit import (
    route_task,        # score a task -> RouteResult
    estimate_context,  # estimate a context budget -> ContextBudget
    default_capabilities,  # the built-in capability catalog (tuple[Capability, ...])
    Capability,        # frozen dataclass: name, domain, description, keywords, risk
    RouteResult,       # frozen dataclass: .primary, .excluded_risk_counts, .to_dict(), .to_markdown()
    ContextBudget,     # frozen dataclass: .status, .ratio, .estimated_tokens, .to_dict()
)
```

Key signatures (from the source):

```python
route_task(
    task: str,
    capabilities: tuple[Capability, ...] | None = None,
    *,
    include_private: bool = False,
    max_results: int = 3,
) -> RouteResult

estimate_context(text: str, max_tokens: int = 8000) -> ContextBudget
```

`RouteResult` highlights:

- `result.primary` -> the top `Capability` (or `None` if nothing matched).
- `result.matches` -> tuple of `(Capability, score)` pairs, best first.
- `result.excluded` -> tuple of omitted `(Capability, score)` pairs.
- `result.excluded_risk_counts` -> e.g. `{"private": 1, "restricted": 1}`.
- `result.to_markdown()` / `result.to_dict()`.

`ContextBudget` highlights:

- `budget.status` -> `"fits"`, `"warn"` (ratio >= 0.75), or `"over"` (ratio >= 1).
- `budget.estimated_tokens` -> `round(len(text) / 4)` (min 1 for non-empty text).
- `budget.ratio`, `budget.characters`, `budget.max_tokens`, `budget.to_dict()`.

---

## Worked Examples

> Output blocks below were captured by running the commands at version `0.1.0`.

### 1. Default Markdown route (CLI)

```bash
agent-route "write tests and docs for a small Python CLI"
```

Expected output:

```
Task: write tests and docs for a small Python CLI

Route:
- python-packaging (engineering, score 2): Python packages, CLIs, pyproject metadata, import boundaries, and tests.
- documentation (publishing, score 1): READMEs, contributing guides, public positioning, release notes, and handoffs.

Context: 11/8000 tokens (fits)
```

### 2. JSON route (CLI)

```bash
agent-route "write tests and docs for a small Python CLI" --json
```

Expected output:

```json
{
  "route": {
    "task": "write tests and docs for a small Python CLI",
    "primary": "python-packaging",
    "excluded_risk_counts": {},
    "matches": [
      {
        "name": "python-packaging",
        "domain": "engineering",
        "description": "Python packages, CLIs, pyproject metadata, import boundaries, and tests.",
        "risk": "public",
        "score": 2
      },
      {
        "name": "documentation",
        "domain": "publishing",
        "description": "READMEs, contributing guides, public positioning, release notes, and handoffs.",
        "risk": "public",
        "score": 1
      }
    ]
  },
  "context": {
    "characters": 43,
    "estimated_tokens": 11,
    "max_tokens": 8000,
    "ratio": 0.0014,
    "status": "fits"
  }
}
```

### 3. Private lanes omitted by default, then opted in (CLI)

```bash
agent-route "design a frontend dashboard with private broker credentials"
```

Expected output:

```
Task: design a frontend dashboard with private broker credentials

Route:
- frontend-engineering (engineering, score 2): Interfaces, dashboards, browser behavior, accessibility, and interaction design.

Private/restricted matches omitted by default: private=1

Context: 15/8000 tokens (fits)
```

Add `--include-private` to surface the omitted lane:

```bash
agent-route "design a frontend dashboard with private broker credentials" --include-private
```

Expected output:

```
Task: design a frontend dashboard with private broker credentials

Route:
- frontend-engineering (engineering, score 2): Interfaces, dashboards, browser behavior, accessibility, and interaction design.
- private-corridor (governance, score 2): Private-only work that should not be published as a standalone utility.

Context: 15/8000 tokens (fits)
```

### 4. Python API

```python
from agent_routing_kit import route_task, estimate_context

result = route_task("write docs and tests for a Python package")
budget = estimate_context("some model-bound context", max_tokens=8000)

print(result.to_markdown())
print("primary:", result.primary.name)
print("budget:", budget.status, budget.estimated_tokens, budget.ratio)
```

Expected output:

```
Task: write docs and tests for a Python package

Route:
- python-packaging (engineering, score 2): Python packages, CLIs, pyproject metadata, import boundaries, and tests.
- documentation (publishing, score 1): READMEs, contributing guides, public positioning, release notes, and handoffs.
primary: python-packaging
budget: fits 6 0.0008
```

## How scoring works

For each capability, the score is the number of its keywords that appear as
whole tokens in the lowercased task (tokens are matched via `[a-z0-9]+`), plus a
`+2` bonus if the capability's name (with `-` replaced by a space) appears as a
substring of the task. Capabilities with a non-`public` risk are routed only
when `include_private=True` / `--include-private`; otherwise they are counted in
`excluded_risk_counts` and reported as omitted.
