"""Stage Hugging Face model repository metadata without copying model weights."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402


SCHEMA = "harness.model-repo-stage/v1"
MODEL_SCHEMA = "harness.model-repo-stage.model/v1"
REQUIRED_REPO_FILES = [
    "README.md",
    "MODEL_CARD.md",
    "LICENSE",
    "checksums.sha256",
    "provenance.json",
    "endpoint.json",
    "usage.md",
    "benchmark-summary.json",
    "safety.md",
    "release-checklist.md",
]
DOC_SOURCE_MAP = {
    "README.md": "README.md",
    "MODEL_CARD.md": "MODEL_CARD.md",
    "usage.md": "USAGE.md",
    "safety.md": "SAFETY-ACCOUNTABILITY.md",
    "release-checklist.md": "RELEASE-CHECKLIST.md",
}


def now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except FileNotFoundError:
        return None, "missing_artifact"
    except (OSError, json.JSONDecodeError) as exc:
        return None, type(exc).__name__


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _copy_text(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _readiness_by_model(readiness: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = readiness.get("models") if isinstance(readiness.get("models"), list) else []
    return {
        str(row.get("model", "")).upper(): row
        for row in rows
        if isinstance(row, dict) and row.get("model")
    }


def _safe_slug(row: dict[str, Any]) -> str:
    slug = str(row.get("candidate_slug", "")).strip().lower()
    if slug:
        return slug
    return str(row.get("candidate_name", row.get("model", "model"))).strip().lower().replace(" ", "-")


def _copy_docs(*, model: str, docs_root: Path, stage_root: Path) -> list[dict[str, Any]]:
    copied = []
    model_docs = docs_root / model
    for target, source_name in DOC_SOURCE_MAP.items():
        src = model_docs / source_name
        dst = stage_root / target
        ok = _copy_text(src, dst)
        copied.append({
            "target": target,
            "source": str(src),
            "source_exists": src.exists(),
            "written": ok,
        })
    return copied


def _copy_license(*, model_root: Path, stage_root: Path) -> dict[str, Any]:
    src = model_root / "LICENSE"
    dst = stage_root / "LICENSE"
    if _copy_text(src, dst):
        return {"target": "LICENSE", "source": str(src), "source_exists": True, "written": True}
    _write(
        dst,
        "\n".join([
            "License pending",
            "",
            "The source model root did not contain a LICENSE file when this repository stage was generated.",
            "Do not publish this model until license provenance is verified and this file is replaced.",
            "",
        ]),
    )
    return {"target": "LICENSE", "source": str(src), "source_exists": False, "written": True}


def _endpoint_payload(model: str, readiness_row: dict[str, Any], publish_row: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "harness.model-repo-stage.endpoint/v1",
        "model": model,
        "candidate_name": publish_row.get("candidate_name", ""),
        "generated_utc": now_utc(),
        "endpoint_profiles": readiness_row.get("endpoint_profiles", []),
        "endpoint_gate_rows": readiness_row.get("endpoint_gate_rows", []),
        "endpoint_gate_generation_ok_count": readiness_row.get("endpoint_gate_generation_ok_count", 0),
        "publication_note": "Endpoint profiles are local defaults. Public upload remains blocked until endpoint generation gates pass.",
    }


def _provenance_payload(model: str, readiness_row: dict[str, Any], publish_row: dict[str, Any], repo_id: str) -> dict[str, Any]:
    return {
        "schema": "harness.model-repo-stage.provenance/v1",
        "model": model,
        "candidate_name": publish_row.get("candidate_name", ""),
        "candidate_slug": publish_row.get("candidate_slug", ""),
        "repo_id": repo_id,
        "generated_utc": now_utc(),
        "source_model_root": readiness_row.get("root", publish_row.get("root", "")),
        "source_verdict": publish_row.get("source_verdict", ""),
        "weight_file_count": readiness_row.get("weight_file_count", 0),
        "weight_total_size_bytes": readiness_row.get("weight_total_size_bytes", 0),
        "weight_files": readiness_row.get("weight_files", []),
        "content_policy": "Model weight bodies were not read, copied, or hashed by this metadata staging command.",
        "publish_policy": "Do not publish until benchmark, endpoint, checksum, provenance, and operator approval gates pass.",
    }


def _benchmark_payload(model: str, readiness_row: dict[str, Any], publish_row: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "harness.model-repo-stage.benchmark-summary/v1",
        "model": model,
        "candidate_name": publish_row.get("candidate_name", ""),
        "generated_utc": now_utc(),
        "benchmark_artifact_count": readiness_row.get("benchmark_artifact_count", 0),
        "benchmark_artifacts": readiness_row.get("benchmark_artifacts", []),
        "status": "PENDING_BENCHMARK_EVIDENCE"
        if int(readiness_row.get("benchmark_artifact_count", 0) or 0) == 0
        else "BENCHMARK_EVIDENCE_ATTACHED",
        "note": "Benchmark execution is intentionally separate from repository staging.",
    }


def _write_generated_files(*, model: str, stage_root: Path, readiness_row: dict[str, Any], publish_row: dict[str, Any], repo_id: str) -> list[str]:
    generated = []
    payloads = {
        "endpoint.json": _endpoint_payload(model, readiness_row, publish_row),
        "provenance.json": _provenance_payload(model, readiness_row, publish_row, repo_id),
        "benchmark-summary.json": _benchmark_payload(model, readiness_row, publish_row),
    }
    for name, payload in payloads.items():
        _write(stage_root / name, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        generated.append(name)
    _write(
        stage_root / "WEIGHT-CHECKSUMS-PENDING.md",
        "\n".join([
            "# Weight checksums pending",
            "",
            "This repository stage does not hash or copy model weights.",
            "Generate final weight checksums from the release machine before public upload.",
            "",
        ]),
    )
    generated.append("WEIGHT-CHECKSUMS-PENDING.md")
    return generated


def _write_checksums(stage_root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(stage_root.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file() or path.name == "checksums.sha256":
            continue
        rows.append({
            "relative_path": path.name,
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        })
    text = "\n".join(f"{row['sha256']}  {row['relative_path']}" for row in rows) + "\n"
    _write(stage_root / "checksums.sha256", text)
    rows.append({
        "relative_path": "checksums.sha256",
        "bytes": (stage_root / "checksums.sha256").stat().st_size,
        "sha256": _sha256(stage_root / "checksums.sha256"),
    })
    return rows


def stage_model(
    publish_row: dict[str, Any],
    *,
    readiness_row: dict[str, Any],
    docs_root: Path,
    stage_base: Path,
    namespace: str,
    sync_to_model_root: bool,
) -> dict[str, Any]:
    model = str(publish_row.get("model") or readiness_row.get("model") or "")
    slug = _safe_slug(publish_row)
    repo_id = f"{namespace.rstrip('/')}/{slug}"
    stage_root = stage_base / slug
    if stage_root.exists():
        shutil.rmtree(stage_root)
    stage_root.mkdir(parents=True, exist_ok=True)
    docs = _copy_docs(model=model, docs_root=docs_root, stage_root=stage_root)
    license_row = _copy_license(model_root=Path(str(readiness_row.get("root", publish_row.get("root", "")))), stage_root=stage_root)
    generated = _write_generated_files(
        model=model,
        stage_root=stage_root,
        readiness_row=readiness_row,
        publish_row=publish_row,
        repo_id=repo_id,
    )
    checksums = _write_checksums(stage_root)
    present = [name for name in REQUIRED_REPO_FILES if (stage_root / name).exists()]
    missing = [name for name in REQUIRED_REPO_FILES if name not in present]
    sync_targets: list[str] = []
    if sync_to_model_root:
        model_root = Path(str(readiness_row.get("root", publish_row.get("root", ""))))
        if model_root.exists():
            for name in REQUIRED_REPO_FILES:
                shutil.copy2(stage_root / name, model_root / name)
                sync_targets.append(str(model_root / name))
    upload_ready = not missing and publish_row.get("publish_status") == "READY_TO_STAGE"
    return {
        "schema": MODEL_SCHEMA,
        "model": model,
        "candidate_name": publish_row.get("candidate_name", ""),
        "candidate_slug": slug,
        "repo_id": repo_id,
        "stage_root": str(stage_root),
        "source_model_root": readiness_row.get("root", publish_row.get("root", "")),
        "required_files": REQUIRED_REPO_FILES,
        "required_files_present": len(present),
        "required_files_missing": missing,
        "doc_copies": docs + [license_row],
        "generated_files": generated,
        "checksums": checksums,
        "sync_to_model_root": bool(sync_to_model_root),
        "sync_targets": sync_targets,
        "upload_status": "READY_TO_UPLOAD_AFTER_OPERATOR_APPROVAL" if upload_ready else "DO_NOT_UPLOAD",
        "remaining_blockers": list(publish_row.get("blockers", [])),
    }


def build_stage(
    *,
    readiness: dict[str, Any],
    publish_plan: dict[str, Any],
    readiness_artifact: str,
    publish_plan_artifact: str,
    docs_root: Path,
    stage_root: Path,
    namespace: str,
    sync_to_model_root: bool,
) -> dict[str, Any]:
    readiness_rows = _readiness_by_model(readiness)
    publish_rows = publish_plan.get("models") if isinstance(publish_plan.get("models"), list) else []
    models = [
        stage_model(
            row,
            readiness_row=readiness_rows.get(str(row.get("model", "")).upper(), {}),
            docs_root=docs_root,
            stage_base=stage_root,
            namespace=namespace,
            sync_to_model_root=sync_to_model_root,
        )
        for row in publish_rows
        if isinstance(row, dict)
    ]
    return {
        "schema": SCHEMA,
        "timestamp_utc": now_utc(),
        "source_artifacts": {
            "release_readiness": readiness_artifact,
            "publish_plan": publish_plan_artifact,
        },
        "docs_root": str(docs_root),
        "stage_root": str(stage_root),
        "namespace": namespace,
        "secret_policy": "metadata-only; model weight bodies are not read, copied, hashed, or bundled",
        "sync_to_model_root": bool(sync_to_model_root),
        "models": models,
        "summary": {
            "models": len(models),
            "required_files": len(REQUIRED_REPO_FILES) * len(models),
            "required_files_present": sum(int(row["required_files_present"]) for row in models),
            "required_files_missing": sum(len(row["required_files_missing"]) for row in models),
            "synced_files": sum(len(row["sync_targets"]) for row in models),
            "ready_to_upload_after_operator_approval": sum(
                1 for row in models if row["upload_status"] == "READY_TO_UPLOAD_AFTER_OPERATOR_APPROVAL"
            ),
            "do_not_upload_models": sum(1 for row in models if row["upload_status"] == "DO_NOT_UPLOAD"),
            "repo_ids": [row["repo_id"] for row in models],
        },
    }


def render_markdown(stage: dict[str, Any]) -> str:
    summary = stage["summary"]
    lines = [
        "# Model repository staging",
        "",
        f"- Schema: `{stage['schema']}`",
        f"- Stage root: `{stage['stage_root']}`",
        f"- Namespace: `{stage['namespace']}`",
        f"- Secret policy: {stage['secret_policy']}",
        f"- Required files present: `{summary['required_files_present']}` / `{summary['required_files']}`",
        f"- Synced to model roots: `{summary['synced_files']}` files",
        f"- Ready to upload after operator approval: `{summary['ready_to_upload_after_operator_approval']}`",
        f"- Do not upload: `{summary['do_not_upload_models']}`",
        "",
        "| Model | Repo ID | Stage root | Required files | Upload status |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for row in stage["models"]:
        lines.append(
            f"| {row['model']} | `{row['repo_id']}` | `{row['stage_root']}` | "
            f"{row['required_files_present']}/{len(row['required_files'])} | {row['upload_status']} |"
        )
    lines.extend([
        "",
        "The staged folders contain publication metadata and documentation only. Model weights remain in the local model root and are not copied into the package.",
    ])
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
    verdict = "MODEL_REPO_STAGE_COMPLETE" if stage["summary"]["required_files_missing"] == 0 else "MODEL_REPO_STAGE_PARTIAL"
    outputs = [store.put_receipt(kind="model_repo_stage", body=stage, run_id=run_id, verdict=verdict)]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-readiness-artifact", required=True)
    parser.add_argument("--publish-plan-artifact", required=True)
    parser.add_argument("--docs-root", default="C:/dev/local-model/project-docs/releases")
    parser.add_argument("--stage-root", default="C:/dev/local-model/artifacts/exe/model_repositories")
    parser.add_argument("--namespace", default="HarperZ9")
    parser.add_argument("--sync-to-model-root", action="store_true")
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
        docs_root=Path(args.docs_root),
        stage_root=Path(args.stage_root),
        namespace=args.namespace,
        sync_to_model_root=args.sync_to_model_root,
    )
    stage["source_load_errors"] = {
        "release_readiness": readiness_error,
        "publish_plan": publish_error,
    }
    json_text = json.dumps(stage, indent=2, sort_keys=True)
    markdown = render_markdown(stage)
    json_path = write_text(args.out, json_text)
    markdown_path = write_text(args.markdown_out, markdown)
    store_outputs = store_stage(
        stage,
        store_root=args.store_root,
        run_id=args.run_id,
        artifacts=[
            (json_path, "model-repo-stage-json"),
            (markdown_path, "model-repo-stage-markdown"),
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
