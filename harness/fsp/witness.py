"""Witness cosigning and split-view proofs (SPEC.md sections 9.3 and 9.4).

A witness keeps the latest checkpoint it verified for each log. It cosigns
a new checkpoint only after a consistency proof from that one verifies, as
the C2SP tlog-witness protocol describes. Two checkpoints signed by one log
key with the same size and different roots are a self-contained split-view
proof that anyone can check offline.
"""

from __future__ import annotations

from typing import Callable

from .canon import canon, tag
from .crypto import ED25519, Ed25519Signer, verify
from .log import checkpoint_valid, ms, root_bytes
from .merkle import verify_consistency


class Refused(Exception):
    def __init__(self, reason: str, proof: dict | None = None) -> None:
        super().__init__(reason)
        self.reason, self.proof = reason, proof


def cosig_message(cp_body: dict, timestamp_ms: int) -> bytes:
    return tag("cosignature") + canon({"checkpoint": cp_body, "timestamp_ms": timestamp_ms})


class Witness:
    def __init__(self, witness_id: str, custodian_state: str,
                 clock: Callable[[], float]) -> None:
        self.witness_id = witness_id
        self.custodian_state = custodian_state
        self.clock = clock
        self.signer = Ed25519Signer()
        self.latest: dict[str, dict] = {}

    @property
    def key(self) -> str:
        return self.signer.public_hex()

    def cosign(self, cp: dict, log_key: str, proof: list[str]) -> dict:
        """Cosign ``cp`` or raise Refused, with a split-view proof when one exists."""
        if not checkpoint_valid(cp, log_key):
            raise Refused("bad log signature")
        origin = cp["body"]["origin"]
        prev = self.latest.get(origin)
        if prev is not None:
            self._check_against(prev, cp, proof)
        self.latest[origin] = cp
        now = ms(self.clock())
        sig = self.signer.sign(cosig_message(cp["body"], now))
        return {"alg": ED25519, "witness": self.key, "timestamp_ms": now, "sig": sig.hex()}

    def _check_against(self, prev: dict, cp: dict, proof: list[str]) -> None:
        old, new = prev["body"]["size"], cp["body"]["size"]
        if new < old:
            raise Refused("checkpoint smaller than one already cosigned")
        if new == old:
            if prev["body"]["root"] != cp["body"]["root"]:
                raise Refused("split view", {"a": prev, "b": cp})
            return
        hashes = [bytes.fromhex(h) for h in proof]
        if not verify_consistency(old, new, root_bytes(prev), root_bytes(cp), hashes):
            raise Refused("no valid consistency proof", {"a": prev, "b": cp})


def cosig_valid(cp_body: dict, cosig: dict) -> bool:
    return verify(cosig.get("alg", ""), cosig.get("witness", ""),
                  cosig_message(cp_body, cosig.get("timestamp_ms", -1)), cosig.get("sig", ""))


def count_cosigs(cp_body: dict, cosigs: list[dict], witness_keys: set[str]) -> int:
    """Distinct policy witnesses with a valid cosignature; one count per key."""
    good: set[str] = set()
    for cs in cosigs:
        key = cs.get("witness")
        if key in witness_keys and key not in good and cosig_valid(cp_body, cs):
            good.add(key)
    return len(good)


def is_split_view_proof(a: dict, b: dict, log_key: str) -> bool:
    """Self-contained proof: one key, one origin, one size, two roots."""
    if not (checkpoint_valid(a, log_key) and checkpoint_valid(b, log_key)):
        return False
    ab, bb = a["body"], b["body"]
    return ab["origin"] == bb["origin"] and ab["size"] == bb["size"] and ab["root"] != bb["root"]
