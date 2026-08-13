from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys

import pytest

from harness.evidence_journey import append_event, new_journey, run_journey_check
from harness.evidence_json import canonical_sha256
from harness.evidence_packet import pack_journey_packet, verify_journey_packet


def _journey():
    journey = new_journey(
        journey_id="software-failure-v1", goal="Reproduce the software failure",
        intake={"summary": "add returns the wrong value"},
        created_at="2026-08-12T12:00:00Z",
    )
    return append_event(journey, {
        "stage": "decomposed", "occurred_at": "2026-08-12T12:01:00Z",
        "claims": [{
            "claim_id": "claim-root", "statement": "The submitted add fails its test",
            "depends_on": [], "verdict": "UNDECIDED",
            "reason": "registered checker has not run", "receipt_refs": [],
        }],
    })


def _software_fixture(tmp_path, *, slow=False):
    root = tmp_path / "artifacts"
    root.mkdir()
    candidate = root / "candidate.py"
    candidate.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    test_body = (
        "import time\nfrom candidate import add\n"
        + ("def test_add():\n    time.sleep(10)\n" if slow else
           "def test_add():\n    assert add(2, 3) == 5\n")
    )
    (root / "test_candidate.py").write_text(test_body, encoding="utf-8")
    context = {
        "task_id": "software-failure-v1", "prompt": "Repair add",
        "oracle_cmd": f'"{sys.executable}" -m pytest test_candidate.py',
        "candidate_ref": "candidate.py",
        "raw_artifact_refs": ["candidate.py", "test_candidate.py"],
        "timeout_seconds": 1 if slow else 15,
    }
    return root, candidate, context


def _checked(tmp_path, *, slow=False):
    journey = _journey()
    root, candidate, context = _software_fixture(tmp_path, slow=slow)
    check = run_journey_check(journey, "claim-root", "code", candidate, context)
    return journey, root, check


def _conclude(journey, check, **claim_overrides):
    claim = {
        "claim_id": "claim-root", "statement": "The submitted add fails its test",
        "depends_on": [], "verdict": check["verdict"],
        "receipt_refs": [check["receipt_ref"]],
        "raw_artifact_refs": check["raw_artifact_refs"],
    }
    claim.update(claim_overrides)
    if claim["verdict"] in {"UNDECIDED", "UNVERIFIABLE"}:
        claim.setdefault("reason", check.get("reason", "checker did not dispose"))
    return append_event(journey, {
        "stage": "preflight", "occurred_at": "2026-08-12T12:02:00Z",
        "claims": [claim],
    })


def _rewrite_manifest_hash(packet, rel):
    manifest_path = packet / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest["files"]:
        if item["path"] == rel:
            data = (packet / rel).read_bytes()
            item["sha256"] = hashlib.sha256(data).hexdigest()
            item["bytes"] = len(data)
            break
    manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")


def test_registered_code_oracle_emits_typed_failure_and_receipt(tmp_path):
    journey, root, check = _checked(tmp_path)
    assert check["verdict"] == "FAIL"
    assert check["oracle_id"] == "code" and check["oracle_type"] == "pytest"
    assert check["execution"] == "COMPLETED" and check["attribution"] == "CANDIDATE"
    assert check["claim_verdict_before"] == "UNDECIDED"
    assert check["denominator"] == {
        "attempts": 1, "oracle_calls_consumed": 1, "hits": 0,
        "undecided": 0, "unverifiable": 0, "timeouts": 0,
    }
    envelope = json.loads((root / check["receipt_ref"]).read_text(encoding="utf-8"))
    assert envelope["receipt"]["verdict"] == "FAIL"
    assert envelope["receipt"]["objective"] == "claim-root"
    assert envelope["receipt"]["does_not_prove"]
    assert journey == _journey()
    assert str(root.resolve()) not in json.dumps(check)


def test_unknown_oracle_is_typed_unverifiable_without_dispatch(tmp_path):
    journey = _journey()
    root, candidate, context = _software_fixture(tmp_path)
    check = run_journey_check(journey, "claim-root", "shell-plugin", candidate, context)
    assert check["verdict"] == "UNVERIFIABLE"
    assert check["unverifiable_reason"] == "ORACLE_UNAVAILABLE"
    assert check["oracle_calls_consumed"] == 0
    assert "receipt_ref" not in check
    assert not (root / "receipts").exists()


def test_timeout_remains_candidate_failure_with_typed_execution(tmp_path):
    _, root, check = _checked(tmp_path, slow=True)
    assert check["verdict"] == "FAIL"
    assert check["execution"] == "TIMEOUT"
    assert check["attribution"] == "CANDIDATE"
    assert check["denominator"]["timeouts"] == 1
    assert (root / check["receipt_ref"]).is_file()


@pytest.mark.parametrize("candidate_kind", ["missing", "directory"])
def test_malformed_candidate_fails_closed_without_receipt(tmp_path, candidate_kind):
    root, candidate, context = _software_fixture(tmp_path)
    if candidate_kind == "missing":
        candidate.unlink()
    else:
        candidate.unlink()
        candidate.mkdir()
    check = run_journey_check(_journey(), "claim-root", "code", candidate, context)
    assert check["verdict"] == "UNVERIFIABLE"
    assert check["unverifiable_reason"] == "MALFORMED_CANDIDATE"
    assert "receipt_ref" not in check
    assert not (root / "receipts").exists()


def test_context_is_a_closed_bounded_json_envelope(tmp_path):
    _, candidate, context = _software_fixture(tmp_path)
    context["plugin"] = "arbitrary.module:Oracle"
    result = run_journey_check(_journey(), "claim-root", "code", candidate, context)
    assert result["verdict"] == "UNVERIFIABLE"
    assert result["unverifiable_reason"] == "INVALID_CONTEXT"
    assert "unknown" in result["reason"]


def test_packet_binds_journey_receipt_raw_evidence_and_checker(tmp_path):
    journey, root, check = _checked(tmp_path)
    journey = _conclude(journey, check)
    packet = tmp_path / "packet"
    packed = pack_journey_packet(packet, journey=journey, artifact_root=root)
    assert packed["verdict"] == "MATCH"
    criterion = json.loads((packet / "criterion.json").read_text(encoding="utf-8"))
    assert criterion["journey"] == journey
    assert criterion["event_head_sha256"] == journey["event_head_sha256"]
    assert criterion["raw_artifacts"] and criterion["receipts"]
    assert criterion["checker_manifest"] and criterion["does_not_prove"]
    assert criterion["criteria"][0]["denominator"]["attempts"] == 1
    assert verify_journey_packet(packet)["verdict"] == "MATCH"


def test_clean_directory_recheck_is_offline_and_serializes_no_host_root(
        tmp_path, monkeypatch):
    journey, root, check = _checked(tmp_path)
    packet = tmp_path / "packet"
    pack_journey_packet(packet, journey=_conclude(journey, check), artifact_root=root)
    clean = tmp_path / "clean" / "packet"
    clean.parent.mkdir()
    shutil.copytree(packet, clean)
    monkeypatch.chdir(clean.parent)
    monkeypatch.setattr("harness.evidence_packet.default_registry",
                        lambda: (_ for _ in ()).throw(AssertionError("oracle dispatch")))
    result = verify_journey_packet(Path("packet"))
    assert result["verdict"] == "MATCH"
    carried = "".join(p.read_text(encoding="utf-8") for p in clean.rglob("*") if p.is_file())
    assert str(root.resolve()) not in carried


def test_pack_refuses_tampered_chain_and_omitted_raw_evidence(tmp_path):
    journey, root, check = _checked(tmp_path)
    journey = _conclude(journey, check)
    tampered = deepcopy(journey)
    tampered["events"][0]["occurred_at"] = "2026-08-12T12:59:00Z"
    with pytest.raises(ValueError, match="journey|event|hash"):
        pack_journey_packet(tmp_path / "bad-chain", journey=tampered, artifact_root=root)
    (root / "test_candidate.py").unlink()
    with pytest.raises(ValueError, match="artifact|evidence|exist"):
        pack_journey_packet(tmp_path / "missing-raw", journey=journey, artifact_root=root)


def test_external_root_escape_is_refused_before_read(tmp_path):
    journey, root, check = _checked(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    journey = _conclude(journey, check, raw_artifact_refs=["../outside.txt"])
    with pytest.raises(ValueError, match="traverse|relative|escape"):
        pack_journey_packet(tmp_path / "packet", journey=journey, artifact_root=root)


def test_receipt_drift_fails_even_when_manifest_hash_is_rewritten(tmp_path):
    journey, root, check = _checked(tmp_path)
    packet = tmp_path / "packet"
    pack_journey_packet(packet, journey=_conclude(journey, check), artifact_root=root)
    receipt_path = next((packet / "receipts").iterdir())
    envelope = json.loads(receipt_path.read_text(encoding="utf-8"))
    envelope["receipt"]["verdict"] = "PASS"
    receipt_path.write_text(json.dumps(envelope), encoding="utf-8")
    rel = receipt_path.relative_to(packet).as_posix()
    _rewrite_manifest_hash(packet, rel)
    result = verify_journey_packet(packet)
    assert result["verdict"] == "DRIFT" and "receipt" in result["detail"]


def test_tampered_event_chain_fails_after_attacker_rehashes_manifest(tmp_path):
    journey, root, check = _checked(tmp_path)
    packet = tmp_path / "packet"
    pack_journey_packet(packet, journey=_conclude(journey, check), artifact_root=root)
    criterion_path = packet / "criterion.json"
    criterion = json.loads(criterion_path.read_text(encoding="utf-8"))
    criterion["journey"]["events"][0]["occurred_at"] = "2026-08-12T12:59:00Z"
    criterion.pop("criterion_sha256")
    criterion["criterion_sha256"] = canonical_sha256(criterion)
    criterion_path.write_text(json.dumps(criterion), encoding="utf-8")
    _rewrite_manifest_hash(packet, "criterion.json")
    result = verify_journey_packet(packet)
    assert result["verdict"] == "DRIFT" and "journey" in result["detail"]
