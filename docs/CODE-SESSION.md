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
`--output-format json` prints one result object (schema
`flywheel.code-result/v1`: final answer, steps, seconds, test verdict, ledger
head, chain check, token counts, session id); `--output-format stream-json`
prints one JSON object per loop event as it happens, then the result. The exit
code is 1 when the test gate fails or no model answered.

## Tokens

The session totals the token counts each hosted provider reports (OpenAI
compatible, Anthropic, Gemini) and Ollama's native counts. `/cost` shows them.
A call whose backend reported no counts is listed as uncounted; nothing is
estimated, and no price is applied.

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

In plan mode each request also tells the model it is read-only and asks for a
numbered plan of the changes and how to check them.

## Permission rules

Standing rules go in `.flywheel/permissions.json` in the project and
`permissions.json` in the Flywheel home; both are merged:

```json
{"allow": ["run:python -m pytest*", "write_file:src/*"],
 "deny":  ["run:git push*", "*:.env*"]}
```

A rule is `TOOL:PATTERN`, where TOOL is a tool name or `*` and PATTERN is a
shell-style wildcard over the command (for `run`) or the path (for file tools).
A deny rule wins over every mode, `auto` included, and over any allow rule. An
allow rule answers yes for you; it never opens what plan mode closes. A rules
file that cannot be read stops the session before it starts, because a deny
list that silently failed to load would protect nothing. The rules in force go
on the ledger, and each decision names the rule that made it.

## Todo list

For work with several steps the agent keeps a todo list with its `todo` tool
(pending, in progress, done). `/todo` shows it, and it is saved with the
session. The tool works in every mode, plan mode included.

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

## Undo and resume

Before a write tool changes a file, the session keeps that file's bytes as they
were at the start of the turn, or notes that the file did not exist. `/undo`
puts back the newest turn that changed files, byte for byte, deletes files that
turn created, and tells the model on the next turn which files went back.
Run it again to step further back. Snapshots live for the session; they are
not kept after it ends.

Each session is saved after every turn under the Flywheel home, in
`sessions/<id>/` (the ledger and a meta.json with the conversation). Each save
appends the sha256 of the conversation to the ledger first.
`flywheel code --continue` resumes the newest session for the folder,
`--resume ID` a named one, and `--sessions` lists them. A session whose chain
does not verify, or whose conversation no longer matches its recorded hash, is
refused. `--no-save` keeps a session off disk.

## Slash commands

`/help`, `/exit`, `/clear`, `/mode [plan|ask|edit|auto]`, `/model [ID]`,
`/status`, `/diff`, `/undo`, `/sessions`, `/todo`, `/cost`, `/init`. Slash commands never call
the model.

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
