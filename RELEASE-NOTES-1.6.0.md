# Flywheel 1.6.0

`flywheel code` opens a coding session in your terminal, in the base install.
You type a request; the agent reads, edits and runs your tests across turns, on
any model you can reach: a local server, a hosted provider key, or the claude or
codex CLI. It asks before it writes or runs anything unless you choose a mode
that does not, puts back a turn's file changes with `/undo`, saves and resumes
sessions, reads AGENTS.md and CLAUDE.md, starts the MCP servers you configure,
runs your hooks, and serves editors over the Agent Client Protocol. Every turn,
tool call and permission decision lands on one hash-chained ledger you can
recheck. `flywheel doctor` checks an install, `flywheel update` says whether a
newer release is out, and a crash leaves a local report that sends nothing.

## Behaviour changes to check before you upgrade

- **The installed `flywheel` command enters through `cli_entry.console_main`.**
  An unhandled exception now writes a crash report under the Flywheel home and
  exits 70 instead of printing a bare traceback. `FLYWHEEL_DEBUG=1` restores the
  traceback. `harness.cli_entry.main` is unchanged for callers. (#382)
- **`--help` on gate, up, lanes, loop-status, down, corpus-export and why prints
  usage and runs nothing.** `flywheel gate --help` used to run the gate and write
  `artifacts/gate`. (#382)
- **Hosted backends carry the provider's token counts** on the response as
  `x_token_usage`. The existing word-count `usage` field is unchanged. (#384)

## flywheel code (#383, #384, #385)

- Multi-turn agentic session on the in-package gated loop; `-p REQUEST` for one
  request, with `--output-format text|json|stream-json`.
- Permission modes `plan`, `ask` (default), `edit`, `auto`, decided before the
  existing gate, pre-action monitor and receipts. Standing allow and deny rules
  in `.flywheel/permissions.json`; deny wins over every mode.
- `/undo` restores the newest changing turn byte for byte. Sessions save after
  every turn; `--continue`, `--resume ID`, `--sessions`. A session whose chain,
  head or conversation does not verify is refused.
- Project instructions from AGENTS.md, CLAUDE.md and FLYWHEEL.md; `/init`
  drafts one.
- `todo` tool, plan-mode prompt, `/cost` with provider-reported tokens (none
  estimated, no price applied).
- MCP servers from `.mcp.json`-shaped files, user trusted, project asks first;
  `flywheel mcp list|add|remove`.
- Hooks in Claude Code's format (SessionStart, UserPromptSubmit, PreToolUse,
  PostToolUse, Stop, SessionEnd) and Markdown custom slash commands.
- Agent Skills (SKILL.md) loaded on demand; `web_fetch` over HTTPS.
- `--worktree NAME` works in a git worktree beside the repository on branch
  `flywheel/NAME`, carrying your uncommitted changes; `--plain` prints tool
  activity in words for screen readers.
- `flywheel code --acp`: an ACP agent (protocol version 1, schema v1.25.0) for
  Zed, JetBrains and VS Code ACP hosts.
- Commands run in the OS sandbox with a scratch TEMP and HOME. The earlier
  default runner gave sandboxed commands no writable temp folder, so
  `python -m pytest` failed inside it; that is fixed for the session.

See docs/CODE-SESSION.md.

## Install and support (#382)

- `flywheel doctor [--json]`, `flywheel update [--json]`, local crash reports.
- The bare-install relay message names `flywheel install --lanes relay`.
- README and GETTING-STARTED name the current release, issue templates, SUPPORT.md.

## Also in this release

- The explainer and README show the 1.5.1 release films. (#379)
- The ablation runner refuses a criterion run that gives no readable verdict instead of counting it. (#380)
- The 1.1.2 notes cite advisory GHSA-g5gv-7893-ff5c. (#381)

## Monitor rule pack

The pre-action monitor's rule pack is unchanged from 1.5.1, so a pinned
`expected_rules_digest` stays valid. `flywheel monitor owner` prints it as
`installed_rules_digest`:

```
a76b7e8995c91861e92ce2198cd62d722deede9fb8307463c68b8aa5d5cdf8c4
```

## Limits

- The session is tested with a scripted model through the real agent. It has
  not been run against each hosted provider in this release's checks.
- Commands cannot write into the project folder; files change only through the
  gated write tools. A build step that writes into the tree fails in a session.
- ACP: the MCP server list an editor sends is not started, and session/load is
  not supported. There is no web search tool.
- No measured task-success comparison against other harnesses is claimed.
