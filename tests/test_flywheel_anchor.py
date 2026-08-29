"""The anchor CLI ties the key, the signed head, and the timestamp end to end.

These exercise the testable core the CLI is built from: what `keygen` prints
(public material only, never the secret), what `stamp` writes (a head a stranger
checks, with the timestamp record embedded), what `verify` concludes, and how
`upgrade` rebuilds a full proof from the artifact digest. The network legs are
thin wrappers over `anchor_submit`, injected here so the core is exercised
offline; the live round trip is proven separately against a real calendar.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness import ots_verify  # noqa: E402
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


def test_keygen_report_shows_public_material_and_never_the_private_key():
    info = receipt_signer.SigningKeyInfo(
        private_key_path=Path("/held/offline/receipt-signing-ed25519"),
        public_key_path=Path("/held/offline/receipt-signing-ed25519.pub"),
        public_key_bytes=b"\x11" * 32,
        key_id=receipt_signer.key_id_for(b"\x11" * 32),
        fingerprint=receipt_signer.fingerprint_for(b"\x11" * 32))
    out = "\n".join(fa.keygen_report(info))
    assert info.key_id in out and info.fingerprint in out
    assert "ssh-ed25519 " in out            # the public line to upload
    assert "gh ssh-key add" in out          # the exact next command
    assert "BEGIN OPENSSH PRIVATE KEY" not in out
    assert "\x11" * 32 not in out           # no raw secret, ever


def test_build_stamp_offline_produces_a_head_a_stranger_can_check():
    key = _key()
    anchor_rec, ots = fa.build_stamp(HEAD, key, TS, submit=None)
    assert ots is None
    assert anchor_rec["ots"]["state"] == "absent"
    r = fa.verify_stamp(anchor_rec, None, key.public_key_bytes)
    assert r["head_ok"] is True


def test_build_stamp_online_embeds_the_ots_record_and_binds_the_digest():
    key = _key()
    anchor_rec, ots = fa.build_stamp(HEAD, key, TS, submit=_fake_submit())
    assert ots is not None
    assert anchor_rec["ots"]["state"] == "pending"
    assert anchor_rec["ots"]["calendar"] == "https://cal.example"
    assert len(bytes.fromhex(anchor_rec["ots"]["nonce_hex"])) == 16
    r = fa.verify_stamp(anchor_rec, ots, key.public_key_bytes)
    assert r["timestamp"]["file_digest"] == anchor_rec["digest_hex"]


def test_verify_stamp_catches_a_timestamp_over_a_different_digest():
    key = _key()
    # a calendar reply that (via the fake) commits the wrong artifact: forge by
    # stamping a different digest, then checking against the real anchor.
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    wrong = fa.anchor_submit.build_ots(b"\x00" * 32, b"\x5a" * 16, _calendar_reply())
    r = fa.verify_stamp(anchor_rec, wrong, key.public_key_bytes)
    assert r["ok"] is False
    assert "digest_mismatch" in r["timestamp"]["reason"]


def test_apply_upgrade_confirms_and_stores_the_verified_block_header():
    # a spliced full proof whose merkle root is the artifact digest, with the
    # matching header, is confirmed AND carries the header a stranger needs to
    # prove the block offline. (digest == genesis merkle so a real header exists.)
    digest = GENESIS_MERKLE
    rec = {"digest_hex": digest.hex(),
           "ots": {"state": "pending", "submitted_hex": "de",
                   "nonce_hex": "ad", "calendar": "https://cal.example"}}
    new_rec, new_ots = fa.apply_upgrade(rec, _full_block_proof(digest),
                                        header=GENESIS_HEADER)
    assert new_rec["ots"]["state"] == "confirmed"
    assert new_rec["ots"]["block_height"] == 0
    assert new_rec["ots"]["block_header"] == GENESIS_HEADER.hex()
    # the record now verifies offline from its own stored header, no network
    checked = ots_verify.verify(new_ots, digest, fa._header_provider(new_rec))
    assert checked["ok"] is True


def test_apply_upgrade_stores_no_header_when_the_block_does_not_verify():
    # a bitcoin leaf landed, but the supplied header does not verify the block:
    # the height is recorded honestly, the wrong header is NOT persisted.
    digest = GENESIS_MERKLE
    rec = {"digest_hex": digest.hex(), "ots": {"state": "pending"}}
    wrong = bytes(80)   # 80 zero bytes: no work, wrong merkle
    new_rec, _ = fa.apply_upgrade(rec, _full_block_proof(digest), header=wrong)
    assert new_rec["ots"]["state"] == "confirmed"     # the block did land
    assert new_rec["ots"]["block_height"] == 0
    assert "block_header" not in new_rec["ots"]        # but never a header that lies


def test_apply_upgrade_stays_pending_without_a_bitcoin_leaf():
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=_fake_submit())
    digest = bytes.fromhex(anchor_rec["digest_hex"])
    # the calendar's continuation is still just a pending promise, no block
    pending_full = fa.anchor_submit.build_ots(
        digest, bytes.fromhex(anchor_rec["ots"]["nonce_hex"]), _calendar_reply())
    new_anchor, _ = fa.apply_upgrade(anchor_rec, pending_full)
    assert new_anchor["ots"]["state"] == "pending"
    assert "block_header" not in new_anchor["ots"]


def test_header_provider_yields_the_stored_header_for_its_height_only():
    rec = {"ots": {"block_header": GENESIS_HEADER.hex(), "block_height": 964462}}
    provider = fa._header_provider(rec)
    assert provider(964462) == GENESIS_HEADER
    assert provider(964463) is None            # a different height gets nothing


def test_header_provider_is_none_without_a_stored_header():
    assert fa._header_provider({"ots": {"state": "pending"}}) is None
    assert fa._header_provider({}) is None


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

# Honest null: no fa.main(["verify"]) test drives the timestamp leg to ok=True
# offline. `verify_anchor` checks the .ots against sha256(canonical(signed_head)),
# so a Bitcoin leaf verifies only when that digest equals a real block's merkle
# root -- a sha256 preimage, not constructible here. The header-through-verify
# path is covered at the record level instead: test_apply_upgrade_confirms...,
# test_cmd_upgrade_polls_R... (asserts ots_verify.verify(..., _header_provider)
# is ok), and the _header_provider tests.


def test_a_stamped_anchor_serializes_to_json_without_raw_bytes():
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=_fake_submit())
    round_tripped = json.loads(json.dumps(anchor_rec))
    assert round_tripped["ots"]["submitted_hex"] == anchor_rec["ots"]["submitted_hex"]


# --- the Zenodo durability leg: a dry run before the one live mint ----------
#
# The DOI is irreversible: a published record cannot be unpublished. So the
# producer step before it is a dry run that computes the exact (filename, size,
# bound digest) a deposit WOULD carry and a metadata skeleton to review, and
# calls nothing. It must also refuse a record whose stored digest disagrees with
# its own head here, at the terminal, not at the network, so a corrupt record is
# caught before the operator crosses the live gate.

def test_zenodo_dry_run_reports_the_bound_bytes_and_the_digest():
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    report = fa.zenodo_dry_run(anchor_rec)
    assert report["filename"] == "signed-head.json"
    # the deposited bytes are the canonical signed head, and their sha256 IS the
    # record's digest, so the DOI witnesses the same digest the Bitcoin leg does
    from harness.receipt_fields import canonical
    assert report["size_bytes"] == len(canonical(anchor_rec["signed_head"]).encode())
    assert report["bound_digest"] == anchor_rec["anchor_digest"]
    assert report["digest_hex"] == anchor_rec["digest_hex"]
    assert report["metadata"]["metadata"]["title"]        # a fillable skeleton
    assert report["metadata"]["metadata"]["creators"]


def test_zenodo_dry_run_refuses_a_record_whose_digest_disagrees_with_its_head():
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    anchor_rec["digest_hex"] = "00" * 32          # no longer matches the head
    with pytest.raises(fa.zenodo_deposit.DepositError):
        fa.zenodo_dry_run(anchor_rec)


def test_zenodo_dry_run_surfaces_the_binding_caveats():
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    report = fa.zenodo_dry_run(anchor_rec)
    joined = " ".join(report["does_not_prove"])
    assert "NOT_PROVES_THE_TIMESTAMP" in joined     # a DOI alone orders nothing


def test_zenodo_dry_run_metadata_is_overridable():
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    report = fa.zenodo_dry_run(
        anchor_rec, title="Custom title",
        creators=[{"name": "Doe, Jane"}])
    md = report["metadata"]["metadata"]
    assert md["title"] == "Custom title"
    assert md["creators"] == [{"name": "Doe, Jane"}]


def test_cmd_zenodo_is_a_dry_run_and_never_touches_the_network(tmp_path, capsys,
                                                               monkeypatch):
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    path = tmp_path / "anchor.json"
    path.write_text(json.dumps(anchor_rec), encoding="utf-8")

    def _boom(*a, **k):
        raise AssertionError("a dry run must not reach the deposit client")

    monkeypatch.setattr(fa.zenodo_deposit, "deposit", _boom)
    code = fa.main(["zenodo", "--anchor", str(path)])
    assert code == 0
    out = capsys.readouterr().out
    assert "signed-head.json" in out
    assert anchor_rec["anchor_digest"] in out
    assert "dry run" in out.lower()          # says plainly it minted nothing


def test_cmd_zenodo_refuses_a_corrupt_record_with_a_nonzero_exit(tmp_path, capsys):
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    anchor_rec["digest_hex"] = "00" * 32
    path = tmp_path / "anchor.json"
    path.write_text(json.dumps(anchor_rec), encoding="utf-8")
    code = fa.main(["zenodo", "--anchor", str(path)])
    assert code != 0
    err = capsys.readouterr().err
    assert "REFUSED" in err


# --- the Zenodo live deposit: the one gated step past the dry run ------------
#
# Past the dry run is a single live deposit. It must upload exactly the bound
# bytes the dry run showed, read its token from a file and never from argv or a
# URL, stay a draft unless --publish is given (publish is the one irreversible
# switch), and route a corrupt record to a refusal before any network call. The
# transport is injected, so these run against a fake and never a live service.

class _FakeTransport:
    """Records every call and returns programmed (status, body) replies in order."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []

    def __call__(self, method, url, *, headers=None, body=None):
        self.calls.append((method, url, dict(headers or {}), body))
        status, payload = self._replies.pop(0)
        if isinstance(payload, (bytes, bytearray)):
            return status, bytes(payload)
        return status, json.dumps(payload).encode()


def _created(dep_id=51, base="https://sandbox.zenodo.org/api"):
    self_url = f"{base}/deposit/depositions/{dep_id}"
    return {"id": dep_id, "links": {
        "self": self_url,
        "bucket": f"{base}/files/bucket-{dep_id}",
        "publish": f"{self_url}/actions/publish"}}


def test_zenodo_live_deposits_exactly_the_bound_bytes_as_a_draft():
    from harness.receipt_fields import canonical
    key = _key()
    rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    want = canonical(rec["signed_head"]).encode()
    ft = _FakeTransport([
        (201, _created()),                    # create
        (201, {"key": "signed-head.json"}),   # upload
        (200, _created()),                    # set metadata
    ])
    result = fa.zenodo_live(rec, ft, token="tok_never_in_url",
                            sandbox=True, publish=False)
    assert result["published"] is False
    assert result["anchor_digest"] == rec["anchor_digest"]
    put = [c for c in ft.calls if c[0] == "PUT" and "/files/" in c[1]]
    assert len(put) == 1 and put[0][3] == want   # the exact canonical head bytes
    for (_m, url, headers, _b) in ft.calls:
        assert "tok_never_in_url" not in url     # never in a URL
        assert headers["Authorization"] == "Bearer tok_never_in_url"


def test_zenodo_live_publish_is_the_one_irreversible_switch():
    key = _key()
    rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    ft = _FakeTransport([
        (201, _created()),
        (201, {"key": "signed-head.json"}),
        (200, _created()),
        (202, {"doi": "10.5281/zenodo.9",
               "links": {"doi": "https://doi.org/10.5281/zenodo.9"}}),
    ])
    result = fa.zenodo_live(rec, ft, token="t", sandbox=True, publish=True)
    assert result["published"] is True
    assert result["doi"] == "10.5281/zenodo.9"
    assert any(c[0] == "POST" and c[1].endswith("/actions/publish")
               for c in ft.calls)


def test_zenodo_live_refuses_a_corrupt_record_before_any_network():
    key = _key()
    rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    rec["digest_hex"] = "00" * 32
    ft = _FakeTransport([])   # any network call pops an empty list and raises
    with pytest.raises(fa.zenodo_deposit.DepositError):
        fa.zenodo_live(rec, ft, token="t", sandbox=True, publish=True)
    assert ft.calls == []     # nothing was sent


def test_cmd_zenodo_live_reads_the_token_from_a_file_and_never_from_argv(
        tmp_path, capsys, monkeypatch):
    key = _key()
    rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    apath = tmp_path / "anchor.json"
    apath.write_text(json.dumps(rec), encoding="utf-8")
    tpath = tmp_path / "sandbox.token"
    tpath.write_text("SECRET_TOKEN_VALUE\n", encoding="utf-8")  # trailing newline stripped
    ft = _FakeTransport([
        (201, _created()),
        (201, {"key": "signed-head.json"}),
        (200, _created()),
    ])
    monkeypatch.setattr(fa.zenodo_deposit, "urllib_transport", ft)
    code = fa.main(["zenodo", "--anchor", str(apath), "--live",
                    "--sandbox", "--token-file", str(tpath)])
    assert code == 0
    assert any(h.get("Authorization") == "Bearer SECRET_TOKEN_VALUE"
               for (_m, _u, h, _b) in ft.calls)     # read from the file
    out = capsys.readouterr().out
    assert "SANDBOX" in out
    assert "SECRET_TOKEN_VALUE" not in out          # the token is never printed


def test_cmd_zenodo_live_refuses_a_missing_token_file(tmp_path, capsys):
    key = _key()
    rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    apath = tmp_path / "anchor.json"
    apath.write_text(json.dumps(rec), encoding="utf-8")
    code = fa.main(["zenodo", "--anchor", str(apath), "--live",
                    "--token-file", str(tmp_path / "nope.token")])
    assert code != 0
    err = capsys.readouterr().err
    assert "token" in err.lower()


def test_read_token_strips_a_utf8_bom(tmp_path):
    # PowerShell's default Out-File writes UTF-8 with a BOM. A BOM is not
    # whitespace, so .strip() leaves it on the token and corrupts the Bearer
    # header. The reader must strip it.
    tpath = tmp_path / "bom.token"
    tpath.write_bytes(b"\xef\xbb\xbfTOKEN_VALUE")   # UTF-8 BOM then the token
    token = fa._read_token(str(tpath))
    assert token == "TOKEN_VALUE"
    assert not token.startswith("﻿")


def test_read_token_funnels_an_unreadable_path_through_deposit_error(tmp_path):
    # A --token-file that is a directory (or otherwise unreadable) must leave
    # through DepositError, the one taxonomy this path uses, not a raw traceback.
    with pytest.raises(fa.zenodo_deposit.DepositError):
        fa._read_token(str(tmp_path))   # a directory, not a file


def test_zenodo_live_report_lines_tolerates_a_none_file_entry():
    # If an upload reply is a 2xx with an empty body, the file key is None. This
    # print runs AFTER a successful publish, so a crash here would hide the DOI
    # and invite a second, duplicate mint. It must not raise.
    result = {"deposition_id": 7, "self_url": "https://zenodo.org/api/x",
              "files": [None], "anchor_digest": "sha256:" + "a" * 64,
              "published": True, "doi": "10.5281/zenodo.7",
              "doi_url": "https://doi.org/10.5281/zenodo.7", "does_not_prove": []}
    lines = fa.zenodo_live_report_lines(result, sandbox=False)
    assert any("10.5281/zenodo.7" in ln for ln in lines)


def test_cmd_zenodo_refuses_publish_without_live(tmp_path, capsys):
    # --publish without --live is a nonsensical combination (a dry run mints
    # nothing). It must be refused, not silently ignored.
    code = fa.main(["zenodo", "--anchor", str(tmp_path / "any.json"), "--publish"])
    assert code != 0
    assert "--live" in capsys.readouterr().err


def test_cmd_zenodo_refuses_a_missing_anchor_file(tmp_path, capsys):
    # A missing or malformed --anchor file must leave through the REFUSED path,
    # not an uncaught traceback.
    code = fa.main(["zenodo", "--anchor", str(tmp_path / "nope.json")])
    assert code != 0
    assert "anchor" in capsys.readouterr().err.lower()
