# flywheel code

`flywheel code` opens a coding session in the current folder. You type a
request; the agent reads files, edits them and runs commands to finish it, and
the next request starts from what the last one did. It ships in the base
install, `python -m pip install flywheel-verify`, with no extra packages.

The shape of a session (illustrative, abridged; the model's words vary):

```text
$ flywheel code
flywheel> add a --verbose flag to cli.py and run the tests
  > read_file {"path": "cli.py"}
    ok ...
  > edit_file {"path": "cli.py", ...}
  allow edit_file {...}? [y]es [n]o [a]lways: y
    ok edited cli.py (1 replacement)
  > run {"cmd": "python -m pytest -q"}
  allow run {...}? [y]es [n]o [a]lways: y
    ok [exit 0]
Added --verbose; the tests pass.
[4 step(s) | 9.2s | chain ok | ledger 3f9a1c0d2e44]
```

For one request from a script: `flywheel code -p "fix the failing test" --mode edit`.

## Models

The session uses the first model it can reach, in this order: a local server
(serve.py, then Ollama), a hosted provider whose key is set
(`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`,
`OPENROUTER_API_KEY`, `GLM_API_KEY`), then the `claude` or `codex` CLI on PATH.
`--backend NAME` pins one, `--model ID` picks its model, `--local-only` never
calls a hosted provider, and `/model ID` switches mid-session. `flywheel doctor`
shows what is set.

## Permission modes

| Mode | Reads | Writes | Commands |
|---|---|---|---|
| `plan` | run | refused | refused |
| `ask` (default) | run | ask | ask |
| `edit` | run | run | ask |
| `auto` | run | run | run |

Answer `a` (always) to stop asking for that tool for the rest of the session.
In `-p` mode nobody is there to ask, so a call that would ask is refused; pass
`--mode edit` or `--mode auto`. In every mode the command denylist and the
pre-action monitor still apply, and plan mode closes writes and commands at the
tool gate itself, not only in the prompt.

## Commands run in a sandbox

On Windows, commands run in the low-integrity sandbox; on Linux and macOS, in
bubblewrap or Seatbelt when installed. The project folder is read-only to
commands: files change only through the agent's write tools, which are gated
and receipted. TEMP and HOME point at a scratch folder per command, and
`PYTHONDONTWRITEBYTECODE=1` and `PYTEST_ADDOPTS=-p no:cacheprovider` keep Python
tools from writing caches into the tree. A host with no sandbox refuses
commands unless `FLYWHEEL_ALLOW_UNSANDBOXED=1` is set, and then every output is
labeled unsandboxed.

## Project instructions

The session reads `AGENTS.md`, `CLAUDE.md` and `FLYWHEEL.md` from the folder up
to the repository root, plus `AGENTS.md` in the Flywheel home, nearest file
last, up to 32 KiB in all. It never climbs to your home folder. `/init` drafts
an `AGENTS.md` for the folder and never overwrites one. `--no-instructions`
skips them.

## Slash commands

`/help`, `/exit`, `/clear`, `/mode [plan|ask|edit|auto]`, `/model [ID]`,
`/status`, `/diff`, `/init`. Slash commands never call the model.

## The record

Every user turn, model reply, tool call, tool result, permission decision,
mode change and instruction file (by path and sha256) goes on one hash-chained
ledger. `/status` shows its head and whether the chain verifies.

## Limits

- Commands cannot write into the project folder. A build or code generator
  that writes into the tree fails inside the session today; a writable
  workspace option for the sandbox is planned.
- The tool protocol is text lines, which any model can follow; native function
  calling is not used yet.
- This session has been tested with a scripted model. A run against each
  hosted provider is not part of the test suite.
