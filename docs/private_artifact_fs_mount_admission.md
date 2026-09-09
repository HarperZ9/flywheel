# Private artifact filesystem mount admission

`harness.private_artifact_fs` refuses POSIX directory authority when the opened
filesystem cannot support the object-bound contract the helper needs.

The POSIX backend is currently Linux-only. Before `root_identity()`,
`open_artifact_root()`, operation parent-chain opens, file reads, anonymous
temporary writes, or `borrow_descriptor()` return authority, the backend
classifies the already-open fd with Linux `fstatfs()` and cross-checks
`/proc/self/mountinfo` by device number. It does not admit a root from a path
prefix, a path reopen, or fd identity alone.

Supported POSIX filesystem types are limited to the local set named in
`harness.private_artifact_fs_mount`: `ext2`, `ext3`, `ext4`, `xfs`, `btrfs`,
`tmpfs`, and `overlay`. Known unsafe WSL/Windows mount types `9p` and `drvfs`
are refused. If the fd cannot be classified, or the type is not in the supported
set, the API raises `PrivateArtifactError` with code `UNSUPPORTED_FS`.

The descendant mount contract is the same as the root contract. Every directory
in the retained root chain and every directory opened while resolving a relative
artifact path must classify as supported. A relative path that crosses into an
unsupported descendant mount is refused before bytes are read, written, or
borrowed. The regular file fd and anonymous temporary file fd are also checked.

This contract does not claim that a path-only external reader is safe on a
filesystem with weaker directory-fd semantics. Callers that need custody across
processes should pass the borrowed descriptor and identity, not a raw path.
