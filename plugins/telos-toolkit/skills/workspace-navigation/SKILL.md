---
name: workspace-navigation
description: Use when the user asks where something lives or should go in the Telos workspace, e.g. "where does X live", "where do I store this", "where should this file go", "find the doc / research / plan / spec / lesson for X", "which repo owns X", or "how do I verify this claim". Points at project-docs/WORKSPACE-MAP.md and routes the task to the right flagship MCP tool.
---

# Workspace navigation

This skill is the "know where everything lives" half of the toolkit. When a
task is about locating a file, a repo, a source, a decision, or a verdict, do
this before searching blindly.

## Step 1: consult the map

Read `project-docs/WORKSPACE-MAP.md` in the folder that holds your repositories.
It is the index of which repo owns which concern and where docs, research, plans,
and specs are stored. If the file is not present in the current project, say so
and fall back to the flagship MCP tools below rather than guessing a path.

## Step 2: route to the right flagship MCP tool

The five flagship servers are provided by this plugin. Pick by intent:

- **index** (`index_*` tools): "which repo owns X", "give me context for this
  file/area", repo and dependency graph, workspace map. Start here for
  "where does X live" when the map does not answer it directly.
- **gather** (`gather_*` tools): "find the source / paper / doc for X",
  research intake with a source receipt and a re-verifiable corpus.
- **crucible** (`crucible_*` tools): "verify this claim", "is this measurement
  within tolerance", register a claim then measure it and read the MATCH /
  DRIFT / UNVERIFIABLE verdict.
- **forum** (`forum_*` tools): "who should handle this", route a task across
  agents or rooms, read the witnessed causal ledger.
- **learn** (`learn_*` tools): "what lesson / study plan / mastery state applies
  here", advisory read-only tutor and credential-provenance receipts. Learn's
  MCP surface is advisory only; real runs stay on the `learn` CLI.

## Step 3: answer with a location, not a guess

Return the concrete repo and path (or the tool you queried and its result). If
nothing resolves, say the location is unknown and name the next check
(WORKSPACE-MAP entry to add, or the flagship tool to run) rather than inventing
a path.

## What this plugin does NOT provide

`emet` and `proof-surface` are library/CLI tools with no MCP server. To use
them, shell out to their CLIs (`emet ...`, `telos-proof ...`,
`proof-surface-*`). Do not expect `emet_*` or `proof_surface_*` MCP tools;
they do not exist.
