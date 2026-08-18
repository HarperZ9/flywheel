"""The bundle: everything a stranger needs, and nothing that could hurt them.

A receipt alone is not enough to re-derive anything. The criterion it was judged
against, the checker source that judged it, the QA card that bounds the checker's
false accepts, and a tree head to anchor the log all have to travel with it. That
is the bundle.

Two halves, and the second is the one that matters for safety:

  PACK writes a directory plus a manifest that binds every file by sha256, strips
  local-only signatures, and refuses to ship if a secret scan hits.

  VERIFY is what a stranger runs on a bundle THEY did not build, so it treats
  every path in the manifest as hostile: absolute paths, parent traversal, and
  symlinks are refused before anything is opened. A verifier that trusts manifest
  paths is a file-write primitive wearing a checker's coat.
"""
import json
import os
from pathlib import Path

import pytest

from harness.bundle import (
    pack_bundle, verify_bundle, BundleError, MANIFEST_NAME, scan_for_secrets,
    safe_relative,
)
from harness.receipt import Receipt
from harness.receipt_fields import (
    Budget, Denominator, EvidenceKind, Tier)
from harness.receipt_sign import unsigned, hmac_sign, ed25519_attach
from harness.verdict import Verdict, Attribution

import receipt_factories as factories


def _den():
    return factories.den(filter_id="f.v1")


def _r(objective="21"):
    return factories.receipt(objective=objective, denominator=_den())


def _parts(**over):
    base = dict(
        envelopes=[unsigned(_r("21")), unsigned(_r("22"))],
        criterion={"criterion_id": "zarankiewicz.z_2_2", "version": 1,
                   "criterion_sha256": "sha256:" + "c" * 64},
        checker_sources={"zarankiewicz.py": "def k22_free(): return True\n"},
        qa_card={"schema": "flywheel.oracle-qa-card/v2", "passed": True,
                 "false_accept_upper_bound": "0.021600"},
        tree_head={"schema": "flywheel.tree-head/v1", "size": 2,
                   "root": "sha256:" + "1" * 64})
    base.update(over)
    return base


def _pack(tmp_path, **over):
    return pack_bundle(tmp_path / "b.frb", **_parts(**over))


# --- packing ------------------------------------------------------------------

def test_packing_writes_a_manifest_and_the_parts(tmp_path):
    d = _pack(tmp_path)
    assert (d / MANIFEST_NAME).exists()
    m = json.loads((d / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert m["schema"].startswith("flywheel.bundle/")
    names = {f["path"] for f in m["files"]}
    assert "criterion.json" in names
    assert "qa_card.json" in names
    assert "tree_head.json" in names
    assert any(n.startswith("receipts/") for n in names)
    assert any(n.startswith("checker/") for n in names)


def test_the_manifest_binds_every_file_by_hash(tmp_path):
    d = _pack(tmp_path)
    m = json.loads((d / MANIFEST_NAME).read_text(encoding="utf-8"))
    import hashlib
    for f in m["files"]:
        actual = hashlib.sha256((d / f["path"]).read_bytes()).hexdigest()
        assert f["sha256"] == actual, f["path"]


def test_the_manifest_is_not_listed_in_itself(tmp_path):
    d = _pack(tmp_path)
    m = json.loads((d / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert MANIFEST_NAME not in {f["path"] for f in m["files"]}


def test_a_reproduce_script_ships_with_the_bundle(tmp_path):
    d = _pack(tmp_path)
    assert (d / "reproduce.py").exists()
    text = (d / "reproduce.py").read_text(encoding="utf-8")
    assert "verify_bundle" in text or "manifest" in text.lower()


def test_packing_is_deterministic(tmp_path):
    a = json.loads((_pack(tmp_path / "x") / MANIFEST_NAME)
                   .read_text(encoding="utf-8"))
    b = json.loads((_pack(tmp_path / "y") / MANIFEST_NAME)
                   .read_text(encoding="utf-8"))
    assert a["files"] == b["files"]


def test_packing_refuses_an_empty_bundle(tmp_path):
    with pytest.raises(BundleError):
        pack_bundle(tmp_path / "b.frb", **_parts(envelopes=[]))


# --- local signatures are stripped --------------------------------------------

def test_a_local_only_signature_is_stripped_at_pack_time(tmp_path):
    signed = hmac_sign(_r(), b"a-local-secret", key_id="local").to_dict()
    d = _pack(tmp_path, envelopes=[signed])
    body = json.loads((d / "receipts" / sorted(
        os.listdir(d / "receipts"))[0]).read_text(encoding="utf-8"))
    assert body["signature"] is None
    assert "NOT_THIRD_PARTY_VERIFIABLE_SIGNATURE" in body["receipt"]["does_not_prove"]
    assert verify_bundle(d)["verdict"] == "MATCH"


def test_no_secret_reaches_the_packed_bundle(tmp_path):
    secret = b"correct-horse-battery-staple"
    signed = hmac_sign(_r(), secret, key_id="local").to_dict()
    d = _pack(tmp_path, envelopes=[signed])
    blob = "".join((d / p).read_text(encoding="utf-8", errors="replace")
                   for p in ("manifest.json",))
    for f in (d / "receipts").iterdir():
        blob += f.read_text(encoding="utf-8", errors="replace")
    assert secret.decode() not in blob


def test_an_ed25519_signature_survives_packing(tmp_path):
    nacl = pytest.importorskip("nacl.signing")
    sk = nacl.SigningKey.generate()
    r = _r()
    env = ed25519_attach(r, bytes(sk.sign(r.claim_sha256().encode()).signature),
                         bytes(sk.verify_key), key_id="k1").to_dict()
    d = _pack(tmp_path, envelopes=[env])
    body = json.loads((d / "receipts" / sorted(
        os.listdir(d / "receipts"))[0]).read_text(encoding="utf-8"))
    assert body["signature"]["sig_alg"] == "ed25519"


# --- the secret scan hard-fails -----------------------------------------------

@pytest.mark.parametrize("text", [
    "AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE",
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
    "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
    "Authorization: Bearer sk-live-0123456789abcdefghij",
])
def test_the_secret_scan_hits_known_shapes(text):
    hits = scan_for_secrets(text)
    assert hits, text


def test_the_secret_scan_does_not_hit_ordinary_hashes():
    assert not scan_for_secrets("sha256:" + "a" * 64)
    assert not scan_for_secrets('{"claim_sha256": "sha256:deadbeef"}')


def test_packing_refuses_when_a_checker_source_carries_a_secret(tmp_path):
    with pytest.raises(BundleError) as e:
        _pack(tmp_path, checker_sources={
            "bad.py": "TOKEN = 'ghp_abcdefghijklmnopqrstuvwxyz0123456789'\n"})
    assert "secret" in str(e.value).lower()


# --- verifying a bundle someone else built ------------------------------------

def test_a_freshly_packed_bundle_verifies(tmp_path):
    d = _pack(tmp_path)
    v = verify_bundle(d)
    assert v["verdict"] == "MATCH"
    assert v["files_checked"] >= 5


def test_an_edited_file_is_caught(tmp_path):
    d = _pack(tmp_path)
    (d / "criterion.json").write_text('{"criterion_id":"something-else"}',
                                      encoding="utf-8")
    v = verify_bundle(d)
    assert v["verdict"] == "DRIFT"
    assert "criterion.json" in v["detail"]


def test_a_missing_file_is_caught(tmp_path):
    d = _pack(tmp_path)
    (d / "qa_card.json").unlink()
    assert verify_bundle(d)["verdict"] == "DRIFT"


def test_an_extra_unlisted_file_is_caught(tmp_path):
    # A file nobody vouched for is not evidence, and shipping it under a
    # verified-looking bundle is how something unreviewed gets read as reviewed.
    d = _pack(tmp_path)
    (d / "surprise.json").write_text("{}", encoding="utf-8")
    v = verify_bundle(d)
    assert v["verdict"] == "DRIFT"
    assert "surprise.json" in v["detail"]


def test_a_receipt_whose_digest_does_not_match_its_body_is_caught(tmp_path):
    d = _pack(tmp_path)
    p = sorted((d / "receipts").iterdir())[0]
    body = json.loads(p.read_text(encoding="utf-8"))
    body["receipt"]["objective"] = "999"
    p.write_text(json.dumps(body), encoding="utf-8")
    # The manifest hash catches the byte change first; that is correct and is
    # still a refusal.
    assert verify_bundle(d)["verdict"] == "DRIFT"


def test_a_missing_manifest_is_unverifiable_never_match(tmp_path):
    d = _pack(tmp_path)
    (d / MANIFEST_NAME).unlink()
    assert verify_bundle(d)["verdict"] == "UNVERIFIABLE"


def test_a_corrupt_manifest_is_unverifiable(tmp_path):
    d = _pack(tmp_path)
    (d / MANIFEST_NAME).write_text("{not json", encoding="utf-8")
    assert verify_bundle(d)["verdict"] == "UNVERIFIABLE"


def test_a_nonexistent_bundle_is_unverifiable(tmp_path):
    assert verify_bundle(tmp_path / "nope")["verdict"] == "UNVERIFIABLE"


# --- hostile manifest paths ----------------------------------------------------

@pytest.mark.parametrize("hostile", [
    "../escape.json",
    "a/../../escape.json",
    "/etc/passwd",
    "C:/Windows/System32/x.dll",
    "a/./../../b.json",
])
def test_safe_relative_refuses_traversal_and_absolute_paths(hostile):
    with pytest.raises(BundleError):
        safe_relative(hostile)


def test_safe_relative_accepts_ordinary_nested_paths():
    assert safe_relative("receipts/a.json") == Path("receipts/a.json")
    assert safe_relative("checker/zarankiewicz.py") == Path("checker/zarankiewicz.py")


def test_a_manifest_with_a_traversal_path_is_refused(tmp_path):
    # This is the attack: verify() on an untrusted bundle must not be persuaded
    # to read or report on a file outside the bundle.
    d = _pack(tmp_path)
    m = json.loads((d / MANIFEST_NAME).read_text(encoding="utf-8"))
    m["files"].append({"path": "../../../../etc/passwd", "sha256": "0" * 64})
    (d / MANIFEST_NAME).write_text(json.dumps(m), encoding="utf-8")
    v = verify_bundle(d)
    assert v["verdict"] == "UNVERIFIABLE"
    assert "path" in v["detail"].lower()


def test_a_manifest_with_an_absolute_path_is_refused(tmp_path):
    d = _pack(tmp_path)
    m = json.loads((d / MANIFEST_NAME).read_text(encoding="utf-8"))
    m["files"].append({"path": "/etc/shadow", "sha256": "0" * 64})
    (d / MANIFEST_NAME).write_text(json.dumps(m), encoding="utf-8")
    assert verify_bundle(d)["verdict"] == "UNVERIFIABLE"


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlink support")
def test_a_symlink_in_the_bundle_is_refused(tmp_path):
    d = _pack(tmp_path)
    target = tmp_path / "outside.txt"
    target.write_text("secret-ish", encoding="utf-8")
    link = d / "receipts" / "link.json"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted here")
    v = verify_bundle(d)
    assert v["verdict"] in ("DRIFT", "UNVERIFIABLE")


# --- the bundle states its own limits -----------------------------------------

def test_the_bundle_carries_what_it_does_not_prove(tmp_path):
    d = _pack(tmp_path)
    m = json.loads((d / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert m["does_not_prove"]
    joined = " ".join(m["does_not_prove"])
    assert "COMPLETENESS" in joined


def test_verification_reports_signature_state_per_receipt(tmp_path):
    d = _pack(tmp_path)
    v = verify_bundle(d)
    assert v["receipts"]
    for r in v["receipts"]:
        assert "signature" in r
        assert "claim_sha256" in r
