"""Building, submitting and reproving a Rekor entry, with a fake transport.

No test here touches the network. The fake Rekor answers with the shapes the real
one returns; the real entries are checked in test_rekor_anchor_records.py.
"""
from __future__ import annotations

import base64
import json

import pytest

pytest.importorskip("nacl.bindings")

from harness import anchor_cli, cli_entry, rekor_online, rekor_submit, rekor_verify  # noqa: E402

SEED = bytes(range(1, 33))
ARTIFACT = b'{"schema":"flywheel.signed-tree-head/v1","size":3}'


def _signer():
    return rekor_submit.ph_signer_from_seed(SEED)


def test_entry_carries_only_hash_signature_and_key():
    sign_ph, public = _signer()
    entry = rekor_submit.proposed_entry(ARTIFACT, sign_ph, public)
    assert entry["kind"] == "hashedrekord"
    assert entry["spec"]["data"]["hash"]["algorithm"] == "sha512"
    wire = json.dumps(entry).encode()
    assert ARTIFACT not in wire and base64.b64encode(ARTIFACT) not in wire


def test_hash_only_guard_refuses_extra_fields_and_content():
    sign_ph, public = _signer()
    entry = rekor_submit.proposed_entry(ARTIFACT, sign_ph, public)
    extra = json.loads(json.dumps(entry))
    extra["spec"]["data"]["content"] = "x"
    with pytest.raises(rekor_submit.RekorError):
        rekor_submit.assert_hash_only(extra, ARTIFACT)
    smuggled = json.loads(json.dumps(entry))
    smuggled["spec"]["signature"]["content"] = base64.b64encode(ARTIFACT).decode()
    with pytest.raises(rekor_submit.RekorError):
        rekor_submit.assert_hash_only(smuggled, ARTIFACT)


def test_signer_refuses_a_key_that_is_not_the_pinned_one(tmp_path):
    key = tmp_path / "seed.hex"
    key.write_text(SEED.hex())
    with pytest.raises(rekor_submit.RekorError):
        rekor_submit.load_ph_signer(key, "00" * 32)
    _, public = rekor_submit.load_ph_signer(key, _signer()[1].hex())
    assert public == _signer()[1]


def test_submit_handles_created_duplicate_and_refusal():
    calls = []

    def request(method, url, body=None):
        calls.append((method, url))
        if method == "POST" and len(calls) == 1:
            return 201, json.dumps({"u1": {"logIndex": 5}}).encode(), {}
        if method == "POST":
            return 409, b"{}", {"Location": "/api/v1/log/entries/u2"}
        return 200, json.dumps({"u2": {"logIndex": 6}}).encode(), {}

    assert rekor_submit.submit({}, request) == ("u1", {"logIndex": 5})
    assert rekor_submit.submit({}, request) == ("u2", {"logIndex": 6})
    assert calls[-1] == ("GET", rekor_verify.REKOR_URL + "/api/v1/log/entries/u2")
    with pytest.raises(rekor_submit.RekorError):
        rekor_submit.submit({}, lambda *a, **k: (400, b"bad", {}))


def test_offline_check_names_the_body_failures():
    sign_ph, public = _signer()
    entry = rekor_submit.proposed_entry(ARTIFACT, sign_ph, public)
    body = base64.b64encode(json.dumps(entry).encode()).decode()
    rec = {"entry": {"body": body, "logID": rekor_verify.REKOR_LOG_ID,
                     "integratedTime": 1, "logIndex": 1, "verification": {}}}
    ok = rekor_verify.verify_record(rec, ARTIFACT, public)["reasons"]
    # A body we built ourselves has no Rekor signature, so only the log's parts fail.
    assert "ARTIFACT_HASH_DIFFERS" not in ok and "ARTIFACT_SIGNATURE_INVALID" not in ok
    assert "SET_INVALID" in ok
    other = rekor_verify.verify_record(rec, ARTIFACT + b" ", public)["reasons"]
    assert "ARTIFACT_HASH_DIFFERS" in other and "ARTIFACT_SIGNATURE_INVALID" in other
    wrong_key = rekor_verify.verify_record(rec, ARTIFACT, b"\x01" * 32)["reasons"]
    assert "BODY_KEY_NOT_PINNED_KEY" in wrong_key


def test_online_refetch_flags_a_changed_entry():
    stored = {"body": "YQ==", "integratedTime": 1, "logID": rekor_verify.REKOR_LOG_ID,
              "logIndex": 7, "verification": {}}
    changed = dict(stored, integratedTime=2)
    res = rekor_online.verify_online(
        {"uuid": "u", "entry": stored}, ARTIFACT, b"\x00" * 32,
        lambda m, u, body=None: (200, json.dumps({"u": changed}).encode(), {}))
    assert not res["ok"] and "REFETCHED_INTEGRATEDTIME_DIFFERS" in res["reasons"]


def test_cli_dry_run_sends_nothing(tmp_path, monkeypatch, capsys):
    key = tmp_path / "seed.hex"
    key.write_text(SEED.hex())
    head = tmp_path / "head.json"
    head.write_text(json.dumps({"b": 1, "a": 2}, indent=2), encoding="utf-8")

    def no_network(*a, **k):
        raise AssertionError("dry run touched the network")

    monkeypatch.setattr(rekor_submit, "urllib_request", no_network)
    assert anchor_cli.main(["head", str(head), "--key", str(key), "--dry-run"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["artifact_form"] == "canonical-json"
    want = __import__("hashlib").sha512(b'{"a":2,"b":1}').hexdigest()
    assert out["entry"]["spec"]["data"]["hash"]["value"] == want


def test_flywheel_anchor_is_a_packaged_command():
    assert cli_entry._PACKAGED["anchor"] == "harness.anchor_cli"
