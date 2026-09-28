# Flywheel Verify

Flywheel Verify lets Claude check the numbers and codes in an answer against the source that decides them, before the answer reaches you. You supply the source, such as a rate card, a fee schedule, or a formulary extract, and Claude writes a short contract that says which source decides which field. Each field comes back confirmed, contradicted, or unchecked, with a release decision for the whole answer. The check never hands Claude a value, so a failed field sends Claude back to your source instead of to a better guess.

It can also recheck a Flywheel receipt bundle that someone sent you, offline: every file against its manifest hash, every receipt digest recomputed from its own body, and every signature checked against the key it carries.

All three tools are read-only. The check server writes no file and opens no network connection.

## Install

The plugin starts its server with [uv](https://docs.astral.sh/uv/getting-started/installation/), so install uv first. Then, in Claude Code:

```
claude plugin marketplace add HarperZ9/flywheel
claude plugin install flywheel-verify@flywheel-skills
```

On first start, uv downloads the pinned `flywheel-verify` package from the Python Package Index, and a Python build if your computer has no Python 3.11 or later. Later starts use uv's local cache.

The server also runs without the plugin, in other MCP clients that start stdio servers: `pip install flywheel-verify`, then register the `flywheel-check-mcp` command as a stdio server.

## Try it

Three prompts to start with:

1. "Before you send me this invoice, check each unit rate against rates.json and tell me which lines the table does not confirm."
2. "I was sent a Flywheel receipt bundle in the evidence folder. Verify it and tell me what it does and does not show."
3. "Which fields does the medicine pack say a formulary must decide, and what does it refuse to decide?"

To see it work on sample data, ask: "Check the sample invoice answers that ship with Flywheel Verify, then verify the sample receipt bundle." The `examples` folder holds a contract, a rate table, one answer that agrees with the table and one that does not, and a small receipt bundle. The bundle's receipts are made-up demonstration records: one carries a signature from a key made for the sample, and one is unsigned.

## What each tool does

| Tool | What it does | What it reads |
| :-- | :-- | :-- |
| `check_answer` | Checks each field of an answer against the source the contract names, and reports PASS, FAIL, or UNVERIFIABLE per field plus RELEASE, RELEASE_WITH_CAVEAT, or HOLD for the answer. | Only the contract, answer, and source tables in the call. It reads no files. |
| `domain_packs` | Describes the finance, medicine, and law packs: which fields each names, which kind of source decides each, and what each pack refuses to decide. | Nothing outside the server. |
| `verify_bundle` | Rechecks a receipt bundle folder and reports MATCH, DRIFT, or UNVERIFIABLE with signature counts. | The files in the named folder, which must sit inside your project folder or the plugin's `examples` folder. |

The full inputs and outputs are in [docs/tools.md](docs/tools.md), and the skill that tells Claude when and how to use them is in `skills/check-before-answering`.

## What the results do not show

- PASS means the value agrees with the source you supplied. It does not show that the source is right, complete, or current.
- A field whose source was not in the call comes back UNVERIFIABLE, never PASS. Command authorities, which run a program, are never run here; their fields come back UNVERIFIABLE with the `flywheel check-output --allow-commands` route that can run them on your machine.
- MATCH on a bundle covers the file and digest hashes. A failed signature is counted in the result and does not change the verdict. A verified signature shows the receipt was signed by the key it carries, not whose key that is.
- The packs hold no domain data, and nothing here is medical, legal, or financial advice.

## Privacy Policy

This policy covers the Flywheel Verify plugin and its check server, from version 1.1.0.

**Data collected.** The plugin collects no personal data. It has no account, telemetry, analytics, or crash reporting. The check server receives only the arguments Claude passes in a tool call: the contract, answer, and source tables for `check_answer`; a pack name for `domain_packs`; and a folder path for `verify_bundle`, after which it reads the files inside that folder.

**Use and storage.** Each call is handled by a process on your own computer. The server keeps nothing between calls, writes no file, and opens no network connection. The result goes back to Claude as the tool's reply, and from there it is part of your conversation like any other tool result, under the terms of the Claude product you use.

**Third-party sharing.** The server shares nothing with anyone. To start the server, the plugin runs uv. The first time, uv downloads the pinned `flywheel-verify` package from the Python Package Index (pypi.org), and, if your computer has no compatible Python, a Python build from Astral's python-build-standalone project. Those requests carry what any package download carries, such as your IP address and uv's user agent. No tool arguments or results are part of them.

**Retention.** Nothing is kept after a call returns. uv keeps the downloaded package in its cache on your computer until you clear it with `uv cache clean`.

**Children.** The plugin is not directed at children under 18.

**Contact.** For questions about this policy or the plugin, open an issue at https://github.com/HarperZ9/flywheel/issues. Report a security problem privately as described in [SECURITY.md](SECURITY.md).

**Changes.** A change to this policy ships in this README with a new plugin version, and [CHANGELOG.md](CHANGELOG.md) notes it.

## Troubleshooting

- **The server does not start.** Run `uvx --version` in a terminal. If the command is missing, install uv and restart Claude Code, then check the server under `/mcp`. On Windows, a uv installed with pip puts `uvx.exe` in the Python Scripts folder, which has to be on your PATH.
- **No network on this computer.** The plugin's start command needs uv to reach the Python Package Index at least once. On a computer that never goes online, install the package with `pip install flywheel-verify==1.1.0` from a local copy of the wheel and register the `flywheel-check-mcp` command as your own stdio server instead of using the plugin.
- **verify_bundle answers OUTSIDE_PROJECT.** Copy the bundle into your project folder and pass its path relative to the project.
- **A field is UNVERIFIABLE.** Its source was not in the call, the answer does not state the key the table looks up, or the contract names a command authority. The reply's `next` list says which, per field.

## License

FSL-1.1-MIT. See [LICENSE](LICENSE).
