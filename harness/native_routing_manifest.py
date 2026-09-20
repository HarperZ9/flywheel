"""Planned-only native routing task-family manifest utilities."""
from __future__ import annotations
import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any
from harness.routing_collection import canonical_sha256, text_sha256, utc_now
SCHEMA = "harness.native-routing-task-family-manifest/v1"
TASK_SET_SCHEMA = "harness.native-routing-task-family-set/v1"
PROJECTION_SCHEMA = "harness.native-routing-projection/v1"
DEFAULT_ARTIFACT_DIR = "artifacts/native-routing"
OPAQUE_PATTERNS = {
    "case_id": re.compile(r"^c_[0-9a-f]+$"),
    "case_group_id": re.compile(r"^g_[0-9a-f]+$"),
    "family_id": re.compile(r"^f_[a-z0-9]+_[0-9a-f]+$"),
    "policy_excerpt_id": re.compile(r"^p_[0-9a-f]+$"),
    "option_id": re.compile(r"^o_[0-9]{2,}$"),
    "arm_id": re.compile(r"^arm_[a-z0-9]+_[0-9]{3,}$"),
}
DENOMINATOR_FIELDS = {
    "host_region_or_locality", "local_hardware", "cache_hit_miss",
    "concurrency_policy", "option_count", "retries_attempted", "p50_ms",
    "p95_ms", "provider_cost_or_null", "local_compute_cost_or_null",
    "null_reason_for_unavailable_cost_or_tokens",
}
def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()
def build_manifest(
    doc: dict[str, Any],
    *,
    source_path: str = "",
    source_sha256: str = "",
    artifact_dir: str = DEFAULT_ARTIFACT_DIR,
) -> dict[str, Any]:
    validate_task_family_set(doc)
    case_rows = [_case_row(doc, case, artifact_dir) for case in doc["cases"]]
    projection_rows = [
        _projection_row(case, arm, artifact_dir)
        for case in doc["cases"]
        for arm in doc["candidate_arms"]
    ]
    return {
        "schema": SCHEMA,
        "timestamp_utc": utc_now(),
        "status": "planned_not_executed",
        "task_set_id": doc["task_set_id"],
        "dataset_status": doc["dataset_status"],
        "source_path": source_path,
        "source_sha256": source_sha256,
        "artifact_dir": artifact_dir,
        "case_rows": case_rows,
        "projection_rows": projection_rows,
        "dry_scorecard_rows": [_scorecard_row(row) for row in case_rows],
        "summary": {
            "total_cases": len(case_rows),
            "candidate_arms": len(doc["candidate_arms"]),
            "model_execution": False,
            "endpoint_probe": False,
            "benchmark_execution": False,
            "workflow_utility_measured": any(
                c["workflow_utility_contract"].get("measured") is True
                for c in doc["cases"]
            ),
            "demo_fixture": doc["dataset_status"] == "demo_fixture_not_180_case_benchmark",
        },
        "does_not_prove": [
            "Planned-only manifest; no model, endpoint, benchmark, or utility run executed.",
            "Demo fixture does not satisfy or replace a complete 180-case benchmark.",
            "Text/state fixture does not prove multimodal, UI, OCR, image, video, or LRM performance.",
        ],
    }
def render_case_projection(doc: dict[str, Any], case: dict[str, Any], arm: dict[str, Any]) -> dict[str, Any]:
    validate_task_family_set(doc)
    if case.get("case_id") not in {row["case_id"] for row in doc.get("cases", [])}:
        raise ValueError(f"unknown case id: {case.get('case_id')}")
    if arm.get("arm_id") not in _arms(doc):
        raise ValueError(f"unknown arm id: {arm.get('arm_id')}")
    options = [
        {"option_id": opt["option_id"], "label": opt.get("label", "")}
        for opt in case["option_set"]
    ]
    prompt = "\n".join([
        f"Case id: {case['case_id']}",
        f"Arm id: {arm['arm_id']}",
        f"Arm class: {arm['arm_class']}",
        "",
        "User text:",
        str(case["scenario_state"].get("redacted_user_text", "")),
        "",
        "Account state:",
        str(case["scenario_state"].get("redacted_account_state", "")),
        "",
        "Action log:",
        str(case["scenario_state"].get("redacted_action_log", "")),
        "",
        "Options:",
        *[f"- {opt['option_id']}: {opt.get('label', '')}" for opt in options],
        "",
        "Policy excerpts:",
        *[f"- {policy_id}" for policy_id in case.get("policy_excerpt_ids", [])],
    ]).strip() + "\n"
    features = {
        "schema": PROJECTION_SCHEMA,
        "case_id": case["case_id"],
        "arm_id": arm["arm_id"],
        "arm_class": arm["arm_class"],
        "option_ids": [opt["option_id"] for opt in options],
        "policy_excerpt_ids": list(case.get("policy_excerpt_ids", [])),
        "modality_scope": "text_state_only",
    }
    cache = {
        "schema": "harness.native-routing-cache-key/v1",
        "case_id": case["case_id"],
        "arm_id": arm["arm_id"],
        "prompt_sha256": text_sha256(prompt),
        "features_sha256": canonical_sha256(features),
    }
    hidden = {
        "schema": "harness.native-routing-hidden-authority/v1",
        "case_id": case["case_id"],
        "hidden_leakage_sentinels": list(case.get("hidden_leakage_sentinels", [])),
        "hidden_authority_refs": case.get("hidden_authority_refs", {}),
    }
    visible = prompt + json.dumps(features, sort_keys=True) + json.dumps(cache, sort_keys=True)
    _guard_no_projection_leakage(doc, case, visible)
    return {
        "schema": PROJECTION_SCHEMA,
        "case_id": case["case_id"],
        "arm_id": arm["arm_id"],
        "model_visible_prompt": prompt,
        "model_visible_features": features,
        "cache_key_material": cache,
        "hidden_authority_manifest": hidden,
    }
def render_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# Native routing task-family manifest",
        "",
        f"- Schema: `{manifest['schema']}`",
        f"- Status: `{manifest['status']}`",
        f"- Dataset status: `{manifest['dataset_status']}`",
        f"- Cases: `{manifest['summary']['total_cases']}`",
        f"- Candidate arms: `{manifest['summary']['candidate_arms']}`",
        f"- Model execution: `{str(manifest['summary']['model_execution']).lower()}`",
        f"- Benchmark execution: `{str(manifest['summary']['benchmark_execution']).lower()}`",
        f"- Workflow utility measured: `{str(manifest['summary']['workflow_utility_measured']).lower()}`",
        "",
        "## Case rows",
        "",
        "| Case | Split | Workflow utility | Planned artifacts |",
        "|---|---|---|---:|",
    ]
    for row in manifest["case_rows"]:
        lines.append(
            f"| `{row['case_id']}` | `{row['split_role']}` | "
            f"`{row['workflow_utility_status']}` | {len(row['planned_artifacts'])} |"
        )
    lines.extend(["", "## Limits", ""])
    lines.extend(f"- {item}" for item in manifest.get("does_not_prove", []))
    return "\n".join(lines) + "\n"
def validate_task_family_set(doc: dict[str, Any]) -> None:
    _require(doc, ["schema", "task_set_id", "dataset_status", "modality_scope",
                   "execution_denominator_schema", "task_families", "cases", "candidate_arms"], "task set")
    if doc["schema"] != TASK_SET_SCHEMA:
        raise ValueError(f"unsupported native routing schema: {doc.get('schema')}")
    if doc["dataset_status"] != "demo_fixture_not_180_case_benchmark":
        raise ValueError("this source slice accepts demo fixtures only, not complete benchmark claims")
    scope = doc["modality_scope"].get("current_manifest_scope", "")
    if "text/account-state/action-log" not in scope:
        raise ValueError("native routing demo must declare text/account-state/action-log scope")
    missing = DENOMINATOR_FIELDS - set(doc["execution_denominator_schema"].get("required_per_case_attempt_fields", []))
    if missing:
        raise ValueError(f"execution denominator missing fields: {', '.join(sorted(missing))}")
    families = _families(doc)
    arms = _arms(doc)
    seen_cases: set[str] = set()
    for case in doc["cases"]:
        _validate_case(case, families)
        if case["case_id"] in seen_cases:
            raise ValueError(f"duplicate case id: {case['case_id']}")
        seen_cases.add(case["case_id"])
    if not arms:
        raise ValueError("candidate_arms must not be empty")
def _validate_case(case: dict[str, Any], families: dict[str, dict[str, Any]]) -> None:
    _require(case, ["case_id", "family_id", "case_group_id", "split_role", "scenario_state",
                   "option_set", "policy_excerpt_ids", "hard_policy_contract",
                   "workflow_utility_contract"], "case")
    for field in ("case_id", "case_group_id", "family_id"):
        _opaque(case[field], field)
    if case["family_id"] not in families:
        raise ValueError(f"unknown family id: {case['family_id']}")
    if case["split_role"] != families[case["family_id"]]["split_role"]:
        raise ValueError(f"case split does not match family: {case['case_id']}")
    if case["hard_policy_contract"].get("labels_are") != "constraints_only":
        raise ValueError("hard policy labels must be constraints only")
    utility = case["workflow_utility_contract"]
    if utility.get("no_optimal_gold") is not True:
        raise ValueError("workflow utility must declare no optimal gold")
    if utility.get("measured") is True:
        raise ValueError("planned manifest cannot contain measured workflow utility")
    for policy_id in case.get("policy_excerpt_ids", []):
        _opaque(policy_id, "policy_excerpt_id")
    for option in case["option_set"]:
        _opaque(option.get("option_id", ""), "option_id")
def _guard_no_projection_leakage(doc: dict[str, Any], case: dict[str, Any], visible: str) -> None:
    forbidden: set[str] = set()
    for family in doc.get("task_families", []):
        forbidden.update([family.get("split_role", ""), family.get("private_human_label", "")])
        forbidden.update(family.get("semantic_family_tags", []))
    for row in doc.get("cases", []):
        forbidden.update(row.get("hidden_leakage_sentinels", []))
        forbidden.update(_strings(row.get("hidden_authority_refs", {})))
        forbidden.update(_strings(row.get("hard_policy_contract", {}).get("hidden_expected_fields", [])))
    for term in _term_variants(forbidden):
        if term and term in _normalize(visible):
            raise ValueError(f"projection leakage detected: {term}")
def _case_row(doc: dict[str, Any], case: dict[str, Any], artifact_dir: str) -> dict[str, Any]:
    family = _families(doc)[case["family_id"]]
    base = Path(artifact_dir) / case["case_id"]
    return {
        "schema": "harness.native-routing-task-family.case/v1",
        "task_set_id": doc["task_set_id"],
        "case_id": case["case_id"],
        "split_role": case["split_role"],
        "decision_surfaces": list(family.get("decision_surfaces", [])),
        "hard_policy_labels": "constraints_only",
        "workflow_utility_status": case["workflow_utility_contract"].get("status", "planned_unmeasured"),
        "workflow_utility_measured": False,
        "planned_artifacts": [(base / name).as_posix() for name in ("prompt.txt", "features.json", "cache_key.json", "hidden_authority.json")],
    }
def _projection_row(case: dict[str, Any], arm: dict[str, Any], artifact_dir: str) -> dict[str, Any]:
    base = Path(artifact_dir) / case["case_id"] / arm["arm_id"]
    return {
        "case_id": case["case_id"],
        "arm_id": arm["arm_id"],
        "execution_mode": "projection_only",
        "prompt_path": (base / "model_visible_prompt.txt").as_posix(),
        "features_path": (base / "model_visible_features.json").as_posix(),
        "cache_key_path": (base / "cache_key_material.json").as_posix(),
    }
def _scorecard_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "harness.native-routing-scorecard/v1",
        "case_id": row["case_id"],
        "execution_mode": "manifest_only",
        "status": "planned",
        "metrics": {"hard_policy_pass": None, "observed_workflow_utility": None},
    }
def _families(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {family["family_id"]: family for family in doc.get("task_families", [])}
def _arms(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {arm["arm_id"]: arm for arm in doc.get("candidate_arms", [])}
def _require(obj: dict[str, Any], fields: list[str], label: str) -> None:
    missing = [field for field in fields if field not in obj]
    if missing:
        raise ValueError(f"{label} missing required fields: {', '.join(missing)}")
def _opaque(value: str, field: str) -> None:
    if not isinstance(value, str) or not OPAQUE_PATTERNS[field].match(value):
        raise ValueError(f"{field} must use opaque {field} id")
def _strings(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        out: set[str] = set()
        for item in value.values():
            out.update(_strings(item))
        return out
    if isinstance(value, list):
        out: set[str] = set()
        for item in value:
            out.update(_strings(item))
        return out
    return set()
def _term_variants(values: set[str]) -> set[str]:
    out: set[str] = set()
    for value in values:
        text = _normalize(value)
        out.update({text, text.replace(" ", "-"), text.replace(" ", "_")})
    return out
def _normalize(value: str) -> str:
    return value.lower().replace("_", " ").replace("-", " ")
