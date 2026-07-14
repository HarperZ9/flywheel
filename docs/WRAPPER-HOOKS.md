# Wrapper hooks: the scaffold for harnesses that are not Flywheel

The engine's own message paths (route, companion, OpenAI-compat plain
and streaming, agent) freeze named sources before answering and chain
a turn receipt. A wrapper that is not Flywheel gets the same guarantee
by mounting one hook script; the gateway does the work.

## What ships

`scripts/hooks/wrapper_scaffold_hook.py`: reads a prompt event on
stdin, extracts URLs, freezes each through `POST /api/snapshot`, and
prints a provenance manifest for the wrapper to inject as context. It
fails open and silent: a dead gateway or a promptless event costs
nothing and never blocks a turn. Degraded sources are named with
reasons, never faked.

## Mounting

Claude Code (`settings.json` or a project `.claude/settings.json`):

```json
{"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command",
  "command": "python C:/path/to/scripts/hooks/wrapper_scaffold_hook.py"}]}]}}
```

Any other harness with prompt-time hooks mounts it the same way: pipe
the prompt event as JSON on stdin, inject stdout as context. The
script reads `prompt`, `user_prompt`, `message`, or `input`, so most
event shapes work unmodified.

## What the injected manifest gives the model

- Every URL the user named, with the sha256 of its frozen bytes,
  fetched before the model started working.
- A named degradation for every source that could not be frozen.
- The instruction to cite by byte range against the hashes, which the
  engine's `verify_citations` can then check mechanically.

## Boundary

The hook covers perception (freeze before work). The post-pass (turn
receipt chaining the answer hash) belongs to the harness's stop-hook
slot and needs the wrapper to hand over the final answer text; that
wiring is per-wrapper and not shipped here yet. A wrapper that wants
the full guarantee today routes through `POST /api/route` or the
OpenAI-compat surface instead, where both passes run engine-side.
