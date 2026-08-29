# Signing key provenance (2026-08-27)

The flywheel signing layer now has a real identity key. This record fixes the
public half of that key, the anchor design it feeds, and the evidence that both
were verified end to end. It is the durable copy; the operator's working memory
holds the same facts. The private half is held offline outside every repository,
was generated with an empty passphrase for headless signing, its file locked to
the owning user with inheritance removed, and it has never been printed to any
log or transcript.

## The key

One Ed25519 key serves both signing surfaces. Receipts are signed raw over
`claim_sha256` through `receipt_sign.ed25519_attach`; the tree head is signed
through `tree_head.sign_head`. Both consume the identical primitive, a callable
from bytes to a 64-byte signature plus the raw 32-byte public key, so neither the
ledger nor a receipt ever touches private key material.

| Field | Value |
|-------|-------|
| Algorithm | Ed25519 |
| Public key (raw hex) | `f3701ca549bb7042c569f7b22a92cddb59ccf288c5fc57a481332acad53b49c2` |
| Key id | `ed25519:e9056d65a51cb5c4c034d3ede0bbbb72` |
| OpenSSH fingerprint | `SHA256:8HZV+KW6Fw68bJfgPvGpp9YUwBKbAYqzQ+HrP0/5n1o` |
| OpenSSH public line | `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPNwHKVJu3BCxWn3siqSzdtZzPKIxfxXpIEzKsrVO0nC flywheel-receipt-signing` |

`key_id` is `ed25519:` plus the first 32 hex of `sha256(pubkey)`. The fingerprint
is the same value GitHub and `ssh-keygen -lf` print, so a reader can confirm the
key on their own machine without trusting this document.

## The external anchor

OpenTimestamps to Bitcoin is the default anchor: zero cost, no trusted
timestamper, and it verifies fully offline against a Bitcoin block header whose
proof of work the verifier rechecks. A Zenodo DOI is the durability dual anchor.
The anchored artifact is `sha256` over the canonical bytes of the signed tree
head, so the timestamp binds the exact head a stranger later checks. RFC 3161
(freeTSA) and Rekor are dropped: freeTSA's offline check needs OpenSSL rather than
the standard library, and Rekor's v2 dropped the signed-timestamp-with-proof
semantics that made it worth a network dependency.

## Verification evidence

Against the real key, not a fixture:

- A sample receipt signed with the key verifies through the shipped stdlib
  verifier: `(True, "ok")`.
- A sample tree head signed with the key verifies through `check_signed_head`:
  `(True, "ok")`.
- Altering the receipt body after signing is caught: `(False, "digest_mismatch")`.
- The fingerprint above matches `ssh-keygen -lf` run on the public file.

## The one open gate

`github.com/HarperZ9.keys` returned HTTP 200 with zero bytes this session. That
endpoint serves authentication keys only, so a key registered purely for signing
never appears there. Until the public key is uploaded to GitHub as an
authentication key, any identity anchor that resolves through `.keys` resolves to
nothing. That upload is an account-settings change and is the operator's to make.

## What this does not prove

A signed head attests to the tree the log chose to build, not that nothing was
withheld. One signed head proves one view; catching a log that shows two views
needs the head gossiped or contested. Binding the signing key to a person is
outside the key itself, which is exactly what the GitHub authentication-key upload
is for.
