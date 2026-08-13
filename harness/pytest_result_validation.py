"""Offline semantic validation for a carried prepared-pytest result."""
from __future__ import annotations

import hashlib
from pathlib import PurePosixPath

from .checker_identity import runtime_digest
from .evidence_json import strict_load_json

PROTECTION = "windows-low-integrity-namespace/v1"
NAMESPACE = {"input": "read-only-medium-integrity",
             "output": "separate-low-integrity",
             "candidate_binding": "exact-source-compile/v1"}


def _module(ref: str) -> str:
    path = PurePosixPath(ref)
    if path.name == "__init__.py":
        return ".".join(path.parts[:-1])
    return ".".join((*path.parts[:-1], path.stem))


def _provenance(value: object, candidate_ref: str, candidate_sha: str) -> None:
    expected = {"schema": "flywheel.python-module-provenance/v1",
        "module": _module(candidate_ref), "source_ref": candidate_ref,
        "source_sha256": candidate_sha, "loaded": True,
        "origin": candidate_ref, "binding": "exact-source-compile/v1"}
    if (type(value) is not dict or set(value) != set(expected) | {"load_count"}
            or any(value.get(key) != item for key, item in expected.items())
            or type(value.get("load_count")) is not int or value["load_count"] < 1):
        raise ValueError("candidate provenance is absent or drifted")


def validate_pytest_result(receipt, check: dict, result_blob: bytes,
                           raw: dict[str, dict], filter_hash: str,
                           denominator) -> None:
    result = strict_load_json(result_blob, max_depth=32)
    required = {"schema", "command", "execution_input_protection",
        "execution_namespace", "candidate_provenance", "runtime", "inputs",
        "outcomes", "return_code"}
    if type(result) is not dict or set(result) != required or result["schema"] != "flywheel.pytest-result/v2":
        raise ValueError("pytest result artifact is not closed")
    output_ref = receipt.coverage.get("oracle_output_ref")
    inputs = [item for ref, item in raw.items() if ref != output_ref]
    if result["command"] != check["command"] or result["inputs"] != inputs:
        raise ValueError("pytest result command or inputs drift")
    protection = receipt.coverage.get("execution_input_protection")
    namespace = receipt.coverage.get("execution_namespace")
    if (protection != PROTECTION or result["execution_input_protection"] != protection
            or namespace != NAMESPACE or result["execution_namespace"] != namespace):
        raise ValueError("execution namespace protection is absent or drifted")
    candidate_ref = receipt.coverage.get("candidate_ref")
    provenance = receipt.coverage.get("candidate_provenance")
    _provenance(result["candidate_provenance"], candidate_ref,
                receipt.candidate_sha256)
    if provenance != result["candidate_provenance"]:
        raise ValueError("receipt candidate provenance drift")
    runtime = receipt.coverage.get("runtime_descriptor")
    if runtime != result["runtime"]:
        raise ValueError("receipt runtime descriptor drift")
    runtime_sha = runtime_digest(runtime)
    if receipt.coverage.get("runtime_descriptor_sha256") != runtime_sha:
        raise ValueError("receipt runtime descriptor digest drift")
    outcomes, rc = result["outcomes"], result["return_code"]
    if (type(outcomes) is not list or outcomes != sorted(set(outcomes))
            or any(type(item) is not str or not item.endswith(("=PASS", "=FAIL", "=SKIP"))
                   for item in outcomes) or type(rc) is not int):
        raise ValueError("pytest result outcomes or return code are malformed")
    value = hashlib.sha256(("\n".join(outcomes) + f"\n{rc}").encode()).hexdigest()[:16]
    timed_out = rc == 124
    verdict = "PASS" if rc == 0 and any(item.endswith("=PASS") for item in outcomes) else "FAIL"
    expected = {"command": result["command"], "output_hash": value,
        "return_code": rc, "execution": "TIMEOUT" if timed_out else "COMPLETED",
        "attribution": "CANDIDATE", "verdict": verdict,
        "denominator": denominator(verdict, timed_out, filter_hash)}
    if check != expected:
        raise ValueError("check result contradicts carried pytest result")
    if (receipt.verdict.value != verdict or receipt.attribution.value != "CANDIDATE"
            or receipt.denominator.to_dict() != expected["denominator"]):
        raise ValueError("receipt contradicts carried pytest result")
