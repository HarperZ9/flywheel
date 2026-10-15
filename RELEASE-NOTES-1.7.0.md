# Flywheel 1.7.0

`flywheel code` grows into a full terminal coding harness. It hands work to
subagents you define in Markdown, keeps long sessions inside the model's
window, runs dev servers and watchers in the background, signs in to HTTP MCP
servers with OAuth, installs plugins, and runs inside VS Code and GitHub
Actions. Flywheel installs with one line on macOS, Linux and Windows, and the
documented first run is checked on all three in CI. The docs now live at
https://harperz9.github.io/flywheel/docs/, built from the repository with a
command reference generated from the code.

Every new tool call goes through the same permission mode, rules, pre-action
monitor and hash-chained ledger as the rest of the session.

## Behaviour changes to check before you upgrade

- **Long sessions fold automatically.** Past about 60,000 estimated tokens the
  middle of the conversation is folded into one summary before the next model
  call; the ledger keeps the full record. `--compact-budget 0` turns it off.
- **The Windows sandbox runner can be cancelled.** `sandboxed_run` takes
  `cancel` and `work_hook`; the low-integrity runner waits in 250 ms slices
  when a cancel flag is given. Callers that pass neither are unchanged.

## flywheel code

- Subagents from `.flywheel/agents/`, `.claude/agents/` and the Flywheel home,
  a built-in read-only `explore`, and a `task` tool. A subagent works under
  the session's mode, rules and approvals, only with its listed tools, cannot
  nest, and its edits undo with the turn. Its own ledger is recorded.
- Automatic compaction, `@path` mentions with the file's sha256 on the ledger,
  `/context` and `/compact`.
- Background jobs: `run_background`, a `processes` tool and `/jobs`, in the same
  sandbox and under the same gate as `run`. On Windows, output can be read while
  a job runs and stop is immediate; on Linux and macOS, output arrives at the
  end and stop takes effect at the 30-minute limit.
- Plugins in Claude Code's folder shape: `flywheel plugin install <folder or
  git URL>` shows every hook and MCP server command first; `list`, `remove`.
- `flywheel mcp login NAME`: OAuth for HTTP MCP servers (resource metadata,
  authorization server discovery, dynamic registration, PKCE S256, resource
  indicator, refresh). Tokens stay in the Windows credential store or an
  owner-only file and go only to their server.

## Where it runs

- One-line installers: `install.sh` for macOS and Linux and `install.ps1` for
  Windows install the command for the current user in a private environment.
- CI runs the documented first run on all three systems: install, `flywheel
  doctor`, one finished `flywheel code -p` request. Measured on the hosted
  runners: Linux 17 s, macOS 39 s, Windows 32 s, against a 300 s bar.
- A VS Code extension (`flywheel-code-0.1.0.vsix`, attached to this release)
  starts sessions in the workspace and asks about the current file or
  selection. It has no dependencies.
- The repository is a GitHub Action (`uses: HarperZ9/flywheel@v1.7.0`) that
  runs one request and keeps the result and ledger as an artifact.

## Docs

- https://harperz9.github.io/flywheel/docs/ with getting started, the
  flywheel code guide, a generated command reference, licensing in plain words,
  support and the changelog.

## Monitor rule pack

The pre-action monitor's rule pack is unchanged from 1.6.0, so a pinned
`expected_rules_digest` stays valid. `flywheel monitor owner` prints it as
`installed_rules_digest`:

```
a76b7e8995c91861e92ce2198cd62d722deede9fb8307463c68b8aa5d5cdf8c4
```

## Limits

- All session features are tested with a scripted model through the real
  agent loop; no hosted provider was called in this release's checks.
- MCP OAuth does not support servers that require a pre-registered client id.
- The VS Code extension is not on the Marketplace yet; install the `.vsix`.
  A file path with a space is named but not attached by an `@` mention.
- There is no plugin marketplace and no web search tool.
- No task-success comparison against other harnesses is claimed.
