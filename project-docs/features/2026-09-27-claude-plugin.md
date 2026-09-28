# Flywheel Verify: the Claude plugin

Maintainer notes for `plugins/flywheel-verify`. The public description lives in that folder's README and `docs/tools.md`; this file records how the plugin is built, released, and checked.

## What ships

| Part | Where |
| :-- | :-- |
| MCP server `check` (stdio, standard library only) | `harness/check_mcp.py`, with the tools in `harness/check_mcp_tools.py` and `harness/check_mcp_bundle.py` |
| Console script | `flywheel-check-mcp = "harness.check_mcp:main"` in `pyproject.toml` |
| Plugin folder | `plugins/flywheel-verify`: manifest, `.mcp.json`, the `check-before-answering` skill, sample data, README with the Privacy Policy, `SECURITY.md`, `CHANGELOG.md`, `LICENSE`, `docs/tools.md` |
| Sample bundle builder | `scripts/build_verify_plugin_examples.py` (needs PyNaCl or cryptography; makes a new key on every run) |
| Export for a directory listing | `scripts/export_claude_plugin.py` |

Three tools, all read-only: `check_answer` (values against sources passed inline, never a file read, never a command run), `domain_packs` (what the finance, medicine, and law packs declare), and `verify_bundle` (a receipt bundle folder inside the project folder or the plugin's examples, with caps, link refusal, signature counts, and manifest text marked untrusted).

## Why this server and not the others

- `writing_lint.mcp` duplicates the prose tools the Articulate plugin lists from the same publisher.
- `writing_mcp` writes state on every call, status included, and needs a Flywheel home that only a `userConfig` value could supply, which Cowork ignores.
- `local_mcp` sends prompts to third-party providers when `online` is set, starts subprocesses, runs an agent that can write and execute, and stores conversation-derived context.

The check server is the verification core in a form that needs no account, no model, and no network once installed.

## Annotations on every server

Every tool on every Flywheel MCP server now carries a top-level `title`, `annotations.title`, and all four hints set explicitly (`harness/mcp_annotations.py`; per-server tables in `harness/local_mcp_hints.py` and `harness/writing_mcp_hints.py`, inline in `harness/writing_lint/mcp.py`). `tests/test_mcp_tool_annotations.py` finds servers by what they answer, so a new server is covered without a list edit. It also fails a description that overclaims, one that tells a model to call a tool unprompted, and a verification claim with no stated limit. Two descriptions changed to pass it: `flywheel.context.preflight` no longer says "before assuming context is new", and `local_agent_run` now says what its ledger flag shows and what it does not.

Writing Workspace tools, status and doctor included, are not read-only: building the service creates the owner ref on first call. The hints say so, and a test proves the write happens.

## Launch route and release coupling

`.mcp.json` runs `uvx --from flywheel-verify==<version> flywheel-check-mcp`. The pin, `plugin.json` `version`, and `pyproject.toml` `version` must be equal; `tests/test_verify_plugin.py` holds them together, and `tests/test_check_mcp_installed.py` runs that exact command offline against a locally built wheel, with a control showing a pin no wheel carries does not start.

- Why uvx: `uvx.exe` is a real executable on Windows, so the command needs no shell shim; uv supplies a Python when the machine has none that satisfies `requires-python`; and there is no `python` versus `python3` token to choose per platform.
- Cost: the directory always holds a pinned launcher for a reviewer (**Runs a pinned npx or uvx package**). The user needs uv, and network on first start.
- Order of release: the pin resolves only after PyPI carries a `flywheel-verify` release with the `flywheel-check-mcp` script. Publish the package first, then the plugin.
- The other route, a vendored standard-library copy of the server launched by a bare interpreter token, avoids the launcher hold but needs `python3` on every user's path and a vendored-closure drift check. It stays open if the hold turns out to matter.

## Directory submission

This repository cannot be the submission source: it holds more than 10,000 files and folders, and its root `.gitattributes` has line-ending rules. `scripts/export_claude_plugin.py --out DIR` writes the plugin as the root of a new tree, adds `.claude-plugin/marketplace.json` with one entry whose source is `./`, and refuses to finish when the tree breaks a file rule. Creating and publishing that repository, and submitting it, are release steps a person takes.

The sample bundle's bytes are hashed, so the plugin's `.gitattributes` sets `examples/bundle/** -text`, which turns line-ending conversion off and rewrites nothing.

## Checks

- `claude plugin validate --strict` on the plugin manifest, the plugin folder, the repository marketplace, and the exported tree, each run with `CLAUDE_CONFIG_DIR` and `CLAUDE_CODE_PLUGIN_CACHE_DIR` pointed at a scratch folder. Claude Code before 2.1.281 skips `.mcp.json`, so an older run says nothing about the server entry.
- Tests: `test_mcp_tool_annotations.py`, `test_check_mcp.py`, `test_check_mcp_bundle.py`, `test_check_mcp_installed.py`, `test_verify_plugin.py`, `test_export_claude_plugin.py`.

## Open items

- The privacy policy URL in `plugin.json` resolves once the plugin folder is on the default branch.
- Only the portal's Validate says whether another organization uses the `flywheel-verify` name.
- Where a plugin card's icon comes from is not documented; the README carries no image today.
