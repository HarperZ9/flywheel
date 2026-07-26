"""ledger.py -- the receipt log that spans runs, with Merkle inclusion proofs.

Three chain-like things exist in this repository and confusing them wastes time,
so the boundary is explicit:

  - `chain.py` chains the STAGES of one run. Per-run, and its links are truncated
    to 64 bits, which is roughly 2^32 birthday work and is not a link.
  - `store.py` chains writes to the SQLite entity store. Full sha256, general
    purpose, not receipt-shaped.
  - this module spans RUNS. It holds signed receipt envelopes keyed by claim
    digest, links them with FULL sha256, and issues Merkle inclusion proofs so a
    stranger can check that one receipt is in the log without being handed the
    whole log.

Append-only is enforced here in three ways, and the third is the one that matters:

  1. A re-append of a byte-identical envelope is idempotent.
  2. A DIFFERENT envelope under an existing claim digest is refused. Same digest,
     different bytes, means one is a forgery or the digest is broken, and holding
     both silently would make the log the least trustworthy thing in the system.
  3. An envelope whose recorded digest does not match its own body is refused at
     the door, so a stale or edited receipt never enters.

WHAT THIS DOES NOT ESTABLISH, and the ledger says so in `does_not_prove`:
inclusion proves MEMBERSHIP in one tree. It does not prove the log only ever grew.
That needs a consistency proof between two tree sizes, and until that exists
append-only is a property of this code rather than something an outsider can
check. Selective publication remains undetectable regardless: a log can be honest
about everything in it and silent about what was never added.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .merkle import (
    inclusion_proof, merkle_root, consistency_proof, verify_consistency,
    MerkleError,
)
from .receipt import Receipt
from .receipt_fields import canonical

SCHEMA = "flywheel.receipt-ledger/v1"


class LedgerError(ValueError):
    """The ledger refuses to hold something that would make it untrustworthy."""


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


class Ledger:
    """An append-only JSONL log of receipt envelopes."""

    GENESIS = "sha256:" + "0" * 64

    def __init__(self, path, *, log_id: "str | None" = None):
        self.path = Path(path)
        # RFC 9162 puts log_id in both proof structures so a proof names the log
        # it came from. Derive it with tree_head.log_id_for(public_key); a ledger
        # with no key has no honest id and reports None rather than inventing one.
        self.log_id = log_id

    # --- reads ---------------------------------------------------------------

    def _rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for i, line in enumerate(
                self.path.read_text(encoding="utf-8").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception as e:
                raise LedgerError(f"ledger line {i} is unreadable: {e}")
        return out

    def entries(self) -> list[dict]:
        return self._rows()

    def size(self) -> int:
        return len(self._rows())

    def _leaves(self) -> list[bytes]:
        """One leaf per entry, keyed by that entry's `key`.

        For a receipt the key is its claim digest, which is the value a stranger
        already holds when they hold a receipt. For a contest or a resolution it
        is that record's id. Every kind shares one tree, because a contest that
        lived in a side channel could be dropped without breaking anything.
        """
        return [r["key"].encode() for r in self._rows()]

    def root(self) -> str:
        return "sha256:" + merkle_root(self._leaves()).hex()

    # --- writes --------------------------------------------------------------

    def append(self, envelope: dict) -> dict:
        if not isinstance(envelope, dict):
            raise LedgerError("an envelope must be a dict")
        body = envelope.get("receipt")
        if not isinstance(body, dict) or not body:
            raise LedgerError("an envelope must carry a receipt object")
        try:
            receipt = Receipt.from_dict(body)
        except Exception as e:
            raise LedgerError(f"envelope does not contain a receipt: {e}")

        claim = receipt.claim_sha256()
        if claim != body.get("claim_sha256"):
            raise LedgerError(
                "the envelope's recorded claim digest does not match its body; "
                "a stale or edited receipt does not enter the log")

        # Idempotency and the same-digest-different-bytes refusal are handled once,
        # in append_record, keyed on (kind, key). Duplicating the check here is how
        # the two copies drift apart.
        blob = canonical(envelope)
        return self.append_record(
            self.KIND_RECEIPT, claim,
            {"envelope": json.loads(blob),
             "subject_sha256": receipt.subject_sha256(),
             "claim_sha256": claim})

    KIND_RECEIPT = "receipt"
    KIND_CONTEST = "contest"
    KIND_RESOLUTION = "resolution"

    def append_record(self, kind: str, key: str, payload: dict) -> dict:
        """Append any kind of record to the one chain.

        Contests and resolutions share this log with receipts on purpose. A
        contest kept in a side channel could be dropped without breaking any
        link, which would leave the author's discretion exactly where the contest
        channel exists to remove it from.
        """
        if not kind or not key:
            raise LedgerError("a record needs a kind and a key")
        rows = self._rows()
        body = canonical(payload)
        for r in rows:
            if r["key"] == key and r["kind"] == kind:
                if r["body_sha256"] == _sha(body):
                    return r                          # idempotent
                raise LedgerError(
                    f"{kind} {key[:22]}... is already in the log with different "
                    "bytes; the log holds neither silently")

        entry = {
            "schema": SCHEMA, "seq": len(rows), "kind": kind, "key": key,
            "body_sha256": _sha(body),
            "prev_hash": rows[-1]["entry_hash"] if rows else self.GENESIS,
        }
        entry.update(payload)
        entry["entry_hash"] = _sha(canonical(
            {k: entry[k] for k in ("seq", "kind", "key", "body_sha256",
                                   "prev_hash")}))
        entry["_body"] = body
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({k: v for k, v in entry.items()
                                 if k != "_body"}, sort_keys=True) + "\n")
        entry.pop("_body", None)
        return entry

    def records(self, kind: str) -> list[dict]:
        return [r for r in self._rows() if r.get("kind") == kind]

    # --- proofs --------------------------------------------------------------

    def proof_for(self, claim_sha256: str) -> dict:
        rows = self._rows()
        for i, r in enumerate(rows):
            if r["key"] == claim_sha256:
                path = inclusion_proof(self._leaves(), i)
                return {"leaf": claim_sha256, "index": i, "size": len(rows),
                        "path": [h.hex() for h in path], "root": self.root(),
                        "log_id": self.log_id,
                        "schema": "flywheel.inclusion-proof/v2"}
        raise LedgerError(f"no entry for claim {claim_sha256[:22]}...")

    def head(self) -> dict:
        """The tree head a stranger keeps so they can check later growth.

        Deliberately small: a size and a root. Keeping this one line is what lets
        someone verify months later that the log they were shown then is a prefix
        of the log they are shown now.
        """
        return {"schema": "flywheel.tree-head/v1", "size": self.size(),
                "root": self.root()}

    def consistency_since(self, old_head: dict) -> dict:
        """A proof that this log still contains `old_head`'s tree as a prefix."""
        old_size = old_head.get("size")
        if not isinstance(old_size, int) or old_size <= 0:
            raise LedgerError("a tree head needs a positive integer size")
        if old_size > self.size():
            raise LedgerError(
                f"the recorded head claims size {old_size} and this log holds "
                f"{self.size()}: the log has SHRUNK, which append-only forbids")
        return {"schema": "flywheel.consistency-proof/v2",
                "log_id": self.log_id,
                "old_size": old_size, "new_size": self.size(),
                "old_root": old_head.get("root", ""), "new_root": self.root(),
                "path": [h.hex() for h in
                         consistency_proof(self._leaves(), old_size)]}

    @staticmethod
    def check_consistency(proof: dict) -> tuple[bool, str]:
        """(ok, reason). A stranger runs this holding only the old head and the
        proof; the log itself is not needed."""
        try:
            ok = verify_consistency(
                proof["old_size"], proof["new_size"],
                bytes.fromhex(proof["old_root"].split(":", 1)[1]),
                bytes.fromhex(proof["new_root"].split(":", 1)[1]),
                [bytes.fromhex(h) for h in proof["path"]])
        except MerkleError as e:
            return False, f"not_a_growth_claim: {e}"
        except (KeyError, ValueError, IndexError) as e:
            return False, f"malformed_proof: {e}"
        return (True, "ok") if ok else (False, "prefix_was_modified")

    # --- integrity -----------------------------------------------------------

    def verify(self) -> dict:
        """Walk the chain, recomputing every link and every entry digest."""
        try:
            rows = self._rows()
        except LedgerError as e:
            return {"verdict": "UNVERIFIABLE", "size": 0, "broken_at": None,
                    "detail": str(e)}
        prev = self.GENESIS
        _META = {"schema", "seq", "kind", "key", "body_sha256", "prev_hash",
                 "entry_hash"}
        for i, r in enumerate(rows):
            try:
                payload = {k: v for k, v in r.items() if k not in _META}
                recomputed_body = _sha(canonical(payload))
                expected = _sha(canonical(
                    {"seq": r["seq"], "kind": r["kind"], "key": r["key"],
                     "body_sha256": r["body_sha256"],
                     "prev_hash": r["prev_hash"]}))
            except Exception as e:
                return {"verdict": "UNVERIFIABLE", "size": len(rows),
                        "broken_at": i, "detail": f"entry {i} malformed: {e}"}
            if r["seq"] != i:
                return {"verdict": "DRIFT", "size": len(rows), "broken_at": i,
                        "detail": f"entry {i} declares seq {r['seq']}"}
            if r["body_sha256"] != recomputed_body:
                return {"verdict": "DRIFT", "size": len(rows), "broken_at": i,
                        "detail": f"entry {i} body does not match its digest"}
            if r["prev_hash"] != prev:
                return {"verdict": "DRIFT", "size": len(rows), "broken_at": i,
                        "detail": f"entry {i} prev_hash does not link"}
            if r["entry_hash"] != expected:
                return {"verdict": "DRIFT", "size": len(rows), "broken_at": i,
                        "detail": f"entry {i} entry_hash does not match"}
            prev = r["entry_hash"]
        return {"verdict": "MATCH", "size": len(rows), "broken_at": None,
                "detail": "every link recomputed and every entry digest matched",
                "root": self.root()}

    # The ledger's own limits, carried with it rather than left implicit. Codes
    # and prose are separated so `does_not_prove()` matches the shape
    # Receipt.does_not_prove() already uses (bare codes a caller can test), while
    # the explanation survives for a human reading the record.
    LIMITS = {
        "NOT_PROVES_APPEND_ONLY_WITHOUT_A_KEPT_HEAD":
            "Append-only is checkable now, but only by someone who WROTE DOWN a "
            "tree head earlier. consistency_since() proves this log still contains "
            "that head's tree as a prefix. A reader who kept nothing has nothing "
            "to compare against, and no amount of chaining fixes that: the "
            "guarantee is anchored in what an outside party retained, not in what "
            "this log asserts about itself.",
        "NOT_PROVES_PUBLICATION_COMPLETENESS":
            "A log can be honest about everything it holds and silent about what "
            "was never added. No chaining or anchoring makes non-publication "
            "detectable.",
        "NOT_PROVES_RECEIPT_CORRECTNESS":
            "The chain shows the record was not rewritten. A chain of forged "
            "verdicts with intact links still verifies structurally.",
    }

    def does_not_prove(self) -> list[str]:
        out = list(self.LIMITS)
        if self.log_id is None:
            from .tree_head import NO_LOG_ID
            out.append(NO_LOG_ID.split(":", 1)[0])
        return out

    def does_not_prove_detail(self) -> dict:
        return dict(self.LIMITS)
