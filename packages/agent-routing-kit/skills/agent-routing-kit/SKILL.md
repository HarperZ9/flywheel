---
name: agent-routing-kit
description: Deterministic task routing and context-budget workflow for public-safe agentic development. Use when Codex needs to choose a capability lane, split harmless utility modules from larger private systems, prepare compact handoffs, or check context size before loading files.
---

# Agent Routing Kit

Use this skill to route ordinary development work into simple capability lanes
and to keep public-safe extraction work separated from private systems.

## Workflow

1. State the task in one sentence.
2. Route it with the package CLI when available:

```bash
agent-route "write tests and docs for a Python CLI" --json
```

3. Treat routing as advisory. Use local repo context and tests as the final
   source of truth.
4. Keep `private` and `restricted` lanes out of public artifacts unless the
   user explicitly asks for a private-only plan.
5. Treat omitted private/restricted counts as a boundary signal, not as public
   content to expand.
6. Before loading large files, estimate context and prefer summaries, line
   ranges, or structured metadata when the budget status is `warn` or `over`.

## Public Extraction Rule

Extract small utilities only when they stand alone without:

- secrets, tokens, credentials, or `.env` data,
- private customer, target, corpus, or broker state,
- exploit payloads or live-operation paths,
- proprietary orchestration bundles,
- claims that cannot be verified from the public repo.

## Handoff Shape

Use this compact handoff when splitting tools:

```markdown
Utility:
Source:
Public-safe surface:
Private/restricted exclusions:
Tests:
Publication status:
```
