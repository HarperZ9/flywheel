# Flywheel tools

Flywheel tools is a restricted companion to the full Flywheel client. It exposes
`flywheel.tool_status`, `receipt.verify_inclusion` and two public evidence-task
resources. Receipt membership proves inclusion in the selected local receipt log;
it does not establish the receipt's truth, completeness or meaning.

This source plugin requires Python 3.11 or later as `python3`. It carries the
reviewed Python source and public resources, with no model or bundled runtime.
The separate Windows native MCPB includes its runtime and uses the same restricted
profile. The evidence-task skill remains a separate package with its own version.

## Setup

In Claude Code, select an existing workspace folder and an existing receipt-state
folder. They must be separate, non-overlapping local directories with no linked
path components. No default roots are supplied. The state folder contains an
`envelopes` directory; a missing envelopes directory means an empty receipt log.
The plugin creates neither selected directory. Restart after changing setup.
Cowork setup for these required fields remains unverified.

Portable and Codex MCP clients use `mcp.json` or `.codex-mcp.json`. Resolve
`${PLUGIN_ROOT}` to this plugin folder and replace `REPLACE_WITH_ABSOLUTE_WORKSPACE`
and `REPLACE_WITH_ABSOLUTE_RECEIPT_STATE` with the two selected roots. Use an
absolute trusted Python executable if `python3` is unavailable. Keep each argument
as a separate JSON list entry. No installer edits the operator's configuration.

## What runs and what remains unavailable

The client starts `python3 -I -S -B server/serve.py` with the two root arguments.
The launcher calls the existing `harness.tool_mcp.main` entrypoint. The profile
reads local receipt envelopes and packaged public resources. It grants no model
calls, network access, command execution or file writes. Ambient credentials,
environment grants and tool arguments cannot expand its tool surface.

The host may send conversation text and returned tool results to its model
provider under that host's settings. The plugin starts no publisher service and
requires no publisher account. Its code imports a reviewed subset of the engine;
the packaged module set is not the complete harness or a supported general CLI.
Path checks provide a local convenience boundary. This profile provides no
operating-system sandbox.

## Verification and support

Packaged text uses UTF-8 and LF newlines. `SOURCE.json` binds each payload file to its hash and records the source commit,
version and development or release mode. Verify the ZIP against the release's
`source-plugin-SHA256SUMS.txt` before extracting. Development archives include
`-dev` in their filename and must not be published as a release.

Local protocol checks, installed-client checks and marketplace approval are
separate evidence states. No OpenAI local-MCP listing route is established by
this package. Report issues at https://github.com/HarperZ9/flywheel/issues.
The source license is in `LICENSE`.
