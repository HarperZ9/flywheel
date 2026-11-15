# AGENTS.md - Agent Routing Kit

## Scope

This repository is a public-safe Python package and Codex plugin for
deterministic task routing and context-budget estimation.

Use this file for work in this repo. Hygiene rules are stated here so they travel
with the repo when it is cloned on its own: never commit secrets, `.env` files,
tokens, or private operational material to this public repository.

## Product Boundary

`agent-routing-kit` is a standalone utility. It may include:

- deterministic routing helpers in `src/agent_routing_kit/`,
- CLI behavior exposed through `agent-route`,
- public-safe plugin skill instructions in `skills/agent-routing-kit/`,
- tests, README material, release notes, and packaging metadata.

It must not include:

- private agent corpora, client data, target data, or broker state,
- credentials, tokens, browser profiles, `.env` values, or local vault data,
- live-operation paths, exploit payloads, or restricted workflow details,
- claims that cannot be verified from this public repo.

When extracting from a larger private system, keep only behavior that stands on
its own as a harmless developer utility. Replace private context with neutral
examples and tests.

## Repo Map

- `src/agent_routing_kit/routing.py` - capability catalog and deterministic
  scoring.
- `src/agent_routing_kit/budget.py` - conservative context-budget estimate.
- `src/agent_routing_kit/cli.py` - command-line interface.
- `skills/agent-routing-kit/SKILL.md` - Codex plugin skill surface.
- `tests/test_routing.py` - package regression tests.

## Development

Install locally:

```bash
python -m pip install -e .
```

Run the package:

```bash
python -m agent_routing_kit "write tests and docs for a Python CLI" --json
agent-route "write tests and docs for a Python CLI" --json
```

Run targeted verification before committing:

```bash
python -m pytest -q
python -m agent_routing_kit "write tests and docs for a Python CLI" --json
git diff --check
```

Before publishing, scan changed files for secrets. Do not commit `.env` files
or generated caches.

## Change Rules

- Keep routing deterministic and easy to test.
- Prefer small explicit catalogs over hidden model-state assumptions.
- Keep private and restricted lanes excluded from default output.
- Update tests when scoring behavior, CLI flags, or budget thresholds change.
- Keep plugin instructions aligned with package behavior.
