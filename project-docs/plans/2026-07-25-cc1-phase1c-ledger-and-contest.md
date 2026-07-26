# CC-1 Phase 1C (Ledger and Contest) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn append-only from a policy into a proven property, and give a stranger a way to disagree on the record. That means an RFC 6962 Merkle ledger with inclusion and consistency proofs, a signed tree head an outside party can anchor, a self-contained bundle, and a contest channel where a counter-receipt is signed by the contester rather than filtered by the author.

**Architecture:** Phase 1B made a single receipt checkable. A ledger makes the *set* checkable: inclusion proves a receipt is in the log, and consistency proves the log only ever grew. Those two together are what make "the record cannot be tidied" testable rather than promised. RFC 6962 is chosen over a hand-rolled tree because its domain-separated hashing (0x00 for leaves, 0x01 for interior nodes) prevents second-preimage attacks that a naive tree admits, and because a stranger may already have tooling that speaks it.

The contest channel is the part with no precedent in the landscape. A refutation signed by the party being refuted is worthless, so a contest carries the contester's own key, enters the same append-only log as any other record, and open contests are a published series rather than a queue the author drains.

**Tech Stack:** Python 3.10+ stdlib only under `harness/`. `hashlib.sha256`, integer arithmetic, `json`. The vendored `harness/ed25519_verify.py` from Phase 1B. pytest.

## Global Constraints

Copied verbatim from `project-docs/specs/2026-07-25-certified-commons-design.md`:

- Records are append-only: repair adds on top, never rewrites. Invalidation appends; it never deletes.
- A permanent record must not function as a permanent sentence. How age and repair weight a past failure is an OPEN design question, recorded as such and not invented here.
- Receipts state what they do NOT prove.
- Full sha256 chain links. The prior 64-bit truncation is roughly 2^32 birthday work and is not a link.
- Signing: Ed25519 for anything exportable, HMAC local-only and stripped at pack time. `signed_over` fixed in code.
- No floats in any hashed field.
- Selective publication is detectable only as rollback, never as absence. `NOT_PROVES_PUBLICATION_COMPLETENESS` rides on every receipt and no design choice removes it.
- No aggregate is ever computed over the person. No trust score, ever.
- `harness/` is stdlib-only. Files under 300 lines; the burn-down list may only shrink.
- Voice rule: no em-dashes.
- Apache-2.0 for everything load-bearing for verification.

**Verified repository facts this plan depends on** (re-read at HEAD `7a5dd0f`):

- `harness/receipt.py` `Receipt.claim_sha256()` returns `"sha256:<64 hex>"`; `SIGNED_OVER == ("claim_sha256",)`.
- `harness/receipt_sign.py` `verify_signed(envelope, public_key) -> (ok, reason)`; `pack_for_export(envelope)` strips local-only signatures; `LOCAL_ONLY_ALGS == {"hmac-sha256"}`.
- `harness/ed25519_verify.py` `verify(public_key, message, signature) -> bool`, raising `Ed25519Error` on malformed input. Verify only; it cannot sign.
- `harness/chain.py` already has `StageReceipt.receipt_hash()` (which includes the verdict) and a `verify_chain` that re-witnesses each stage. That is a per-run chain and is NOT the ledger; the ledger spans runs.
- `harness/why.py` `explain(target, prefix="")` reads envelope files from a path or directory.
- `scripts/check_verifier_stdlib.py` walks the transitive closure of 13 entry points; new verifier modules must be added there.

---

### Task 1: The append-only ledger with inclusion proofs

**Files:**
- Create: `harness/merkle.py`
- Create: `harness/ledger.py`
- Test: `tests/test_merkle.py`
- Test: `tests/test_ledger.py`

**Interfaces:**
- Consumes: `harness.receipt.Receipt`, `harness.receipt_fields.canonical`
- Produces: `leaf_hash(data: bytes) -> bytes`, `node_hash(l: bytes, r: bytes) -> bytes`, `root(leaves) -> bytes`, `inclusion_proof(leaves, index) -> list[bytes]`, `verify_inclusion(leaf, index, size, proof, root) -> bool`; `Ledger(path)` with `append(envelope) -> dict`, `entries()`, `size()`, `root()`, `proof_for(claim_sha256) -> dict`, `LedgerError`

**Why RFC 6962 rather than a plain tree:** the domain separation matters. Hashing a leaf as `sha256(0x00 || data)` and an interior node as `sha256(0x01 || left || right)` makes it impossible to present an interior node as a leaf, which is a second-preimage attack a naive tree admits. A ledger whose proofs can be forged is worse than a flat file, because it looks like evidence.

- [ ] **Step 1: Write the failing test for the tree**

Create `tests/test_merkle.py`:

```python
"""RFC 6962 Merkle hashing. The domain separation is the load-bearing part.

A naive tree that hashes leaves and nodes identically admits a second-preimage
attack: an interior node can be presented as a leaf, so a prover can claim a
subtree hash is a record. RFC 6962 prefixes leaves with 0x00 and interior nodes
with 0x01, which makes the two spaces disjoint.
"""
import hashlib

import pytest

from harness.merkle import (
    leaf_hash, node_hash, root, inclusion_proof, verify_inclusion, MerkleError,
)


def test_leaf_and_node_hashing_are_domain_separated():
    a, b = b"x", b"y"
    assert leaf_hash(a) == hashlib.sha256(b"\x00" + a).digest()
    assert node_hash(a, b) == hashlib.sha256(b"\x01" + a + b).digest()
    # The two spaces must not collide for any input.
    assert leaf_hash(a + b) != node_hash(a, b)


def test_an_interior_node_cannot_be_presented_as_a_leaf():
    leaves = [b"a", b"b"]
    interior = node_hash(leaf_hash(b"a"), leaf_hash(b"b"))
    assert leaf_hash(interior) != interior


def test_the_empty_tree_has_the_defined_root():
    assert root([]) == hashlib.sha256(b"").digest()


def test_a_single_leaf_tree_roots_at_its_leaf_hash():
    assert root([b"only"]) == leaf_hash(b"only")


def test_the_root_changes_when_any_leaf_changes():
    base = root([b"a", b"b", b"c"])
    assert root([b"a", b"b", b"d"]) != base
    assert root([b"a", b"c", b"b"]) != base       # order matters


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 7, 8, 9, 16, 17, 33])
def test_every_leaf_has_a_verifying_inclusion_proof(n):
    leaves = [f"leaf-{i}".encode() for i in range(n)]
    r = root(leaves)
    for i in range(n):
        proof = inclusion_proof(leaves, i)
        assert verify_inclusion(leaves[i], i, n, proof, r) is True


def test_a_proof_for_the_wrong_index_fails():
    leaves = [f"leaf-{i}".encode() for i in range(8)]
    r = root(leaves)
    proof = inclusion_proof(leaves, 3)
    assert verify_inclusion(leaves[3], 4, 8, proof, r) is False


def test_a_proof_for_a_leaf_not_in_the_tree_fails():
    leaves = [f"leaf-{i}".encode() for i in range(8)]
    r = root(leaves)
    proof = inclusion_proof(leaves, 3)
    assert verify_inclusion(b"forged", 3, 8, proof, r) is False


def test_a_truncated_proof_fails():
    leaves = [f"leaf-{i}".encode() for i in range(8)]
    r = root(leaves)
    proof = inclusion_proof(leaves, 3)
    assert verify_inclusion(leaves[3], 3, 8, proof[:-1], r) is False


def test_a_proof_with_a_flipped_bit_fails():
    leaves = [f"leaf-{i}".encode() for i in range(8)]
    r = root(leaves)
    proof = inclusion_proof(leaves, 3)
    mangled = list(proof)
    b = bytearray(mangled[0]); b[0] ^= 0x01
    mangled[0] = bytes(b)
    assert verify_inclusion(leaves[3], 3, 8, mangled, r) is False


def test_an_out_of_range_index_is_refused():
    with pytest.raises(MerkleError):
        inclusion_proof([b"a", b"b"], 5)


def test_a_size_mismatch_is_refused_rather_than_silently_false():
    leaves = [b"a", b"b", b"c"]
    proof = inclusion_proof(leaves, 0)
    with pytest.raises(MerkleError):
        verify_inclusion(leaves[0], 0, 0, proof, root(leaves))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_merkle.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'harness.merkle'`

- [ ] **Step 3: Write the tree**

Create `harness/merkle.py` implementing RFC 6962 section 2.1. The recursive split point is the largest power of two strictly less than `n`, which is what makes proofs and consistency proofs agree with other implementations. Domain separation prefixes are `b"\x00"` for leaves and `b"\x01"` for interior nodes. `root([])` is `sha256(b"")`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_merkle.py -q`
Expected: PASS, 15 or more passed depending on parameterization.

- [ ] **Step 5: Cross-check against an independent implementation**

Verify the roots against a second source before trusting them. A tree that agrees only with itself is the same failure class as the Ed25519 base point in Phase 1B, which passed every self-consistent check while being wrong. If no library is available, compute a small tree by hand in the test and assert the exact expected root bytes.

- [ ] **Step 6: Write the ledger test and implementation, then commit**

The ledger appends envelopes keyed by `claim_sha256`, stores full sha256 links, refuses to rewrite an existing entry, and issues an inclusion proof for any claim it holds. A re-append of an identical claim is idempotent; a different envelope under an existing claim digest is a hard error.

```bash
git add harness/merkle.py harness/ledger.py tests/test_merkle.py tests/test_ledger.py
git commit -m "feat(ledger): RFC 6962 Merkle ledger with inclusion proofs"
```

---

### Remaining Phase 1C tasks

Written out when Task 1 lands, so their interfaces are real rather than predicted.

- **Task 2: consistency proofs and the signed tree head.** `consistency_proof(old_size, new_size)` and `verify_consistency`, which is what makes append-only a PROVEN property rather than a policy: a stranger holding an old tree head can check that the new log contains the old one unchanged. Plus an `sth` record (size, root, timestamp, signature) and a documented anchor path. The honest bound stays: this makes rollback detectable and never makes non-publication detectable.
- **Task 3: bundle pack and verify.** A self-contained `.frb` directory a stranger checks offline: receipts, the criterion, the checker source, the QA card, the tree head, and a `reproduce` script. Hardened against zip-slip, symlinks, and absolute paths. Local-only signatures stripped. A secret scan that hard-fails rather than warns.
- **Task 4: the contest channel.** A counter-receipt signed with the CONTESTER's key, appended to the same log, with open-contest count and time-to-resolution as published series. The party being refuted must not be the party who decides which refutations are recorded.
- **Task 5: Phase 1 acceptance record.** Real numbers, the honest non-claims, and an explicit statement of what Phase 1 did and did not establish.

## Self-Review

**Spec coverage.** Phase 1C completes spec Layer 2. It does NOT cover Layer 3 (cost meter and amortization), Layer 4 (the model adapter layer), Layer 5 (the science: preregistration, control arms, uplift statistics), or Layer 6 (training). Nothing here trains a model or measures uplift, and the acceptance record in Task 5 must say so.

**Placeholder scan.** Task 1 carries the complete test for the tree and a precise specification of the implementation rather than its code, because the RFC's split rule is the only real decision in it and stating that rule is more useful than transcribing twenty lines. Tasks 2 through 5 are specified rather than written, stated as a scoping decision.

**Type consistency.** `verify_inclusion(leaf, index, size, proof, root)` in Task 1 matches the RFC's argument order and is the signature Task 2's consistency check will sit beside. `Ledger.proof_for(claim_sha256)` takes the tagged `"sha256:<hex>"` form that `Receipt.claim_sha256()` returns, not raw bytes.
