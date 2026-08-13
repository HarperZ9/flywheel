from copy import deepcopy
import hashlib, json, shutil, sys
from pathlib import Path
import pytest
import harness.evidence_packet as evidence_packet
import harness.evidence_packet_validation as packet_validation
from harness.evidence_journey import append_event, new_journey, run_journey_check
from harness.evidence_json import canonical_sha256
from harness.evidence_packet import pack_journey_packet, verify_journey_packet
from harness.python_execution_containment import REASON
from harness.receipt import Receipt
def _journey(*, measurement=False):
    statement = ("The submitted effect misses its registered threshold" if measurement
                 else "The submitted add fails its test")
    journey = new_journey(journey_id="software-failure-v1",
        goal="Reproduce the software failure", intake={"summary": "add returns wrong value"},
        created_at="2026-08-12T12:00:00Z")
    return append_event(journey, {"stage": "decomposed",
        "occurred_at": "2026-08-12T12:01:00Z", "claims": [{
            "claim_id": "claim-root", "statement": statement,
            "depends_on": [], "verdict": "UNDECIDED",
            "reason": "registered checker has not run", "receipt_refs": []}]})

def _software_fixture(tmp_path, *, slow=False):
    root = tmp_path / "artifacts"; root.mkdir(parents=True)
    candidate = root / "candidate.py"
    candidate.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    body = "import time\nfrom candidate import add\n" + (
        "def test_add():\n    time.sleep(10)\n" if slow else
        "def test_add():\n    assert add(2, 3) == 5\n")
    (root / "test_candidate.py").write_text(body, encoding="utf-8")
    context = {"task_id": "software-failure-v1", "prompt": "Repair add",
        "oracle_cmd": f'"{sys.executable}" -m pytest test_candidate.py',
        "candidate_ref": "candidate.py",
        "raw_artifact_refs": ["candidate.py", "test_candidate.py"],
        "timeout_seconds": 1 if slow else 15}
    return root, candidate, context

def _measurement_fixture(tmp_path):
    root = tmp_path / "artifacts"; root.mkdir(parents=True)
    candidate = root / "measurement.json"
    candidate.write_text(json.dumps({"effect": 0.1, "ci_low": 0.05, "ci_high": 0.15,
        "min_effect": 0.2, "n": 10,
        "negative_control": {"effect": 0, "ci_low": -0.1, "ci_high": 0.1}}), encoding="utf-8")
    context = {"task_id": "software-failure-v1", "prompt": "Check measurement",
        "oracle_cmd": "measurement-gate", "candidate_ref": candidate.name,
        "raw_artifact_refs": [candidate.name], "timeout_seconds": 15}
    return root, candidate, context

def _checked(tmp_path):
    journey = _journey(measurement=True); root, candidate, context = _measurement_fixture(tmp_path)
    return journey, root, run_journey_check(journey, "claim-root", "ml", candidate, context)

def _conclude(journey, check, **overrides):
    claim = {"claim_id": "claim-root", "statement": journey["events"][-1]["claims"][0]["statement"],
        "depends_on": [], "verdict": check["verdict"],
        "receipt_refs": [check["receipt_ref"]],
        "raw_artifact_refs": check["raw_artifact_refs"]}
    claim.update(overrides)
    if claim["verdict"] in {"UNDECIDED", "UNVERIFIABLE"}:
        claim.setdefault("reason", check.get("reason", "checker did not dispose"))
    return append_event(journey, {"stage": "preflight",
        "occurred_at": "2026-08-12T12:02:00Z", "claims": [claim]})

def _load(path): return json.loads(path.read_text(encoding="utf-8"))
def _store(path, value): path.write_text(json.dumps(value, indent=1, sort_keys=True), encoding="utf-8")
def _seal(packet, rel):
    path = packet / rel; manifest_path = packet / "manifest.json"; manifest = _load(manifest_path)
    data = path.read_bytes()
    for item in manifest["files"]:
        if item["path"] == rel:
            item.update(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data)); break
    _store(manifest_path, manifest)

def _packet(tmp_path):
    journey, root, check = _checked(tmp_path); packet = tmp_path / "packet"
    pack_journey_packet(packet, journey=_conclude(journey, check), artifact_root=root)
    return packet

def _save_criterion(packet, criterion):
    criterion.pop("criterion_sha256", None); criterion["criterion_sha256"] = canonical_sha256(criterion)
    _store(packet / "criterion.json", criterion); _seal(packet, "criterion.json")

def _save_receipt(packet, body, criterion):
    receipt = Receipt.from_dict(body); body["claim_sha256"] = receipt.claim_sha256()
    path = next((packet / "receipts").iterdir()); _store(path, {"receipt": body})
    criterion["receipts"][0]["claim_sha256"] = receipt.claim_sha256()
    _seal(packet, path.relative_to(packet).as_posix()); return receipt
def test_registered_code_oracle_is_terminally_unverifiable_without_a_receipt(tmp_path):
    root, candidate, context = _software_fixture(tmp_path)
    check = run_journey_check(_journey(), "claim-root", "code", candidate, context)
    assert (check["verdict"], check["oracle_id"], check["oracle_type"]) == (
        "UNVERIFIABLE", "code", "pytest")
    assert check["unverifiable_reason"] == REASON and check["oracle_calls_consumed"] == 0
    assert "receipt_ref" not in check and not (root / "receipts").exists()
def test_unknown_oracle_is_typed_unverifiable_without_dispatch(tmp_path):
    root, candidate, context = _software_fixture(tmp_path)
    check = run_journey_check(_journey(), "claim-root", "shell-plugin", candidate, context)
    assert check["verdict"] == "UNVERIFIABLE" and check["unverifiable_reason"] == "ORACLE_UNAVAILABLE"
    assert check["oracle_calls_consumed"] == 0 and "receipt_ref" not in check
    assert not (root / "receipts").exists()
def test_timeout_attempt_is_not_spawned_or_misreported_as_candidate_failure(tmp_path):
    root, candidate, context = _software_fixture(tmp_path, slow=True)
    check = run_journey_check(_journey(), "claim-root", "code", candidate, context)
    assert (check["verdict"], check["unverifiable_reason"]) == ("UNVERIFIABLE", REASON)
    assert check["oracle_calls_consumed"] == 0 and not (root / "receipts").exists()
@pytest.mark.parametrize("candidate_kind", ["missing", "directory"])
def test_malformed_candidate_fails_closed_without_receipt(tmp_path, candidate_kind):
    root, candidate, context = _software_fixture(tmp_path); candidate.unlink()
    if candidate_kind == "directory": candidate.mkdir()
    check = run_journey_check(_journey(), "claim-root", "code", candidate, context)
    assert (check["verdict"], check["unverifiable_reason"]) == ("UNVERIFIABLE", REASON)
    assert "receipt_ref" not in check and not (root / "receipts").exists()
def test_context_is_a_closed_bounded_json_envelope(tmp_path):
    _, candidate, context = _software_fixture(tmp_path); context["plugin"] = "arbitrary.module:Oracle"
    result = run_journey_check(_journey(), "claim-root", "code", candidate, context)
    assert result["unverifiable_reason"] == "INVALID_CONTEXT" and "unknown" in result["reason"]
@pytest.mark.parametrize("actor", ["candidate", "test"])
@pytest.mark.parametrize("action", ["modify", "delete"])
def test_execution_input_mutation_is_prevented_or_typed_unverifiable(tmp_path, actor, action):
    root, candidate, context = _software_fixture(tmp_path); target = candidate if actor == "candidate" else root / "test_candidate.py"
    effect = "Path(__file__).unlink()" if action == "delete" else "Path(__file__).write_text('changed')"
    prefix = f"from pathlib import Path\n{effect}\n"
    target.write_text(prefix + target.read_text(encoding="utf-8"), encoding="utf-8")
    result = run_journey_check(_journey(), "claim-root", "code", candidate, context)
    assert (result["verdict"], result["unverifiable_reason"]) == ("UNVERIFIABLE", REASON)
    assert "receipt_ref" not in result and target.read_text(encoding="utf-8").startswith(prefix)
def test_check_result_closes_command_oracle_result_and_denominator(tmp_path):
    _, root, check = _checked(tmp_path); closed = check["check_result"]
    assert set(closed) == {"command", "output_hash", "return_code", "execution",
                           "attribution", "verdict", "denominator"}
    assert closed["command"] == {"args": ["measurement"], "targets": []}
    assert closed["output_hash"] and closed["return_code"] == 1
    assert closed["denominator"] == _load(root / check["receipt_ref"])["receipt"]["denominator"]
def test_different_measurement_bytes_are_a_different_check(tmp_path):
    root, candidate, context = _measurement_fixture(tmp_path)
    first = run_journey_check(_journey(), "claim-root", "ml", candidate, context)
    candidate.write_text(candidate.read_text(encoding="utf-8").replace("0.05", "0.04"), encoding="utf-8")
    second = run_journey_check(_journey(), "claim-root", "ml", candidate, context)
    assert first["receipt_claim_sha256"] != second["receipt_claim_sha256"]
def test_pytest_target_admission_is_unreachable_without_containment(tmp_path):
    root, candidate, context = _software_fixture(tmp_path); context["raw_artifact_refs"] = ["candidate.py"]
    result = run_journey_check(_journey(), "claim-root", "code", candidate, context)
    assert (result["verdict"], result["unverifiable_reason"]) == ("UNVERIFIABLE", REASON)
    assert "receipt_ref" not in result and not (root / "receipts").exists()
def test_pytest_attempt_does_not_touch_the_byte_exact_crlf_candidate(tmp_path):
    root, candidate, context = _software_fixture(tmp_path)
    source = b"def add(a, b):\r\n    return a + b\r\n"; candidate.write_bytes(source)
    (root / "test_candidate.py").write_text(
        "from pathlib import Path\ndef test_bytes(): assert Path('candidate.py').read_bytes() == "
        + repr(source), encoding="utf-8")
    check = run_journey_check(_journey(), "claim-root", "code", candidate, context)
    assert (check["verdict"], check["unverifiable_reason"]) == ("UNVERIFIABLE", REASON)
    assert candidate.read_bytes() == source and "receipt_ref" not in check
def test_pytest_selector_metacharacters_cannot_spawn_a_shell_command(tmp_path):
    root, candidate, context = _software_fixture(tmp_path); marker = tmp_path / "selector-owned.txt"
    context["oracle_cmd"] += f"::test_add&echo.owned>{marker}"
    run_journey_check(_journey(), "claim-root", "code", candidate, context)
    assert not marker.exists()
def test_packet_binds_journey_receipt_raw_evidence_and_checker(tmp_path):
    packet = _packet(tmp_path); criterion = _load(packet / "criterion.json")
    result = verify_journey_packet(packet)
    assert (result["verdict"], result["structural_verdict"], result["authenticity_verdict"]) == (
        "UNVERIFIABLE", "MATCH", "UNVERIFIABLE")
    anchor = "sha256:" + hashlib.sha256((packet / "manifest.json").read_bytes()).hexdigest()
    anchored = verify_journey_packet(packet, expected_manifest_sha256=anchor)
    assert (anchored["verdict"], anchored["authenticity_verdict"], anchored["rehash_resistance_verdict"]) == ("MATCH", "UNVERIFIABLE", "MATCH")
    assert criterion["journey"] and criterion["event_head_sha256"]
    assert criterion["raw_artifacts"] and criterion["receipts"] and criterion["checker_manifest"]
    assert criterion["criteria"][0]["denominator"]["attempts"] == 1 and criterion["does_not_prove"]
    checker = _load(packet / criterion["checker_manifest"][0]["packet_path"])
    assert [item["module"] for item in checker["sources"]] == ["harness.measurement_oracle"]
    assert criterion["checker_manifest"][0]["runtime_descriptor_sha256"] is None
def test_clean_directory_recheck_is_offline_and_serializes_no_host_root(tmp_path, monkeypatch):
    packet = _packet(tmp_path); clean = tmp_path / "clean" / "packet"; clean.parent.mkdir(); shutil.copytree(packet, clean)
    monkeypatch.chdir(clean.parent); monkeypatch.setattr(evidence_packet, "default_registry",
        lambda: (_ for _ in ()).throw(AssertionError("oracle dispatch")))
    assert verify_journey_packet(Path("packet"))["authenticity_verdict"] == "UNVERIFIABLE"
    anchor = "sha256:" + hashlib.sha256((clean / "manifest.json").read_bytes()).hexdigest()
    assert verify_journey_packet(Path("packet"), expected_manifest_sha256=anchor)["verdict"] == "MATCH"
    carried = "".join(p.read_text(encoding="utf-8") for p in clean.rglob("*") if p.is_file())
    assert str((tmp_path / "artifacts").resolve()) not in carried
def test_pack_refuses_tampered_chain_and_omitted_raw_evidence(tmp_path):
    journey, root, check = _checked(tmp_path); journey = _conclude(journey, check)
    tampered = deepcopy(journey); tampered["events"][0]["occurred_at"] = "2026-08-12T12:59:00Z"
    with pytest.raises(ValueError, match="journey|event|hash"):
        pack_journey_packet(tmp_path / "bad-chain", journey=tampered, artifact_root=root)
    (root / "measurement.json").unlink()
    with pytest.raises(ValueError, match="artifact|evidence|exist"):
        pack_journey_packet(tmp_path / "missing-raw", journey=journey, artifact_root=root)
def test_rehashed_packet_with_a_tampered_event_chain_fails_closed(tmp_path):
    packet = _packet(tmp_path); criterion = _load(packet / "criterion.json")
    criterion["journey"]["events"][0]["occurred_at"] = "2026-08-12T12:59:00Z"
    _save_criterion(packet, criterion)
    assert verify_journey_packet(packet)["verdict"] == "DRIFT"
def test_external_root_escape_is_refused_before_read(tmp_path):
    journey, root, check = _checked(tmp_path); (tmp_path / "outside.txt").write_text("outside", encoding="utf-8")
    with pytest.raises(ValueError, match="traverse|relative|escape"):
        pack_journey_packet(tmp_path / "packet", journey=_conclude(journey, check,
            raw_artifact_refs=["../outside.txt"]), artifact_root=root)
@pytest.mark.parametrize("fact", ["verdict", "criterion_id", "criterion_sha256", "statement",
    "depends_on", "denominator", "claim_ids",
    "tree_size", "tree_root", "manifest_schema", "pack_schema", "receipt_count",
    "raw_artifact_count", "checker_count", "file_count", "criterion_dnp", "manifest_dnp"])
def test_rehashed_packet_fact_tamper_fails_closed(tmp_path, fact):
    packet = _packet(tmp_path); criterion = _load(packet / "criterion.json")
    if fact in {"verdict", "criterion_id", "criterion_sha256", "statement"}:
        criterion["criteria"][0][fact] = "PASS" if fact == "verdict" else "tampered"
    elif fact == "depends_on": criterion["criteria"][0][fact] = ["ghost"]
    elif fact == "denominator": criterion["criteria"][0][fact]["attempts"] = 2
    elif fact == "claim_ids": criterion["claim_ids"].append("ghost")
    elif fact.startswith("tree_"):
        tree = _load(packet / "tree_head.json"); tree[fact[5:]] = 999 if fact == "tree_size" else "sha256:bad"
        _store(packet / "tree_head.json", tree); _seal(packet, "tree_head.json")
    elif fact == "manifest_schema":
        manifest = _load(packet / "manifest.json"); manifest["schema"] = "tampered"; _store(packet / "manifest.json", manifest)
    elif fact == "criterion_dnp": criterion["does_not_prove"] = criterion["does_not_prove"][1:]
    elif fact == "manifest_dnp":
        manifest = _load(packet / "manifest.json"); manifest["does_not_prove"].append("invented"); _store(packet / "manifest.json", manifest)
    else: criterion["pack_manifest"][fact.replace("pack_schema", "schema")] = 999 if fact != "pack_schema" else "tampered"
    if fact not in {"tree_size", "tree_root", "manifest_schema", "manifest_dnp"}: _save_criterion(packet, criterion)
    assert verify_journey_packet(packet)["verdict"] == "DRIFT"
@pytest.mark.parametrize("fact", ["command", "output_hash", "return_code", "execution",
    "attribution", "verdict", "denominator"])
def test_rehashed_check_result_fact_tamper_fails_closed(tmp_path, fact):
    packet = _packet(tmp_path); criterion = _load(packet / "criterion.json")
    changed = criterion["criteria"][0]["check_result"]
    replacements = {"command": {"args": ["python", "-m", "pytest", "candidate.py"],
                                 "targets": ["candidate.py"]},
        "output_hash": "0" * 16, "return_code": 0, "execution": "CRASHED",
        "attribution": "ENVIRONMENT", "verdict": "PASS",
        "denominator": {**changed["denominator"], "attempts": 2}}
    changed[fact] = replacements[fact]; _save_criterion(packet, criterion)
    assert verify_journey_packet(packet)["verdict"] == "DRIFT"
def test_receipt_criterion_id_is_derived_not_self_asserted(tmp_path):
    packet = _packet(tmp_path); body = _load(next((packet / "receipts").iterdir()))["receipt"]
    criterion = _load(packet / "criterion.json"); body["criterion_id"] = "arbitrary"
    changed = _save_receipt(packet, body, criterion); criterion["criteria"][0]["criterion_id"] = changed.criterion_id
    _save_criterion(packet, criterion); assert verify_journey_packet(packet)["verdict"] == "DRIFT"
def test_receipt_raw_byte_count_is_cross_checked(tmp_path):
    packet = _packet(tmp_path); body = _load(next((packet / "receipts").iterdir()))["receipt"]
    criterion = _load(packet / "criterion.json"); body["coverage"]["raw_artifacts"][0]["bytes"] += 1
    _save_receipt(packet, body, criterion); _save_criterion(packet, criterion)
    assert verify_journey_packet(packet)["verdict"] == "DRIFT"
def test_extra_manifest_member_fails_even_when_rehashed_and_recounted(tmp_path):
    packet = _packet(tmp_path); extra = packet / "extra.txt"; extra.write_text("extra", encoding="utf-8")
    criterion = _load(packet / "criterion.json"); criterion["pack_manifest"]["file_count"] += 1
    _save_criterion(packet, criterion); manifest = _load(packet / "manifest.json"); blob = extra.read_bytes()
    manifest["files"].append({"path": "extra.txt", "sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)})
    manifest["files"].sort(key=lambda item: item["path"]); _store(packet / "manifest.json", manifest)
    assert verify_journey_packet(packet)["verdict"] == "DRIFT"
def test_preflight_stops_consuming_a_traversal_after_the_file_cap(tmp_path, monkeypatch):
    packet = _packet(tmp_path); original = Path.rglob
    def endless(path, pattern):
        if path != packet: return original(path, pattern)
        def paths():
            for _ in range(packet_validation.MAX_FILES + 1): yield packet / "manifest.json"
            raise AssertionError("traversal consumed beyond bound")
        return paths()
    monkeypatch.setattr(Path, "rglob", endless)
    assert verify_journey_packet(packet)["verdict"] == "UNVERIFIABLE"
@pytest.mark.parametrize("kind", ["directories", "depth"])
def test_preflight_bounds_directory_count_and_depth(tmp_path, kind):
    packet = _packet(tmp_path)
    if kind == "directories":
        for index in range(packet_validation.MAX_FILES + 1): (packet / f"d{index}").mkdir()
    else:
        path = packet
        for _ in range(40): path /= "d"; path.mkdir()
    assert verify_journey_packet(packet)["verdict"] == "UNVERIFIABLE"
def test_pack_streams_receipt_envelope_through_a_byte_cap(tmp_path, monkeypatch):
    journey, root, check = _checked(tmp_path); receipt = root / check["receipt_ref"]
    original = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", lambda path: (_ for _ in ()).throw(
        AssertionError("unbounded receipt read")) if path == receipt else original(path))
    pack_journey_packet(tmp_path / "packet", journey=_conclude(journey, check), artifact_root=root)
@pytest.mark.parametrize("where,kind", [("manifest", "oversized"), ("manifest", "deep"),
                                         ("receipt", "oversized"), ("receipt", "deep")])
def test_hostile_json_is_strictly_preflighted_before_legacy_verify(tmp_path, monkeypatch, where, kind):
    packet = _packet(tmp_path); path = packet / "manifest.json" if where == "manifest" else next((packet / "receipts").iterdir())
    value = _load(path); value["padding"] = "x" * 1_100_000 if kind == "oversized" else []
    if kind == "deep":
        nested = 0
        for _ in range(40): nested = [nested]
        value["padding"] = nested
    _store(path, value)
    if where == "receipt": _seal(packet, path.relative_to(packet).as_posix())
    monkeypatch.setattr(packet_validation, "verify_bundle", lambda _: (_ for _ in ()).throw(AssertionError("legacy called")))
    assert verify_journey_packet(packet)["verdict"] == "UNVERIFIABLE"
@pytest.mark.parametrize("raw", [b'{"files":[],"files":[]}', b'{"files":[],"value":NaN}'])
def test_duplicate_or_nonfinite_manifest_is_refused_before_legacy_verify(tmp_path, monkeypatch, raw):
    packet = _packet(tmp_path); (packet / "manifest.json").write_bytes(raw)
    monkeypatch.setattr(packet_validation, "verify_bundle", lambda _: (_ for _ in ()).throw(AssertionError("legacy called")))
    assert verify_journey_packet(packet)["verdict"] == "UNVERIFIABLE"
