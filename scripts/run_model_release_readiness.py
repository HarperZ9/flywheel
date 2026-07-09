"""Emit static release-readiness receipts for local model publish tracks.

The command records metadata only: model-root existence, top-level weight-file
counts/sizes, release document presence, and benchmark artifact-name matches.
It does not hash large model files, read file bodies, run endpoints, or copy
model weights into the store.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402
from harness.model_profiles import candidate_model_roots, model_key  # noqa: E402


WEIGHT_SUFFIXES = {".gguf", ".safetensors", ".bin", ".pt", ".pth", ".onnx", ".mlmodel"}

GATE_FILES = {
    "identity": [
        "MODEL_CARD.md",
        "README.md",
        "LICENSE",
        "config.json",
    ],
    "tokenizer": [
        "tokenizer.json",
        "tokenizer_config.json",
    ],
    "integrity": [
        "checksums.sha256",
        "provenance.json",
    ],
    "serving": [
        "endpoint.json",
        "usage.md",
    ],
    "evaluation": [
        "benchmark-summary.json",
        "safety.md",
        "release-checklist.md",
    ],
}


def now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def split_names(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def split_paths(value: str) -> list[Path]:
    return [Path(item.strip()) for item in value.split(";") if item.strip()]


def _model_key(model: str) -> str:
    return model_key(model)


def _candidate_roots(model: str, base_root: Path) -> list[Path]:
    return candidate_model_roots(model, base_root)


def _pick_root(model: str, base_root: Path, explicit_root: Path | None) -> tuple[Path, list[str]]:
    if explicit_root is not None:
        return explicit_root, [str(explicit_root)]
    candidates = _candidate_roots(model, base_root)
    for path in candidates:
        if path.exists():
            return path, [str(item) for item in candidates]
    return candidates[0], [str(item) for item in candidates]


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _top_level_files(root: Path, *, max_entries: int) -> list[Path]:
    if not root.exists() or not root.is_dir():
        return []
    try:
        rows = sorted(root.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return []
    return [path for path in rows[:max_entries] if path.is_file()]


def _gate(root: Path, names: list[str]) -> dict[str, Any]:
    present = [name for name in names if (root / name).exists()]
    missing = [name for name in names if name not in present]
    total = len(names)
    return {
        "required": total,
        "present": len(present),
        "missing": len(missing),
        "score": round(len(present) / total, 4) if total else 1.0,
        "present_files": present,
        "missing_files": missing,
    }


def _artifact_matches(model: str, artifact_roots: list[Path], *, max_entries: int) -> list[dict[str, Any]]:
    key = _model_key(model)
    matches: list[dict[str, Any]] = []
    for root in artifact_roots:
        if not root.exists() or not root.is_dir():
            continue
        try:
            entries = sorted(root.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            continue
        for path in entries[:max_entries]:
            if not path.is_file():
                continue
            name_key = _model_key(path.name)
            if key in name_key and any(hint in name_key for hint in ("bench", "score", "eval", "safety", "release")):
                matches.append({
                    "path": str(path),
                    "name": path.name,
                    "suffix": path.suffix.lower(),
                    "size_bytes": _safe_size(path),
                    "content_read": False,
                })
    return matches


def _load_endpoint_profiles(paths: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    profiles: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            errors.append({"path": str(path), "error": "missing_artifact"})
            continue
        except (OSError, json.JSONDecodeError) as exc:
            errors.append({"path": str(path), "error": type(exc).__name__})
            continue
        schema = str(data.get("schema", ""))
        if schema == "harness.model-endpoint-profiles/v1":
            rows = data.get("profiles", [])
            if isinstance(rows, list):
                profiles.extend(row for row in rows if isinstance(row, dict))
        elif schema == "harness.model-endpoint-profile/v1":
            profiles.append(data)
    return profiles, errors


def _endpoint_profiles_for_model(model: str, profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    key = _model_key(model)
    rows = []
    for profile in profiles:
        if str(profile.get("model_key", "")) == key or _model_key(str(profile.get("model", ""))) == key:
            rows.append({
                "profile_id": profile.get("profile_id", ""),
                "backend": profile.get("backend", ""),
                "provider_role": profile.get("provider_role", ""),
                "endpoint_url": profile.get("endpoint_url", ""),
                "agentic_backend": profile.get("agentic_backend", ""),
                "root_exists": bool(profile.get("root_exists")),
                "live_probed": bool(profile.get("live_probed")),
                "content_read": bool(profile.get("content_read", False)),
            })
    return rows


def _load_endpoint_gate_rows(paths: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            errors.append({"path": str(path), "error": "missing_artifact"})
            continue
        except (OSError, json.JSONDecodeError) as exc:
            errors.append({"path": str(path), "error": type(exc).__name__})
            continue
        if str(data.get("schema", "")) == "harness.model-endpoint-gate/v1":
            payload_rows = data.get("rows") if isinstance(data.get("rows"), list) else []
            rows.extend(row for row in payload_rows if isinstance(row, dict))
    return rows, errors


def _endpoint_gate_rows_for_model(model: str, gate_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    key = _model_key(model)
    rows = []
    for row in gate_rows:
        if str(row.get("model_key", "")) == key or _model_key(str(row.get("model", ""))) == key:
            rows.append({
                "profile_id": row.get("profile_id", ""),
                "backend": row.get("backend", ""),
                "provider_role": row.get("provider_role", ""),
                "health_ok": bool(row.get("health_ok")),
                "generation_ok": bool(row.get("generation_ok")),
                "failure_class": row.get("failure_class", ""),
                "quality_score": row.get("quality_score", 0.0),
                "receipt_hash": row.get("receipt_hash", ""),
            })
    return rows


def _verdict(
    *,
    root_exists: bool,
    weight_count: int,
    gates: dict[str, dict[str, Any]],
    benchmark_artifacts: list[dict[str, Any]],
    endpoint_profile_count: int,
    endpoint_gate_generation_ok_count: int,
) -> str:
    if not root_exists:
        return "MODEL_RELEASE_MISSING"
    if weight_count <= 0:
        return "MODEL_ROOT_WITHOUT_WEIGHTS"
    all_docs_ready = all(float(gate["score"]) >= 1.0 for gate in gates.values())
    if all_docs_ready and benchmark_artifacts and endpoint_profile_count > 0 and endpoint_gate_generation_ok_count > 0:
        return "MODEL_RELEASE_READY_STATIC"
    return "MODEL_ARTIFACTS_WITH_RELEASE_GAPS"


def profile_model(
    model: str,
    *,
    base_root: Path,
    explicit_root: Path | None,
    artifact_roots: list[Path],
    max_entries: int,
    endpoint_profiles: list[dict[str, Any]] | None = None,
    endpoint_gate_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    root, candidates = _pick_root(model, base_root, explicit_root)
    root_exists = root.exists()
    files = _top_level_files(root, max_entries=max_entries)
    weight_files = [
        {
            "name": path.name,
            "suffix": path.suffix.lower(),
            "size_bytes": _safe_size(path),
            "content_read": False,
        }
        for path in files
        if path.suffix.lower() in WEIGHT_SUFFIXES
    ]
    gates = {
        name: _gate(root, required)
        if root_exists
        else {
            "required": len(required),
            "present": 0,
            "missing": len(required),
            "score": 0.0,
            "present_files": [],
            "missing_files": required,
        }
        for name, required in GATE_FILES.items()
    }
    artifacts = _artifact_matches(model, artifact_roots, max_entries=max_entries)
    endpoint_rows = _endpoint_profiles_for_model(model, endpoint_profiles or [])
    gate_rows = _endpoint_gate_rows_for_model(model, endpoint_gate_rows or [])
    gate_generation_ok = sum(1 for row in gate_rows if row.get("generation_ok"))
    verdict = _verdict(
        root_exists=root_exists,
        weight_count=len(weight_files),
        gates=gates,
        benchmark_artifacts=artifacts,
        endpoint_profile_count=len(endpoint_rows),
        endpoint_gate_generation_ok_count=gate_generation_ok,
    )
    required_total = sum(gate["required"] for gate in gates.values())
    present_total = sum(gate["present"] for gate in gates.values())
    return {
        "schema": "harness.model-release-readiness.model/v1",
        "model": model,
        "model_key": _model_key(model),
        "root": str(root),
        "candidate_roots": candidates,
        "root_exists": root_exists,
        "content_read": False,
        "weight_file_count": len(weight_files),
        "weight_total_size_bytes": sum(int(row["size_bytes"]) for row in weight_files),
        "weight_files": weight_files,
        "gates": gates,
        "endpoint_profiles": endpoint_rows,
        "endpoint_profile_count": len(endpoint_rows),
        "endpoint_gate_rows": gate_rows,
        "endpoint_gate_row_count": len(gate_rows),
        "endpoint_gate_generation_ok_count": gate_generation_ok,
        "benchmark_artifacts": artifacts,
        "required_total": required_total,
        "present_total": present_total,
        "release_doc_score": round(present_total / required_total, 4) if required_total else 1.0,
        "benchmark_artifact_count": len(artifacts),
        "enterprise_release_ready": verdict == "MODEL_RELEASE_READY_STATIC",
        "verdict": verdict,
    }


def build_report(
    *,
    models: list[str],
    base_root: Path,
    explicit_roots: dict[str, Path],
    artifact_roots: list[Path],
    max_entries: int,
    endpoint_profile_artifacts: list[Path] | None = None,
    endpoint_gate_artifacts: list[Path] | None = None,
) -> dict[str, Any]:
    endpoint_profiles, endpoint_profile_load_errors = _load_endpoint_profiles(endpoint_profile_artifacts or [])
    endpoint_gate_rows, endpoint_gate_load_errors = _load_endpoint_gate_rows(endpoint_gate_artifacts or [])
    rows = [
        profile_model(
            model,
            base_root=base_root,
            explicit_root=explicit_roots.get(model),
            artifact_roots=artifact_roots,
            endpoint_profiles=endpoint_profiles,
            endpoint_gate_rows=endpoint_gate_rows,
            max_entries=max_entries,
        )
        for model in models
    ]
    verdict_counts: dict[str, int] = {}
    for row in rows:
        verdict = str(row["verdict"])
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
    return {
        "schema": "harness.model-release-readiness/v1",
        "timestamp_utc": now_utc(),
        "secret_policy": "metadata-only; model file bodies are not read; large model files are not hashed or copied",
        "base_root": str(base_root),
        "artifact_roots": [str(path) for path in artifact_roots],
        "endpoint_profile_artifacts": [str(path) for path in endpoint_profile_artifacts or []],
        "endpoint_profile_load_errors": endpoint_profile_load_errors,
        "endpoint_gate_artifacts": [str(path) for path in endpoint_gate_artifacts or []],
        "endpoint_gate_load_errors": endpoint_gate_load_errors,
        "models": rows,
        "summary": {
            "models": len(rows),
            "existing_models": sum(1 for row in rows if row["root_exists"]),
            "missing_models": sum(1 for row in rows if not row["root_exists"]),
            "models_with_weights": sum(1 for row in rows if row["weight_file_count"] > 0),
            "release_ready_models": sum(1 for row in rows if row["enterprise_release_ready"]),
            "endpoint_profile_matches": sum(int(row["endpoint_profile_count"]) for row in rows),
            "endpoint_gate_rows": sum(int(row["endpoint_gate_row_count"]) for row in rows),
            "endpoint_gate_generation_ok": sum(int(row["endpoint_gate_generation_ok_count"]) for row in rows),
            "benchmark_artifact_matches": sum(int(row["benchmark_artifact_count"]) for row in rows),
            "verdict_counts": verdict_counts,
            "mean_release_doc_score": round(sum(float(row["release_doc_score"]) for row in rows) / len(rows), 4) if rows else 0.0,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Model release readiness receipt",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Timestamp UTC: `{report['timestamp_utc']}`",
        f"- Secret policy: {report['secret_policy']}",
        f"- Existing models: `{summary['existing_models']}` / `{summary['models']}`",
        f"- Models with weights: `{summary['models_with_weights']}`",
        f"- Release-ready static models: `{summary['release_ready_models']}`",
        f"- Endpoint profile matches: `{summary['endpoint_profile_matches']}`",
        f"- Endpoint gate rows: `{summary['endpoint_gate_rows']}`",
        f"- Endpoint gate generation OK: `{summary['endpoint_gate_generation_ok']}`",
        f"- Benchmark artifact matches: `{summary['benchmark_artifact_matches']}`",
        "",
        "| Model | Verdict | Root exists | Weights | Doc score | Endpoint profiles | Endpoint gate OK | Benchmark artifacts |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["models"]:
        lines.append(
            "| {model} | {verdict} | {exists} | {weights} | {score} | {endpoints} | {gate_ok} | {artifacts} |".format(
                model=row["model"],
                verdict=row["verdict"],
                exists=str(row["root_exists"]).lower(),
                weights=row["weight_file_count"],
                score=row["release_doc_score"],
                endpoints=row["endpoint_profile_count"],
                gate_ok=row["endpoint_gate_generation_ok_count"],
                artifacts=row["benchmark_artifact_count"],
            )
        )
    return "\n".join(lines) + "\n"


def _write(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def _parse_roots(values: list[str]) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"--model-root expects name=path, got {value!r}")
        name, path = value.split("=", 1)
        roots[name.strip()] = Path(path.strip())
    return roots


def _store_outputs(report: dict[str, Any], *, store_root: str, run_id: str, artifacts: list[tuple[str, str]]) -> list[dict[str, Any]]:
    if not store_root:
        return []
    store = FileBackedHarnessStore(Path(store_root))
    outputs = [
        store.put_receipt(
            kind="model_release_readiness",
            body=report,
            run_id=run_id,
            verdict="MODEL_RELEASE_READY"
            if report["summary"]["release_ready_models"] == report["summary"]["models"]
            else "MODEL_RELEASE_PARTIAL",
        )
    ]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default="14B,32B")
    parser.add_argument("--base-root", default="E:/local-model-run")
    parser.add_argument("--artifact-roots", default="C:/dev/local-model/artifacts;C:/tmp")
    parser.add_argument("--endpoint-profile-artifacts", default="")
    parser.add_argument("--endpoint-gate-artifacts", default="")
    parser.add_argument("--model-root", action="append", default=[], help="override a model root as name=path")
    parser.add_argument("--max-entries", type=int, default=200)
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    report = build_report(
        models=split_names(args.models),
        base_root=Path(args.base_root),
        explicit_roots=_parse_roots(args.model_root),
        artifact_roots=split_paths(args.artifact_roots),
        endpoint_profile_artifacts=split_paths(args.endpoint_profile_artifacts),
        endpoint_gate_artifacts=split_paths(args.endpoint_gate_artifacts),
        max_entries=args.max_entries,
    )
    json_text = json.dumps(report, indent=2, sort_keys=True)
    md_text = render_markdown(report)
    json_path = _write(args.out, json_text)
    md_path = _write(args.markdown_out, md_text)
    store_outputs = _store_outputs(
        report,
        store_root=args.store_root,
        run_id=args.run_id,
        artifacts=[
            (json_path, "model-release-readiness-json"),
            (md_path, "model-release-readiness-markdown"),
        ],
    )
    if store_outputs:
        report = {**report, "store_outputs": store_outputs}
        json_text = json.dumps(report, indent=2, sort_keys=True)
    print(json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
