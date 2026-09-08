# Flywheel 0.5.0

This release connects continuation, workstation approvals, native Bulletin
identity setup, and bounded local execution to the existing Flywheel surface.

## Continue work with a preview

Start a new Evidence Journey from a local workspace and an optional local
export. The preview shows selected context, repository state, and omissions.
Starting the Journey checks the source state again and refuses drift.
This is portable context continuation; it does not imply that an arbitrary
ChatGPT or Claude web session can resume natively in another provider.
Credentials remain in the native keychain and supported provider sign-in paths.

See [native continuation](native-continuation.md).

## Review workstation proposals

The Approvals inbox shows bounded pages of pending workstation proposals.
Approval binds the exact proposal and review content; rejection does not
dispatch work. Interrupted index updates report recovery rather than a false
empty inbox, and reconciliation rebuilds the index from source proposal records.
The client preserves the current selection when an older request finishes late.

See [the approval contract](mobile-approval-inbox-backend.md) and
[mobile setup](../desktop/docs/MOBILE-SETUP.md). Loopback acceptance is distinct
from acceptance on a physical Android device.

## Keep Bulletin identity in native custody

The Keys panel separates Bulletin identity setup from generic provider-key
entry. Creation stores an Ed25519 identity in the OS keychain. Registration is
an explicit separate action; neither the key nor a pasted JWK is displayed.
The CLI also supports reuse and import. Protected slot rules reject generic
replacement, while cooperating setup and deletion operations share a lock.
The Windows engine bundle includes the optional signing backend.

See [identity and outcome publication](outcome-bulletin.md). A stored key,
a registered identity, and a published post are separate states.

## Bound local execution and report what was applied

Large local files can be read in pages with continuation metadata and a checked
open-file identity. Compaction fits the configured token estimate into its
budget or reports the minimum that cannot be folded. Model tokenization and
prompt overhead can differ. Supported local and Flywheel adapters record applied
compaction; unsupported adapters do not claim to have applied it.
Package lane selection can pin the runtime version and refuse a mismatch
instead of silently selecting a source checkout.

See [paged reads](local-read-file.md), [runtime selection](lane-runtime-selection.md),
and [the source-derived benchmark checker](benchmarks/kv-source-oracle-checker.md).
These controls do not establish improved model accuracy or task completion.

## Distribution boundary

The Python package and Windows installer use one version and tag. The Windows
installer remains unsigned, with a SHA-256 receipt identifying the artifact.
Release checks do not imply Authenticode signing, clean-VM installation,
upgrade/rollback acceptance, or third-party marketplace approval.
