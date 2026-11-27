"""Checkpoint gossip at the seat desk (SPEC.md sections 4.1 and 9.4, point 2).

Each heartbeat carries, for every log, the size, the root and the log's
signature on that checkpoint. The desk keeps one signed checkpoint per log
and size. Two signed checkpoints of one size with different roots are a
self-contained split-view proof. For two sizes, the desk asks the log for a
consistency proof between them; a refusal or a proof that fails verification
is a split view too, and the desk emits both signed checkpoints and the
failed proof as the evidence. Adjacent sizes suffice: if every neighbouring
pair is consistent, every pair is, so any fork shows at some neighbour.

The desk keeps no unsigned gossip. An entry whose signature fails is
reported as ``gossip_unverifiable`` against the device that sent it, since it
proves nothing about the log.
"""

from __future__ import annotations

from .log import checkpoint_valid, root_bytes
from .merkle import verify_consistency


class GossipDesk:
    def __init__(self) -> None:
        self.log_keys: dict[str, str] = {}
        self.logs: dict[str, object] = {}
        self.seen: dict[str, dict[int, tuple[dict, str]]] = {}
        self.verified: set[tuple] = set()

    def attach(self, logs: list) -> None:
        """Know each log's key and a way to ask it for consistency proofs."""
        for log in logs:
            self.log_keys[log.log_id] = log.key
            self.logs[log.log_id] = log

    def observe(self, entry: dict, device_key: str) -> dict | None:
        log_id = entry.get("log_id")
        cp = {"type": "checkpoint", "sigs": entry.get("log_sigs", []),
              "body": {"origin": log_id, "size": entry.get("size"), "root": entry.get("root")}}
        key = self.log_keys.get(log_id)
        if key is None or not checkpoint_valid(cp, key):
            return {"kind": "gossip_unverifiable", "device_key": device_key,
                    "evidence": {"log_id": log_id, "size": entry.get("size")}}
        size = cp["body"]["size"]
        sizes = self.seen.setdefault(log_id, {})
        same = sizes.get(size)
        if same is not None:
            if same[0]["body"]["root"] == cp["body"]["root"]:
                return None
            return self._event(device_key, log_id, same, (cp, device_key), None)
        sizes[size] = (cp, device_key)
        smaller = max((s for s in sizes if s < size), default=None)
        larger = min((s for s in sizes if s > size), default=None)
        for low, high in ((smaller, size), (size, larger)):
            if low is None or high is None or low == 0:
                continue
            proof = self._inconsistency(log_id, sizes[low][0], sizes[high][0])
            if proof is not None:
                return self._event(device_key, log_id, sizes[low], sizes[high], proof)
        return None

    def _inconsistency(self, log_id: str, a: dict, b: dict):
        """None when a consistency proof from a to b verifies; else the failed
        proof, or the string "refused" when the log gave none."""
        tag = (log_id, a["body"]["size"], a["body"]["root"], b["body"]["size"], b["body"]["root"])
        if tag in self.verified:
            return None
        log = self.logs.get(log_id)
        old, new = a["body"]["size"], b["body"]["size"]
        try:
            proof = log.consistency(old, new)
            hashes = [bytes.fromhex(h) for h in proof]
        except (AttributeError, IndexError, KeyError, ValueError, AssertionError):
            return "refused"
        if verify_consistency(old, new, root_bytes(a), root_bytes(b), hashes):
            self.verified.add(tag)
            return None
        return proof

    @staticmethod
    def _event(device_key: str, log_id: str, first: tuple, second: tuple, proof) -> dict:
        return {"kind": "split_view_proof", "device_key": device_key,
                "evidence": {"log_id": log_id, "a": first[0], "b": second[0],
                             "devices": [first[1], second[1]], "consistency": proof}}
