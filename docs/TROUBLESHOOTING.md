# Troubleshooting

Run `flywheel doctor` first. It checks Python, the installed version, the
Flywheel home, Git, which provider keys are set (by name only), whether a local
model server answers and whether relay is installed, and it prints the next
step for anything that is not ready. `flywheel doctor --json` gives the same
checks for a bug report.

## "No model is reachable"

`flywheel code` found no local server, no provider key and no `claude` or
`codex` CLI on PATH. Do one of these:

- `flywheel setup --provider anthropic` (or openai, gemini, deepseek,
  openrouter) to store a key.
- Set a provider key in the environment; the [configuration](CONFIGURATION.md)
  page lists them.
- Start a local server such as Ollama.

## The wrong model answered

The session uses the first model it can reach, local servers first. If a local
server is running, it answers before a hosted provider. Pin one with
`--backend NAME` (for example `--backend claude` for the Anthropic API or
`--backend codex` for the OpenAI API), pick its model with `--model ID`, or
switch mid-session with `/model ID`. `/status` shows which backend and model
are live.

## A tool call was refused in `-p` mode

With `-p` nobody is at the keyboard to answer a permission prompt, so a call
that would ask is refused. Pass `--mode edit` (writes run, commands ask, so
commands are refused) or `--mode auto` (both run). Deny rules and the command
denylist still apply in every mode.

## A build or code generator fails inside a session

Commands run in a sandbox where the project folder is read-only; files change
only through the agent's write tools, which are gated and recorded. A command
that writes into the tree, such as a build that writes `dist/`, fails today.
Run that step yourself, or ask the agent to make the change with its file
tools.

## "[refused] no OS sandbox on this host"

On Linux, install bubblewrap (`bwrap`). macOS has Seatbelt built in; Windows
uses its low-integrity sandbox. To run commands without a sandbox anyway, set
`FLYWHEEL_ALLOW_UNSANDBOXED=1`; every output is then labeled unsandboxed.

## Project MCP servers or hooks did not start

A project file can name any program, so project MCP servers and hooks start
only after you say yes at the prompt. In `-p` mode nobody is there to say yes,
so they are skipped. Pass `--trust-project-mcp` or `--trust-project-hooks` when
you trust the project. Servers in your own `mcp.json` in the Flywheel home
start without asking.

## The session stopped before it started, naming a rules or hooks file

A `permissions.json` or `hooks.json` that cannot be read stops the session on
purpose: a deny list that silently failed to load would protect nothing. Fix
the JSON the message names, then start again.

## A saved session will not resume

Resume refuses a session whose ledger chain does not verify, whose head differs
from the one recorded, or whose conversation no longer matches its recorded
hash. That means the saved files were changed after the session saved them.
Start a new session; the refused one stays on disk under `sessions/` in the
Flywheel home for you to inspect.

## An MCP server asks for a sign-in

Run `flywheel mcp login NAME`. Servers that need a client id registered in
advance are not supported yet.

## `flywheel relay` says relay is not installed

relay, the older chat-first coding agent, is a separate lane. Install it with
`flywheel install --lanes relay`. For agentic coding in the terminal,
`flywheel code` is in the base install.

## The Flywheel home is not writable

Set `FLYWHEEL_HOME` to a folder you own. Everything Flywheel keeps for you
moves with it.

## A command crashed

Flywheel writes a crash report to `crashes/` in the Flywheel home and prints
its path. Your home folder is replaced by `~` and secret-looking environment
values by their names. Nothing is sent. Set `FLYWHEEL_DEBUG=1` to see the raw
traceback instead.

## Still stuck

Open an issue with `flywheel doctor --json`, the command you ran and what you
expected; [support](../SUPPORT.md) has the details.
