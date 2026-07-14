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

## The post-pass

`scripts/hooks/wrapper_turn_receipt_hook.py` completes the guarantee
from the wrapper's stop-hook slot: it sends the prompt and final
answer to `POST /api/scaffold`, which runs both passes engine-side and
chains the turn receipt (prompt hash, answer hash, frozen sources)
into the audit ledger. Same failure posture: open and silent, and a
turn that could not be banked is simply not banked, never faked.

Claude Code mount for the pair:

```json
{"hooks": {
  "UserPromptSubmit": [{"hooks": [{"type": "command",
    "command": "python <abspath>/scripts/hooks/wrapper_scaffold_hook.py"}]}],
  "Stop": [{"hooks": [{"type": "command",
    "command": "python <abspath>/scripts/hooks/wrapper_turn_receipt_hook.py"}]}]
}}
```

## Boundary

The stop-hook can only bank what the wrapper hands it: if the event
shape carries no final answer text, the receipt records the prompt
side only. `POST /api/scaffold` also accepts a `citations` list
(offset-bound, per docs on verify_citations) so a wrapper that cites
byte ranges gets them verified in the same receipt.
