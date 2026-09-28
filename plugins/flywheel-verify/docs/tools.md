# Flywheel Verify tools

The plugin runs one MCP server, `check`, started as `uvx --from flywheel-verify==1.1.0 flywheel-check-mcp`. It speaks MCP over stdin and stdout and lists three tools. Each tool sets a title and all four MCP hints: read-only, not destructive, idempotent, and closed-world. In Claude Code the tools are callable as `mcp__plugin_flywheel-verify_check__<tool>`.

Every refusal comes back as a result with `isError: true` and a `structuredContent.error` object holding a stable `code` and a message that says what to change.

## check_answer

Checks each field of an answer against the source the contract names.

Inputs:

| Name | Type | Required | Meaning |
| :-- | :-- | :-- | :-- |
| `contract` | object | yes | `fields`: a list of `{name, authority, source}`, with optional `criticality` (`advisory`, `standard`, `critical`), `method`, `tolerance`, and `describes`. `authority` is `TABLE`, `RECOMPUTE`, `CITED`, `UNIT`, or `BOUND`. `authorities`: source name to `{"kind": "table", "path", "key_field"}` or `{"kind": "citation"}`. Optional `pack`: `finance`, `medicine`, or `law`, with fields that name a `use` from the pack. |
| `answer` | object | yes | Field name to `{"value", "source"}`, with optional `method` and `unit`, plus any key field a table looks up by. |
| `sources` | object | no | Table `path` to a JSON object of key to value. Nothing is read from disk. |
| `detail` | string | no | `summary` (default) leaves out the per-field rows; `full` includes them. |

Output: `verdict` (PASS, FAIL, UNVERIFIABLE), `release` (RELEASE, RELEASE_WITH_CAVEAT, HOLD), `blocking`, `checked`, `passed`, `unresolved`, `next` (per unresolved field: `field`, `verdict`, `code`, `source`, `criticality`, `reason`, `do`), `fields` with `detail: full`, `commands_not_run` and `commands_note` when the contract names a command authority, and `does_not_prove`.

Limits: at most 200 fields, a 256 KiB contract, a 256 KiB answer, and 1 MiB of sources. Strings from the call are clipped to 300 characters in the reply.

Refusal codes: `INVALID_ARGUMENTS`, `INVALID_CONTRACT`, `INVALID_SOURCES`, `UNKNOWN_PACK`, `TOO_LARGE`.

## domain_packs

Describes the contract packs.

Input: `name` (optional): `finance`, `law`, or `medicine`. Without it, the reply lists the packs.

Output: `packs` with each pack's name and summary, or, for one pack, `name`, `describes`, `caution`, and `fields`, where each field gives its `use`, `authority`, `criticality`, `method`, `unit`, and the failure it `catches`.

Refusal code: `UNKNOWN_PACK`.

## verify_bundle

Rechecks a Flywheel receipt bundle folder.

Input: `path` (required): the folder that holds `manifest.json`, relative to the project folder, or an absolute path inside the project folder or the plugin's `examples` folder.

Output: `verdict` (MATCH, DRIFT, UNVERIFIABLE), `files_checked`, `detail`, `receipts_total`, `receipts` (up to 200, each with `path`, `claim_sha256`, and `signature`), `signature_summary` (`verified`, `failed`, `unsigned`, `local_only`, `malformed`), `trusted_limits`, and, when the manifest carries its own limits text, `manifest_does_not_prove` marked `untrusted: true` (at most 10 items of 300 characters).

What a verdict covers: MATCH means every listed file matches its SHA-256, no unlisted file is present, and every receipt digest re-derives from its body. A failed signature is counted in `signature_summary` and does not change the verdict. A manifest path that is absolute or climbs out with `..` makes the verdict UNVERIFIABLE before any listed file is opened, and a symlink, a Windows junction, or any entry that resolves outside the folder makes it DRIFT. The folder path itself must resolve, after links are followed, inside the project folder or the plugin's `examples` folder.

Limits: at most 2,000 entries and 64 MiB in the folder.

Refusal codes: `INVALID_ARGUMENTS`, `OUTSIDE_PROJECT`, `TOO_LARGE`.

## Protocol details

- `initialize` answers the client's protocol version when it is 2025-06-18, 2025-03-26, or 2024-11-05, and 2025-06-18 otherwise.
- `ping` returns an empty result.
- A line that is not JSON gets a `-32700` error, an unknown method `-32601`, and an unknown tool `-32602`. The server logs each to stderr and keeps serving.
- The server reads and writes UTF-8 whatever the console code page is.
