"""The gate result as a signed receipt, and its re-derivation by a stranger.

A valid signature is not enough: verify() rescores the records against the pinned
set and reruns the planted controls, so a result re-signed over a changed verdict
is still refused. MATCH needs a trust root; UNANCHORED and UNSIGNED are not passes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.monitor_gate import gate_set, monitors, receipt, score  # noqa: E402
from harness.preaction import cli as monitor_cli  # noqa: E402

GATE = gate_set.load()


def _doc(name="oracle", key=None):
    monitor, descriptor = monitors.resolve(f"planted:{name}", seed=GATE.spec["random_seed"])
    records = score.run_monitor(GATE, monitor)
    result = score.decide(GATE, records, score.controls(GATE))
    return receipt.result_document(GATE, descriptor, records, result, signing_key=key)


def _key():
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from harness.receipt_signer import SigningKey
    return SigningKey(Ed25519PrivateKey.generate())


def test_unsigned_result_rederives_but_is_not_a_pass():
    report = receipt.verify(_doc())
    assert (report["status"], report["gate_verdict"], report["code_match"]) == (
        "UNSIGNED", "ADMIT", True)


def test_receipt_carries_the_gate_limits_and_rates():
    body = _doc("always-yes")["envelope"]["receipt"]
    for limit in receipt.LIMITS:
        assert limit in body["does_not_prove"]
    assert body["verdict"] == "FAIL"
    assert body["coverage"]["failed"] == ["known_visible:false_alarm"]
    assert body["coverage"]["sides"]["known_visible"]["upper"] == "1.0000"
    assert body["criterion_sha256"] == "sha256:" + gate_set.SPEC_SHA256
    assert body["denominator"]["filter_hash"] == "sha256:" + gate_set.SET_SHA256


def test_signed_result_matches_only_against_its_trust_root():
    key = _key()
    doc = _doc(key=key)
    assert receipt.verify(doc, trust_root=key.public_key_bytes)["status"] == "MATCH"
    assert receipt.verify(doc)["status"] == "UNANCHORED"
    other = _key()
    assert receipt.verify(doc, trust_root=other.public_key_bytes)["status"] == "MISMATCH"


def test_a_flipped_record_breaks_rederivation():
    doc = _doc()
    rec = next(r for r in doc["records"] if r["verdict"] == "NO")
    rec.update(raw="YES", verdict="YES")
    report = receipt.verify(doc)
    assert report["status"] == "MISMATCH"


def test_a_resigned_false_admission_is_still_refused():
    """Turn a REFUSE into ADMIT and sign it with a key the verifier trusts."""
    key = _key()
    doc = _doc("always-yes")
    body = doc["envelope"]["receipt"]
    body["coverage"]["gate_verdict"] = "ADMIT"
    body["verdict"] = "PASS"
    forged = receipt.Receipt.from_dict({**body, "does_not_prove": body["does_not_prove"]})
    from harness.receipt_signer import sign_receipt
    doc["envelope"] = sign_receipt(forged, key).to_dict()
    report = receipt.verify(doc, trust_root=key.public_key_bytes)
    assert report["status"] == "MISMATCH"
    assert "does not follow" in report["detail"]


def test_an_edited_rate_breaks_the_signature():
    key = _key()
    doc = _doc(key=key)
    doc["envelope"]["receipt"]["coverage"]["sides"]["known_invisible"]["upper"] = "0.0001"
    assert receipt.verify(doc, trust_root=key.public_key_bytes)["status"] == "MISMATCH"


@pytest.mark.parametrize("bad", [None, {}, {"schema": receipt.SCHEMA},
                                 {"schema": receipt.SCHEMA, "envelope": 5, "records": []}])
def test_verify_never_raises_on_garbage(bad):
    assert receipt.verify(bad)["status"] == "MISMATCH"


def _run(argv):
    import io
    out, err = io.StringIO(), io.StringIO()
    code = monitor_cli.main(argv, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


@pytest.mark.parametrize("name,code", [("oracle", 0), ("always-yes", 1), ("always-no", 1),
                                       ("always-unverifiable", 1), ("random", 1),
                                       ("shortcut", 1)])
def test_cli_exit_codes_follow_the_verdict(tmp_path, name, code):
    out_path = tmp_path / "r.json"
    got, out, _ = _run(["gate", f"planted:{name}", "--out", str(out_path), "--json"])
    assert got == code
    assert json.loads(out)["verdict"] == ("ADMIT" if code == 0 else "REFUSE")
    assert receipt.verify(json.loads(out_path.read_text()))["status"] == "UNSIGNED"


def test_cli_signs_and_verifies_end_to_end(tmp_path):
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    priv = Ed25519PrivateKey.generate()
    key_path = tmp_path / "key"
    key_path.write_bytes(priv.private_bytes(serialization.Encoding.PEM,
                                            serialization.PrivateFormat.OpenSSH,
                                            serialization.NoEncryption()))
    out_path = tmp_path / "r.json"
    assert _run(["gate", "planted:oracle", "--sign-key", str(key_path),
                 "--out", str(out_path)])[0] == 0
    pub = priv.public_key().public_bytes_raw().hex()
    code, out, _ = _run(["gate-verify", str(out_path), "--trust-root", pub])
    assert (code, json.loads(out)["status"]) == (0, "MATCH")
    assert _run(["gate-verify", str(out_path), "--trust-root", "00" * 32])[0] == 1


def test_cli_refuses_an_ollama_adapter_with_no_endpoint(tmp_path):
    code, _, err = _run(["gate", "ollama:some-model", "--out", str(tmp_path / "r.json")])
    assert code == 2 and "--endpoint" in err


def test_cli_reports_unverifiable_when_the_pin_breaks(tmp_path, monkeypatch):
    monkeypatch.setattr(gate_set, "SET_SHA256", "0" * 64)
    code, _, err = _run(["gate", "planted:oracle", "--out", str(tmp_path / "r.json")])
    assert code == 3 and "UNVERIFIABLE" in err

