# Reseal log

Each entry records one reseal of a committed proof bundle and why it happened.
This file sits outside every bundle, so a new entry here never changes a sealed
digest.

## 2026-10-04: demo bundle digests recomputed over the committed LF bytes

- Bundle: `examples/agent_action/demo-otel-out/bundle.json`.
- Cause: the four file digests were computed over CRLF working-copy bytes of files
  that Git stores with LF line endings. A checkout that keeps the stored bytes
  fails `python verify_bundle.py` with DRIFT on all four files, and a
  `core.autocrlf=true` checkout passed only by accident.
- Content did not change. Each old digest equals the SHA-256 of the stored blob
  with every LF replaced by CRLF. Each new digest is the SHA-256 of the stored
  blob itself. No bundled file was edited.
- Method: SHA-256 over each committed blob, then `bundle_hash` re-derived with the
  formula in `verify_bundle.py` (SHA-256 over the `name:sha256` lines in file
  order). Only the digest values changed; names, order and layout are unchanged.
- `.gitattributes` now pins the bundle folder with `-text`, so every platform
  checks out the committed bytes.
- CI runs `verify_bundle.py` on this bundle on Ubuntu and on Windows with
  `core.autocrlf=true`.
- Approval: the author's standing approval of 2026-10-04, "You no longer need to
  wait on my approval. Approved."
- Does not prove: this reseal attests byte identity of the listed files with the
  new digests. It does not re-attest any earlier claim made with the old digests,
  and it says nothing new about what the packet contains.

| Entry | Old digest (CRLF bytes) | New digest (committed LF bytes) |
|:--|:--|:--|
| `packet.json` | `9be07f8894bfa1147b998c9d96027ec09b81a8286d43ca9bcf96bccbd6cb1e1a` | `07eb2b3e12d0cf7919baf419f52da08225f93dd1ab88642f48494502ef98e860` |
| `report.md` | `ed665f4922c1f13840929878cd987c46889c8b5f1294c49974101c49cb32cfe2` | `47456d81ab1c4fe23c3951ef304757d2927fa29789af5c040defa2a9e870913f` |
| `crucible-thesis.json` | `0f9cc4b089d55f4644e06ecd2bd2ccbb878f2b6a453db22f92fc3c638e16d394` | `c2a916eef7e1d0cc7a5c67f7dbad49766c4fb7dc597d9296e1249360b1c0a83b` |
| `crucible-measurements.json` | `0b150d6d6a729d8d286cef458f242cde820f3ae24ce089cf056df0e45dd4dc49` | `1f655406b44cf281a4bf0bac16f2d8d0124d3444f2f7f41b03bc68d79160d6e1` |
| `bundle_hash` | `ed83172629be5a194f7a5b6dea24c9ee69ccba16f74e6f240d445b7fa52263ec` | `f0181e948e6fb21f20ee48b16c84745382f8d779b32160995214696c9beaf499` |

The old values stay readable in Git history at commit 9bc99e7.
