"""grounding_corpus.py: a false-accept gate for the layer that holds receipts.

`adversarial_corpus.py` scores the pure closure over synthetic dependency
graphs, and the accountability benchmark reads its false-accept rate as the
adversarial-soundness axis. Nothing in it touches a store. Every attack closed
on the resolution path this month lives below that line: an edit in place, a
rewrite refiled under its new hash, a whole-cone rewrite, a lifted sidecar, an
ancestor with no signature at all. A regression that deleted `_load_intact`
would leave that axis reading 1.0.

This corpus runs against a real directory of real receipts, and the resolver
under test is whatever the caller passes with the signature of
`resolve_ancestors`. An attack passes when its target refuses to resolve. A
control passes when its target resolves.

Two things keep the result from being decoration. The controls fail a resolver
that refuses everything. The strawmen in grounding_corpus_strawmen.py are each
wrong in one named way, and each has to be caught by something here.

No oracle runs, because resolution runs no oracle. The whole corpus is file
writes and hashes, plus one Ed25519 verification per signed case.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import grounding_corpus_stores as stores

SKIPPED = "no signer available"


@dataclass(frozen=True)
class StoreAttack:
    """One store, one target, and what a sound resolver must do with it."""
    name: str
    build: Callable
    why: str
    kind: str = "false-accept"          # or "control"
    needs_signer: bool = False


def corpus() -> list[StoreAttack]:
    """The stores a sound resolver must refuse, and the ones it must accept."""
    return [
        StoreAttack("edited_in_place", stores.edited_in_place,
                    "the receipt no longer hashes to the name it is filed under"),
        StoreAttack("refiled_rewrite", stores.refiled_rewrite,
                    "self-consistent after refiling; only the pin disagrees"),
        StoreAttack("whole_cone_rewrite", stores.whole_cone_rewrite,
                    "every hash and pin agrees; the carried sidecar does not",
                    needs_signer=True),
        StoreAttack("absent_ancestor", stores.absent_ancestor,
                    "cited and never stored"),
        StoreAttack("pin_fork", stores.pin_fork,
                    "two citers read different sealings of one source"),
        StoreAttack("unsigned_ancestor", stores.unsigned_ancestor,
                    "signatures required and none present"),
        StoreAttack("sidecar_names_the_trusted_key",
                    stores.sidecar_names_the_trusted_key,
                    "a real signature under a key the trusted set does not hold",
                    needs_signer=True),
        StoreAttack("lifted_signature", stores.lifted_signature,
                    "a valid signature over a different receipt, copied across",
                    needs_signer=True),
        StoreAttack("clean_unsigned", stores.clean_unsigned,
                    "an untouched store predating signatures", kind="control"),
        StoreAttack("clean_pinned_chain", stores.clean_pinned_chain,
                    "a pin the store still satisfies", kind="control"),
        StoreAttack("clean_signed", stores.clean_signed,
                    "signatures required, present, and valid",
                    kind="control", needs_signer=True),
    ]


def default_signer():
    """An ephemeral Ed25519 signer, or None when neither backend is installed.

    The harness runs on the stdlib, so a signer is never a hard dependency.
    Callers that get None report the signed attacks as skipped by name rather
    than scoring a shorter corpus as if it were the whole one.
    """
    from .receipt_signer import key_id_for
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey)
        from .receipt_signer import SigningKey
        return SigningKey(Ed25519PrivateKey.generate())
    except Exception:                             # noqa: BLE001
        pass
    try:
        from nacl.signing import SigningKey as NaclKey
    except Exception:                             # noqa: BLE001
        return None
    return _NaclSigner(NaclKey.generate(), key_id_for)


class _NaclSigner:
    """The signer duck over PyNaCl: sign(bytes) -> 64 bytes, and public material."""

    def __init__(self, key, key_id_for) -> None:
        self._key = key
        self.public_key_bytes = bytes(key.verify_key)
        self.key_id = key_id_for(self.public_key_bytes)

    def sign(self, data: bytes) -> bytes:
        return self._key.sign(bytes(data)).signature


def run_one(attack: StoreAttack, resolver_fn, signer) -> bool:
    """Build the store, resolve over it, and report whether the target resolved."""
    with tempfile.TemporaryDirectory(prefix="fw-store-corpus-") as tmp:
        case = attack.build(Path(tmp), signer)
        out, _ = resolver_fn(Path(tmp), case["sources"], case["pins"],
                             case["trusted"])
        return out.get(case["target"]) is not None


def run_corpus(resolver_fn, attacks: list[StoreAttack] | None = None,
               signer=None) -> dict:
    """Run a resolver against the corpus. A sound resolver scores 0 false
    accepts and 0 over-rejects. Attacks needing a signer that is not available
    are named in `skipped` and left out of the denominator, so a short run
    cannot read as a clean one."""
    attacks = attacks if attacks is not None else corpus()
    if signer is None:
        signer = default_signer()
    false_accepts, over_rejects, skipped = [], [], []
    per: dict[str, dict] = {}
    for a in attacks:
        if a.needs_signer and signer is None:
            skipped.append(a.name)
            per[a.name] = {"kind": a.kind, "resolved": None, "caught": None,
                           "note": SKIPPED}
            continue
        resolved = run_one(a, resolver_fn, signer)
        if a.kind == "false-accept":
            bad = resolved
            if bad:
                false_accepts.append(a.name)
        else:
            bad = not resolved
            if bad:
                over_rejects.append(a.name)
        per[a.name] = {"kind": a.kind, "resolved": resolved, "caught": bad}
    n_fa = sum(1 for a in attacks
               if a.kind == "false-accept" and a.name not in skipped)
    return {"false_accepts": len(false_accepts),
            "false_accept_names": false_accepts,
            "over_rejects": len(over_rejects),
            "over_reject_names": over_rejects,
            "n_false_accept_attacks": n_fa,
            "false_accept_rate": round(len(false_accepts) / max(n_fa, 1), 3),
            "skipped": skipped,
            "per_attack": per}


def gate_report(result: dict) -> str:
    fa, orj = result["false_accepts"], result["over_rejects"]
    status = "SOUND" if (fa == 0 and orj == 0) else "FAILED"
    tail = (", %d skipped without a signer" % len(result["skipped"])
            if result["skipped"] else "")
    return ("store false-accept gate: %s, %d/%d false-accepts, %d over-rejects%s"
            % (status, fa, result["n_false_accept_attacks"], orj, tail))
