"""Generate a 14B/32B model naming and publication plan from readiness receipts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402


SCHEMA = "harness.model-publish-plan/v1"

REQUIRED_RELEASE_FILES = [
    "MODEL_CARD.md",
    "README.md",
    "LICENSE",
    "checksums.sha256",
    "provenance.json",
    "endpoint.json",
    "usage.md",
    "benchmark-summary.json",
    "safety.md",
    "release-checklist.md",
]


def now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-")
    return text or "model"


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except FileNotFoundError:
        return None, "missing_artifact"
    except (OSError, json.JSONDecodeError) as exc:
        return None, type(exc).__name__


def _gate(gate_id: str, *, passed: bool, evidence: str, blocker: str) -> dict[str, Any]:
    return {
        "schema": "harness.model-publish-plan.gate/v1",
        "gate_id": gate_id,
        "passed": bool(passed),
        "evidence": evidence,
        "blocker": "" if passed else blocker,
    }


def _missing_from_gates(row: dict[str, Any]) -> list[str]:
    gates = row.get("gates") if isinstance(row.get("gates"), dict) else {}
    missing = []
    for gate in gates.values():
        if isinstance(gate, dict):
            missing.extend(str(item) for item in gate.get("missing_files", []) if item)
    return sorted(set(missing))


def _present_from_gates(row: dict[str, Any]) -> list[str]:
    gates = row.get("gates") if isinstance(row.get("gates"), dict) else {}
    present = []
    for gate in gates.values():
        if isinstance(gate, dict):
            present.extend(str(item) for item in gate.get("present_files", []) if item)
    return sorted(set(present))


def release_gates_for_model(row: dict[str, Any]) -> list[dict[str, Any]]:
    present_files = set(_present_from_gates(row))
    gates = [
        _gate(
            "root_exists",
            passed=bool(row.get("root_exists")),
            evidence="harness.model-release-readiness/v1",
            blocker="Model root is missing.",
        ),
        _gate(
            "weights_present",
            passed=int(row.get("weight_file_count", 0) or 0) > 0,
            evidence="harness.model-release-readiness/v1",
            blocker="No top-level weight file was detected.",
        ),
        _gate(
            "release_docs_complete",
            passed=float(row.get("release_doc_score", 0.0) or 0.0) >= 1.0,
            evidence="harness.model-release-readiness/v1",
            blocker="Release documentation gate is incomplete.",
        ),
        _gate(
            "endpoint_profiles_present",
            passed=int(row.get("endpoint_profile_count", 0) or 0) > 0,
            evidence="harness.model-endpoint-profiles/v1",
            blocker="No endpoint profile is attached to the release row.",
        ),
        _gate(
            "endpoint_generation_ok",
            passed=int(row.get("endpoint_gate_generation_ok_count", 0) or 0) > 0,
            evidence="harness.model-endpoint-gate/v1",
            blocker="No endpoint generation gate has passed.",
        ),
        _gate(
            "benchmark_evidence_present",
            passed=int(row.get("benchmark_artifact_count", 0) or 0) > 0,
            evidence="benchmark artifacts",
            blocker="No benchmark artifact is attached to the release row.",
        ),
    ]
    for filename in REQUIRED_RELEASE_FILES:
        gates.append(_gate(
            f"file:{filename}",
            passed=filename in present_files,
            evidence="harness.model-release-readiness/v1",
            blocker=f"`{filename}` is missing.",
        ))
    return gates


def actions_for_model(row: dict[str, Any], gates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    model = str(row.get("model", ""))
    missing_files = _missing_from_gates(row)
    actions = [
        {
            "schema": "harness.model-publish-plan.action/v1",
            "model": model,
            "priority": "P1",
            "owner": "model-foundry",
            "action": f"Create or restore `{filename}` for {model}.",
            "acceptance_gate": f"`file:{filename}` passes in the next publish plan.",
        }
        for filename in missing_files
    ]
    for gate in gates:
        if gate.get("passed") or str(gate.get("gate_id", "")).startswith("file:"):
            continue
        actions.append({
            "schema": "harness.model-publish-plan.action/v1",
            "model": model,
            "priority": "P0" if gate["gate_id"] in {"root_exists", "weights_present"} else "P1",
            "owner": "model-foundry",
            "action": str(gate.get("blocker", "")),
            "acceptance_gate": f"`{gate['gate_id']}` passes in the next publish plan.",
        })
    return actions


def publish_row(row: dict[str, Any], *, name_prefix: str) -> dict[str, Any]:
    model = str(row.get("model", ""))
    candidate_name = f"{name_prefix}-{model}".replace(" ", "-")
    candidate_slug = slugify(candidate_name).lower()
    gates = release_gates_for_model(row)
    actions = actions_for_model(row, gates)
    ready = bool(row.get("enterprise_release_ready")) and all(gate.get("passed") for gate in gates)
    return {
        "schema": "harness.model-publish-plan.model/v1",
        "model": model,
        "model_key": row.get("model_key", ""),
        "candidate_name": candidate_name,
        "candidate_slug": candidate_slug,
        "root": row.get("root", ""),
        "source_verdict": row.get("verdict", ""),
        "publish_status": "READY_TO_STAGE" if ready else "DO_NOT_PUBLISH",
        "release_gates": gates,
        "actions": actions,
        "blockers": [str(gate["blocker"]) for gate in gates if gate.get("blocker")],
        "required_artifacts": REQUIRED_RELEASE_FILES,
    }


def build_plan(
    readiness: dict[str, Any],
    *,
    readiness_artifact: str,
    source_loaded: bool = True,
    source_load_error: str = "",
    name_prefix: str = "Flywheel-Local-Coder",
) -> dict[str, Any]:
    model_rows = readiness.get("models") if isinstance(readiness.get("models"), list) else []
    models = [
        publish_row(row, name_prefix=name_prefix)
        for row in model_rows
        if isinstance(row, dict)
    ]
    actions = [action for model in models for action in model["actions"]]
    blockers = [blocker for model in models for blocker in model["blockers"]]
    ready_to_stage = [model for model in models if model["publish_status"] == "READY_TO_STAGE"]
    source_ready = bool(source_loaded and readiness.get("schema") == "harness.model-release-readiness/v1")
    return {
        "schema": SCHEMA,
        "timestamp_utc": now_utc(),
        "source_artifact": readiness_artifact,
        "source_schema": readiness.get("schema", ""),
        "source_loaded": bool(source_loaded),
        "source_load_error": source_load_error,
        "name_prefix": name_prefix,
        "publish_policy": "No model is published by this command; READY_TO_STAGE only means release evidence is complete enough for an operator-gated staging decision.",
        "models": models,
        "summary": {
            "source_loaded": bool(source_loaded),
            "source_load_error": source_load_error,
            "source_ready": source_ready,
            "models": len(models),
            "ready_to_stage_models": len(ready_to_stage),
            "do_not_publish_models": len(models) - len(ready_to_stage),
            "actions": len(actions),
            "blockers": len(blockers),
            "candidate_names": [model["candidate_name"] for model in models],
        },
    }


def render_markdown(plan: dict[str, Any]) -> str:
    summary = plan["summary"]
    lines = [
        "# Model naming and publication plan",
        "",
        f"- Schema: `{plan['schema']}`",
        f"- Timestamp UTC: `{plan['timestamp_utc']}`",
        f"- Source artifact: `{plan['source_artifact']}`",
        f"- Source loaded: `{str(plan['source_loaded']).lower()}`",
        f"- Source load error: `{plan['source_load_error']}`",
        f"- Name prefix: `{plan['name_prefix']}`",
        f"- Ready to stage: `{summary['ready_to_stage_models']}` / `{summary['models']}`",
        f"- Do not publish: `{summary['do_not_publish_models']}`",
        "",
        "| Model | Candidate name | Status | Gates passed | Actions | Blockers |",
        "|---|---|---|---:|---:|---:|",
    ]
    for model in plan["models"]:
        gates = model["release_gates"]
        lines.append(
            "| {model} | {name} | {status} | {passed}/{total} | {actions} | {blockers} |".format(
                model=model["model"],
                name=model["candidate_name"],
                status=model["publish_status"],
                passed=sum(1 for gate in gates if gate.get("passed")),
                total=len(gates),
                actions=len(model["actions"]),
                blockers=len(model["blockers"]),
            )
        )
    lines.extend(["", "## Policy", "", plan["publish_policy"], ""])
    return "\n".join(lines) + "\n"


def write_text(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def store_plan(plan: dict[str, Any], *, store_root: str, run_id: str, artifacts: list[tuple[str, str]]) -> list[dict[str, Any]]:
    if not store_root:
        return []
    store = FileBackedHarnessStore(Path(store_root))
    verdict = (
        "MODEL_PUBLISH_PLAN_READY"
        if plan["summary"]["source_ready"] and plan["summary"]["do_not_publish_models"] == 0
        else ("MODEL_PUBLISH_PLAN_UNVERIFIABLE" if not plan["summary"]["source_ready"] else "MODEL_PUBLISH_PLAN_BLOCKED")
    )
    outputs = [store.put_receipt(kind="model_publish_plan", body=plan, run_id=run_id, verdict=verdict)]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-readiness-artifact", required=True)
    parser.add_argument("--name-prefix", default="Flywheel-Local-Coder")
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    readiness, error = _load_json(Path(args.release_readiness_artifact))
    if readiness is None:
        readiness = {"schema": "", "models": []}
    plan = build_plan(
        readiness,
        readiness_artifact=args.release_readiness_artifact,
        source_loaded=not error,
        source_load_error=error,
        name_prefix=args.name_prefix,
    )
    if error:
        plan["load_error"] = error
    json_text = json.dumps(plan, indent=2, sort_keys=True)
    md_text = render_markdown(plan)
    json_path = write_text(args.out, json_text)
    md_path = write_text(args.markdown_out, md_text)
    store_outputs = store_plan(
        plan,
        store_root=args.store_root,
        run_id=args.run_id,
        artifacts=[
            (json_path, "model-publish-plan-json"),
            (md_path, "model-publish-plan-markdown"),
        ],
    )
    if store_outputs:
        plan = {**plan, "store_outputs": store_outputs}
        json_text = json.dumps(plan, indent=2, sort_keys=True)
        write_text(args.out, json_text)
    print(json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
