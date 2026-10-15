# Configuration

Flywheel reads its settings from three places: files in the Flywheel home,
files in your project, and environment variables. Nothing needs configuring to
start; `flywheel setup` connects a model and `flywheel doctor` shows what is set.

## The Flywheel home

The Flywheel home is `~/.flywheel`, or the folder named by `FLYWHEEL_HOME`.
Everything Flywheel writes for you lives there, never in your project, except
the files you ask the agent to change.

| Path in the home | What it holds |
|---|---|
| `AGENTS.md` | Instructions for every session, read before the project's own |
| `permissions.json` | Your standing allow and deny rules ([rules](CODE-SESSION.md#permission-rules)) |
| `mcp.json` | Your MCP servers ([MCP](CODE-SESSION.md#mcp-servers)) |
| `hooks.json` | Your hooks ([hooks](CODE-SESSION.md#hooks)) |
| `commands/`, `agents/`, `skills/` | Your slash commands, subagents and skills |
| `code-plugins/`, `code-plugins.json` | Installed plugins and their record |
| `code-marketplaces/` | Added plugin marketplaces |
| `sessions/<id>/` | Saved sessions: the ledger and the conversation |
| `memory/` | Project memory notes, one file per project folder |
| `mcp-tokens/` | MCP sign-in tokens where there is no OS credential store (owner-only files) |
| `crashes/` | Local crash reports; nothing is sent |
| `update.json` | Whether the weekly update check is on, and when it last ran |
| `lanes.json`, `lanes/` | Installed lanes and their working folders |

Provider keys are never written to these files. On Windows, `flywheel setup`
stores them in the OS credential store; elsewhere you set environment variables.

## Files in your project

| Path in the project | What it holds |
|---|---|
| `AGENTS.md`, `CLAUDE.md`, `FLYWHEEL.md` | Project instructions, read from the folder up to the repository root |
| `.flywheel/permissions.json` | Project allow and deny rules, merged with yours |
| `.flywheel/mcp.json`, `.mcp.json` | Project MCP servers; they start only after you say yes |
| `.flywheel/hooks.json` | Project hooks; they run only after you say yes |
| `.flywheel/commands/`, `.claude/commands/` | Project slash commands |
| `.flywheel/agents/`, `.claude/agents/` | Project subagents |
| `.flywheel/skills/`, `.claude/skills/` | Project skills |

A project file can name programs to run, so project MCP servers and hooks wait
for your yes, or for `--trust-project-mcp` and `--trust-project-hooks`. A rules
or hooks file that cannot be read stops the session, because a deny list that
silently failed to load would protect nothing.

## Environment variables

### Models

| Variable | Effect |
|---|---|
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`, `GLM_API_KEY` | Turn on that hosted provider |
| `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT` | Azure OpenAI |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `BEDROCK_MODEL` | Amazon Bedrock |
| `VERTEX_PROJECT`, `VERTEX_LOCATION`, `VERTEX_MODEL`, `VERTEX_ACCESS_TOKEN` | Google Vertex AI (without a token, `gcloud auth print-access-token` is used) |

Which model answers, and in what order Flywheel tries them, is on the
[flywheel code](CODE-SESSION.md#models) page.

### Search

| Variable | Effect |
|---|---|
| `SEARXNG_URL` | `web_search` uses this SearXNG instance |
| `BRAVE_API_KEY` | `web_search` uses Brave Search |

With neither set, `web_search` uses DuckDuckGo with no key.

### Flywheel itself

| Variable | Effect |
|---|---|
| `FLYWHEEL_HOME` | Where the Flywheel home is (default `~/.flywheel`) |
| `FLYWHEEL_SCREEN_READER=1` | Plain, screen-reader friendly output, the same as `--plain` |
| `FLYWHEEL_ALLOW_UNSANDBOXED=1` | Run commands on a host with no sandbox; every output is labeled unsandboxed |
| `FLYWHEEL_DEBUG=1` | Print the raw traceback on a crash instead of writing a crash report |

## Command-line flags

Every command and flag is on the Commands page of the docs site, generated
from the program itself so it cannot drift.
`flywheel <command> --help` prints the same text and runs nothing.
