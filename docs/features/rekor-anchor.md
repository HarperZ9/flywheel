# Public-log anchors

`flywheel anchor` puts a signed head into two public timelines that the author does
not run. Sigstore's Rekor transparency log records the head's SHA-512 and a
signature over it. OpenTimestamps commits the head's SHA-256 into a Bitcoin block.
Each anchor gives a time by which the exact bytes existed, and neither depends on a
key, a server or a git date the author controls.

Only hashes and a signature leave the machine. The head's bytes are never sent.

## Try it

Recheck the preregistration ledger's current head, offline, with nothing installed:

```
flywheel anchor verify artifacts/prereg/heads/head-0008.json \
  --public-key 1f85627e7e0dd4c6c73593d785b669b2abe4701ea780e26d1024b45dc1546111 \
  --anchor-dir artifacts/anchor \
  --ots-anchor artifacts/anchor/head-0008-anchor.json
```

From a checkout without the package installed, `python -m harness.anchor_cli`
takes the same arguments. Add `--online` to refetch the entry from Rekor and prove
that the stored checkpoint is part of today's log. Exit 0 means every anchor
checked holds; exit 1 names what failed.

Anchor a new head going forward:

```
flywheel anchor head artifacts/prereg/heads/head-0009.json \
  --key <key file> --expect-public-key <hex> --anchor-dir artifacts/anchor
```

`--dry-run` prints the exact entry that would be sent and sends nothing. The
OpenTimestamps leg is on by default (`--no-ots` turns it off) and starts pending;
finish it once Bitcoin confirms with `python scripts/flywheel_anchor.py upgrade`.
An existing OpenTimestamps record is never overwritten.

## The anchored heads

| Artifact | Signing key | Rekor log index | Integrated (UTC) | OpenTimestamps |
|:--|:--|:--|:--|:--|
| Prereg head, size 8 (`heads/head-0008.json`, same bytes as `signed-head.json`) | prereg log key `1f85627e...` | [3077414145](https://search.sigstore.dev/?logIndex=3077414145) | 2026-10-04 09:25:59 | Bitcoin block 964462 |
| The same head | receipt-signing key `f3701ca5...` | [3077405366](https://search.sigstore.dev/?logIndex=3077405366) | 2026-10-04 09:17:14 | (same bytes as above) |

Both Rekor entries and the OpenTimestamps proof cover one byte string: the head in
canonical JSON (sorted keys, no spaces), whose SHA-256 is
`728c15a4...afed2c015`. The canonical form keeps the hash the same on a checkout
that rewrites line endings.

The head was logged twice. The first upload used the receipt-signing key, the
documented Flywheel identity key, because the prereg log's own key had not been
found yet. The log key turned up later in the session and the head was logged under
it as well, so that one pinned key now verifies the head's signature and both
anchors. Rekor entries cannot be removed, so both records stay in
`artifacts/anchor/` and both are checked in CI.

## The separate signer's heads

The separate signer anchors its own heads, with no command to remember. Its
anchor job (`python -m harness.signer anchor`) runs every 15 minutes from the
timer or scheduled task the setup scripts install. It logs every store head
that moved since its last anchor in Rekor, under the signer's own key, and in
OpenTimestamps, and writes a receipt beside the signer's other public files.
`flywheel monitor verify --anchors <dir>` then holds the store to every
anchored head, and a history rewritten after an anchor fails with
`ANCHORED_HEAD_DISAGREES`. Records after the newest anchor are reported as
unanchored, never as anchored. The anchoring period is the exposure window.
Setup, findings and limits: `docs/SEPARATE-SIGNER.md`, section "Public anchors".

No signer head appears in the table above. No signer is installed on a machine
this repository knows of, so no signer head exists to anchor yet.

## How it works

- **The entry.** A Rekor `hashedrekord` entry holds three things: the SHA-512 of
  the artifact, an Ed25519ph signature, and the public key as PEM. Rekor checks an
  Ed25519 key in this entry type with Ed25519ph (RFC 8032, prehashed, empty
  context) because it only sees the digest. So the anchor is a second signature by
  the same key over the same bytes, made with libsodium. No account, no OIDC login
  and no Fulcio certificate are involved. `assert_hash_only` refuses an entry with
  any other field, or one that carries the artifact's bytes.
- **The record.** `artifacts/anchor/<stem>-rekor-<key8>.json` keeps the entry body,
  the log index, the integrated time, the signed entry timestamp (SET), the
  inclusion proof and the checkpoint it was proven against.
- **Offline check** (`harness/rekor_verify.py`, standard library only). It confirms
  the body is the `hashedrekord` for these bytes under the pinned public key, and
  that the Ed25519ph signature verifies. It verifies the SET under Rekor's public
  key, which is pinned in the code with its log ID
  (`c0d23d6a...9591801d`, the SHA-256 of that key). It recomputes the Merkle root
  from the inclusion proof (RFC 9162) and checks the checkpoint's signature under
  the same pinned key. Nothing about the log is taken from the record. ECDSA P-256
  verification is in `harness/p256_verify.py`, also standard library only.
- **Online check** (`harness/rekor_online.py`). It refetches the entry by UUID and
  requires the same body, time and index. It runs the offline check on the fresh
  copy, then fetches a consistency proof from the stored checkpoint to the fresh
  one, so the tree the record was proven against is a prefix of the current tree.
- **Two controllers.** The Sigstore project runs Rekor. OpenTimestamps calendars
  aggregate digests into Bitcoin, whose ordering no single party controls. A
  dishonest anchor would need both to cooperate.

## What it proves

- These exact bytes existed by the integrated time, and by the Bitcoin block's time.
- The holder of the named key signed them.
- After an online check, the log still holds the entry and has not rewritten the
  tree it was proven against.

## What it does not prove

- That the content is correct. A preregistration anchored on time can still be a
  bad preregistration.
- That the key holder is honest. The holder could have signed and logged other
  bytes as well; the log records what it is given.
- That the key belongs to the author. That binding comes from where the key is
  published (`artifacts/prereg/FREEZE.json` and
  `project-docs/records/2026-08-27-signing-key-provenance.md`), not from the log.
- That no earlier version existed. Both anchors bound the time from above only.
- That everyone sees one log, from the offline check alone. One checkpoint is one
  view; the online check and Sigstore's public monitors cover the rest.
