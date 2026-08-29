"""The anchor CLI wiring: `upgrade` and `verify` end to end, network mocked.

These drive `fa.main([...])` the way a person at a terminal does, with only the
two network boundaries (`_get_timestamp`, `_fetch_block_header`) stubbed, so the
parse, splice, verify, and file-write paths run for real. The pure core the CLI
sits on is tested in test_flywheel_anchor.py; the Zenodo leg in
test_flywheel_anchor_zenodo.py.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
pytest.importorskip("cryptography")

from tests._anchor_fixtures import (  # noqa: E402
    GENESIS_HEADER, GENESIS_MERKLE, HEAD, MAGIC, PENDING_TAG, TS, _bitcoin_edge,
    _full_block_proof, _key, _varbytes, fa, ots_verify)


def test_cmd_upgrade_polls_R_fetches_the_header_and_writes_a_confirmed_record(
        tmp_path, capsys, monkeypatch):
    # end-to-end wiring with only the network boundary mocked: a genesis-digest
    # record + its pending proof, upgraded to a confirmed record whose stored
    # header verifies the block offline.
    digest = GENESIS_MERKLE
    rec = {"schema": "flywheel.anchor/v1", "digest_hex": digest.hex(),
           "signed_head": {"public_key": "00" * 32},
           "ots": {"state": "pending", "submitted_hex": "de",
                   "nonce_hex": "ad", "calendar": "https://cal.example"}}
    apath = tmp_path / "anchor.json"
    apath.write_text(json.dumps(rec), encoding="utf-8")
    # the pending proof sits beside it: pending directly on the digest
    pending = (MAGIC + b"\x01" + b"\x08" + digest + b"\x00" + PENDING_TAG
               + _varbytes(_varbytes(b"https://cal.example")))
    (tmp_path / "anchor.json.ots").write_bytes(pending)

    # mock ONLY the two network fetchers, leave the parse/splice/verify real
    monkeypatch.setattr(fa.anchor_submit, "_get_timestamp",
                        lambda uri, r_hex, **k: _bitcoin_edge(0))
    monkeypatch.setattr(fa.anchor_submit, "_fetch_block_header",
                        lambda height, **k: GENESIS_HEADER)

    code = fa.main(["upgrade", "--anchor", str(apath)])
    assert code == 0
    written = json.loads(apath.read_text(encoding="utf-8"))
    assert written["ots"]["state"] == "confirmed"
    assert written["ots"]["block_height"] == 0
    assert written["ots"]["block_header"] == GENESIS_HEADER.hex()
    # the written proof verifies offline from the written header
    confirmed_ots = (tmp_path / "anchor.json.ots").read_bytes()
    checked = ots_verify.verify(confirmed_ots, digest, fa._header_provider(written))
    assert checked["ok"] is True
    out = capsys.readouterr().out
    assert "confirmed" in out


def _confirmed_record_and_proof(tmp_path):
    """Write a confirmed anchor + its offline-verifiable .ots (genesis digest), and
    return their paths. The head is a stub (identity is out of scope here); the
    timestamp leg is a real, PoW-checkable genesis block."""
    digest = GENESIS_MERKLE
    rec = {"schema": "flywheel.anchor/v1", "digest_hex": digest.hex(),
           "signed_head": {"public_key": "00" * 32},
           "ots": {"state": "confirmed", "submitted_hex": "de", "nonce_hex": "ad",
                   "calendar": "https://cal.example", "block_height": 0,
                   "block_header": GENESIS_HEADER.hex()}}
    apath = tmp_path / "anchor.json"
    apath.write_text(json.dumps(rec), encoding="utf-8")
    (tmp_path / "anchor.json.ots").write_bytes(_full_block_proof(digest))
    return apath


def test_cmd_upgrade_short_circuits_on_an_already_confirmed_record(
        tmp_path, capsys, monkeypatch):
    # A re-run against an already-confirmed record must not poll the calendar (a
    # confirmed proof has no pending message, so the old code found None and printed
    # "still pending" -- disagreeing with `verify`, which reports it ANCHORED). It
    # must recognize the confirmed state and say so, exercising nothing on the wire.
    apath = _confirmed_record_and_proof(tmp_path)

    def _boom(*a, **k):
        raise AssertionError("a confirmed record must not touch the calendar")

    monkeypatch.setattr(fa.anchor_submit, "_get_timestamp", _boom)
    monkeypatch.setattr(fa.anchor_submit, "_fetch_block_header", _boom)

    code = fa.main(["upgrade", "--anchor", str(apath)])
    assert code == 0
    out = capsys.readouterr().out.lower()
    assert "still pending" not in out          # the bug: a confirmed record is not pending
    assert "confirmed" in out


def test_cmd_upgrade_preserves_the_pending_proof_when_the_explorer_fails(
        tmp_path, capsys, monkeypatch):
    # The block landed (the calendar upgraded), but the block-header explorer errors
    # transiently. That must leave through a clean message and a nonzero exit with
    # the good pending .ots untouched, so a later re-run finishes the job -- not a
    # raw traceback with the sole pending proof already overwritten.
    digest = GENESIS_MERKLE
    rec = {"schema": "flywheel.anchor/v1", "digest_hex": digest.hex(),
           "signed_head": {"public_key": "00" * 32},
           "ots": {"state": "pending", "submitted_hex": "de", "nonce_hex": "ad",
                   "calendar": "https://cal.example"}}
    apath = tmp_path / "anchor.json"
    apath.write_text(json.dumps(rec), encoding="utf-8")
    pending = (MAGIC + b"\x01" + b"\x08" + digest + b"\x00" + PENDING_TAG
               + _varbytes(_varbytes(b"https://cal.example")))
    opath = tmp_path / "anchor.json.ots"
    opath.write_bytes(pending)

    monkeypatch.setattr(fa.anchor_submit, "_get_timestamp",
                        lambda uri, r_hex, **k: _bitcoin_edge(0))   # the block landed

    def _explorer_down(height, **k):
        raise fa.anchor_submit.SubmitError("blockstream.info: 503 Service Unavailable")

    monkeypatch.setattr(fa.anchor_submit, "_fetch_block_header", _explorer_down)

    code = fa.main(["upgrade", "--anchor", str(apath)])
    assert code != 0                                   # did not finish, said so
    assert opath.read_bytes() == pending               # the pending proof is untouched
    err = capsys.readouterr().err
    assert err.strip()                                 # a message, not a silent failure


def test_cmd_upgrade_preserves_the_pending_proof_when_the_continuation_is_garbage(
        tmp_path, capsys, monkeypatch):
    # A calendar answers 200 with bytes that do not reach a block. cmd_upgrade must
    # NOT overwrite the sole pending .ots with that unverifiable splice and exit 0;
    # it must refuse, keep the pending proof, and exit nonzero.
    digest = GENESIS_MERKLE
    rec = {"schema": "flywheel.anchor/v1", "digest_hex": digest.hex(),
           "signed_head": {"public_key": "00" * 32},
           "ots": {"state": "pending", "submitted_hex": "de", "nonce_hex": "ad",
                   "calendar": "https://cal.example"}}
    apath = tmp_path / "anchor.json"
    apath.write_text(json.dumps(rec), encoding="utf-8")
    pending = (MAGIC + b"\x01" + b"\x08" + digest + b"\x00" + PENDING_TAG
               + _varbytes(_varbytes(b"https://cal.example")))
    opath = tmp_path / "anchor.json.ots"
    opath.write_bytes(pending)

    monkeypatch.setattr(fa.anchor_submit, "_get_timestamp",
                        lambda uri, r_hex, **k: b"an-http-error-page-not-a-proof")

    code = fa.main(["upgrade", "--anchor", str(apath)])
    assert code != 0
    assert opath.read_bytes() == pending               # the only pending proof survives


def test_cmd_verify_reports_not_anchored_with_a_nonzero_exit(tmp_path, capsys):
    # An offline stamp (real head, no timestamp) is a valid head but not anchored.
    # `verify` end to end must print the head as ok and exit nonzero because the
    # timestamp is absent -- the exit code follows `ok`, wired through fa.main.
    key = _key()
    rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    apath = tmp_path / "anchor.json"
    apath.write_text(json.dumps(rec), encoding="utf-8")
    pub = key.public_key_bytes.hex()

    code = fa.main(["verify", "--anchor", str(apath), "--pub", pub])
    assert code != 0
    out = capsys.readouterr().out
    assert "head_ok   : True" in out
    assert "ANCHORED  : False" in out

def test_cmd_upgrade_never_strands_a_confirmed_record_over_a_stale_proof(
        tmp_path, capsys, monkeypatch):
    # The record and its .ots are two separate on-disk artifacts, written in
    # sequence, and a process can die between them. Writing the record first and
    # the proof second (or non-atomically) lets a crash during the proof write
    # leave a `confirmed` record beside the stale pending .ots; the confirmed
    # short-circuit then refuses to re-poll, so the obtained block is unrecoverable
    # from the CLI (Finding 7). Persisting the proof before the record, each atomic,
    # keeps every interruption on the safe side: the intact old pending pair, or a
    # confirmed pair, never a confirmed record over a proof that cannot back it.
    digest = GENESIS_MERKLE
    rec = {"schema": "flywheel.anchor/v1", "digest_hex": digest.hex(),
           "signed_head": {"public_key": "00" * 32},
           "ots": {"state": "pending", "submitted_hex": "de", "nonce_hex": "ad",
                   "calendar": "https://cal.example"}}
    apath = tmp_path / "anchor.json"
    apath.write_text(json.dumps(rec), encoding="utf-8")
    pending = (MAGIC + b"\x01" + b"\x08" + digest + b"\x00" + PENDING_TAG
               + _varbytes(_varbytes(b"https://cal.example")))
    opath = tmp_path / "anchor.json.ots"
    opath.write_bytes(pending)

    monkeypatch.setattr(fa.anchor_submit, "_get_timestamp",
                        lambda uri, r_hex, **k: _bitcoin_edge(0))
    monkeypatch.setattr(fa.anchor_submit, "_fetch_block_header",
                        lambda height, **k: GENESIS_HEADER)

    # The process dies the instant it goes to persist the proof bytes (the real
    # .ots or its temp sibling). Proof-first, this is reached before the record is
    # touched; record-first, the confirmed record has already landed.
    real_write_bytes = Path.write_bytes

    def _die_on_ots_write(self, data):
        if ".ots" in self.name:
            raise OSError("process killed mid-write")
        return real_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", _die_on_ots_write)

    with pytest.raises(OSError):
        fa.main(["upgrade", "--anchor", str(apath)])

    # The record must never claim confirmed while its .ots cannot verify offline.
    persisted = json.loads(apath.read_text(encoding="utf-8"))
    if persisted["ots"]["state"] == "confirmed":
        checked = ots_verify.verify(opath.read_bytes(), digest,
                                    fa._header_provider(persisted))
        assert checked["ok"] is True, (
            "record says confirmed but its .ots does not verify offline -- the "
            "confirmed short-circuit now blocks a re-run from finishing")


# Honest null: no fa.main(["verify"]) test drives the timestamp leg to ok=True
# offline. `verify_anchor` checks the .ots against sha256(canonical(signed_head)),
# so a Bitcoin leaf verifies only when that digest equals a real block's merkle
# root -- a sha256 preimage, not constructible here. The header-through-verify
# path is covered at the record level instead: test_apply_upgrade_confirms...,
# test_cmd_upgrade_polls_R... (asserts ots_verify.verify(..., _header_provider)
# is ok), and the _header_provider tests.
