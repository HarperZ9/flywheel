"""Adversarial regressions for the Task 3 execution and authenticity boundaries."""
from copy import deepcopy
import hashlib, json, sys
from pathlib import Path

from harness.evidence_journey import append_event, new_journey, run_journey_check
from harness.evidence_json import canonical_sha256
from harness.evidence_packet import pack_journey_packet, verify_journey_packet
from harness.receipt import Receipt
from harness.runtime_descriptor import PYTHON_LIMITS
import pytest


def _journey():
    journey = new_journey(journey_id="software-failure-v1",
        goal="Reproduce the software failure", intake={"summary": "add returns wrong value"},
        created_at="2026-08-12T12:00:00Z")
    return append_event(journey, {"stage": "decomposed",
        "occurred_at": "2026-08-12T12:01:00Z", "claims": [{
            "claim_id": "claim-root", "statement": "The submitted add fails its test",
            "depends_on": [], "verdict": "UNDECIDED",
            "reason": "registered checker has not run", "receipt_refs": []}]})


def _fixture(tmp_path):
    root = tmp_path / "artifacts"; root.mkdir(); candidate = root / "candidate.py"
    candidate.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (root / "test_candidate.py").write_text(
        "from candidate import add\ndef test_add(): assert add(2, 3) == 5\n", encoding="utf-8")
    context = {"task_id": "software-failure-v1", "prompt": "Repair add",
        "oracle_cmd": f'"{sys.executable}" -m pytest test_candidate.py',
        "candidate_ref": "candidate.py", "raw_artifact_refs": ["candidate.py", "test_candidate.py"],
        "timeout_seconds": 15}
    return root, candidate, context


def _load(path): return json.loads(path.read_text(encoding="utf-8"))
def _store(path, value): path.write_text(json.dumps(value, indent=1, sort_keys=True), encoding="utf-8")
def _seal(packet, rel):
    path = packet / rel; manifest_path = packet / "manifest.json"; manifest = _load(manifest_path)
    data = path.read_bytes()
    for item in manifest["files"]:
        if item["path"] == rel:
            item.update(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data)); break
    _store(manifest_path, manifest)
def _rehash_journey(journey):
    prior = None
    for event in journey["events"]:
        event["prior_event_sha256"] = prior; event.pop("event_sha256", None)
        event["event_sha256"] = prior = canonical_sha256(event)
    journey["event_head_sha256"] = prior
def _packet(tmp_path):
    journey = _journey(); root, candidate, context = _fixture(tmp_path)
    check = run_journey_check(journey, "claim-root", "code", candidate, context)
    claim = {"claim_id": "claim-root", "statement": "The submitted add fails its test",
        "depends_on": [], "verdict": check["verdict"], "receipt_refs": [check["receipt_ref"]],
        "raw_artifact_refs": check["raw_artifact_refs"]}
    journey = append_event(journey, {"stage": "preflight",
        "occurred_at": "2026-08-12T12:02:00Z", "claims": [claim]})
    packet = tmp_path / "packet"; pack_journey_packet(packet, journey=journey, artifact_root=root)
    return packet
def _save_criterion(packet, criterion):
    criterion.pop("criterion_sha256", None); criterion["criterion_sha256"] = canonical_sha256(criterion)
    _store(packet / "criterion.json", criterion); _seal(packet, "criterion.json")
def _save_receipt(packet, body, criterion):
    receipt = Receipt.from_dict(body); body["claim_sha256"] = receipt.claim_sha256()
    path = next((packet / "receipts").iterdir()); _store(path, {"receipt": body})
    criterion["receipts"][0]["claim_sha256"] = receipt.claim_sha256()
    _seal(packet, path.relative_to(packet).as_posix()); return receipt


def test_result_receipt_and_checker_manifest_bind_runtime_and_provenance(tmp_path):
    packet = _packet(tmp_path); criterion = _load(packet / "criterion.json")
    body = _load(next((packet / "receipts").iterdir()))["receipt"]
    coverage = body["coverage"]; runtime = coverage["runtime_descriptor"]
    assert coverage["runtime_descriptor_sha256"] == "sha256:" + canonical_sha256(runtime)
    assert all(limit in body["extra_does_not_prove"] for limit in PYTHON_LIMITS)
    raw = next(item for item in criterion["raw_artifacts"]
               if item["ref"] == coverage["oracle_output_ref"])
    result = _load(packet / raw["packet_path"])
    assert result["runtime"] == runtime
    assert result["candidate_provenance"] == coverage["candidate_provenance"]
    assert result["candidate_provenance"]["authority"] == "untrusted-test-process/v1"
    assert result["dependency_boundary"] == coverage["dependency_boundary"]
    checker = _load(packet / criterion["checker_manifest"][0]["packet_path"])
    executor = next(item for item in checker["sources"]
                    if item["module"] == "harness.pytest_executor")
    assert coverage["dependency_boundary"]["executor_source_sha256"] == executor["sha256"]
    assert criterion["checker_manifest"][0]["runtime_descriptor_sha256"] == coverage["runtime_descriptor_sha256"]


@pytest.mark.parametrize("fact", ["runtime", "provenance", "executor", "checker-manifest"])
def test_bound_runtime_provenance_and_executor_tampering_fails_closed(tmp_path, fact):
    packet = _packet(tmp_path); criterion = _load(packet / "criterion.json")
    if fact == "checker-manifest":
        criterion["checker_manifest"][0]["runtime_descriptor_sha256"] = "sha256:" + "0" * 64
    else:
        path = next((packet / "receipts").iterdir()); body = _load(path)["receipt"]
        if fact == "runtime":
            body["coverage"]["runtime_descriptor"]["pytest"]["version"] = "0.0-tampered"
        elif fact == "executor":
            body["coverage"]["dependency_boundary"]["executor_source_sha256"] = "sha256:" + "0" * 64
        else:
            body["coverage"]["candidate_provenance"]["source_sha256"] = "sha256:" + "0" * 64
        _save_receipt(packet, body, criterion)
    _save_criterion(packet, criterion)
    assert verify_journey_packet(packet)["verdict"] == "DRIFT"


def test_child_cannot_replace_import_and_restore_candidate_as_a_pass(tmp_path):
    root, candidate, context = _fixture(tmp_path); test = root / "test_candidate.py"
    test.write_text("from pathlib import Path\np=Path('candidate.py'); original=p.read_bytes()\n"
        "p.write_text('def add(a, b): return a + b\\n')\nfrom candidate import add\np.write_bytes(original)\n"
        "def test_add(): assert add(2, 3) == 5\n", encoding="utf-8")
    check = run_journey_check(_journey(), "claim-root", "code", candidate, context)
    if sys.platform == "win32":
        assert check["verdict"] != "PASS"
        if "execution_input_protection" in check:
            assert check["execution_input_protection"] == "windows-low-integrity-namespace/v1"
    else:
        assert (check["verdict"], check["unverifiable_reason"]) == (
            "UNVERIFIABLE", "EXECUTION_INPUT_PROTECTION_UNAVAILABLE")
        assert "receipt_ref" not in check and not (root / "receipts").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows namespace boundary")
def test_candidate_cannot_replace_pytest_before_the_checker_starts(tmp_path):
    root, candidate, context = _fixture(tmp_path)
    candidate.write_text(
        "from pathlib import Path\nimport sys, types\n"
        "fake=types.ModuleType('pytest')\n"
        "def main(args):\n"
        " p=Path(sys.argv[sys.argv.index('--junit')+1])\n"
        " p.write_text('<testsuites><testsuite><testcase classname=\"test_candidate\" name=\"test_add\"/></testsuite></testsuites>')\n"
        " return 0\n"
        "fake.main=main\nsys.modules['pytest']=fake\n"
        "def add(a,b): return a-b\n", encoding="utf-8")
    check = run_journey_check(_journey(), "claim-root", "code", candidate, context)
    assert check["verdict"] != "PASS"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows namespace boundary")
@pytest.mark.parametrize("target", ["pytest.main", "_pytest.config.main"])
def test_candidate_cannot_mutate_cached_checker_code_into_a_pass(tmp_path, target):
    root, candidate, context = _fixture(tmp_path)
    imports = "import pytest\n" if target == "pytest.main" else "import pytest, _pytest.config\n"
    if target == "pytest.main":
        trusted = pytest.main
    else:
        import _pytest.config
        trusted = _pytest.config.main
    trusted_code = trusted.__code__
    candidate.write_text(
        imports +
        "def forged(args):\n"
        " for arg in args:\n"
        "  if arg.startswith('--junitxml='):\n"
        "   open(arg.split('=',1)[1],'w').write('<testsuites><testsuite>"
        "<testcase classname=\"test_candidate\" name=\"test_add\"/>"
        "</testsuite></testsuites>')\n"
        " return 0\n"
        f"{target}.__code__=forged.__code__\n"
        "def add(a,b): return a-b\n", encoding="utf-8")
    check = run_journey_check(_journey(), "claim-root", "code", candidate, context)
    assert trusted.__code__ is trusted_code
    assert (check["verdict"], check["reason"]) == (
        "UNVERIFIABLE", "PYTHON_ACCEPTANCE_BOUNDARY_UNAVAILABLE")
    body = _load(root / check["receipt_ref"])["receipt"]
    assert body["verdict"] == "UNVERIFIABLE"
    assert any(item.startswith("NOT_PROVES_TRUSTWORTHY_PYTHON_PASS:")
               for item in body["extra_does_not_prove"])


@pytest.mark.skipif(sys.platform != "win32", reason="Windows namespace boundary")
@pytest.mark.parametrize("loader", ["spec", "source-loader", "run-path"])
def test_unadmitted_external_python_dependency_cannot_yield_pass(tmp_path, loader):
    root, candidate, context = _fixture(tmp_path)
    external = tmp_path / "unadmitted_dependency.py"
    external.write_text("def add(a,b): return a+b\n", encoding="utf-8")
    literal = repr(str(external))
    if loader == "spec":
        load = ("import importlib.util\ns=importlib.util.spec_from_file_location('outside',p)\n"
                "m=importlib.util.module_from_spec(s); s.loader.exec_module(m)\n")
    elif loader == "source-loader":
        load = "from importlib.machinery import SourceFileLoader\nm=SourceFileLoader('outside',p).load_module()\n"
    else:
        load = "import runpy\nm=type('Module',(),runpy.run_path(p))\n"
    candidate.write_text(f"p={literal}\n{load}add=m.add\n", encoding="utf-8")
    check = run_journey_check(_journey(), "claim-root", "code", candidate, context)
    assert (check["verdict"], check["reason"]) == (
        "UNVERIFIABLE", "PYTHON_ACCEPTANCE_BOUNDARY_UNAVAILABLE")
    body = _load(root / check["receipt_ref"])["receipt"]
    boundary = body["coverage"]["dependency_boundary"]
    assert boundary["admitted_source_refs"] == ["candidate.py", "test_candidate.py"]
    assert boundary["closure"] == "UNVERIFIABLE"
    assert external.name not in {item["ref"] for item in body["coverage"]["raw_artifacts"]}
    assert any(item.startswith("NOT_PROVES_CLOSED_EXECUTION_DEPENDENCIES:")
               for item in body["extra_does_not_prove"])


@pytest.mark.skipif(sys.platform != "win32", reason="Windows namespace boundary")
def test_benign_python_pass_is_honestly_unverifiable_without_independent_checker(tmp_path):
    root, candidate, context = _fixture(tmp_path)
    candidate.write_text("def add(a,b): return a+b\n", encoding="utf-8")
    check = run_journey_check(_journey(), "claim-root", "code", candidate, context)
    assert (check["verdict"], check["reason"]) == (
        "UNVERIFIABLE", "PYTHON_ACCEPTANCE_BOUNDARY_UNAVAILABLE")
    body = _load(root / check["receipt_ref"])["receipt"]
    assert body["unverifiable_reason"] == "PYTHON_ACCEPTANCE_BOUNDARY_UNAVAILABLE"
    assert body["denominator"]["hits"] == 0 and body["denominator"]["unverifiable"] == 1


@pytest.mark.skipif(sys.platform != "win32", reason="Windows namespace boundary")
@pytest.mark.parametrize("attack", ["transient-package", "unchecked-pyc",
                                     "nested-module", "create-import-delete"])
def test_entire_import_namespace_rejects_candidate_shadowing(tmp_path, attack):
    root, candidate, context = _fixture(tmp_path); test = root / "test_candidate.py"
    package = (
        "from pathlib import Path\n"
        "p=Path('candidate'); p.mkdir()\n"
        "(p/'__init__.py').write_text('def add(a,b): return a+b\\n')\n")
    if attack == "transient-package":
        source = package + "from candidate import add\n"
    elif attack == "nested-module":
        source = package + (
            "(p/'nested.py').write_text('def add(a,b): return a+b\\n')\n"
            "from candidate.nested import add\n")
    elif attack == "create-import-delete":
        source = package + "from candidate import add\nimport shutil\nshutil.rmtree(p)\n"
    else:
        source = (
            "from pathlib import Path\nimport importlib.util\n"
            "import importlib._bootstrap_external as bootstrap\n"
            "original=Path('candidate.py').read_bytes()\n"
            "cache=Path(importlib.util.cache_from_source('candidate.py'))\n"
            "cache.parent.mkdir(parents=True, exist_ok=True)\n"
            "code=compile('def add(a,b): return a+b\\n','candidate.py','exec')\n"
            "cache.write_bytes(bootstrap._code_to_hash_pyc("
            "code,importlib.util.source_hash(original),checked=False))\n"
            "from candidate import add\n")
    test.write_text(source + "def test_add(): assert add(2,3)==5\n", encoding="utf-8")
    admitted = {path: path.read_bytes() for path in (candidate, test)}
    check = run_journey_check(_journey(), "claim-root", "code", candidate, context)
    assert check["verdict"] != "PASS", attack
    assert all(path.read_bytes() == blob for path, blob in admitted.items())
    if "receipt_ref" in check:
        body = _load(root / check["receipt_ref"])["receipt"]
        assert body["coverage"]["candidate_provenance"]["loaded"] is True


@pytest.mark.skipif(sys.platform != "win32", reason="packet fixture needs an executed code receipt")
def test_unsigned_coherent_honest_null_rewrite_needs_an_external_anchor(tmp_path):
    packet = _packet(tmp_path); receipt_path = next((packet / "receipts").iterdir())
    anchor = "sha256:" + hashlib.sha256((packet / "manifest.json").read_bytes()).hexdigest()
    body = _load(receipt_path)["receipt"]
    reason = "PYTHON_ACCEPTANCE_BOUNDARY_UNAVAILABLE"
    body["verdict"] = body["coverage"]["check_result"]["verdict"] = "UNVERIFIABLE"
    body["attribution"] = body["coverage"]["check_result"]["attribution"] = "ENVIRONMENT"
    body["unverifiable_reason"] = reason
    body["denominator"]["unverifiable"] = body["coverage"]["check_result"]["denominator"]["unverifiable"] = 1
    output_ref = body["coverage"]["oracle_output_ref"]; criterion = _load(packet / "criterion.json")
    claim = criterion["journey"]["events"][-1]["claims"][0]
    raw = next(item for item in criterion["raw_artifacts"] if item["ref"] == output_ref)
    old_packet_path = raw["packet_path"]; result_path = packet / old_packet_path; carried = _load(result_path)
    carried.update(outcomes=["test_candidate::test_add=PASS"], return_code=0); _store(result_path, carried)
    blob = result_path.read_bytes(); raw.update(sha256="sha256:" + hashlib.sha256(blob).hexdigest(), bytes=len(blob))
    raw_index = criterion["raw_artifacts"].index(raw)
    raw["packet_path"] = f"checker/raw/{raw_index:04d}-{raw['sha256'][7:23]}.txt"
    result_path.rename(packet / raw["packet_path"]); manifest = _load(packet / "manifest.json")
    manifest_item = next(item for item in manifest["files"] if item["path"] == old_packet_path)
    manifest_item.update(path=raw["packet_path"], sha256=raw["sha256"][7:], bytes=len(blob))
    manifest["files"].sort(key=lambda item: item["path"]); _store(packet / "manifest.json", manifest)
    receipt_raw = next(item for item in body["coverage"]["raw_artifacts"] if item["ref"] == output_ref)
    receipt_raw.update(sha256=raw["sha256"], bytes=raw["bytes"]); body["raw_stdout_sha256"] = raw["sha256"]
    body["coverage"]["check_result"].update(return_code=0,
        output_hash=hashlib.sha256(b"test_candidate::test_add=PASS\n0").hexdigest()[:16])
    claim.update(verdict="UNVERIFIABLE", reason=reason); _rehash_journey(criterion["journey"])
    criterion["journey_sha256"] = canonical_sha256(criterion["journey"])
    criterion["event_head_sha256"] = criterion["journey"]["event_head_sha256"]
    changed = _save_receipt(packet, body, criterion); criterion["criteria"][0].update(
        verdict="UNVERIFIABLE", denominator=changed.denominator.to_dict(),
        check_result=body["coverage"]["check_result"])
    tree = _load(packet / "tree_head.json"); tree["root"] = "sha256:" + criterion["event_head_sha256"]
    _store(packet / "tree_head.json", tree); _save_criterion(packet, criterion); _seal(packet, "tree_head.json")
    unsigned = verify_journey_packet(packet)
    assert (unsigned["verdict"], unsigned["structural_verdict"], unsigned["authenticity_verdict"]) == (
        "UNVERIFIABLE", "MATCH", "UNVERIFIABLE")
    assert verify_journey_packet(packet, expected_manifest_sha256=anchor)["verdict"] == "DRIFT"
