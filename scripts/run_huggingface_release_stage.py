"""Generate a dry-run Hugging Face release staging receipt for local models."""

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


SCHEMA = "harness.huggingface-release-stage/v1"
UPLOAD_MODE = "dry_run_metadata_only"
SOURCE_REFERENCES = [
    {
        "label": "Hugging Face Hub CLI upload guide",
        "url": "https://huggingface.co/docs/huggingface_hub/guides/cli",
        "observed_guidance": "`hf upload <repo_id> <local_folder>` uploads a local folder to a model repository.",
    },
    {
        "label": "Hugging Face Hub upload_folder guide",
        "url": "https://huggingface.co/docs/huggingface_hub/guides/upload",
        "observed_guidance": "`HfApi.upload_folder(..., repo_type='model')` uploads a folder through the Python API.",
    },
]


def now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-")
    return (text or "model").lower()


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except FileNotFoundError:
        return None, "missing_artifact"
    except (OSError, json.JSONDecodeError) as exc:
        return None, type(exc).__name__


def _model_key(row: dict[str, Any]) -> str:
    raw = row.get("model") or row.get("model_key") or row.get("candidate_name") or ""
    return str(raw).strip().upper()


def _readiness_by_model(readiness: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = readiness.get("models") if isinstance(readiness.get("models"), list) else []
    return {
        _model_key(row): row
        for row in rows
        if isinstance(row, dict) and _model_key(row)
    }


def _gate_status(release_gates: list[dict[str, Any]], gate_id: str) -> bool:
    for gate in release_gates:
        if isinstance(gate, dict) and gate.get("gate_id") == gate_id:
            return bool(gate.get("passed"))
    return False


def _stage_gate(gate_id: str, passed: bool, evidence: str, blocker: str) -> dict[str, Any]:
    return {
        "schema": "harness.huggingface-release-stage.gate/v1",
        "gate_id": gate_id,
        "passed": bool(passed),
        "evidence": evidence,
        "blocker": "" if passed else blocker,
    }


def _upload_templates(repo_id: str, model_root: str, *, trained_artifact_present: bool) -> dict[str, str]:
    if not trained_artifact_present:
        marker = (
            "# DO NOT UPLOAD: no trained artifact exists for this track; "
            "base weights must not be republished under a Flywheel name."
        )
        return {"cli": marker, "python": marker}
    folder = model_root or "<local_model_dir>"
    return {
        "cli": f"hf upload {repo_id} {folder} --repo-type model",
        "python": (
            "from huggingface_hub import HfApi\n"
            "api = HfApi()\n"
            f"api.upload_folder(repo_id='{repo_id}', folder_path=r'{folder}', repo_type='model')"
        ),
    }


def stage_model(
    plan_row: dict[str, Any],
    *,
    readiness_row: dict[str, Any],
    namespace: str,
    private: bool,
    operator_upload_approved: bool,
) -> dict[str, Any]:
    release_gates = [
        gate for gate in plan_row.get("release_gates", [])
        if isinstance(gate, dict)
    ]
    model = str(plan_row.get("model") or readiness_row.get("model") or "")
    candidate_name = str(plan_row.get("candidate_name") or f"Flywheel-Local-Coder-{model}")
    candidate_slug = str(plan_row.get("candidate_slug") or slugify(candidate_name))
    repo_id = f"{namespace.rstrip('/')}/{candidate_slug}"
    model_root = str(plan_row.get("root") or readiness_row.get("root") or "")
    blockers = [str(item) for item in plan_row.get("blockers", []) if item]
    publish_ready = plan_row.get("publish_status") == "READY_TO_STAGE" and not blockers
    release_gate_complete = bool(release_gates) and all(bool(gate.get("passed")) for gate in release_gates)
    trained_artifact_present = bool(
        plan_row.get("trained_artifact_present") or readiness_row.get("trained_artifact_present")
    )
    stage_gates = [
        _stage_gate(
            "trained_artifact_present",
            trained_artifact_present,
            "harness.model-release-readiness/v1",
            "No trained model artifact exists for this track; base weights must not be republished under a Flywheel name.",
        ),
        _stage_gate(
            "publish_plan_ready_to_stage",
            publish_ready,
            "harness.model-publish-plan/v1",
            "Model publish plan is not READY_TO_STAGE.",
        ),
        _stage_gate(
            "release_gates_complete",
            release_gate_complete,
            "harness.model-publish-plan/v1",
            "One or more release gates are incomplete.",
        ),
        _stage_gate(
            "model_root_present",
            bool(model_root and readiness_row.get("root_exists")),
            "harness.model-release-readiness/v1",
            "Model root is missing or not represented in readiness.",
        ),
        _stage_gate(
            "weights_present",
            int(readiness_row.get("weight_file_count", 0) or 0) > 0,
            "harness.model-release-readiness/v1",
            "No model weight file is represented in readiness.",
        ),
        _stage_gate(
            "checksums_present",
            _gate_status(release_gates, "file:checksums.sha256"),
            "harness.model-publish-plan/v1",
            "`checksums.sha256` is missing.",
        ),
        _stage_gate(
            "benchmark_evidence_present",
            _gate_status(release_gates, "benchmark_evidence_present"),
            "harness.model-publish-plan/v1",
            "No benchmark evidence is attached to the model release.",
        ),
        _stage_gate(
            "operator_upload_approval",
            operator_upload_approved,
            "operator release decision",
            "Operator upload approval has not been recorded for this staging receipt.",
        ),
    ]
    release_ready = all(gate["passed"] for gate in stage_gates if gate["gate_id"] != "operator_upload_approval")
    if release_ready and operator_upload_approved:
        upload_status = "READY_TO_UPLOAD"
    elif release_ready:
        upload_status = "WAITING_FOR_OPERATOR_UPLOAD_APPROVAL"
    else:
        upload_status = "DO_NOT_UPLOAD"
    return {
        "schema": "harness.huggingface-release-stage.model/v1",
        "model": model,
        "candidate_name": candidate_name,
        "candidate_slug": candidate_slug,
        "repo_id": repo_id,
        "repo_type": "model",
        "private": bool(private),
        "model_root": model_root,
        "publish_status": plan_row.get("publish_status", ""),
        "upload_status": upload_status,
        "release_ready_without_operator_approval": release_ready,
        "stage_gates": stage_gates,
        "trained_artifact_present": trained_artifact_present,
        "release_identity": plan_row.get("release_identity", readiness_row.get("release_identity", {})),
        "blockers": sorted(set(blockers + [gate["blocker"] for gate in stage_gates if gate["blocker"]])),
        "upload_templates": _upload_templates(repo_id, model_root, trained_artifact_present=trained_artifact_present),
    }


def build_stage(
    *,
    readiness: dict[str, Any],
    publish_plan: dict[str, Any],
    readiness_artifact: str,
    publish_plan_artifact: str,
    readiness_loaded: bool,
    publish_plan_loaded: bool,
    readiness_load_error: str,
    publish_plan_load_error: str,
    namespace: str,
    private: bool,
    operator_upload_approved: bool,
) -> dict[str, Any]:
    readiness_rows = _readiness_by_model(readiness)
    plan_models = publish_plan.get("models") if isinstance(publish_plan.get("models"), list) else []
    models = [
        stage_model(
            row,
            readiness_row=readiness_rows.get(_model_key(row), {}),
            namespace=namespace,
            private=private,
            operator_upload_approved=operator_upload_approved,
        )
        for row in plan_models
        if isinstance(row, dict)
    ]
    return {
        "schema": SCHEMA,
        "timestamp_utc": now_utc(),
        "upload_mode": UPLOAD_MODE,
        "publication_policy": (
            "This command never uploads model files. It emits repo IDs, commands, blockers, and release gates. "
            "Actual upload requires complete release evidence plus explicit operator approval."
        ),
        "namespace": namespace,
        "private": bool(private),
        "operator_upload_approved": bool(operator_upload_approved),
        "source_artifacts": {
            "release_readiness": readiness_artifact,
            "publish_plan": publish_plan_artifact,
        },
        "source_loaded": {
            "release_readiness": bool(readiness_loaded),
            "publish_plan": bool(publish_plan_loaded),
        },
        "source_load_errors": {
            "release_readiness": readiness_load_error,
            "publish_plan": publish_plan_load_error,
        },
        "source_references": SOURCE_REFERENCES,
        "models": models,
        "summary": {
            "models": len(models),
            "ready_to_upload_models": sum(1 for row in models if row["upload_status"] == "READY_TO_UPLOAD"),
            "waiting_for_operator_upload_approval": sum(
                1 for row in models if row["upload_status"] == "WAITING_FOR_OPERATOR_UPLOAD_APPROVAL"
            ),
            "do_not_upload_models": sum(1 for row in models if row["upload_status"] == "DO_NOT_UPLOAD"),
            "blockers": sum(len(row["blockers"]) for row in models),
            "repo_ids": [row["repo_id"] for row in models],
            "source_ready": bool(readiness_loaded and publish_plan_loaded),
        },
    }


def render_markdown(stage: dict[str, Any]) -> str:
    summary = stage["summary"]
    lines = [
        "# Hugging Face release staging",
        "",
        f"- Schema: `{stage['schema']}`",
        f"- Upload mode: `{stage['upload_mode']}`",
        f"- Namespace: `{stage['namespace']}`",
        f"- Private repos: `{str(stage['private']).lower()}`",
        f"- Ready to upload: `{summary['ready_to_upload_models']}` / `{summary['models']}`",
        f"- Waiting for operator approval: `{summary['waiting_for_operator_upload_approval']}`",
        f"- Do not upload: `{summary['do_not_upload_models']}`",
        "",
        "## Policy",
        "",
        stage["publication_policy"],
        "",
        "## Models",
        "",
        "| Model | Candidate | Repo ID | Upload status | Blockers |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for row in stage["models"]:
        lines.append(
            f"| {row['model']} | {row['candidate_name']} | `{row['repo_id']}` | "
            f"{row['upload_status']} | {len(row['blockers'])} |"
        )
    lines.extend(["", "## Upload command templates", ""])
    for row in stage["models"]:
        lines.extend([
            f"### {row['candidate_name']}",
            "",
            "CLI:",
            "",
            "```powershell",
            row["upload_templates"]["cli"],
            "```",
            "",
            "Python:",
            "",
            "```python",
            row["upload_templates"]["python"],
            "```",
            "",
        ])
    lines.extend(["## References", ""])
    for ref in stage["source_references"]:
        lines.append(f"- {ref['label']}: {ref['url']}")
    return "\n".join(lines) + "\n"


def write_text(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def store_stage(stage: dict[str, Any], *, store_root: str, run_id: str, artifacts: list[tuple[str, str]]) -> list[dict[str, Any]]:
    if not store_root:
        return []
    store = FileBackedHarnessStore(Path(store_root))
    verdict = "HF_READY_TO_UPLOAD" if stage["summary"]["ready_to_upload_models"] else "HF_UPLOAD_BLOCKED"
    outputs = [store.put_receipt(kind="huggingface_release_stage", body=stage, run_id=run_id, verdict=verdict)]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-readiness-artifact", required=True)
    parser.add_argument("--publish-plan-artifact", required=True)
    parser.add_argument("--namespace", default="zaindanaharper")
    parser.add_argument("--private", action="store_true")
    parser.add_argument("--operator-upload-approved", action="store_true")
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    readiness, readiness_error = _load_json(Path(args.release_readiness_artifact))
    publish_plan, publish_error = _load_json(Path(args.publish_plan_artifact))
    if readiness is None:
        readiness = {"schema": "", "models": []}
    if publish_plan is None:
        publish_plan = {"schema": "", "models": []}
    stage = build_stage(
        readiness=readiness,
        publish_plan=publish_plan,
        readiness_artifact=args.release_readiness_artifact,
        publish_plan_artifact=args.publish_plan_artifact,
        readiness_loaded=not readiness_error,
        publish_plan_loaded=not publish_error,
        readiness_load_error=readiness_error,
        publish_plan_load_error=publish_error,
        namespace=args.namespace,
        private=args.private,
        operator_upload_approved=args.operator_upload_approved,
    )
    json_text = json.dumps(stage, indent=2, sort_keys=True)
    markdown = render_markdown(stage)
    json_path = write_text(args.out, json_text)
    markdown_path = write_text(args.markdown_out, markdown)
    store_outputs = store_stage(
        stage,
        store_root=args.store_root,
        run_id=args.run_id,
        artifacts=[
            (json_path, "huggingface-release-stage-json"),
            (markdown_path, "huggingface-release-stage-markdown"),
        ],
    )
    if store_outputs:
        stage = {**stage, "store_outputs": store_outputs}
        json_text = json.dumps(stage, indent=2, sort_keys=True)
        write_text(args.out, json_text)
    print(json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
