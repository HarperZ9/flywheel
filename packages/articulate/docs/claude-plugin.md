# Claude Code, Codex and Claude Desktop packaging

Articulate Writing is the local plugin form of Articulate. It gives Claude Code and Codex
local checks, the `edit_plan`/`edit_submit` host-edit protocol, offline editor
entrypoints, status and doctor tools. Its `prose-review` and `prose-edit` skills
explain how to use those tools. The checker runs on your computer and sends the
text nowhere; the calling model reads the text as part of your conversation. The server has
automated Windows and Linux test coverage. The plugin's own README, which is
also its listing text,
covers install, example prompts, the privacy policy and troubleshooting: see
`claude-plugin/README.md`.

## Install

This source plugin targets the 0.19.1 package on the retained-detector release line. It bundles
the package source. Build from the matching package tag for release use; use
`--dev` for a local test build before that tag exists.

The same release workflow prepares [Windows x64 native ZIP and MCPB packages](native-local-package.md)
with their runtime included. Those packages start from a binary entrypoint, so
they run on a machine with Python absent. The instructions below cover the
separate source plugin. Both forms use the calling model for host edits.

The plugin needs Python 3.9 or later, runnable as `python3`, and nothing else:
it carries its own copy of the package source, which uses only the standard
library. Restart Claude Code after the install, then run `/mcp`; the
`articulate` server shows as connected.

To install a local build of this repository, build it as
[Build the plugin from this repository](#build-the-plugin-from-this-repository)
shows, then add the build folder as a marketplace:

```bash
claude plugin marketplace add ./build/claude-plugin
claude plugin install articulate-writing@articulate-writing
```

## What it runs

Claude Code starts one process for the session:

```text
python3 -I -S -B -X utf8 ${CLAUDE_PLUGIN_ROOT}/server/serve.py
```

`-I` keeps Python from reading `PYTHONPATH` and the user site-packages folder,
and from putting the working folder on the module path. `-S` skips the site
module, so no site-packages folder is searched and no `.pth` file there runs,
including one in an activated virtual environment: the server runs on the
standard library and the plugin's own copy of Articulate, which `serve.py` puts
first on the path. `-B` stops Python from writing bytecode into the plugin
folder. `-X utf8`
makes the standard streams UTF-8, and the server switches them to UTF-8 itself
as well, because Windows reads a pipe in the console code page by default.

The plugin sets two variables, scoped to that process:

| Variable | Value | Effect |
|:-|:-|:-|
| `ARTICULATE_MCP_TOOLS` | `local` | Lists the local tool set and restricts editor tools to host plans or deterministic work. Explicit external backends return a named refusal. |
| `ARTICULATE_LOCAL_ONLY` | `1` | Refuses network, subprocess and sampling backends before execution. Host planning/submission still works. |

The server opens no network connection, starts no other program, opens none of
your files and writes no file. The test suite runs every tool marked local with
sockets, process creation and file access made to fail, and checks that no
module keeps a copy of the text after a call. It also starts the built server
with the declared command under Python's audit hooks and calls every tool,
listed and hidden: the session fails on any file opened for writing or outside
the plugin folder and the Python installation, and on any process, network or
file-change event.

## Host editing and offline editor tools

`edit_plan` returns `masked_text`, instructions, findings, protected spans and a
`plan_id`. The calling model follows those instructions and writes a masked
rewrite. `edit_submit` takes the exact original `text`, that `rewrite` and
`plan_id`; it restores masks, checks protected spans and returns accepted `text`,
`refused` changes, before/after gates, rule deltas and a receipt with backend
`host`. A refusal can restore the original paragraph while `ok` remains true,
so callers must inspect `refused` and use the returned text.

Both tools work with `ARTICULATE_LOCAL_ONLY=1`. The text they handle is the text
already in the calling model's conversation, and the tools open no connection of
their own. The guard compares wording; read the result to judge meaning, quality
and facts. The plan token binds content and settings through a checksum, which
detects a changed plan; it carries no signature.

In the plugin, `fix`, `judge` and `polish` accept `auto` or `host` to prepare a
host plan, or `none` for deterministic checks and edits. A request for an
external backend, negotiated sampling included, is refused before it runs. The
PyPI package, used outside the plugin, can use optional backends under its own
configuration.

`check` retains the 0.5.1 `clean`, `verdict`, `texture_score`, HIGH/MEDIUM hits,
LOW advisory count and cadence fields, with the plugin's bounded hit output.
`score` returns the 0.5.1 heuristic score and structural rates. The density and
fairness outputs are reserved for a later release.

## House-voice hooks

`hooks/hooks.json` declares three hooks. Two run `server/house_hook.py` with the
same isolated Python flags as the server.

- `SessionStart`, on startup, resume, clear and compact: once the user turns the
  house voice on (`ARTICULATE_HOUSE_VOICE=on`, or `articulate house on` with the
  separate command line), the hook answers with
  the house-voice brief as `hookSpecificOutput.additionalContext`, so the model
  writes in the [house voice](house-voice.md) from its first reply and again
  after a compaction. The brief names its version (`house/2`) and fingerprint.
  This hook imports none of the style rules; the plugin shim loads the hook's
  modules without running the package initializer. It measured a 72 ms p95 on
  Windows.
- `Stop`, after every reply: it acts in mode `revise`
  (`ARTICULATE_HOUSE_VOICE=revise`, or `articulate house set mode=revise`) and
  stays silent in the others. Claude Code's Stop event holds the full text of the
  last reply, and in `revise` the hook reads that text. When the reply claims a
  human life or has a HIGH style finding, it asks the model for one revision and
  names each finding by line. `stop_hook_active` stops a second request. The
  transcript file stays unopened.

The house voice is off by default. `ARTICULATE_HOUSE_VOICE=off` or
`articulate house off` keeps both hooks silent. The `articulate` command line
comes with the PyPI package `articulate-writing`, installed on its own with
`pip install articulate-writing`. Every path exits 0. The hooks read the packaged
spec and the house settings file, and write no files.

Codex: the Codex manifest points at the same hooks file. Whether Codex runs
plugin `SessionStart` and `Stop` hooks is unconfirmed: open Codex issues report
plugin-local hooks being skipped (openai/codex #16430) and a root `plugin.json`
disabling a plugin's hooks (openai/codex #39895), and this plugin has a root
`plugin.json`. If the brief is missing from a Codex session, run
`articulate house brief --agents` and paste the result into AGENTS.md, or point
a user-level Codex hook at `articulate-house-hook` after
`pip install articulate-writing`.

## Edit-time hook

The plugin's third hook, also in `hooks/hooks.json`, is the edit-time check. Claude Code reads that file
from the plugin root, and the Codex manifest points at it with its `hooks`
entry. After a `Write`, `Edit`, `MultiEdit` or Codex `apply_patch` call, the
host runs `server/edit_hook.py` with the same isolated Python flags as the
server and passes the event on standard input.

For a prose file, the hook compares the text before and after each edit when the
event carries both, and checks the new text for style findings. It answers with
`hookSpecificOutput.additionalContext`, which the host shows to the model on its
next step. It prints nothing for other files, for a clean edit, or for an event
it cannot read; a read failure goes to standard error. It always exits 0, so it
never blocks an edit. A Claude Code `Write` and a Codex added file carry no
before text, so they get the style check only.

The style check leaves out words inside double quotation marks, curly
quotation marks and Markdown block quotes. Those words belong to the person
quoted, so a finding there is no edit the model should make. The hook says how
many findings it left out. Set `ARTICULATE_EDIT_HOOK_QUOTES=check` to check
quoted words too. Straight single quotes are still checked, because an
apostrophe would open a false quote.

The hook does not open the edited file. It reads the event, which already holds
the text the model wrote. Codex skips plugin hooks until you review and trust
them. Set `ARTICULATE_EDIT_HOOK=off` to turn the hook off in either host.

A host that runs command hooks with the same event shape can also run the hook
from the installed package. After `pip install articulate-writing`, point a
`PostToolUse` command hook at `articulate-edit-hook`.

Limits: the comparison is lexical. It does not catch a changed file path
outside code formatting, an added intensifier or two swapped subjects. It can
read a capitalized word that opens a sentence as a name, and it names changes
the user asked for. Each finding is cut to 240 characters and the whole answer
to 6,000, with a count of what was left out, so a large edit does not copy its
changed code blocks into the model's context.

On Windows, Codex replaces `${CLAUDE_PLUGIN_ROOT}` in the hook command with the
plugin folder before it starts `cmd.exe /C`, so the shell receives a plain path.
`tests/test_codex_hook_windows.py` runs the command that way under cmd.exe,
Windows PowerShell and pwsh, from a folder whose path has a space. The hook needs
a `python3` on PATH that is Python 3.9 or newer, as the MCP server does. An end
to end run inside a live Codex session is still to come.

On Windows the hook needs Codex 0.145.0 or newer. Codex before 0.145.0 (including
the 0.144 patch line) escapes the quotes in the command as `\"` when it starts
`cmd.exe`, so Python receives a file name that contains quote marks and the hook
does not run, with or without a space in the path. The edit still goes ahead,
because the hook is advisory. Codex fixed the launch in openai/codex #33926. Run
`codex --version` to check; the CLI on PATH and the one inside the Codex app can
differ.

## Tool titles and hints

Tools declare titles and all four MCP behavior hints. In the plugin environment,
they are read-only, non-destructive, idempotent and closed-world: the plugin
leaves files as they are and calls only local code. Hints describe behavior;
the edit's truth and quality are for the reader. `src/articulate/tool_meta.py`
holds the metadata shared by both servers.

## Build the plugin from this repository

```bash
python scripts/build_claude_plugin.py build/claude-plugin --dev
python scripts/smoke_claude_plugin.py build/claude-plugin
```

The build copies the files git tracks in `claude-plugin/`, the package modules
the server can import, the package's files that are not Python source, and
`LICENSE` into the output folder. The modules the server can import are every
module reachable from `local_mcp` and the package `__init__` through any import
statement, one inside a function included, so the command line, the LSP server
and unrelated tools stay out. An untracked or ignored file, such as a
`.env`, never ships. The build then
checks the result: file count and sizes, text-only files, names that work on
Windows and macOS, no file named or shaped like a credential, the manifest
fields, a single server variable, a README of at least 40 words with a Privacy
Policy section that matches `PRIVACY.md`, and the skill front matter. It exits 1
and lists each problem when a check fails.

Use `--dev` when testing changes before their package tag exists, and publish
releases from the tagged build.

Without `--dev` the build is a release build. Before it writes anything, it
refuses untracked or changed files in the folders it copies, and it refuses
package code that differs from the release its version names (the tag
`v<version>`), because Claude Code keeps a user on a plugin until the version
string changes. The version tag must be present locally and resolve to a commit;
fetch that tag before a release build. Use `--dev` only for a local test build.
It prints the source commit it built from.

The smoke script starts the built server with the command and arguments in
`.mcp.json` and prints one line for each check, so it is the quick test on a new
machine. It looks `python3` up on absolute `PATH` entries outside the working
folder and the plugin folder; `--command` names another interpreter.

To check the manifest with Claude Code itself:

```bash
claude plugin validate --strict build/claude-plugin/.claude-plugin/plugin.json
```

Set `CLAUDE_CONFIG_DIR` to an empty folder first if you want the check to leave
your own Claude Code configuration alone.

## Future publication

Publication is outside this development handoff. After review and a matching
package release, the maintainer can follow this sequence:

1. Release the package version first. The plugin's `version` must equal the
   package version, and a test holds the two equal. A release build refuses
   package code that differs from that release.
2. From a clean checkout of the release commit, build into a clone of the plugin
   repository with `--replace`, which rewrites every file the build owns and
   keeps `.git`.
3. Run the smoke script on the build, commit with the source commit the build
   printed in the message, and push.

Each user's Claude Code starts whatever the plugin repository's default branch
holds at their next session after an update, so that branch needs protection
with a required review.

The plugin folder is the root of its own repository. Claude's directory holds a
Python server in a plugin that sits in a subfolder of a larger repository for a
reviewer, and a plugin at a repository root avoids that.

The `claude-plugin/` folder in this repository also runs on its own: it carries
the modules its server and edit hook import at `claude-plugin/src/articulate`.
`python scripts/sync_plugin_source.py` regenerates that copy from
`src/articulate` after a source change, and `--check` reports drift; a test
fails when the copy differs. A directory submission of the subfolder works, and
its Python server and hook are held for a reviewer as the paragraph above
describes.

## Portable packaging and Codex installation

The bundle contains root `plugin.json` and `mcp.json` for Agent Plugins 1.0.0.
The portable launch uses `type: "stdio"` and `${PLUGIN_ROOT}/server/serve.py`.
The host expands that root in arguments before launch. `.mcp.json` retains the
Claude launch with `${CLAUDE_PLUGIN_ROOT}`. The Codex compatibility manifest
points to `.codex-mcp.json`, whose script path is relative to `cwd: "."`.

OpenAI presentation lives in `extensions.com.openai.interface`. The compatibility
manifest repeats it for older clients, and the bundle checker rejects drift.
Root portable components stay canonical: an inline OpenAI extension replaces
the compatibility settings; the two are not merged.

For a repo marketplace, copy the built bundle to `plugins/articulate-writing`
and add `.agents/plugins/marketplace.json` at that repository's root:

```json
{
  "name": "articulate-local",
  "interface": {"displayName": "Articulate Local"},
  "plugins": [{
    "name": "articulate-writing",
    "source": {"source": "local", "path": "./plugins/articulate-writing"},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Productivity"
  }]
}
```

Restart the desktop host and install from that marketplace. Confirm the
Articulate server is connected and run a prose check and guarded edit in a new
chat. The smoke runner below checks MCP behavior with the declared launch
settings; it does not prove a fresh host install or directory acceptance.

```bash
python scripts/smoke_claude_plugin.py build/claude-plugin --host portable
python scripts/smoke_claude_plugin.py build/claude-plugin --host codex
python scripts/archive_claude_plugin.py build/claude-plugin build/plugin-artifacts
```

The archive command validates the bundle and writes a deterministic plugin ZIP
and `SHA256SUMS`. Keep these artifacts separate from Python package uploads.
Release builds still require matching package tags and committed source. A local
marketplace install is separate from a public directory listing. The plugin
adds no automatic message interception and needs no second model account.

OpenAI public submission of a local MCP plugin needs a supported route through
an OpenAI contact, or a separately designed remote HTTPS service. This release
does not deploy such a service or establish ordinary web-chat availability.
Client review, approved listing metadata and a fresh install check remain
publication requirements.

Packaging references checked 2026-09-30:
[OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins),
[Agent Plugins manifest schema](https://agent-plugins.org/schemas/1.0.0/plugin.schema.json),
[MCP schema](https://agent-plugins.org/schemas/1.0.0/mcp.schema.json), and
[portable variable expansion](https://agent-plugins.org/plugin-authors/mcp-servers).

## Claude Desktop extension

The archive builder can produce a native MCPB 0.3 extension from the checked
plugin bundle. It copies the same server and package source, license and privacy
documentation. It generates `manifest.json`; it does not add another runtime or
include the Claude Code and Codex skills. The Desktop extension exposes the MCP
tools, including `edit_plan` and `edit_submit`.

```bash
python scripts/archive_claude_plugin.py build/claude-plugin build/plugin-artifacts --format both
```

This writes `articulate-writing-<version>-plugin.zip`,
`articulate-writing-<version>-desktop.mcpb` and one `SHA256SUMS` covering both.
Use `--format mcpb` to build only the Desktop extension. The default remains the
plugin ZIP. Archives have stable ordering, timestamps and permissions, with no
outer directory. Validation rejects symbolic links, Windows reparse points and
paths that resolve outside the bundle before reading bundle content. Keep the
input directory stable during packaging; this check does not lock concurrent
writers out.

The Desktop extension requires an installed Python 3.9 or later interpreter.
It does not bundle Python or promise installation without prerequisites. In
Claude Desktop, open Settings > Extensions > Advanced settings > Install
Extension, select the `.mcpb`, and select your installed Python executable when
prompted. The required file picker has no default executable. The host passes
that path as the command and expands `${__dirname}` in the script argument.
The isolated Python flags and local-only environment settings match the plugin.

Tests extract the MCPB into a path containing spaces, resolve the declared
launch with the test interpreter, and check the tool surface, UTF-8 input,
backend refusal and accepted/refused host edits. Schema validation and that
launch smoke do not prove installation in Claude Desktop, an approved directory
listing or macOS execution. A fresh Desktop install remains a release check.
Development bundles retain the source version for testing and must not be
published as new bytes of an existing release.

The manifest follows the official
[MCPB 0.3 schema](https://github.com/modelcontextprotocol/mcpb/blob/main/schemas/mcpb-manifest-v0.3.schema.json)
and [manifest specification](https://github.com/modelcontextprotocol/mcpb/blob/main/MANIFEST.md).
The install path follows Claude's
[custom Desktop extension instructions](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop).
