"""Emit a metadata-only release doctor for a packaged local harness bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore

SCHEMA = "harness.package-ship-doctor/v1"
DEFAULT_SUMMARY = Path("C:/dev/local-model/artifacts/exe/packages/local-harness-dev-local.package.json")
REQUIRED_BUNDLE_FILES = [
    "README.md",
    "bin/local-harness.exe",
    "bin/local-harness.cmd",
    "bin/local-agent.exe",
    "config/model_endpoint_profiles.local.json",
    "config/model_endpoint_profiles.local.md",
    "config/model_release_readiness.local.json",
    "docs/model_release_readiness.local.md",
    "config/model_publish_plan.local.json",
    "docs/model_publish_plan.local.md",
    "config/tool_integration_contract.local.json",
    "config/tool_integration_contract.local.md",
    "config/tool_readiness.local.json",
    "docs/tool_readiness.local.md",
    "config/tool_hardening_plan.local.json",
    "docs/tool_hardening_plan.local.md",
    "config/runtime_activation_contract.local.json",
    "config/runtime_activation_contract.local.md",
    "config/codex_mcp_launch_contract.local.json",
    "config/codex_mcp_launch_contract.local.md",
    "config/context_inventory.local.json",
    "docs/context_inventory.local.md",
    "config/pubscan_resource_profiles.local.json",
    "docs/pubscan_resource_profiles.local.md",
    "config/harness_architecture_report.local.json",
    "config/enterprise_readiness_report.local.json",
    "docs/harness_architecture_report.local.md",
    "docs/enterprise_readiness_report.local.md",
    "docs/records/ROADMAP-STATUS-2026-07-09.md",
    "docs/records/CAPABILITY-CATALOG-2026-07-09.md",
    "docs/records/OBJECTIVE-EVIDENCE-MATRIX-2026-07-09.md",
    "docs/records/OBJECTIVE-EVIDENCE-MATRIX-2026-07-09.json",
    "docs/records/NEXT-RECURSIVE-IMPROVEMENT-LOOP-2026-07-09.md",
    "manifest/harness_executable_manifest.local.json",
    "manifest/harness_executable_manifest.local.md",
    "docs/HARNESS-PACKAGING.md",
    "manifest/local-harness-release.json",
]
FORBIDDEN_NAME_PATTERNS = [
    re.compile(r"(^|/)\.env($|\.)", re.IGNORECASE),
    re.compile(r"(^|/)(id_rsa|id_dsa|id_ecdsa|id_ed25519)$", re.IGNORECASE),
    re.compile(r"\.(pem|p12|pfx|key)$", re.IGNORECASE),
]
SECRET_TEXT_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}", re.IGNORECASE),
    re.compile(r"gh[pousr]_[0-9A-Za-z_]{36,}", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
TEXT_SCAN_LIMIT_BYTES = 1_000_000


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _file_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return list(summary.get("files") or []) + list(summary.get("included_integrity_files") or [])


def _find_file(summary: dict[str, Any], relative_path: str) -> dict[str, Any] | None:
    for row in _file_rows(summary):
        if row.get("relative_path") == relative_path:
            return row
    return None


def _load_bundled_json(summary: dict[str, Any], relative_path: str) -> dict[str, Any] | None:
    row = _find_file(summary, relative_path)
    if not row:
        return None
    path = Path(str(row.get("path", "")))
    if not path.exists():
        return None
    return _load_json(path)


def _check_required_files(summary: dict[str, Any]) -> dict[str, Any]:
    rows = {str(row.get("relative_path")): row for row in _file_rows(summary)}
    missing = [item for item in REQUIRED_BUNDLE_FILES if item not in rows]
    missing_on_disk = [rel for rel, row in rows.items() if not Path(str(row.get("path", ""))).exists()]
    return {
        "schema": "harness.package-ship-doctor.required-files/v1",
        "required": len(REQUIRED_BUNDLE_FILES),
        "missing": missing,
        "missing_count": len(missing),
        "missing_on_disk": missing_on_disk,
        "missing_on_disk_count": len(missing_on_disk),
        "verdict": "PASS" if not missing and not missing_on_disk else "FAIL",
    }


def _check_zip(summary: dict[str, Any]) -> dict[str, Any]:
    zip_info = summary.get("zip") or {}
    path = Path(str(zip_info.get("path", "")))
    expected = str(zip_info.get("sha256", ""))
    actual = _sha256(path) if path.exists() else ""
    return {
        "schema": "harness.package-ship-doctor.zip/v1",
        "path": str(path),
        "exists": path.exists(),
        "expected_sha256": expected,
        "actual_sha256": actual,
        "matches_summary": bool(expected and actual and expected == actual),
        "verdict": "PASS" if expected and actual == expected else "FAIL",
    }


def _check_forbidden_names(summary: dict[str, Any]) -> dict[str, Any]:
    matches = []
    for row in _file_rows(summary):
        rel = str(row.get("relative_path", ""))
        if any(pattern.search(rel) for pattern in FORBIDDEN_NAME_PATTERNS):
            matches.append(rel)
    return {
        "schema": "harness.package-ship-doctor.forbidden-names/v1",
        "matches": matches,
        "match_count": len(matches),
        "verdict": "PASS" if not matches else "FAIL",
    }


def _check_text_secrets(summary: dict[str, Any]) -> dict[str, Any]:
    matches = []
    skipped = []
    for row in _file_rows(summary):
        rel = str(row.get("relative_path", ""))
        path = Path(str(row.get("path", "")))
        suffix = path.suffix.lower()
        if suffix not in {".json", ".md", ".txt", ".cmd"}:
            continue
        if not path.exists() or path.stat().st_size > TEXT_SCAN_LIMIT_BYTES:
            skipped.append(rel)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(text) for pattern in SECRET_TEXT_PATTERNS):
            matches.append(rel)
    return {
        "schema": "harness.package-ship-doctor.secret-scan/v1",
        "scanned_text_files": len([row for row in _file_rows(summary) if Path(str(row.get("path", ""))).suffix.lower() in {".json", ".md", ".txt", ".cmd"}]),
        "skipped": skipped,
        "matches": matches,
        "match_count": len(matches),
        "verdict": "PASS" if not matches else "FAIL",
    }


def _check_contract_schemas(summary: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "config/model_endpoint_profiles.local.json": "harness.model-endpoint-profiles/v1",
        "config/model_release_readiness.local.json": "harness.model-release-readiness/v1",
        "config/model_publish_plan.local.json": "harness.model-publish-plan/v1",
        "config/tool_integration_contract.local.json": "harness.tool-integration-contract/v1",
        "config/tool_readiness.local.json": "harness.tool-readiness/v1",
        "config/tool_hardening_plan.local.json": "harness.tool-hardening-plan/v1",
        "config/runtime_activation_contract.local.json": "harness.runtime-activation-contract/v1",
        "config/codex_mcp_launch_contract.local.json": "harness.codex-mcp-launch-contract/v1",
        "config/context_inventory.local.json": "harness.context-inventory/v1",
        "config/pubscan_resource_profiles.local.json": "harness.pubscan-resource-profiles/v1",
        "config/harness_architecture_report.local.json": "harness.architecture-report/v1",
        "config/enterprise_readiness_report.local.json": "harness.enterprise-readiness-report/v1",
        "manifest/harness_executable_manifest.local.json": "harness.executable-manifest/v1",
    }
    rows = []
    for rel, schema in expected.items():
        payload = _load_bundled_json(summary, rel)
        observed = payload.get("schema") if isinstance(payload, dict) else None
        rows.append({
            "relative_path": rel,
            "expected_schema": schema,
            "observed_schema": observed,
            "verdict": "PASS" if observed == schema else "FAIL",
        })
    return {
        "schema": "harness.package-ship-doctor.contract-schemas/v1",
        "checks": rows,
        "verdict": "PASS" if all(row["verdict"] == "PASS" for row in rows) else "FAIL",
    }


def _check_model_profiles(summary: dict[str, Any]) -> dict[str, Any]:
    payload = _load_bundled_json(summary, "config/model_endpoint_profiles.local.json") or {}
    profiles = payload.get("profiles") or []
    models = {str(row.get("model")) for row in profiles if isinstance(row, dict)}
    backends = {str(row.get("backend")) for row in profiles if isinstance(row, dict)}
    required_models = {"14B", "32B"}
    required_backends = {"serve", "ollama"}
    return {
        "schema": "harness.package-ship-doctor.model-profiles/v1",
        "profile_count": len(profiles),
        "models": sorted(models),
        "backends": sorted(backends),
        "missing_models": sorted(required_models - models),
        "missing_backends": sorted(required_backends - backends),
        "verdict": "PASS" if required_models <= models and required_backends <= backends else "FAIL",
    }


def _check_source_commit(summary: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    expected = str(summary.get("source_commit", ""))
    git_head = repo_root / ".git" / "HEAD"
    observed = ""
    if git_head.exists():
        head = git_head.read_text(encoding="utf-8", errors="replace").strip()
        if head.startswith("ref:"):
            ref = repo_root / ".git" / head.split(" ", 1)[1]
            if ref.exists():
                observed = ref.read_text(encoding="utf-8", errors="replace").strip()
        else:
            observed = head
    return {
        "schema": "harness.package-ship-doctor.source-commit/v1",
        "expected_source_commit": expected,
        "observed_head": observed,
        "matches_head": bool(expected and observed and expected == observed),
        "verdict": "PASS" if expected and observed == expected else "WARN",
    }


def build_doctor(*, package_summary: Path, repo_root: Path) -> dict[str, Any]:
    summary = _load_json(package_summary)
    checks = [
        _check_required_files(summary),
        _check_zip(summary),
        _check_forbidden_names(summary),
        _check_text_secrets(summary),
        _check_contract_schemas(summary),
        _check_model_profiles(summary),
        _check_source_commit(summary, repo_root),
    ]
    hard_failures = [check for check in checks if check["verdict"] == "FAIL"]
    warnings = [check for check in checks if check["verdict"] == "WARN"]
    verdict = "SHIP_READY" if not hard_failures else "BLOCKED"
    if verdict == "SHIP_READY" and warnings:
        verdict = "SHIP_READY_WITH_WARNINGS"
    return {
        "schema": SCHEMA,
        "created_utc": _now(),
        "package_summary": str(package_summary),
        "package_name": summary.get("package_name"),
        "repo_root": str(repo_root),
        "dependency_posture": "metadata-only package doctor; reads package summary and bundled metadata files but does not run benchmarks or endpoint probes",
        "secret_policy": "scans bundled text metadata for common token/private-key patterns; does not read env files, token stores, model weights, or caches",
        "checks": checks,
        "summary": {
            "verdict": verdict,
            "checks": len(checks),
            "hard_failures": len(hard_failures),
            "warnings": len(warnings),
            "required_bundle_files": len(REQUIRED_BUNDLE_FILES),
        },
    }


def render_markdown(doctor: dict[str, Any]) -> str:
    lines = [
        "# Package ship doctor",
        "",
        f"Schema: `{doctor['schema']}`",
        f"Package: `{doctor.get('package_name')}`",
        f"Verdict: **{doctor['summary']['verdict']}**",
        "",
        "| Check | Verdict |",
        "| --- | --- |",
    ]
    for check in doctor["checks"]:
        lines.append(f"| `{check['schema']}` | {check['verdict']} |")
    lines.extend([
        "",
        "This doctor is metadata-only. It does not run benchmarks, call providers, probe endpoints, or inspect model weights.",
    ])
    return "\n".join(lines) + "\n"


def _write(path_text: str, text: str) -> None:
    if not path_text:
        return
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _store_outputs(store_root: Path, doctor: dict[str, Any], markdown: str, run_id: str) -> dict[str, str]:
    if not run_id:
        return {}
    store = FileBackedHarnessStore(store_root)
    json_record = store.write_json(run_id, "package_ship_doctor", doctor)
    markdown_record = store.write_text(run_id, "package_ship_doctor_md", markdown)
    return {"json": str(json_record.path), "markdown": str(markdown_record.path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--repo-root", default="C:/dev/local-model")
    parser.add_argument("--store-root", default="C:/tmp/harness_file_store")
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--strict-exit", action="store_true")
    args = parser.parse_args(argv)

    doctor = build_doctor(package_summary=Path(args.package_summary), repo_root=Path(args.repo_root))
    markdown = render_markdown(doctor)
    _write(args.out, json.dumps(doctor, indent=2, sort_keys=True))
    _write(args.markdown_out, markdown)
    store_outputs = _store_outputs(Path(args.store_root), doctor, markdown, args.run_id)
    result = {**doctor["summary"], "schema": doctor["schema"]}
    if store_outputs:
        result["store_outputs"] = store_outputs
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.strict_exit and doctor["summary"]["hard_failures"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
