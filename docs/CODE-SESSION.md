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

In GitHub Actions, the repository's own action runs `flywheel code -p` and
keeps the ledger as an artifact; see [GITHUB-ACTION.md](GITHUB-ACTION.md).

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

## MCP servers

The session starts the MCP servers named in `mcp.json` in the Flywheel home,
and in the project's `.flywheel/mcp.json` and `.mcp.json`. The files use the
`mcpServers` shape that Claude Code and Cursor read, with a `command` and
`args` for a local server or `"type": "http"` and a `url` for a Streamable
HTTP one. Manage your own file with `flywheel mcp list`,
`flywheel mcp add NAME -- COMMAND [ARGS...]`, `flywheel mcp add NAME --url URL`
and `flywheel mcp remove NAME`; `--project` writes the project file instead.

A project file can name any program, so a project server starts only after you
answer yes at the prompt, or with `--trust-project-mcp`. In `-p` mode nobody
is there to ask, and project servers are skipped. Each tool reaches the model
as `mcp__<server>__<tool>` and is treated like a command: it asks in `ask` and
`edit`, runs in `auto`, and is refused in `plan`. A server that fails to start
is reported and skipped. `--no-mcp` starts none. Which servers started, from
which file, and with which tools goes on the ledger.

## Hooks

Hooks use Claude Code's `hooks` format, in `hooks.json` in the Flywheel home
and the project's `.flywheel/hooks.json`:

```json
{"hooks": {"PreToolUse": [{"matcher": "write_file|edit_file",
                           "hooks": [{"type": "command", "command": "python check.py"}]}]}}
```

Events: `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`,
`Stop`, `SessionEnd`. The command gets the event as JSON on stdin. A
`UserPromptSubmit` or `PreToolUse` hook blocks by exiting 2 (stderr is the
reason) or by printing `{"decision": "block", "reason": "..."}`; a blocked tool
call never runs, and the model is told why. Hook commands run as you, outside
the command sandbox, so a project's hooks run only after you say yes, or with
`--trust-project-hooks`. A hooks file that cannot be read stops the session.
Every hook run, its exit code and whether it blocked go on the ledger.

## Custom commands

A Markdown file in `.flywheel/commands/`, `.claude/commands/` or `commands/`
in the Flywheel home becomes a slash command named after the file. Its body is
sent as the request, with `$ARGUMENTS` replaced by the text after the command;
a `description:` line in front matter shows in `/help`. Built-in commands
cannot be replaced. Custom commands also work with `-p`, as in
`flywheel code -p "/review parser.py"`.

## Subagents

The agent can hand a piece of work to a subagent with its `task` tool. A
subagent starts on a fresh conversation with its own system prompt and its own
hash-chained ledger, and returns its final answer. Subagents are Markdown files
in `.flywheel/agents/`, `.claude/agents/` or `agents/` in the Flywheel home:

```markdown
---
name: reviewer
description: reviews a diff for bugs and missing tests
tools: read_file, grep, glob, list_dir
model: claude-sonnet-5
---
You review changes. Report each bug with its file and line.
```

`tools` limits what the subagent may call; `model` picks another model on the
same backend. One subagent is built in: `explore`, which can only read and
search. A subagent works under the session's permission mode, rules and
approval prompts, its file changes undo with the turn that started it, and it
cannot start subagents of its own. The session's ledger records each
subagent's name, ledger head and whether its chain verifies, and a saved
session keeps the subagent's ledger in `subagents/`. Subagents run one at a
time.

## Skills

Agent Skills folders (a folder with a `SKILL.md` whose front matter has a
`name` and `description`) are read from `.flywheel/skills/` and
`.claude/skills/` in the project and `skills/` in the Flywheel home. Only the
names and descriptions go into the system prompt; the model loads a skill's
full text with its `skill` tool when one fits. Loading a skill grants no
permission.

## Web pages

The `web_fetch` tool reads one page over HTTPS (plain HTTP only on loopback),
up to 512 KiB, as text, and its result names the status, type, size and sha256
of what came back. It counts as a network call: it asks in `ask` and `edit`,
runs in `auto`, and is refused in `plan`. Permission rules match the URL, so
`"deny": ["web_fetch:https://*.example.com/*"]` works. There is no web search
tool yet.

## In VS Code

The Flywheel extension for VS Code (`integrations/vscode`, packaged as a
`.vsix` by `python scripts/build_vscode_vsix.py`) opens `flywheel code` in a
terminal in your workspace and adds commands to start or continue a session
and to ask about the current file or selection, which it names with an `@`
mention and the line range. It has no dependencies and sends nothing anywhere
itself.

## In an editor (ACP)

`flywheel code --acp` speaks the Agent Client Protocol (protocol version 1,
written against schema v1.25.0) on stdin and stdout, so an ACP editor can host
Flywheel. In Zed, for example, add an agent server whose command is `flywheel`
with arguments `["code", "--acp"]`. Each editor session opens a coding session
in the editor's folder; the model's words stream as message chunks and every
tool call shows as a tool call with its result. A call the permission mode
would ask about goes to the editor as a permission request (allow, always
allow, reject). Cancelling in the editor stops the turn at the next model or
tool call. The MCP server list an editor sends with a new session is not
started yet; the servers in your Flywheel and project config are.

## Working in a separate checkout

`flywheel code --worktree NAME` runs the session in a git worktree at
`<repo>-worktrees/NAME`, beside the repository, on a new branch
`flywheel/NAME` from the current HEAD. Your uncommitted changes come along:
tracked edits are applied as a patch and untracked files that are not ignored
are copied. Your own checkout is not touched. When you are done, merge the
branch, or remove it with `git worktree remove`. The same name again continues
in the same worktree.

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

## Long sessions and @-mentions

When the conversation passes about 60,000 estimated tokens (`--compact-budget`;
0 turns it off), the session folds its middle into one summary before the next
model call. The first request and the latest turns stay verbatim, and the
ledger keeps the full record and the fold's receipt. `/compact` folds now and
`/context` shows the estimated size (at about 4 characters per token), the
budget and the instruction files in force. `@path` in a request attaches that
file from the project folder (up to 64 KiB each, 5 per request), and the ledger
records each attached file's sha256.

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
`/status`, `/diff`, `/undo`, `/sessions`, `/todo`, `/cost`, `/context`, `/compact`, `/init`. Slash commands never call
the model.

## The record

Every user turn, model reply, tool call, tool result, permission decision,
mode change and instruction file (by path and sha256) goes on one hash-chained
ledger. `/status` shows its head and whether the chain verifies.

## Screen readers

`--plain` (or `FLYWHEEL_SCREEN_READER=1`) prints tool activity in words, such
as `Tool call: run` and `Tool result, failed: ...`, in place of the `>`
markers. Output has no color and no spinners in either mode.

## Limits

- Commands cannot write into the project folder. A build or code generator
  that writes into the tree fails inside the session today; a writable
  workspace option for the sandbox is planned.
- The tool protocol is text lines, which any model can follow; native function
  calling is not used yet.
- This session has been tested with a scripted model. A run against each
  hosted provider is not part of the test suite.
