"""trust-card falsifier (F5) — a detached signature catches what a hash cannot.

The signature is attributable (needs the key) and tamper-evident: valid over the
current node -> MATCH; any edit or wrong key -> TAMPERED; no signature -> UNSIGNED.
"""
from dataclasses import replace

from harness import wiki
from harness.trustcard import (sign, verify_sig, make_trustcard, verify_trustcard)

KEY = b"harness-local-signing-key-v1"
WRONG = b"attacker-key"


def _node():
    base = wiki.build([{"id": "a", "ref": "src:a", "text": "oracle verification cache"}])
    return base.nodes[0]


def test_sign_verify_roundtrip():
    assert verify_sig("hello", sign("hello", KEY), KEY) is True


def test_tamper_and_wrong_key_fail():
    sig = sign("hello", KEY)
    assert verify_sig("hell0", sig, KEY) is False       # content tampered
    assert verify_sig("hello", sig, WRONG) is False      # wrong key
    assert verify_sig("hello", "", KEY) is False         # no signature


def test_trustcard_valid_is_match():
    n = _node()
    card = make_trustcard(n, KEY, author="Zain Dana Harper", freshness="MATCH")
    assert card.signature and card.author == "Zain Dana Harper"
    assert verify_trustcard(n, card, KEY) == "MATCH"


def test_edited_node_is_tampered():
    n = _node()
    card = make_trustcard(n, KEY, author="op")
    n.source_hash = "deadbeefdeadbeef"                   # edit the node after signing
    assert verify_trustcard(n, card, KEY) == "TAMPERED"


def test_wrong_key_is_tampered():
    n = _node()
    card = make_trustcard(n, KEY, author="op")
    assert verify_trustcard(n, card, WRONG) == "TAMPERED"


def test_unsigned_card_is_unsigned():
    n = _node()
    card = make_trustcard(n, KEY, author="op")
    blank = replace(card, signature="")
    assert verify_trustcard(n, blank, KEY) == "UNSIGNED"
