"""The agent-side process cannot forge a record once a separate signer is set.

Each test plays the agent: it can write the store, recompute every seal and
chain link, run its own key, and call the signer's socket. It never receives
the signer's home. Success criteria, one per attack: the verifier holding the
pinned key reports DRIFT with a named cause, or the signer refuses, and the
unkeyed baseline shows why the key is needed (the same rewrite reads as an
internally consistent store).

These tests run the signer as the same OS user as the test, so they prove the
protocol and the verifier, not the OS boundary; every attestation they get is
labeled same-identity. The OS boundary is tests/test_signer_two_user.py.
"""
from __future__ import annotations

import json

import pytest

from harness.preaction import records
from harness.preaction.records import DECISION_SCHEMA, HoldStore, RecordWriteError
from harness.preaction.verify import verify_store
from harness.signer import statement
from harness.signer.client import SignerUnavailable
from tests.preaction_fixtures import call, ctx, monitor
from tests.signer_fixtures import RunningSigner

pytest.importorskip("harness.signer.keys")
try:
    import cryptography  # noqa: F401
except ImportError:
    pytest.importorskip("nacl.signing", reason="signing needs cryptography or pynacl")


@pytest.fixture
def signer(tmp_path):
    s = RunningSigner(tmp_path / "signer-home")
    yield s
    s.stop()


def _decision(i: int) -> dict:
    return {"schema": DECISION_SCHEMA, "source": f"decision:h{i}", "hold_id": f"h{i}",
            "hold_record_sha256": "0" * 64, "decision": "REJECTED", "decider": "owner",
            "decided_at": "2026-10-04T00:00:00Z", "grant_id": "", "review_payload_sha256": "",
            "reason_sha256": ""}


def _signed_store(home, signer, n=3):
    store = HoldStore(home, signer=signer.client())
    for i in range(n):
        store.append(_decision(i))
    return store


def _rows(store):
    return [json.loads(l) for l in store.path.read_text(encoding="utf-8").splitlines()]


def _write(store, rows):
    store.path.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows),
                          encoding="utf-8")


def _rechain(rows):
    """What an agent with write access does: edit, then recompute every seal and
    link so the unkeyed chain holds again. Attestations are left in place."""
    prev = ""
    for r in rows:
        r["prev_record_sha256"] = prev
        prev = records.seal(r)
    return rows


def _causes(report):
    return {f["cause"] for f in report["findings"]}


def test_signed_store_matches_under_the_pinned_key(tmp_path, signer):
    _signed_store(tmp_path / "home", signer)
    report = verify_store(tmp_path / "home", trust_root=signer.public_hex)
    assert report["verdict"] == "MATCH", report
    assert report["anchored"] is True
    # Same OS user here, so the label says so and the verifier warns.
    assert report["signer_isolation"] == ["same-identity"]
    assert any("same identity" in n for n in report["notes"])


def test_a_rechained_edit_passes_unkeyed_but_fails_under_the_key(tmp_path, signer):
    store = _signed_store(tmp_path / "home", signer)
    rows = _rows(store)
    rows[1]["decision"] = "APPROVED_ONCE"
    _write(store, _rechain(rows))
    unkeyed = verify_store(tmp_path / "home")
    assert unkeyed["internal_verdict"] == "MATCH"      # the gap the key closes
    assert unkeyed["verdict"] == "UNANCHORED"          # and it is never a pass
    keyed = verify_store(tmp_path / "home", trust_root=signer.public_hex)
    assert keyed["verdict"] == "DRIFT"
    assert "ATTESTATION_DOES_NOT_MATCH_RECORD" in _causes(keyed)


def test_the_signer_will_not_resign_a_sequence_number(tmp_path, signer):
    store = _signed_store(tmp_path / "home", signer)
    rows = _rows(store)
    rows[1]["decision"] = "APPROVED_ONCE"
    forged = _rechain(rows)[1]
    with pytest.raises(SignerUnavailable, match="conflict"):
        signer.client().sign_record(records.store_id(tmp_path / "home"), 2,
                                    forged["prev_record_sha256"], forged["seal"]["hex"])


def test_an_attestation_under_the_agents_own_key_is_refused(tmp_path, signer):
    from harness.signer import keys
    store = _signed_store(tmp_path / "home", signer)
    keys.create(tmp_path / "agent-key")
    own_sign, own_pub = keys.load(tmp_path / "agent-key")
    rows = _rows(store)
    att = dict(rows[0]["attestation"], key_id=statement.key_id_for(own_pub))
    att["signature"] = own_sign(statement.preimage(att)).hex()
    rows[0]["attestation"] = att
    _write(store, rows)
    report = verify_store(tmp_path / "home", trust_root=signer.public_hex)
    assert report["verdict"] == "DRIFT" and "ATTESTATION_INVALID" in _causes(report)


def test_a_relabelled_isolation_breaks_the_signature(tmp_path, signer):
    store = _signed_store(tmp_path / "home", signer)
    rows = _rows(store)
    rows[0]["attestation"]["isolation"]["mode"] = "separate-identity"
    _write(store, rows)
    report = verify_store(tmp_path / "home", trust_root=signer.public_hex)
    assert "ATTESTATION_INVALID" in _causes(report)


def test_an_unsigned_record_appended_by_the_agent_is_drift(tmp_path, signer):
    store = _signed_store(tmp_path / "home", signer)
    HoldStore(tmp_path / "home", signer=None).append(_decision(9))
    report = verify_store(tmp_path / "home", trust_root=signer.public_hex)
    assert report["verdict"] == "DRIFT" and "UNSIGNED_RECORD" in _causes(report)
    assert len(_rows(store)) == 4


def test_truncation_is_caught_by_the_signers_head(tmp_path, signer):
    store = _signed_store(tmp_path / "home", signer)
    _write(store, _rows(store)[:-1])
    blind = verify_store(tmp_path / "home", trust_root=signer.public_hex)
    assert blind["verdict"] == "MATCH" and blind["truncation_checked"] is False
    head = signer.client().head(records.store_id(tmp_path / "home"))
    report = verify_store(tmp_path / "home", trust_root=signer.public_hex, signer_head=head)
    assert report["verdict"] == "DRIFT" and "TRUNCATED_AFTER_SIGNING" in _causes(report)


def test_a_squatting_signer_cannot_get_a_record_written(tmp_path, signer):
    impostor = RunningSigner(tmp_path / "impostor-home")
    try:
        store = HoldStore(tmp_path / "home", signer=impostor.client(pinned=signer.public_hex))
        with pytest.raises(RecordWriteError, match="pinned key"):
            store.append(_decision(0))
        assert not store.path.exists() or store.path.read_text() == ""
    finally:
        impostor.stop()


def test_an_unreachable_signer_fails_closed(tmp_path, monkeypatch):
    from tests.signer_fixtures import new_address
    monkeypatch.setenv("FLYWHEEL_SIGNER", new_address())
    mon = monitor(tmp_path / "home")
    result = mon.gate(call("run", cmd="ls"), ctx())
    assert result.verdict == "BLOCK" and result.run is False
    assert "record_write_failed" in result.agent_text
    assert not (tmp_path / "home" / "records.jsonl").exists() or \
        (tmp_path / "home" / "records.jsonl").read_text() == ""


def test_the_monitor_signs_through_the_environment(tmp_path, signer, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_SIGNER", signer.address)
    monkeypatch.setenv("FLYWHEEL_SIGNER_PUBKEY", signer.public_hex)
    mon = monitor(tmp_path / "home")
    mon.gate(call("run", cmd="git push --force"), ctx())
    mon.gate(call("run", cmd="ls"), ctx())
    report = verify_store(tmp_path / "home", trust_root=signer.public_hex)
    assert report["verdict"] == "MATCH", report
    assert report["n"] >= 2


def test_a_signed_store_without_a_pinned_root_is_unanchored(tmp_path, signer):
    _signed_store(tmp_path / "home", signer)
    report = verify_store(tmp_path / "home")
    assert report["verdict"] == "UNANCHORED" and report["anchored"] is False
