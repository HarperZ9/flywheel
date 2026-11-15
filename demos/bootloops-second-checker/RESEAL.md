# Reseal log

Each entry records one reseal of `results/run-2026-10-02-linux/SHA256SUMS` and why it happened. This file sits
outside the seal, so a new entry here never changes a sealed digest.

## 2026-10-04: digests recomputed over the committed LF bytes

- Cause: 2 digests in `results/run-2026-10-02-linux/SHA256SUMS` were computed over CRLF working-copy bytes of
  files that Git stores with LF line endings. A checkout writes the stored LF
  bytes, so `sha256sum -c` failed on those entries on every platform once
  `.gitattributes` pinned the sealed files to their committed bytes (commit
  3486391).
- Content did not change. For each entry below, the old digest equals the SHA-256
  of the stored blob with every LF replaced by CRLF, and the new digest is the
  SHA-256 of the stored blob itself. No sealed file was edited in this reseal.
- Method: SHA-256 over the committed blob (`git show HEAD:<path>`), the same
  computation `sha256sum` performs on a checkout that keeps committed bytes. Only
  the digest field of each line changed; paths and their order are unchanged.
- Approval: the author approved this reseal in chat on 2026-10-04: "you can reseal faithful transpile and bootloops."
- `results/run-2026-10-02-linux/SHA256SUMS` before: `68885c19b5ff6b8e0c5fc70be0e82d0dcbcc62b0bee50d89688e390f187e42c5`
- `results/run-2026-10-02-linux/SHA256SUMS` after: `42b277b8cdb41db4847314b85c0a140123559183b7dde4a5bcb29fb44d8630f1`
- The old values stay readable in Git history (`git show 3486391:results/run-2026-10-02-linux/SHA256SUMS`) and in the
  table below.
- External anchors: none found for this seal, so none was added or replaced.
- Scope: only `results/run-2026-10-02-linux/SHA256SUMS` changed. `results/run-2026-10-02/SHA256SUMS`
  already passed and is untouched.
- Does not prove: this reseal attests that the listed files now match these
  digests byte for byte. It does not re-attest any earlier claim made with the
  old digests beyond that byte identity, and it says nothing new about what the
  files contain or whether their conclusions hold.

| File | Old digest (CRLF bytes) | New digest (committed LF bytes) |
|:--|:--|:--|
| `results/run-2026-10-02-linux/published_check/bundle_scan.json` | `7413e45c96729c52275c8b36944a15011ffc58d7e484aa2ec79d07c234cc369b` | `366db658f7bd261950034d6bd7eb06b82cbb83d87108c155ba5adb126e4bfec3` |
| `results/run-2026-10-02-linux/seed_check.json` | `70c339bdf830f670fa9b1e57647fcf65863c444c0904fb91550b3d1726b47957` | `e03877786548e74459e8cbee1dfbc5d74aee910c3db153fc09f6e2b7330e4f58` |
