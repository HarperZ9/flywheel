"""Turn receipt v2: commitments and random ids only (7.2, I5, N-03, N-04).

A v2 receipt in `store.db` holds the client, a session ref and a prompt-key
ref keyed with the owner's custody key, the pairing mode and segment, salted
commitments to prompt and answer, and whether content was captured. It holds
no URL, no path and no unsalted digest, and its entity id is random, so the
entity's digest and its audit row confirm no guess once the salts, which live
only in the encrypted turn record, are deleted. The owner proves a turn by
revealing text and salt (`verify_opening`).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from .capture_hooks.protocol import commitment

SCHEMA = "flywheel.turn-receipt/v2"
PAIRINGS = ("prompt_id", "turn_id", "fifo", "unpaired")


def keyed_ref(custody_key: bytes, label: str, *parts) -> str:
    message = "\x00".join((label, *(str(p) for p in parts))).encode("utf-8")
    return hmac.new(custody_key, message, hashlib.sha256).hexdigest()[:32]


def build(*, client: str, session_ref: str, prompt_key_ref, pairing: str, segment: int,
          prompt_commitment, answer_commitment, captured_content: bool) -> dict:
    if pairing not in PAIRINGS:
        raise ValueError("pairing")
    return {"schema": SCHEMA, "client": client, "session_ref": session_ref,
            "prompt_key_ref": prompt_key_ref, "pairing": pairing, "segment": segment,
            "prompt_commitment": prompt_commitment, "answer_commitment": answer_commitment,
            "frozen_urls": 0, "refused_urls": 0, "freeze_commitment": None,
            "captured_content": captured_content}


def store_receipt(home, data: dict) -> dict:
    from .store import put_entity
    eid = "tr2_" + secrets.token_hex(12)
    stored = put_entity("turn-receipt", data, eid=eid, home=home)
    return {"eid": stored["eid"], "chain_hash": stored["chain_hash"]}


def verify_opening(data: dict, which: str, text: str, salt: bytes) -> bool:
    expected = data.get(f"{which}_commitment")
    return bool(expected) and hmac.compare_digest(commitment(which, salt, text), expected)
