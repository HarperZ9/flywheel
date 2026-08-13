"""Byte-exact prepared pytest execution behind the protected namespace."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from .execution_input_protection import PROTECTION, protect_execution_namespace
from .pytest_executor import _module_name
from .checker_identity import runtime_digest
from .runtime_descriptor import PYTHON_ACCEPTANCE_REASON, pytest_runtime_descriptor

MAX_INPUT = 1_048_576
MAX_PROVENANCE = 65_536


def _read(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("prepared pytest artifact exceeds byte limit")
    return data


def _provenance(path: Path, candidate_ref: str, candidate_sha256: str) -> dict:
    value = json.loads(_read(path, MAX_PROVENANCE))
    module, _ = _module_name(candidate_ref)
    expected = {"schema": "flywheel.python-module-provenance/v2",
        "module": module, "source_ref": candidate_ref,
        "source_sha256": candidate_sha256, "loaded": True,
        "origin": candidate_ref, "binding": "exact-source-compile/v1",
        "authority": "untrusted-test-process/v1"}
    if (type(value) is not dict or set(value) != set(expected) | {"load_count"}
            or any(value.get(key) != item for key, item in expected.items())
            or type(value.get("load_count")) is not int or value["load_count"] < 1):
        raise ValueError("candidate module provenance was not established")
    return value


def verify_prepared(oracle, argv, task, input_refs):
    from .oracle import (JUNIT_NAME, OracleResult, _pytest_canonical,
                         _pytest_ran_a_real_pass, canonical_hash, clear_bytecode,
                         run_env)
    work = Path(task.workdir); snapshots = {}; clear_bytecode(work)
    for ref in input_refs:
        blob = _read(work / ref, MAX_INPUT)
        snapshots[ref] = (blob, "sha256:" + hashlib.sha256(blob).hexdigest())
    candidate_ref = task.candidate_path
    if candidate_ref not in snapshots:
        raise ValueError("candidate is not an admitted prepared input")
    output = work.parent / "output"; output.mkdir()
    junit, provenance_path = output / JUNIT_NAME, output / "candidate-provenance.json"
    runner = Path(__file__).with_name("pytest_executor.py").resolve(strict=True)
    runner_blob = _read(runner, MAX_INPUT)
    runner_sha = "sha256:" + hashlib.sha256(runner_blob).hexdigest()
    child_argv = [sys.executable, "-I", "-B", str(runner),
        "--workdir", str(work), "--candidate-ref", candidate_ref,
        "--candidate-sha256", snapshots[candidate_ref][1],
        "--junit", str(junit), "--provenance", str(provenance_path),
        "--", *argv[3:]]
    env = run_env({"TEMP": str(output), "TMP": str(output),
                   "TMPDIR": str(output), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                   "PYTHONNOUSERSITE": "1", "PYTHONPATH": ""})
    with protect_execution_namespace(work, output) as protected:
        rc = protected.run(child_argv, env=env, timeout_seconds=oracle.timeout)
    if _read(runner, MAX_INPUT) != runner_blob:
        raise ValueError("pytest executor changed during protected execution")
    canonical = _pytest_canonical(output)
    provenance = _provenance(provenance_path, candidate_ref,
                             snapshots[candidate_ref][1])
    command = {"args": ["python", "-m", "pytest", *argv[3:]],
        "targets": list(dict.fromkeys(arg.split("::", 1)[0] for arg in argv[3:]))}
    runtime = pytest_runtime_descriptor()
    runtime_sha = runtime_digest(runtime)
    sources = [ref for ref in snapshots if Path(ref).suffix == ".py"]
    boundary = {"schema": "flywheel.python-dependency-boundary/v1",
        "admitted_input_refs": sorted(snapshots),
        "admitted_source_refs": sorted(sources),
        "executor_source_sha256": runner_sha,
        "runtime_descriptor_sha256": runtime_sha,
        "external_read_observation": "unavailable",
        "enforcement": "deny-positive-without-independent-closure/v1",
        "closure": "UNVERIFIABLE"}
    artifact = {"schema": "flywheel.pytest-result/v3", "command": command,
        "execution_input_protection": PROTECTION,
        "execution_namespace": {"input": "read-only-medium-integrity",
            "output": "separate-low-integrity",
            "candidate_binding": "exact-source-compile/v1"},
        "candidate_provenance": provenance, "dependency_boundary": boundary,
        "runtime": runtime,
        "inputs": [{"ref": ref, "sha256": claimed, "bytes": len(blob)}
                   for ref, (blob, claimed) in snapshots.items()],
        "outcomes": canonical.splitlines(), "return_code": rc}
    positive = rc == 0 and _pytest_ran_a_real_pass(output)
    result = OracleResult(verdict_="UNVERIFIABLE" if positive else "FAIL",
        attribution="ENVIRONMENT" if positive else "CANDIDATE", cmd="",
        output_hash=canonical_hash("pytest", output, rc), stdout_excerpt="", rc=rc,
        unverifiable_reason=PYTHON_ACCEPTANCE_REASON if positive else "")
    return result, artifact, snapshots
