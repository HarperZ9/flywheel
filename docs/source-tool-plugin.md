# Flywheel tools source plugin

The source plugin adds the existing restricted `harness.tool_mcp` profile to a
local client with Python 3.11 or later. It exposes two tools and two public
resources. It grants no model calls, network, commands or writes. Receipt
membership is not semantic truth. The full harness, native companion and
evidence-task skill remain distinct installation surfaces.

The source companion follows the full Flywheel version and release tag. The
`flywheel-evidence-task` skill keeps its own compatibility version. The native
MCPB includes a runtime; this source ZIP requires an installed Python runtime.
Neither archive establishes a marketplace listing or OpenAI local-MCP approval.

## Build and qualify

Choose output folders outside the source checkout. Each command refuses an
existing output folder. For an unpublished development candidate:

```text
python scripts/build_source_tool_plugin.py --out OUTPUT --dev
python scripts/check_source_tool_plugin.py --archive OUTPUT/flywheel-tools-VERSION-dev-source-plugin.zip --out ACCEPTANCE --expected-version VERSION --dev
```

Release mode omits `--dev` and requires a clean checkout at exactly `vVERSION`.
Every selected source, template, license, version file, closure record and build
generator must also match its normalized bytes in that exact Git commit. Ignored
files and edits hidden by Git index flags cannot qualify as release inputs.
The archive name then omits `-dev`. The builder writes the archive,
`source-plugin-SHA256SUMS.txt` and `source-plugin-build-receipt.json`. Generated
Claude, Codex and portable manifests share the product identity and selected
profile. All source and resource files are inside the plugin root.

The release publishing gate must verify the checksum file against the accepted
checksum-file digest before uploading either file:

```text
python scripts/build_source_tool_plugin.py --verify OUTPUT/source-plugin-SHA256SUMS.txt --accepted-sha256 ACCEPTED_CHECKSUM_FILE_SHA256 --version VERSION
```

The source checker compares every archive file with the reviewed source and
generated metadata before extraction. It then reuses the native companion's
proof checker for included, missing and malformed leaves, exact resource bytes,
the two-tool surface and refused privilege escalation. Selected roots must remain
unchanged. Its bounded process runner currently requires Windows.

## Reviewed dependency closure

`scripts/source_tool_closure.json` pins 78 existing Python modules and the two
public resource files. The eager receipt code imports gateway helpers, so this
set includes more modules than the exposed tool count suggests. Unused lazy
gateway branches are not recursively bundled and are not supported entrypoints.
The small source launcher only calls `harness.tool_mcp.main`.

All packaged text uses UTF-8 and LF newlines, independent of checkout settings.
Every selected source file must match its reviewed canonical hash. A changed module,
including a new dependency or call into existing lazy functionality, stops the
builder until the closure is reviewed and its pins deliberately updated. Keep
package initializers, the two resource files and the source version file in the
payload. Never add `.flywheel-run-root`, private state or credential files.

`SOURCE.json` records the source commit, development/release state, closure-review
hash and each payload hash. Hashes bind bytes; they do not establish program
correctness. Protocol checks cover this restricted profile, not general harness
availability or every platform.
Development receipts also record each input's Git comparison; an untracked or
changed input marks the source dirty even when `git status` omits that change.

## Client setup

Claude Code asks for existing workspace and receipt-state directories. They must
be separate and non-overlapping. Neither setting has a default. The same root
checks apply to source and native commands. Portable and Codex clients must
resolve the documented placeholders explicitly. See the packaged
[README](../plugins/flywheel-tools/README.md) for permissions and troubleshooting.

Qualify actual client installation separately using an isolated profile and
synthetic receipts. A successful schema check alone does not establish a working
connection. Keep development, released, installed and directory-approved states
separate in receipts and release notes.
