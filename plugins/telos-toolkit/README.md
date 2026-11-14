# Telos Toolkit

A Claude Code plugin that starts five MCP servers from tools you already have installed,
and adds one skill and three commands for finding things in a multi-repo workspace.

## What it provides

**Five stdio MCP servers** (`.mcp.json`):

| Server     | Command started  | Package to install |
| ---------- | ---------------- | ------------------ |
| `crucible` | `crucible mcp`   | `crucible-bench`   |
| `gather`   | `gather mcp`     | `gather-engine`    |
| `index`    | `index mcp`      | `index-graph`      |
| `forum`    | `forum mcp`      | `forum-engine`     |
| `learn`    | `node <mcp.mjs>` | `@harperz9/learn`  |

The four Python tools each have an `mcp` subcommand on their console script. The
`@harperz9/learn` npm package ships its MCP server at `src/mcp.mjs` and exposes only the
`learn` command, so the plugin starts that server by file path (see "learn MCP path").

**One skill**, `workspace-navigation`. It answers "where does X live" and "where should
this go" by reading `project-docs/WORKSPACE-MAP.md` when the workspace has one, and then
by asking the server that fits the question.

**Three commands**:

- `/telos-toolkit:telos-verify <claim>` checks a claim with Crucible and reports MATCH,
  DRIFT or UNVERIFIABLE as returned.
- `/telos-toolkit:telos-map [focus]` maps the workspace with Index.
- `/telos-toolkit:telos-where <thing>` finds where something lives.

`emet` and `proof-surface` have no MCP server, so this plugin starts none for them. Use
their command-line tools.

## Before you load it

Install the tools whose servers you want. A server whose tool is missing fails to start;
the others still load.

```bash
pip install crucible-bench gather-engine index-graph forum-engine
npm install -g @harperz9/learn
```

### learn MCP path

Claude Code asks for `learn_mcp_path` when you enable the plugin. Give it the absolute
path of `src/mcp.mjs` inside the installed package:

```bash
npm root -g
# the file is <that folder>/@harperz9/learn/src/mcp.mjs
```

Leave it blank to switch off the `learn` server only.

## Load it

From a checkout of this repository:

```bash
claude plugin validate plugins/telos-toolkit
claude --plugin-dir plugins/telos-toolkit
```

The plugin is not listed in this repository's marketplace file yet, so
`/plugin install` does not find it.

## Layout

```
plugins/telos-toolkit/
├── .claude-plugin/plugin.json     manifest and the learn_mcp_path setting
├── .mcp.json                      the five servers
├── skills/workspace-navigation/   SKILL.md
└── commands/                      telos-verify.md, telos-map.md, telos-where.md
```

## Checked on 2026-11-14

- `claude plugin validate` accepts the manifest.
- `crucible mcp --help`, `gather mcp --help`, `index mcp --help` and `forum mcp --help`
  each answer on a machine with the four packages installed.
- Starting the five servers from inside Claude Code through this plugin was not run.
