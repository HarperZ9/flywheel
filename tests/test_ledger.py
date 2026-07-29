"""The receipt ledger: append-only across runs, with inclusion and consistency.

There are three chain-like things in this repository and confusing them wastes
everyone's time, so the boundary is stated here as well as in the module:

  - `harness/chain.py` chains the STAGES of one run. Per-run, 64-bit links.
  - `harness/store.py` chains writes to the entity store. SQLite, full sha256,
    general-purpose, not receipt-shaped.
  - `harness/ledger.py`, this one, spans RUNS. It holds signed receipt envelopes
    keyed by claim digest, links them with FULL sha256, and issues Merkle
    inclusion proofs so a stranger can check that one receipt is in the log
    without being handed the whole log.

Inclusion proves membership in one tree. Consistency proves the log only ever
grew: given a tree head someone wrote down earlier, the current log still contains
that head's tree unchanged as a prefix. Together they make append-only checkable
from outside, with one honest condition, which is that the outside party had to
keep a head. A reader who retained nothing has nothing to compare against, and no
amount of chaining fixes that.
"""
import json

import pytest

from harness.ledger import Ledger, LedgerError
from harness.merkle import verify_inclusion
from harness.receipt import Receipt
from harness.receipt_fields import (
    Budget, Denominator, EvidenceKind, Tier)
from harness.receipt_sign import unsigned
from harness.verdict import Verdict, Attribution

import receipt_factories as factories


def _den(**kw):
    return factories.den(**kw)


def _r(objective="21", **kw):
    return factories.receipt(objective=objective, denominator=_den(), **kw)


def _led(tmp_path):
    return Ledger(tmp_path / "ledger.jsonl")


# --- appending ----------------------------------------------------------------

def test_appending_returns_an_entry_with_a_sequence_and_a_link(tmp_path):
    e = _led(tmp_path).append(unsigned(_r()))
    assert e["seq"] == 0
    assert e["claim_sha256"] == _r().claim_sha256()
    assert len(e["entry_hash"].split(":", 1)[1]) == 64
    assert e["prev_hash"] == Ledger.GENESIS


def test_links_are_full_sha256_never_truncated(tmp_path):
    # chain.py truncates to 64 bits, which is roughly 2^32 birthday work and is
    # not a link. This ledger does not.
    led = _led(tmp_path)
    led.append(unsigned(_r()))
    e = led.append(unsigned(_r(objective="22")))
    assert len(e["prev_hash"].split(":", 1)[1]) == 64
    assert len(e["entry_hash"].split(":", 1)[1]) == 64


def test_each_entry_links_to_the_previous(tmp_path):
    led = _led(tmp_path)
    a = led.append(unsigned(_r(objective="1")))
    b = led.append(unsigned(_r(objective="2")))
    c = led.append(unsigned(_r(objective="3")))
    assert b["prev_hash"] == a["entry_hash"]
    assert c["prev_hash"] == b["entry_hash"]


def test_size_and_entries_agree(tmp_path):
    led = _led(tmp_path)
    for i in range(5):
        led.append(unsigned(_r(objective=str(i))))
    assert led.size() == 5
    assert len(led.entries()) == 5


def test_re_appending_an_identical_envelope_is_idempotent(tmp_path):
    led = _led(tmp_path)
    led.append(unsigned(_r()))
    led.append(unsigned(_r()))
    assert led.size() == 1


def test_a_different_envelope_under_an_existing_claim_is_refused(tmp_path):
    # Same claim digest, different bytes, means one of them is a forgery or the
    # digest is broken. Either way the ledger must not hold both silently.
    led = _led(tmp_path)
    env = unsigned(_r())
    led.append(env)
    tampered = json.loads(json.dumps(env))
    tampered["receipt"]["harness_version"] = "somewhere-else"
    with pytest.raises(LedgerError):
        led.append(tampered)


def test_an_envelope_whose_digest_does_not_match_its_body_is_refused(tmp_path):
    env = unsigned(_r())
    env["receipt"]["objective"] = "999"          # body edited, digest stale
    with pytest.raises(LedgerError):
        _led(tmp_path).append(env)


def test_a_malformed_envelope_is_refused(tmp_path):
    for bad in ({}, {"receipt": None}, {"receipt": {}}, {"receipt": []}):
        with pytest.raises(LedgerError):
            _led(tmp_path).append(bad)


# --- the root and inclusion ----------------------------------------------------

def test_the_root_moves_on_every_append(tmp_path):
    led = _led(tmp_path)
    roots = []
    for i in range(4):
        led.append(unsigned(_r(objective=str(i))))
        roots.append(led.root())
    assert len(set(roots)) == 4


def test_an_empty_ledger_has_the_empty_tree_root(tmp_path):
    import hashlib
    assert _led(tmp_path).root() == "sha256:" + hashlib.sha256(b"").hexdigest()


def test_every_receipt_gets_a_verifying_inclusion_proof(tmp_path):
    led = _led(tmp_path)
    claims = []
    for i in range(9):
        claims.append(led.append(unsigned(_r(objective=str(i))))["claim_sha256"])
    root = bytes.fromhex(led.root().split(":", 1)[1])
    for c in claims:
        p = led.proof_for(c)
        assert verify_inclusion(p["leaf"].encode(), p["index"], p["size"],
                                [bytes.fromhex(h) for h in p["path"]],
                                root) is True


def test_a_proof_for_an_absent_claim_is_refused(tmp_path):
    led = _led(tmp_path)
    led.append(unsigned(_r()))
    with pytest.raises(LedgerError):
        led.proof_for("sha256:" + "0" * 64)


def test_a_proof_carries_the_root_it_was_issued_against(tmp_path):
    led = _led(tmp_path)
    c = led.append(unsigned(_r()))["claim_sha256"]
    p = led.proof_for(c)
    assert p["root"] == led.root()
    assert p["size"] == 1


def test_a_proof_issued_earlier_does_not_verify_against_a_later_root(tmp_path):
    # Honest limit of an inclusion proof: it is only about ONE tree. Proving the
    # later tree contains the earlier one is a consistency proof, which is the
    # next task.
    led = _led(tmp_path)
    c = led.append(unsigned(_r(objective="1")))["claim_sha256"]
    early = led.proof_for(c)
    led.append(unsigned(_r(objective="2")))
    later_root = bytes.fromhex(led.root().split(":", 1)[1])
    assert verify_inclusion(early["leaf"].encode(), early["index"],
                            early["size"],
                            [bytes.fromhex(h) for h in early["path"]],
                            later_root) is False


# --- integrity ----------------------------------------------------------------

def test_verify_walks_the_chain_and_reports_match(tmp_path):
    led = _led(tmp_path)
    for i in range(4):
        led.append(unsigned(_r(objective=str(i))))
    v = led.verify()
    assert v["verdict"] == "MATCH"
    assert v["size"] == 4


def test_an_edited_entry_body_is_caught(tmp_path):
    led = _led(tmp_path)
    for i in range(3):
        led.append(unsigned(_r(objective=str(i))))
    lines = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[1])
    row["envelope"]["receipt"]["objective"] = "999"
    lines[1] = json.dumps(row)
    (tmp_path / "ledger.jsonl").write_text("\n".join(lines) + "\n",
                                           encoding="utf-8")
    v = led.verify()
    assert v["verdict"] == "DRIFT"
    assert v["broken_at"] == 1


def test_a_removed_entry_breaks_the_chain(tmp_path):
    led = _led(tmp_path)
    for i in range(4):
        led.append(unsigned(_r(objective=str(i))))
    lines = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    del lines[1]
    (tmp_path / "ledger.jsonl").write_text("\n".join(lines) + "\n",
                                           encoding="utf-8")
    assert led.verify()["verdict"] == "DRIFT"


def test_a_reordered_ledger_breaks_the_chain(tmp_path):
    led = _led(tmp_path)
    for i in range(4):
        led.append(unsigned(_r(objective=str(i))))
    p = tmp_path / "ledger.jsonl"
    lines = p.read_text(encoding="utf-8").splitlines()
    lines[1], lines[2] = lines[2], lines[1]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert led.verify()["verdict"] == "DRIFT"


def test_an_unreadable_ledger_is_unverifiable_never_match(tmp_path):
    p = tmp_path / "ledger.jsonl"
    p.write_text("{not json\n", encoding="utf-8")
    assert Ledger(p).verify()["verdict"] == "UNVERIFIABLE"


def test_an_empty_ledger_verifies_as_match_with_size_zero(tmp_path):
    v = _led(tmp_path).verify()
    assert v["verdict"] == "MATCH"
    assert v["size"] == 0


# --- append-only, and the honest limit ----------------------------------------

def test_the_ledger_states_that_inclusion_is_not_append_only_proof(tmp_path):
    led = _led(tmp_path)
    led.append(unsigned(_r()))
    assert "NOT_PROVES_APPEND_ONLY_WITHOUT_A_KEPT_HEAD" in led.does_not_prove()
    assert "NOT_PROVES_PUBLICATION_COMPLETENESS" in led.does_not_prove()


def test_reloading_sees_the_same_root_and_size(tmp_path):
    led = _led(tmp_path)
    for i in range(3):
        led.append(unsigned(_r(objective=str(i))))
    again = _led(tmp_path)
    assert again.root() == led.root()
    assert again.size() == 3


def test_nothing_in_an_entry_scores_the_operator(tmp_path):
    e = _led(tmp_path).append(unsigned(_r()))
    blob = json.dumps(e).lower()
    for banned in ("trust_score", "operator_score", "reputation", "streak"):
        assert banned not in blob


# --- consistency: append-only becomes checkable from outside -------------------

def test_a_kept_head_verifies_against_later_growth(tmp_path):
    led = _led(tmp_path)
    for i in range(4):
        led.append(unsigned(_r(objective=str(i))))
    head = led.head()                       # what a stranger writes down
    for i in range(4, 9):
        led.append(unsigned(_r(objective=str(i))))
    proof = led.consistency_since(head)
    ok, reason = Ledger.check_consistency(proof)
    assert ok is True
    assert reason == "ok"


def test_a_stranger_needs_only_the_old_head_and_the_proof(tmp_path):
    led = _led(tmp_path)
    for i in range(3):
        led.append(unsigned(_r(objective=str(i))))
    head = led.head()
    led.append(unsigned(_r(objective="9")))
    proof = led.consistency_since(head)
    # Nothing from the ledger object is used here: the check is a pure function
    # of the old head and the proof.
    assert Ledger.check_consistency(proof)[0] is True


def test_rebuilding_the_log_with_an_entry_dropped_is_caught(tmp_path):
    """The attack the whole task exists for. The maintainer removes one entry and
    appends two, so the log GREW and every inclusion proof for the survivors still
    verifies. Only consistency against the old head refuses it."""
    led = _led(tmp_path)
    for i in range(6):
        led.append(unsigned(_r(objective=str(i))))
    head = led.head()

    rows = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    kept = rows[:2] + rows[3:]                      # entry 2 gone
    (tmp_path / "ledger.jsonl").write_text("\n".join(kept) + "\n",
                                           encoding="utf-8")
    rebuilt = _led(tmp_path)
    for i in (100, 101):
        rebuilt.append(unsigned(_r(objective=str(i))))
    assert rebuilt.size() == 7                      # grew, from 6

    proof = rebuilt.consistency_since(head)
    ok, reason = Ledger.check_consistency(proof)
    assert ok is False
    assert reason == "prefix_was_modified"


def test_a_shrunken_log_is_refused_rather_than_reported_invalid(tmp_path):
    led = _led(tmp_path)
    for i in range(5):
        led.append(unsigned(_r(objective=str(i))))
    head = led.head()
    rows = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    (tmp_path / "ledger.jsonl").write_text("\n".join(rows[:3]) + "\n",
                                           encoding="utf-8")
    with pytest.raises(LedgerError):
        _led(tmp_path).consistency_since(head)


def test_a_head_from_a_different_log_fails(tmp_path):
    a = Ledger(tmp_path / "a.jsonl")
    b = Ledger(tmp_path / "b.jsonl")
    for i in range(3):
        a.append(unsigned(_r(objective=f"a{i}")))
        b.append(unsigned(_r(objective=f"b{i}")))
    head_of_a = a.head()
    b.append(unsigned(_r(objective="b9")))
    ok, reason = Ledger.check_consistency(b.consistency_since(head_of_a))
    assert ok is False


def test_a_malformed_proof_is_a_named_refusal(tmp_path):
    for bad in ({}, {"old_size": 1}, {"old_size": 1, "new_size": 2,
                                      "old_root": "nope", "new_root": "nope",
                                      "path": []}):
        ok, reason = Ledger.check_consistency(bad)
        assert ok is False
        assert reason.startswith(("malformed_proof", "not_a_growth_claim"))


def test_the_head_is_small_enough_to_write_down(tmp_path):
    led = _led(tmp_path)
    led.append(unsigned(_r()))
    h = led.head()
    assert set(h) == {"schema", "size", "root"}
