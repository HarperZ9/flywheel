# Contributing

Agent Routing Kit accepts small, reviewable changes that keep the package
public-safe and dependency-light.

## Ground Rules

- Do not add secrets, `.env` files, private corpus data, credentials, customer
  data, live infrastructure details, or proprietary internal prompts.
- Do not add exploit payloads, credential workflows, covert operations, broker
  execution code, or private orchestration bundles.
- Keep the default catalog harmless and publishable.
- Add tests for routing changes.
- Keep public claims modest and verifiable.

## Local Checks

```bash
python -m pytest
python -m agent_routing_kit "write docs and tests for a Python package" --json
```
