# Reseal record

## 2026-10-04: `evidence/benchmark-ci.json`, line endings only

The manifest line for `evidence/benchmark-ci.json` failed `sha256sum -c` on every
checkout setting since the bundle was first committed (c062e969, 2026-07-11). The
file has never changed in Git history. The manifest has been edited three times
since (55eb6bea, d261251a, f1dc33e2), and none of those edits touched this line.

Cause: the recorded digest is the SHA-256 of the file with CRLF line endings. Git
stores the file with LF. The bundle zip `handoff/flywheel-site-designer-handoff.zip`
still holds the CRLF copy, and inside the zip that copy matches the old digest.

| | SHA-256 |
|:--|:--|
| Old value (CRLF form) | `bf091b967bc062870957a4dee1fc1b000ca79eb1118c816a64845fb9cd807c12` |
| New value (committed LF blob) | `1730d36f2336aeceacc75a19686cff93d1cb9db4b85448c13a60e9e04dd1c039` |

Check it yourself:

```sh
git show HEAD:handoff/site-designer/evidence/benchmark-ci.json | sha256sum
git show HEAD:handoff/site-designer/evidence/benchmark-ci.json | sed 's/$/\r/' | head -c -1 | sha256sum
```

The first command prints the new value. The second rebuilds the CRLF form (the file
has no final newline) and prints the old value.

The content is unchanged. The receipt is byte-identical, after LF conversion, to
`artifacts/flywheel-local-coder-14b-benchmark-ci.json`, whose digest is the new value.
The 1.4.0 release notes said this file changed after the manifest was written.
That cause was wrong; see the correction there.

This file is not listed in `MANIFEST.sha256`.
