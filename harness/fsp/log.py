"""The public append-only log (SPEC.md section 9).

Each leaf wraps one signed message with the log's entry time and the
fingerprint of the time quorum the log used, so clock evidence is part of
what the log commits to. Checkpoints follow the shape of a C2SP
tlog-checkpoint note (origin, size, base64 root) and are signed by the log
key. On submission the log returns a signed promise to include the entry
within T_RECORD, the role an SCT plays in Certificate Transparency.
"""

from __future__ import annotations

import base64
from typing import Callable

from .canon import canon, fingerprint
from .crypto import Ed25519Signer, envelope, valid_signers
from .merkle import MerkleTree, leaf_hash


def ms(seconds: float) -> int:
    return int(round(seconds * 1000))


def note_text(body: dict) -> str:
    """The checkpoint as C2SP note text: origin, size, base64 root."""
    return f"{body['origin']}\n{body['size']}\n{body['root']}\n"


class TransparencyLog:
    def __init__(self, log_id: str, jurisdiction: str, clock: Callable[[], float],
                 t_record_s: int = 60, time_fp: Callable[[], str] | None = None,
                 signer: Ed25519Signer | None = None) -> None:
        self.log_id = log_id
        self.jurisdiction = jurisdiction
        self.clock = clock
        self.signer = signer or Ed25519Signer()
        self.t_record_ms = t_record_s * 1000
        self.time_fp = time_fp or (lambda: "none")
        self.tree = MerkleTree()
        self.leaves: list[dict] = []
        self.merge_delay_ms = 0          # red-team knob: a log that delays entries
        self.pending: list[tuple[int, dict]] = []
        self.promises: dict[str, dict] = {}
        self._index: dict[str, int] = {}

    @property
    def key(self) -> str:
        return self.signer.public_hex()

    def size(self) -> int:
        return len(self.leaves)

    def submit(self, msg: dict) -> dict:
        """Accept a message and return the signed inclusion promise."""
        now = ms(self.clock())
        fp = fingerprint("entry", msg)
        promise = envelope("promise", {"log_id": self.log_id, "entry_fp": fp,
                                       "submitted_ms": now,
                                       "deadline_ms": now + self.t_record_ms}, [self.signer])
        self.promises[fp] = promise
        self.pending.append((now, msg))
        self.integrate()
        return promise

    def integrate(self) -> list[int]:
        """Append every pending entry whose merge delay has passed."""
        now = ms(self.clock())
        ready = [(t, m) for t, m in self.pending if now - t >= self.merge_delay_ms]
        self.pending = [(t, m) for t, m in self.pending if now - t < self.merge_delay_ms]
        return [self._append(m, now) for _t, m in ready]

    def _append(self, msg: dict, now: int) -> int:
        leaf = {"entry": msg, "logged_ms": now, "time_fp": self.time_fp()}
        self.leaves.append(leaf)
        index = self.tree.append(canon(leaf))
        self._index.setdefault(fingerprint("entry", msg), index)
        return index

    def checkpoint(self, size: int | None = None) -> dict:
        size = self.size() if size is None else size
        root = base64.b64encode(self.tree.root(size)).decode("ascii")
        return envelope("checkpoint", {"origin": self.log_id, "size": size, "root": root},
                        [self.signer])

    def inclusion(self, index: int, size: int) -> list[str]:
        return [h.hex() for h in self.tree.inclusion_proof(index, size)]

    def consistency(self, old: int, new: int) -> list[str]:
        return [h.hex() for h in self.tree.consistency_proof(old, new)]

    def find(self, entry_fp: str) -> int | None:
        return self._index.get(entry_fp)

    def entries_of(self, msg_type: str) -> list[tuple[int, dict]]:
        return [(i, lf) for i, lf in enumerate(self.leaves) if lf["entry"]["type"] == msg_type]

    def fork(self) -> "TransparencyLog":
        """Red-team helper: a second view under the same key (equivocation)."""
        twin = TransparencyLog(self.log_id, self.jurisdiction, self.clock,
                               self.t_record_ms // 1000, self.time_fp, self.signer)
        for leaf in self.leaves:
            twin.leaves.append(leaf)
            twin.tree.append(canon(leaf))
        twin._index = dict(self._index)
        return twin


def checkpoint_valid(cp: dict, log_key: str) -> bool:
    return cp.get("type") == "checkpoint" and log_key in valid_signers(cp)


def root_bytes(cp: dict) -> bytes:
    return base64.b64decode(cp["body"]["root"])


def leaf_hash_of(leaf: dict) -> bytes:
    return leaf_hash(canon(leaf))


def promise_breached(promise: dict, log: TransparencyLog, now_ms: int) -> bool:
    """True when the promised deadline passed and the entry is not in the log."""
    body = promise["body"]
    if now_ms <= body["deadline_ms"] or log.key not in valid_signers(promise):
        return False
    return log.find(body["entry_fp"]) is None
