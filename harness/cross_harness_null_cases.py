"""Runner-owned good cases for the registered cross-harness null floor."""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import json
from itertools import combinations
from pathlib import Path
from typing import Any

from harness.cross_harness_kv_source_common import CHECKER_ID as KV_CHECKER
from harness.cross_harness_kv_source_oracle import derive_kv_source_result
from harness.cross_harness_oracles import OracleContext
from harness.cross_harness_oracles_v2 import CHECKER_ID as DOCS_V2
from harness.shared_task_artifact_v2 import (
    PRE_ORACLE_STATES,
    SHARED_TASK_CHECKER_ID as SHARED_V2,
    render_shared_task_markdown_v2,
)

ROOT = Path(__file__).resolve().parent.parent
TASK_SET = "benchmarks/agentic-task-set-v1.json"
DOCS_V1 = "documentation_maintenance/v1"
KV_FIXTURE = "benchmarks/fixtures/cross-harness/kv-source-null-floor-v1.json"

class NullFloorCaseError(ValueError): pass

def registered_checker_ids() -> list[str]:
    from harness.cross_harness_oracles import _CHECKERS

    return sorted(_CHECKERS)

def build_case(tmp_path: Path, checker_id: str, *, repo_root: Path = ROOT):
    repo_root = Path(repo_root)
    builder = _BUILDERS.get(checker_id)
    if builder is None:
        raise NullFloorCaseError(f"no null-floor case for {checker_id}")
    try:
        return builder(tmp_path, repo_root)
    except NullFloorCaseError as exc:
        if checker_id in str(exc):
            raise
        raise NullFloorCaseError(f"fixture unavailable for {checker_id}: {exc}") from exc

def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True).encode("utf-8")

def _write(path: Path, value: Any, *, raw: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = str(value).encode("utf-8") if raw else _json_bytes(value)
    path.write_bytes(data)

def _source_file(root: Path, ref: str, checker_id: str) -> Path:
    if not root.is_dir():
        raise NullFloorCaseError(f"fixture unavailable for {checker_id}: source root {root}")
    rel = Path(ref)
    path = (root / rel).resolve()
    if rel.is_absolute() or ".." in rel.parts or not path.is_relative_to(root.resolve()) or not path.is_file():
        label = "fixture" if ref.endswith(".json") else "required input"
        raise NullFloorCaseError(f"{label} unavailable for {checker_id}: {ref}")
    return path

def _load_json(root: Path, ref: str, checker_id: str) -> dict[str, Any]:
    path = _source_file(root, ref, checker_id)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise NullFloorCaseError(f"fixture malformed for {checker_id}: {ref}")
    return value

def _input_hashes(root: Path, refs: list[str], checker_id: str) -> dict[str, str]:
    return {ref: _sha(_source_file(root, ref, checker_id).read_bytes()) for ref in refs}

def _task_rows(root: Path) -> dict[str, dict[str, Any]]:
    task_set = _load_json(root, TASK_SET, "task-set")
    rows: dict[str, dict[str, Any]] = {}
    for task in task_set.get("tasks", []):
        if isinstance(task, dict) and isinstance(task.get("oracle"), dict):
            checker_id = task["oracle"].get("checker_id")
            if isinstance(checker_id, str):
                rows[checker_id] = task
    return rows

def _task_for(root: Path, checker_id: str) -> dict[str, Any]:
    source_id = DOCS_V1 if checker_id == DOCS_V2 else checker_id
    task = _task_rows(root).get(source_id)
    if task is None:
        raise NullFloorCaseError(f"no null-floor task fixture for {checker_id}")
    task = copy.deepcopy(task)
    if checker_id == DOCS_V2:
        task["oracle"]["checker_id"] = DOCS_V2
    return task

def _core(tmp_path: Path, root: Path, *, states: dict[str, str] | None = None) -> dict[str, Any]:
    attempt = tmp_path / "attempt"
    raw, receipt = attempt / "raw.txt", attempt / "receipt.json"
    _write(raw, "raw output", raw=True)
    _write(receipt, "{}", raw=True)
    return {
        "raw_prompt_sha256": "a" * 64,
        "tool_policy_sha256": "b" * 64,
        "attempt_dir": str(attempt),
        "workspace_root": str(root.resolve()),
        "raw_artifact_sha256": _sha(raw.read_bytes()),
        "receipt_sha256": _sha(receipt.read_bytes()),
        "orthogonal_states": states or {
            "execution_state": "timeout",
            "oracle_state": "not_run",
            "receipt_state": "verified",
        },
    }

def _materialize(tmp_path: Path, task_id: str, artifacts: list[str], report: dict[str, Any], markdown: str):
    attempt = tmp_path / "attempt"
    paths = {name: attempt / name for name in artifacts}
    json_name = next(name for name in artifacts if name.endswith(".json"))
    md_name = next(name for name in artifacts if name.endswith(".md"))
    _write(paths[json_name], report)
    _write(paths[md_name], markdown, raw=True)
    _write(attempt / "output.json", {"artifacts": {json_name: report, md_name: markdown}})
    return attempt / "output.json", paths

def _task_case(tmp_path: Path, repo_root: Path, checker_id: str):
    task = _task_for(repo_root, checker_id)
    oracle_spec = dict(task["oracle"])
    artifacts = list(task["expected_artifacts"])
    oracle_spec["expected_artifacts"] = artifacts
    fixture = _load_json(repo_root, str(oracle_spec["fixture"]), checker_id)
    input_hashes = _input_hashes(repo_root, list(task["required_inputs"]), checker_id)
    core = _core(tmp_path, repo_root, states=PRE_ORACLE_STATES if checker_id == SHARED_V2 else None)
    report = _report_for(checker_id, str(task["id"]), input_hashes, fixture, repo_root, oracle_spec, core)
    if checker_id == SHARED_V2:
        markdown = render_shared_task_markdown_v2(report)
    elif checker_id == "context_recovery_state/v1":
        markdown = "# comp-005-context-recovery\nSource context selected.\n"
    else:
        markdown = f"# {task['id']}\n"
    raw_path, paths = _materialize(tmp_path, str(task["id"]), artifacts, report, markdown)
    return OracleContext(str(task["id"]), oracle_spec, raw_path, paths, input_hashes, core), report, fixture

def _report_for(checker_id: str, task_id: str, input_hashes: dict[str, str], fixture: dict[str, Any],
                root: Path, spec: dict[str, Any], core: dict[str, Any]) -> dict[str, Any]:
    if checker_id == "index_fallback_integrity/v1":
        return _index_report(task_id, input_hashes, fixture)
    if checker_id == "shared_task_artifact/v1":
        return _shared_report(task_id, input_hashes, core)
    if checker_id == SHARED_V2:
        return _shared_v2_report(task_id, input_hashes, fixture, core)
    if checker_id == "paired_friction/v1":
        return _paired_report(task_id, input_hashes, fixture, spec)
    if checker_id in (DOCS_V1, DOCS_V2):
        return _docs_report(task_id, input_hashes, fixture, root, checker_id == DOCS_V2)
    if checker_id == "evidence_bound_reporting/v1":
        return _evidence_report(task_id, input_hashes, fixture)
    if checker_id == "contradiction_detection/v1":
        return {"task_id": task_id, "input_sha256s": input_hashes,
                "contradictions": [{"records": pair} for pair in fixture["contradiction_pairs"]]}
    if checker_id == "budgeted_evidence_selection/v1":
        return _budget_report(task_id, input_hashes, fixture)
    if checker_id == "context_recovery_state/v1":
        return _context_report(task_id, input_hashes, fixture, root)
    raise NullFloorCaseError(f"no null-floor report builder for {checker_id}")

def _index_report(task_id: str, input_hashes: dict[str, str], fixture: dict[str, Any]) -> dict[str, Any]:
    classes, citations = set(), set()
    for event in fixture["events"]:
        derived = None
        if event.get("type") == "mcp_call" and event.get("outcome") == "failure":
            derived = "live_mcp_failure"
        elif event.get("type") == "artifact_read" and event.get("source") == "stale":
            derived = "stale_artifact_use"
        elif event.get("type") == "json_parse" and event.get("outcome") == "failure":
            derived = "invalid_json"
        elif event.get("type") == "match" and event.get("mode") == "degraded":
            derived = "degraded_match"
        if derived:
            classes.add(derived)
            citations.add(str(event.get("event_id", "")))
    return {"task_id": task_id, "input_sha256s": input_hashes,
            "failure_classes": sorted(classes), "cited_event_ids": sorted(citations),
            "receipt_input_sha256s": input_hashes}

def _shared_report(task_id: str, input_hashes: dict[str, str], core: dict[str, Any]) -> dict[str, Any]:
    states = core["orthogonal_states"]
    return {"task_id": task_id, "input_sha256s": input_hashes,
            "raw_prompt_sha256": core["raw_prompt_sha256"],
            "tool_policy_sha256": core["tool_policy_sha256"],
            "raw_artifact_path": "raw.txt", "receipt_path": "receipt.json",
            "failure_modes": sorted(value for value in states.values() if value == "timeout")}

def _shared_v2_report(task_id: str, input_hashes: dict[str, str], fixture: dict[str, Any],
                      core: dict[str, Any]) -> dict[str, Any]:
    claims = copy.deepcopy(fixture["participant_contract"]["claim_bindings"])
    for claim in claims:
        if claim.get("claim_id") == "pre_oracle_attempt_state":
            claim["facts"] = {**PRE_ORACLE_STATES, "pre_oracle_failure_modes": []}
    return {"task_id": task_id, "input_sha256s": input_hashes,
            "raw_prompt_sha256": core["raw_prompt_sha256"],
            "tool_policy_sha256": core["tool_policy_sha256"],
            "raw_artifact_path": "raw.txt", "receipt_path": "receipt.json",
            "pre_oracle_failure_modes": [], "claim_bindings": claims}

def _paired_report(task_id: str, input_hashes: dict[str, str], fixture: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    observations = fixture["observations"]
    modes = sorted(spec["exact_modes"])
    keys = sorted({row["task_key"] for row in observations})
    aggregates = []
    for mode in modes:
        rows = [row for row in observations if row["mode"] == mode]
        aggregates.append({"mode": mode, "denominator": len(rows),
                           "completion_counts": dict(sorted(Counter(row["completion"] for row in rows).items())),
                           "friction_events": sum(row["friction_events"] for row in rows),
                           "correction_steps": sum(row["correction_steps"] for row in rows)})
    return {"task_id": task_id, "input_sha256s": input_hashes, "modes": modes, "task_keys": keys,
            "pairs": [{"task_key": key, "modes": modes} for key in keys],
            "denominator": len(keys), "aggregates": aggregates}

def _docs_report(task_id: str, input_hashes: dict[str, str], fixture: dict[str, Any], root: Path, digests: bool) -> dict[str, Any]:
    surfaces = copy.deepcopy(fixture["surfaces"])
    if digests:
        for row in surfaces:
            row["content_sha256"] = _sha((root / row["path"]).read_bytes())
            row["code_ref_sha256s"] = [_sha((root / ref).read_bytes()) for ref in row["code_refs"]]
    return {"task_id": task_id, "input_sha256s": input_hashes, "surfaces": surfaces}

def _evidence_report(task_id: str, input_hashes: dict[str, str], fixture: dict[str, Any]) -> dict[str, Any]:
    support = {row["claim_id"]: sorted(row.get("supported_by", [])) for row in fixture["claims"]}
    return {"task_id": task_id, "input_sha256s": input_hashes,
            "measurements": [{key: row[key] for key in ("measurement_id", "value", "denominator", "interval_95")}
                             for row in fixture["measurements"]],
            "claim_verdicts": [{"claim_id": name, "verdict": "supported" if refs else "unverifiable",
                                "evidence": refs} for name, refs in sorted(support.items())]}

def _budget_report(task_id: str, input_hashes: dict[str, str], fixture: dict[str, Any]) -> dict[str, Any]:
    items = fixture["items"]
    budget = int(round(float(fixture["budget_usd"]) * 100))
    best: tuple[int, int, list[str]] = (0, 0, [])
    for size in range(len(items) + 1):
        for group in combinations(items, size):
            cost = sum(int(round(float(row["cost_usd"]) * 100)) for row in group)
            value = sum(int(row["evidence_value"]) for row in group)
            ids = sorted(str(row["item_id"]) for row in group)
            if cost <= budget and (value, -cost, ids) > (best[0], -best[1], best[2]):
                best = (value, cost, ids)
    return {"task_id": task_id, "input_sha256s": input_hashes, "selected": best[2],
            "total_cost_usd": round(best[1] / 100, 4), "total_value": best[0]}

def _context_report(task_id: str, input_hashes: dict[str, str], fixture: dict[str, Any], root: Path) -> dict[str, Any]:
    state = fixture["continuation_package"]
    files = fixture["workspace_files"]
    expected_count = fixture["journey_state"]["expected_count"]
    return {"task_id": task_id, "input_sha256s": input_hashes, "recovered_context": copy.deepcopy(state),
            "workspace_state": [{"path": row["path"], "role": row["role"],
                                 "sha256": _sha((root / row["path"]).read_bytes())} for row in files],
            "preserved_files": sorted(row["path"] for row in files if row["must_preserve"]),
            "source_drift_decisions": [{"case_id": row["case_id"], "decision": "refuse",
                                        "error_code": row["error_code"], "effect_count": 0}
                                       for row in fixture["drift_cases"]],
            "duplicate_resolutions": [{"case_id": row["case_id"], "decision": row["expected_decision"],
                                       "new_effect_count": 0, "journey_count": expected_count}
                                      for row in fixture["duplicate_cases"]],
            "next_action": {key: fixture["rescue_action"][key]
                            for key in ("action_id", "kind", "selected_files", "basis_refs", "description")},
            "forbidden_effects": [], "native_provenance_state": "separate_dimension"}

def _kv_case(tmp_path: Path, repo_root: Path):
    fixture = _load_json(repo_root, KV_FIXTURE, KV_CHECKER)
    task_id = str(fixture["task_id"])
    input_hashes = _input_hashes(repo_root, [KV_FIXTURE], KV_CHECKER)
    result, codes, _ = derive_kv_source_result(task_id, fixture)
    if result is None or codes:
        raise NullFloorCaseError(f"fixture malformed for {KV_CHECKER}: {codes}")
    report = {"task_id": task_id, "input_sha256s": input_hashes, "result": result}
    spec = {"checker_id": KV_CHECKER, "fixture": KV_FIXTURE, "expected_artifacts": ["report.json", "report.md"],
            "citation_order": "unordered_set"}
    raw_path, paths = _materialize(tmp_path, task_id, spec["expected_artifacts"], report, f"# {task_id}\n")
    return OracleContext(task_id, spec, raw_path, paths, input_hashes, _core(tmp_path, repo_root)), report, fixture

def _pilot(checker_id: str):
    return lambda tmp_path, repo_root: _task_case(tmp_path, repo_root, checker_id)

_BUILDERS = {
    "index_fallback_integrity/v1": _pilot("index_fallback_integrity/v1"),
    "shared_task_artifact/v1": _pilot("shared_task_artifact/v1"),
    "paired_friction/v1": _pilot("paired_friction/v1"),
    DOCS_V1: _pilot(DOCS_V1),
    DOCS_V2: _pilot(DOCS_V2),
    "evidence_bound_reporting/v1": _pilot("evidence_bound_reporting/v1"),
    "contradiction_detection/v1": _pilot("contradiction_detection/v1"),
    "budgeted_evidence_selection/v1": _pilot("budgeted_evidence_selection/v1"),
    "context_recovery_state/v1": _pilot("context_recovery_state/v1"),
    SHARED_V2: _pilot(SHARED_V2),
    KV_CHECKER: _kv_case,
}
