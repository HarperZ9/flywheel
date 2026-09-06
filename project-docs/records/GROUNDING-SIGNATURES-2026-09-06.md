# Requiring a signature on a cited ancestor before it is re-run

2026-09-06. Branch `feat/grounding-signatures-20260906`, off `main`.

Closes the item the fresh-environment record left open: "signature verification
wired into the re-check path, which needs a decision about whose keys are
trusted before it means anything."

## The gap a hash cannot close

Three checks already stand between a stored receipt and a MATCH.

`_load_intact` refuses a receipt that no longer hashes to the name it is filed
under, which catches an edit in place. A citation that pins the ancestor digest
refuses a receipt the store does not hold under that exact name, which catches
an editor who rewrites one receipt and refiles it under its new hash.

Neither catches an editor who rewrites the whole cone. Rewrite the ancestor,
refile it under its new hash, rewrite the citing receipt so its pin names that
new hash, refile that under its own new hash, and walk up to the root. Every
filename check passes. Every pin resolves. Nothing in the store contradicts
anything else in the store, because the store is now internally consistent about
a history that did not happen.

The reason is structural rather than a missing case. A hash binds a receipt to
its own contents. It cannot bind a receipt to an author, and both prior checks
compare the store against itself. The previous record said one externally held
copy of any node catches this, which is true and requires someone to be holding
one. A signature is the version that travels with the store: the editor can
recompute every hash in the cone and cannot produce a signature over the
rewritten hashes without the key.

## What was built

`harness/grounding_signatures.py`, 195 lines. It reads a sidecar filed beside a
receipt under the same stem, `{task_id}-{content_hash}.sig.json`, and answers
`(ok, reason)`. A false is always named and a malformed file never raises.

`resolve_ancestors` and `recheck_grounding` take `trusted_keys`, a mapping of
key_id to a 32-byte Ed25519 public key. Left `None`, which is the default,
nothing changes and an unsigned store behaves exactly as it did. Given a
mapping, an ancestor that carries no signature from one of those keys is
dropped before its oracle runs, alongside the absent, the edited, and the
unpinned, each reported apart because they call for different responses.

The signed message is `schema \n task_id \n content_hash`. The task id travels
with the hash so a signature cannot be lifted onto another receipt that shares a
content hash, and sixteen hex characters is a small space to be arguing about.
The schema string is inside the message rather than only in the file, so a
signature made for this purpose cannot be replayed under a future one.

## Five ways this could have been decoration

Each of these is a version of the check that would pass its own tests and prove
nothing, so each is a named discipline in the module and an attack in the tests.

**The hash is recomputed from the loaded envelope**, never read out of the
sidecar. A verifier that trusted the recorded hash would be checking a signature
over a number the attacker supplied.

**The trusted mapping decides which key is authoritative**, not the sidecar. The
sidecar carries a `public_key` field so a human reader can see which key was
claimed, and `verify_envelope_signature` uses it for nothing. Verifying against
the key the sidecar names would establish that the holder of some key signed
this, which an attacker who generated a key an hour ago can also show.

**Ed25519 only, and an HMAC sidecar is refused by name.** A shared-secret MAC
asks the reader to hold the signing secret, and a reader holding the signing
secret is checking their own work.

**Absent and invalid are different facts.** Both fail closed. A reader who
cannot tell them apart cannot tell an incomplete rollout from an attack.

**The default proves nothing new.** Turning this on over a store with no
sidecars would turn every ancestor UNVERIFIABLE, so it is opt-in by naming keys.

The module signs nothing, for the reason `receipt_sign.py` already gives: a
verifier must need nothing, and a pure-Python signer sitting in a verification
module is an invitation to generate keys with an unaudited RNG. The caller
brings the signature; `sidecar_document` only fixes the shape.

## The tests that have to fail

`tests/test_grounding_signatures.py`, ten tests. Four are attacks that must be
refused rather than paths that must pass.

The headline case carries the sidecar across too: the editor rewrites the whole
cone, refiles every node, repoints every pin, and copies the original sidecar
onto the rewritten ancestor. That is the strongest version, and it fails on
COVERS_OTHER, because the sidecar's `content_hash` no longer matches the receipt
it sits beside. Its control is the one a refuse-everything rule fails: an
untouched signed ancestor still resolves and still reaches MATCH.

One test found a sharper attack than the one it was written for. Signing with a
forger's key while reusing the trusted key_id fails INVALID, because the
mapping's key wins; the same sidecar verifies cleanly under a trusted set that
names the forger's key, which is what proves the forgery is invisible from
inside the file. Naming the forger's own key_id fails UNTRUSTED_KEY before any
curve arithmetic runs. Two distinct routes, and the first run of that test
failed by hitting the one it was not asserting.

The remaining four are honest nulls: naming no keys leaves an unsigned store
exactly as it was, asking for signatures over an unsigned store fails closed
rather than passing, an empty trusted set trusts nothing rather than everything,
and a signature does not carry from one task id to another.

## Cost

One Ed25519 verification per cited ancestor, in the stdlib-only verifier, on one
Windows machine, median of twenty runs:

```
pure-python ed25519 verify   median 0.0025 s   min 0.0024 s   max 0.0026 s
```

The fresh-environment re-run beside it costs about 0.79 s per ancestor. The
signature check is roughly three parts in a thousand of what a re-check already
pays, so cost is not the reason to leave it off.

## What this does not establish

It says a holder of a trusted key signed these exact bytes. It says nothing
about whether the receipt was true when it was signed, and a signature over a
wrong measurement is a signed wrong measurement.

An attacker who holds the signing key rewrites the cone and re-signs it, and
every check here passes. Key material is the boundary and it is not defended
here.

A cone signed by one key, read by a verifier who obtained that key from the same
person who wrote the receipts, has established that the store is self-consistent,
which it already knew. Key distribution is out of scope and is not solved by
naming it. What the check buys is a reader who got the key from somewhere else:
a published key, a key pinned at an earlier date, a key held by a second party.

## Two adjacent facts

`grounding.py` was 282 lines before this and the parameter took it to 304,
against a 300-line gate. The fresh-environment fallback moved to
`harness/grounding_fresh_env.py` along the seam the tests already drew, and
`grounding.py` re-exports those names so existing imports resolve unchanged.
Behaviour is identical; the file is 263 lines.

Ninety modules under `harness/` open with an em dash in the module header, which
the prose rule forbids. The two new files use a colon. The ninety were left
alone as a separate change.
