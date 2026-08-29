"""Shared helpers for the anchor CLI tests, split across three test modules.

These build the byte-level OpenTimestamps proofs and the signing keys the CLI
tests exercise offline. They live in one place so the core, cmd-wiring, and
Zenodo test modules share exactly the same helpers instead of three drifting
copies. This module is not collected as tests (no `test_` prefix); the test
modules import the names they need from it.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness import ots_verify  # noqa: E402,F401
from harness import receipt_signer  # noqa: E402
from scripts import flywheel_anchor as fa  # noqa: E402

cryptography = pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey)

MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"
PENDING_TAG = bytes.fromhex("83dfe30d2ef90c8e")
BITCOIN_TAG = bytes.fromhex("0588960d73d71901")
HEAD = {"schema": "flywheel.tree-head/v1", "size": 7, "root": "sha256:" + "a" * 64}
TS = "2026-08-27T00:00:00Z"

# The genesis block, byte-for-byte: real history, so a stored header verifies as
# a fact. header[36:68] is its merkle root.
GENESIS_HEADER = bytes.fromhex(
    "01000000" + "00" * 32
    + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    + "29ab5f49" + "ffff001d" + "1dac2b7c")
GENESIS_MERKLE = GENESIS_HEADER[36:68]


def _key():
    return receipt_signer.SigningKey(Ed25519PrivateKey.generate())


def _varuint(n):
    out = bytearray()
    while True:
        b, n = n & 0x7F, n >> 7
        out.append(b | 0x80 if n else b)
        if not n:
            return bytes(out)


def _varbytes(b):
    return _varuint(len(b)) + b


def _bitcoin_edge(height):
    return b"\x00" + BITCOIN_TAG + _varbytes(_varuint(height))


def _full_block_proof(digest, height=0):
    """A spliced full proof: file digest -> (zero ops) -> a Bitcoin attestation.
    Its merkle root equals `digest`, so with the matching header it verifies."""
    return MAGIC + b"\x01" + b"\x08" + digest + _bitcoin_edge(height)


def _calendar_reply(uri="https://cal.example/x"):
    """A calendar's serialized reply: from the SUBMITTED digest to a pending leaf."""
    payload = _varuint(len(uri.encode())) + uri.encode()
    return b"\x00" + PENDING_TAG + _varuint(len(payload)) + payload


def _fake_submit(reply=None):
    """A submit() stand-in: nonces the digest, wraps a canned calendar reply."""
    reply = _calendar_reply() if reply is None else reply

    def submit(raw_digest):
        nonce = b"\x5a" * 16
        ots = fa.anchor_submit.build_ots(raw_digest, nonce, reply)
        submitted = fa.anchor_submit.submitted_digest(raw_digest, nonce)
        return {"ots": ots, "submitted_hex": submitted.hex(),
                "nonce_hex": nonce.hex(), "calendar": "https://cal.example",
                "errors": []}
    return submit
