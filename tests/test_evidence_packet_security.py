"""Hostile Python remains inert while journey containment is unavailable."""
import sys

import pytest

from harness.evidence_journey import append_event, new_journey, run_journey_check
from harness.python_execution_containment import REASON


def _journey():
    journey = new_journey(journey_id="software-security-v1", goal="Check Python",
        intake={"summary": "untrusted candidate"}, created_at="2026-08-13T12:00:00Z")
    return append_event(journey, {"stage": "decomposed",
        "occurred_at": "2026-08-13T12:01:00Z", "claims": [{
            "claim_id": "claim-root", "statement": "The candidate meets its tests",
            "depends_on": [], "verdict": "UNDECIDED",
            "reason": "registered checker has not run", "receipt_refs": []}]})


def _fixture(tmp_path):
    root = tmp_path / "artifacts"; root.mkdir()
    candidate, test = root / "candidate.py", root / "test_candidate.py"
    candidate.write_text("def add(a,b): return a-b\n", encoding="utf-8")
    test.write_text("from candidate import add\ndef test_add(): assert add(2,3)==5\n", encoding="utf-8")
    context = {"task_id": "software-security-v1", "prompt": "Check candidate",
        "oracle_cmd": f'"{sys.executable}" -m pytest test_candidate.py',
        "candidate_ref": "candidate.py",
        "raw_artifact_refs": ["candidate.py", "test_candidate.py"],
        "timeout_seconds": 15}
    return root, candidate, test, context


def _check(root, candidate, context):
    result = run_journey_check(_journey(), "claim-root", "code", candidate, context)
    assert (result["verdict"], result["unverifiable_reason"]) == ("UNVERIFIABLE", REASON)
    assert result["oracle_calls_consumed"] == 0
    assert "receipt_ref" not in result and not (root / "receipts").exists()
    return result


def test_child_cannot_replace_import_and_restore_candidate(tmp_path):
    root, candidate, test, context = _fixture(tmp_path)
    original = candidate.read_bytes()
    test.write_text("from pathlib import Path\np=Path('candidate.py'); old=p.read_bytes()\n"
        "p.write_text('def add(a,b): return a+b\\n')\nfrom candidate import add\np.write_bytes(old)\n"
        "def test_add(): assert add(2,3)==5\n", encoding="utf-8")
    _check(root, candidate, context)
    assert candidate.read_bytes() == original


def test_candidate_cannot_replace_pytest_before_checker_start(tmp_path):
    root, candidate, _, context = _fixture(tmp_path); marker = root / "forged-junit.xml"
    candidate.write_text("from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('<testsuite/>')\n"
        "import sys,types\nfake=types.ModuleType('pytest')\nfake.main=lambda args:0\n"
        "sys.modules['pytest']=fake\ndef add(a,b): return a-b\n", encoding="utf-8")
    _check(root, candidate, context)
    assert not marker.exists()


@pytest.mark.parametrize("target", ["pytest.main", "_pytest.config.main"])
def test_candidate_cannot_mutate_cached_checker_code(tmp_path, target):
    root, candidate, _, context = _fixture(tmp_path); marker = root / "forged-junit.xml"
    imports = "import pytest\n" if target == "pytest.main" else "import pytest,_pytest.config\n"
    trusted = pytest.main
    if target != "pytest.main":
        import _pytest.config
        trusted = _pytest.config.main
    trusted_code = trusted.__code__
    candidate.write_text(imports + "from pathlib import Path\n"
        "def forged(args):\n"
        f" Path({str(marker)!r}).write_text('<testsuite/>')\n return 0\n"
        f"{target}.__code__=forged.__code__\ndef add(a,b): return a-b\n", encoding="utf-8")
    _check(root, candidate, context)
    assert trusted.__code__ is trusted_code and not marker.exists()


@pytest.mark.parametrize("loader", ["spec", "source-loader", "run-path"])
def test_unadmitted_external_python_dependency_is_not_loaded(tmp_path, loader):
    root, candidate, _, context = _fixture(tmp_path)
    marker = tmp_path / "external-loaded.txt"; external = tmp_path / "unadmitted.py"
    external.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('loaded')\n"
        "def add(a,b): return a+b\n", encoding="utf-8")
    literal = repr(str(external))
    if loader == "spec":
        load = ("import importlib.util\ns=importlib.util.spec_from_file_location('outside',p)\n"
                "m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\n")
    elif loader == "source-loader":
        load = "from importlib.machinery import SourceFileLoader\nm=SourceFileLoader('outside',p).load_module()\n"
    else:
        load = "import runpy\nm=type('Module',(),runpy.run_path(p))\n"
    candidate.write_text(f"p={literal}\n{load}add=m.add\n", encoding="utf-8")
    _check(root, candidate, context)
    assert not marker.exists()


def test_benign_python_is_honestly_unverifiable_without_containment(tmp_path):
    root, candidate, _, context = _fixture(tmp_path)
    candidate.write_text("def add(a,b): return a+b\n", encoding="utf-8")
    _check(root, candidate, context)


@pytest.mark.parametrize("attack", ["transient-package", "unchecked-pyc",
                                     "nested-module", "create-import-delete"])
def test_entire_import_namespace_shadowing_is_not_executed(tmp_path, attack):
    root, candidate, test, context = _fixture(tmp_path)
    package = ("from pathlib import Path\np=Path('candidate');p.mkdir()\n"
        "(p/'__init__.py').write_text('def add(a,b): return a+b\\n')\n")
    if attack == "transient-package":
        source = package + "from candidate import add\n"
    elif attack == "nested-module":
        source = package + ("(p/'nested.py').write_text('def add(a,b): return a+b\\n')\n"
                            "from candidate.nested import add\n")
    elif attack == "create-import-delete":
        source = package + "from candidate import add\nimport shutil\nshutil.rmtree(p)\n"
    else:
        source = ("from pathlib import Path\nimport importlib.util\n"
            "import importlib._bootstrap_external as bootstrap\n"
            "original=Path('candidate.py').read_bytes()\n"
            "cache=Path(importlib.util.cache_from_source('candidate.py'))\n"
            "cache.parent.mkdir(parents=True,exist_ok=True)\n"
            "code=compile('def add(a,b): return a+b\\n','candidate.py','exec')\n"
            "cache.write_bytes(bootstrap._code_to_hash_pyc("
            "code,importlib.util.source_hash(original),checked=False))\nfrom candidate import add\n")
    test.write_text(source + "def test_add(): assert add(2,3)==5\n", encoding="utf-8")
    admitted = {path: path.read_bytes() for path in (candidate, test)}
    _check(root, candidate, context)
    assert all(path.read_bytes() == blob for path, blob in admitted.items())
    assert not (root / "candidate").exists() and not (root / "__pycache__").exists()
