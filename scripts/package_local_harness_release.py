#!/usr/bin/env python3
"""Assemble a shippable local harness release bundle from built artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIST = ROOT / "artifacts" / "exe"
DEFAULT_PACKAGES = DEFAULT_DIST / "packages"
DOCUMENTATION_RECORDS = [
    "ROADMAP-STATUS-2026-07-09.md",
    "CAPABILITY-CATALOG-2026-07-09.md",
    "OBJECTIVE-EVIDENCE-MATRIX-2026-07-09.md",
    "OBJECTIVE-EVIDENCE-MATRIX-2026-07-09.json",
    "NEXT-RECURSIVE-IMPROVEMENT-LOOP-2026-07-09.md",
]
REPORT_DOCUMENTS = [
    "BENCHMARK-METHODOLOGY-2026-07-09.md",
    "EXPERIMENTAL-OUTCOME-CODEX-FLYWHEEL-LOCAL-ENGINE-2026-07-09.md",
    "PUBSCAN-ZERO-DEPENDENCY-INTEGRATION-2026-07-09.md",
    "PUBLIC-REDTEAM-CONTEXT-BOUNDARY-2026-07-09.md",
]
MODEL_RELEASE_DOCUMENTS = [
    "14B/README.md",
    "14B/MODEL_CARD.md",
    "14B/BENCHMARKS.md",
    "14B/ENDPOINTS.md",
    "14B/USAGE.md",
    "14B/SAFETY-ACCOUNTABILITY.md",
    "14B/RELEASE-CHECKLIST.md",
    "32B/README.md",
    "32B/MODEL_CARD.md",
    "32B/BENCHMARKS.md",
    "32B/ENDPOINTS.md",
    "32B/USAGE.md",
    "32B/SAFETY-ACCOUNTABILITY.md",
    "32B/RELEASE-CHECKLIST.md",
]
FLAGSHIP_DOCUMENTS = [
    "README.md",
    "DEMOS.md",
    "WALKTHROUGH.md",
    "EXTERNAL-DOCS-SYNC.md",
    "EXTERNAL-CONTEXT-SOURCES.md",
    "assets/flywheel-flagship-mark.svg",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def copy_file(src: Path, dst: Path) -> dict[str, str | int]:
    if not src.exists():
        raise FileNotFoundError(f"required release input missing: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return {
        "path": str(dst),
        "relative_path": dst.as_posix(),
        "bytes": dst.stat().st_size,
        "sha256": sha256(dst),
    }


def write_text(path: Path, text: str) -> dict[str, str | int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return {
        "path": str(path),
        "relative_path": path.as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def release_readme(*, package_name: str) -> str:
    return f"""# {package_name}

Local harness executable package.

## Start

```powershell
bin\\local-harness.cmd manifest
```

If the package is moved away from the source checkout, set `LOCAL_HARNESS_REPO` to the checkout that contains `scripts/run_harness_cli.py`.

## Local models

The package includes `config\\model_endpoint_profiles.local.json`.
It includes `config\\model_release_readiness.local.json` and `config\\model_publish_plan.local.json` for the 14B/32B release track.
`config\\huggingface_release_stage.local.json` gives dry-run Hugging Face repo IDs, upload command templates, and model upload blockers.
It also includes `config\\tool_integration_contract.local.json` for the Flywheel/Codex sidecar tool contract.
`config\\tool_readiness.local.json` and `config\\tool_hardening_plan.local.json` provide static readiness and hardening gates for the flagship tool fabric.
`docs\\tool_operator_guide.local.md` gives concise operator instructions for each packaged tool surface.
`config\\runtime_activation_contract.local.json` describes storage, env knobs, and activation boundaries.
`config\\codex_mcp_launch_contract.local.json` describes Codex MCP launch profiles, stale-transport reload boundaries, and direct CLI fallbacks.
`config\\context_inventory.local.json` and `docs\\context_inventory.local.md` provide the metadata-only workspace context map.
`config\\pubscan_resource_profiles.local.json` and `docs\\pubscan_resource_profiles.local.md` provide zero-dependency pubscan, native-rendering, compute, and storage profiles.
`config\\enterprise_readiness_report.local.json` summarizes mneme, relay, and plexus enterprise-readiness gates.
`docs\\harness_architecture_report.local.md` summarizes the executable surface, local model endpoints, tool fabric, runtime activation, and release gates.
`docs\\records\\` carries the current roadmap, capability catalog, objective evidence matrix, and next recursive improvement loop.
`docs\\reports\\` and `docs\\releases\\` carry the benchmark methodology, experimental/reporting documents, and 14B/32B publication scaffolds.
`docs\\flagship\\` carries the public-facing art, demos, walkthrough, source context register, and external docs sync plan.

- 14B serve endpoint: `http://127.0.0.1:8765`
- 32B serve endpoint: `http://127.0.0.1:8768`
- 32B runtime: `cpu-offload`

Model weights, `.env` files, tokens, private keys, caches, benchmark outputs, and user corpora are intentionally not included.
"""


def build_bundle(
    *,
    dist: Path,
    out_root: Path,
    version: str,
    include_serve: bool,
) -> dict:
    package_name = f"local-harness-{version}"
    bundle_root = out_root / package_name
    if bundle_root.exists():
        shutil.rmtree(bundle_root)
    files: list[dict[str, str | int]] = []

    release_manifest = dist / "local-harness-release.json"
    endpoint_profiles = dist / "model_endpoint_profiles.local.json"
    endpoint_profiles_md = dist / "model_endpoint_profiles.local.md"
    model_release = dist / "model_release_readiness.local.json"
    model_release_md = dist / "model_release_readiness.local.md"
    model_publish = dist / "model_publish_plan.local.json"
    model_publish_md = dist / "model_publish_plan.local.md"
    huggingface_stage = dist / "huggingface_release_stage.local.json"
    huggingface_stage_md = dist / "huggingface_release_stage.local.md"
    tool_contract = dist / "tool_integration_contract.local.json"
    tool_contract_md = dist / "tool_integration_contract.local.md"
    tool_readiness = dist / "tool_readiness.local.json"
    tool_readiness_md = dist / "tool_readiness.local.md"
    tool_hardening = dist / "tool_hardening_plan.local.json"
    tool_hardening_md = dist / "tool_hardening_plan.local.md"
    tool_operator_guide = dist / "tool_operator_guide.local.json"
    tool_operator_guide_md = dist / "tool_operator_guide.local.md"
    runtime_contract = dist / "runtime_activation_contract.local.json"
    runtime_contract_md = dist / "runtime_activation_contract.local.md"
    codex_mcp_contract = dist / "codex_mcp_launch_contract.local.json"
    codex_mcp_contract_md = dist / "codex_mcp_launch_contract.local.md"
    context_inventory = dist / "context_inventory.local.json"
    context_inventory_md = dist / "context_inventory.local.md"
    pubscan_profiles = dist / "pubscan_resource_profiles.local.json"
    pubscan_profiles_md = dist / "pubscan_resource_profiles.local.md"
    executable_manifest = dist / "harness_executable_manifest.local.json"
    executable_manifest_md = dist / "harness_executable_manifest.local.md"
    architecture_report = dist / "harness_architecture_report.local.json"
    architecture_report_md = dist / "harness_architecture_report.local.md"
    enterprise_readiness = dist / "enterprise_readiness_report.local.json"
    enterprise_readiness_md = dist / "enterprise_readiness_report.local.md"
    inputs = [
        (dist / "local-harness.exe", bundle_root / "bin" / "local-harness.exe"),
        (dist / "local-harness.cmd", bundle_root / "bin" / "local-harness.cmd"),
        (dist / "local-agent.exe", bundle_root / "bin" / "local-agent.exe"),
        (release_manifest, bundle_root / "manifest" / "local-harness-release.json"),
        (endpoint_profiles, bundle_root / "config" / "model_endpoint_profiles.local.json"),
        (endpoint_profiles_md, bundle_root / "config" / "model_endpoint_profiles.local.md"),
        (model_release, bundle_root / "config" / "model_release_readiness.local.json"),
        (model_release_md, bundle_root / "docs" / "model_release_readiness.local.md"),
        (model_publish, bundle_root / "config" / "model_publish_plan.local.json"),
        (model_publish_md, bundle_root / "docs" / "model_publish_plan.local.md"),
        (huggingface_stage, bundle_root / "config" / "huggingface_release_stage.local.json"),
        (huggingface_stage_md, bundle_root / "docs" / "huggingface_release_stage.local.md"),
        (tool_contract, bundle_root / "config" / "tool_integration_contract.local.json"),
        (tool_contract_md, bundle_root / "config" / "tool_integration_contract.local.md"),
        (tool_readiness, bundle_root / "config" / "tool_readiness.local.json"),
        (tool_readiness_md, bundle_root / "docs" / "tool_readiness.local.md"),
        (tool_hardening, bundle_root / "config" / "tool_hardening_plan.local.json"),
        (tool_hardening_md, bundle_root / "docs" / "tool_hardening_plan.local.md"),
        (tool_operator_guide, bundle_root / "config" / "tool_operator_guide.local.json"),
        (tool_operator_guide_md, bundle_root / "docs" / "tool_operator_guide.local.md"),
        (runtime_contract, bundle_root / "config" / "runtime_activation_contract.local.json"),
        (runtime_contract_md, bundle_root / "config" / "runtime_activation_contract.local.md"),
        (codex_mcp_contract, bundle_root / "config" / "codex_mcp_launch_contract.local.json"),
        (codex_mcp_contract_md, bundle_root / "config" / "codex_mcp_launch_contract.local.md"),
        (context_inventory, bundle_root / "config" / "context_inventory.local.json"),
        (context_inventory_md, bundle_root / "docs" / "context_inventory.local.md"),
        (pubscan_profiles, bundle_root / "config" / "pubscan_resource_profiles.local.json"),
        (pubscan_profiles_md, bundle_root / "docs" / "pubscan_resource_profiles.local.md"),
        (executable_manifest, bundle_root / "manifest" / "harness_executable_manifest.local.json"),
        (executable_manifest_md, bundle_root / "manifest" / "harness_executable_manifest.local.md"),
        (architecture_report, bundle_root / "config" / "harness_architecture_report.local.json"),
        (architecture_report_md, bundle_root / "docs" / "harness_architecture_report.local.md"),
        (enterprise_readiness, bundle_root / "config" / "enterprise_readiness_report.local.json"),
        (enterprise_readiness_md, bundle_root / "docs" / "enterprise_readiness_report.local.md"),
        (ROOT / "project-docs" / "HARNESS-PACKAGING.md", bundle_root / "docs" / "HARNESS-PACKAGING.md"),
    ]
    if include_serve:
        inputs.append((dist / "local-serve.exe", bundle_root / "bin" / "local-serve.exe"))
    for src, dst in inputs:
        copied = copy_file(src, dst)
        copied["relative_path"] = str(dst.relative_to(bundle_root)).replace("\\", "/")
        files.append(copied)
    for record in DOCUMENTATION_RECORDS:
        copied = copy_file(
            ROOT / "project-docs" / "records" / record,
            bundle_root / "docs" / "records" / record,
        )
        copied["relative_path"] = str((bundle_root / "docs" / "records" / record).relative_to(bundle_root)).replace("\\", "/")
        files.append(copied)
    for report in REPORT_DOCUMENTS:
        source_root = ROOT / "project-docs" / ("records" if report.startswith("BENCHMARK-METHODOLOGY") else "reports")
        copied = copy_file(
            source_root / report,
            bundle_root / "docs" / "reports" / report,
        )
        copied["relative_path"] = str((bundle_root / "docs" / "reports" / report).relative_to(bundle_root)).replace("\\", "/")
        files.append(copied)
    for release_doc in MODEL_RELEASE_DOCUMENTS:
        copied = copy_file(
            ROOT / "project-docs" / "releases" / release_doc,
            bundle_root / "docs" / "releases" / release_doc,
        )
        copied["relative_path"] = str((bundle_root / "docs" / "releases" / release_doc).relative_to(bundle_root)).replace("\\", "/")
        files.append(copied)
    for flagship_doc in FLAGSHIP_DOCUMENTS:
        copied = copy_file(
            ROOT / "project-docs" / "flagship" / flagship_doc,
            bundle_root / "docs" / "flagship" / flagship_doc,
        )
        copied["relative_path"] = str((bundle_root / "docs" / "flagship" / flagship_doc).relative_to(bundle_root)).replace("\\", "/")
        files.append(copied)

    readme = write_text(bundle_root / "README.md", release_readme(package_name=package_name))
    readme["relative_path"] = "README.md"
    files.append(readme)

    ship_manifest = {
        "schema": "harness.local-release-bundle/v1",
        "created_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "package_name": package_name,
        "repo_root": str(ROOT),
        "source_commit": git_commit(),
        "dependency_posture": {
            "mandatory_runtime_dependencies": "none beyond Windows process execution for the packaged wrappers",
            "local_model_runtime": "external local serve runtime; model weights are not packaged",
            "hosted_services": "none required",
        },
        "secret_policy": "no .env files, credentials, tokens, private keys, model weights, caches, or benchmark outputs are included",
        "documentation_pack": {
            "records": DOCUMENTATION_RECORDS,
            "reports": REPORT_DOCUMENTS,
            "model_release_documents": MODEL_RELEASE_DOCUMENTS,
            "flagship_documents": FLAGSHIP_DOCUMENTS,
            "record_count": len(DOCUMENTATION_RECORDS),
            "report_count": len(REPORT_DOCUMENTS),
            "model_release_document_count": len(MODEL_RELEASE_DOCUMENTS),
            "flagship_document_count": len(FLAGSHIP_DOCUMENTS),
        },
        "files": sorted(files, key=lambda item: str(item["relative_path"])),
    }
    manifest_path = bundle_root / "manifest" / "ship-manifest.json"
    manifest_path.write_text(json.dumps(ship_manifest, indent=2, sort_keys=True), encoding="utf-8")

    sums_path = bundle_root / "SHA256SUMS.txt"
    sums_entries = [
        *ship_manifest["files"],
        {
            "path": str(manifest_path),
            "relative_path": "manifest/ship-manifest.json",
            "bytes": manifest_path.stat().st_size,
            "sha256": sha256(manifest_path),
        },
    ]
    sums = "\n".join(f"{item['sha256']}  {item['relative_path']}" for item in sorted(sums_entries, key=lambda item: str(item["relative_path"]))) + "\n"
    sums_path.write_text(sums, encoding="utf-8")

    zip_path = out_root / f"{package_name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(bundle_root.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(out_root).as_posix())
    package_summary = {
        **ship_manifest,
        "bundle_root": str(bundle_root),
        "included_integrity_files": [
            {
                "path": str(manifest_path),
                "relative_path": "manifest/ship-manifest.json",
                "bytes": manifest_path.stat().st_size,
                "sha256": sha256(manifest_path),
            },
            {
                "path": str(sums_path),
                "relative_path": "SHA256SUMS.txt",
                "bytes": sums_path.stat().st_size,
                "sha256": sha256(sums_path),
            },
        ],
        "zip": {
        "path": str(zip_path),
        "bytes": zip_path.stat().st_size,
            "sha256": sha256(zip_path),
        },
    }
    summary_path = out_root / f"{package_name}.package.json"
    summary_path.write_text(json.dumps(package_summary, indent=2, sort_keys=True), encoding="utf-8")
    package_summary["package_summary"] = {
        "path": str(summary_path),
        "self_integrity": "omitted to avoid circular hash/size claim",
    }
    doctor_json = out_root / f"{package_name}.doctor.json"
    doctor_md = out_root / f"{package_name}.doctor.md"
    doctor_command = [
        sys.executable,
        "scripts/run_package_ship_doctor.py",
        "--package-summary",
        str(summary_path),
        "--repo-root",
        str(ROOT),
        "--out",
        str(doctor_json),
        "--markdown-out",
        str(doctor_md),
        "--strict-exit",
    ]
    proc = subprocess.run(doctor_command, cwd=ROOT)
    if proc.returncode != 0:
        raise RuntimeError(f"package ship doctor failed ({proc.returncode})")
    package_summary["package_doctor"] = {
        "json": {
            "path": str(doctor_json),
            "bytes": doctor_json.stat().st_size,
            "sha256": sha256(doctor_json),
        },
        "markdown": {
            "path": str(doctor_md),
            "bytes": doctor_md.stat().st_size,
            "sha256": sha256(doctor_md),
        },
    }
    architecture_json = out_root / f"{package_name}.architecture.json"
    architecture_md = out_root / f"{package_name}.architecture.md"
    architecture_command = [
        sys.executable,
        "scripts/run_harness_architecture_report.py",
        "--dist",
        str(dist),
        "--package-doctor",
        str(doctor_json),
        "--out",
        str(architecture_json),
        "--markdown-out",
        str(architecture_md),
    ]
    proc = subprocess.run(architecture_command, cwd=ROOT)
    if proc.returncode != 0:
        raise RuntimeError(f"post-package architecture report failed ({proc.returncode})")
    package_summary["package_architecture_report"] = {
        "json": {
            "path": str(architecture_json),
            "bytes": architecture_json.stat().st_size,
            "sha256": sha256(architecture_json),
        },
        "markdown": {
            "path": str(architecture_md),
            "bytes": architecture_md.stat().st_size,
            "sha256": sha256(architecture_md),
        },
    }
    summary_path.write_text(json.dumps(package_summary, indent=2, sort_keys=True), encoding="utf-8")
    return package_summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=DEFAULT_DIST)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_PACKAGES)
    parser.add_argument("--version", default=datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--include-serve", action="store_true")
    parser.add_argument("--manifest-out", type=Path)
    args = parser.parse_args(argv)

    args.out_root.mkdir(parents=True, exist_ok=True)
    manifest = build_bundle(
        dist=args.dist,
        out_root=args.out_root,
        version=args.version,
        include_serve=args.include_serve,
    )
    if args.manifest_out is not None:
        args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
        args.manifest_out.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
