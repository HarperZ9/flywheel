"""Emit zero-dependency pubscan, native-rendering, compute, and storage profiles.

This command is intentionally conservative:

- no package installs
- no external services
- no secret reads
- no recursive dependency resolution
- no tool execution by default

It turns local filesystem evidence into receipt-shaped profiles so the harness
can distinguish available local capability from missing compute/storage
capacity without depending on enterprise middleware.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402


SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}

MANIFEST_NAMES = {
    "AGENTS.md",
    "Cargo.toml",
    "Makefile",
    "README.md",
    "deno.json",
    "go.mod",
    "justfile",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "tsconfig.json",
}

ENTRYPOINT_SUFFIXES = {
    ".bat": "batch",
    ".cmd": "cmd",
    ".exe": "executable",
    ".ps1": "powershell",
    ".py": "python",
    ".sh": "shell",
}

RENDER_HINTS = (
    "render",
    "renderer",
    "engine",
    "graphics",
    "scene",
    "shader",
    "native",
    "ui",
    "visual",
    "canvas",
)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _safe_path(path: Path) -> str:
    return str(path.resolve())


def _mtime(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat().replace("+00:00", "Z")
    except OSError:
        return ""


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _iter_limited(root: Path, *, max_depth: int, max_entries: int):
    yielded = 0
    stack = [(root, 0)]
    while stack and yielded < max_entries:
        current, depth = stack.pop()
        try:
            children = sorted(current.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            continue
        for child in children:
            if yielded >= max_entries:
                break
            if child.is_dir() and child.name in SKIP_DIRS:
                continue
            yielded += 1
            yield child, depth + 1
            if child.is_dir() and depth + 1 < max_depth:
                stack.append((child, depth + 1))


def _detect_repo_profile(path: Path, pubscan_root: Path, *, max_depth: int, max_entries: int) -> dict:
    manifests = []
    entrypoints = []
    render_hints = []
    truncated = False
    count = 0

    for child, depth in _iter_limited(path, max_depth=max_depth, max_entries=max_entries):
        count += 1
        rel = _relative(child, path)
        lower = child.name.lower()
        if child.is_file() and child.name in MANIFEST_NAMES:
            manifests.append(rel)
        if child.is_file() and child.suffix.lower() in ENTRYPOINT_SUFFIXES:
            entrypoints.append({
                "path": rel,
                "kind": ENTRYPOINT_SUFFIXES[child.suffix.lower()],
                "depth": depth,
            })
        if any(hint in lower for hint in RENDER_HINTS):
            render_hints.append(rel)
    if count >= max_entries:
        truncated = True

    surfaces = ["repo"]
    if entrypoints:
        surfaces.append("local-executable")
    if any(item.endswith("Cargo.toml") for item in manifests):
        surfaces.append("rust")
    if any(item.endswith("package.json") for item in manifests):
        surfaces.append("node")
    if any(item.endswith("pyproject.toml") or item.endswith("requirements.txt") for item in manifests):
        surfaces.append("python")
    if render_hints:
        surfaces.append("native-rendering-candidate")

    if entrypoints:
        health = "profiled_entrypoints"
    elif manifests:
        health = "source_only"
    else:
        health = "unverified"

    return {
        "schema": "harness.tool-profile/v1",
        "id": f"pubscan.{path.name}",
        "name": path.name,
        "path": _safe_path(path),
        "relative_path": _relative(path, pubscan_root),
        "exists": path.exists(),
        "last_modified_utc": _mtime(path),
        "surfaces": sorted(set(surfaces)),
        "health": health,
        "dependency_posture": "zero-mandatory",
        "install_action": "none",
        "manifests": manifests[:40],
        "entrypoints": entrypoints[:80],
        "render_hints": render_hints[:40],
        "scan": {
            "max_depth": max_depth,
            "max_entries": max_entries,
            "observed_entries": count,
            "truncated": truncated,
            "skipped_dirs": sorted(SKIP_DIRS),
        },
        "owner": "operator",
        "retirement_criteria": (
            "explicit operator retirement or replaced by a receipt-compatible successor"
        ),
    }


def _pubscan_profiles(pubscan_root: Path, *, max_depth: int, max_entries: int) -> dict:
    repos = []
    if pubscan_root.exists():
        for child in sorted(pubscan_root.iterdir(), key=lambda p: p.name.lower()):
            if child.is_dir():
                repos.append(_detect_repo_profile(
                    child,
                    pubscan_root,
                    max_depth=max_depth,
                    max_entries=max_entries,
                ))
    return {
        "schema": "harness.pubscan-tool-profiles/v1",
        "root": _safe_path(pubscan_root),
        "exists": pubscan_root.exists(),
        "count": len(repos),
        "profiles": repos,
        "summary": {
            "profiled_entrypoints": sum(1 for row in repos if row["health"] == "profiled_entrypoints"),
            "source_only": sum(1 for row in repos if row["health"] == "source_only"),
            "unverified": sum(1 for row in repos if row["health"] == "unverified"),
            "native_rendering_candidates": sum(
                1 for row in repos if "native-rendering-candidate" in row["surfaces"]
            ),
        },
    }


def _native_rendering_profile(roots: list[Path], *, max_depth: int, max_entries: int) -> dict:
    candidates = []
    for root in roots:
        if not root.exists():
            candidates.append({
                "path": _safe_path(root),
                "exists": False,
                "matches": [],
            })
            continue
        matches = []
        for child, depth in _iter_limited(root, max_depth=max_depth, max_entries=max_entries):
            name = child.name.lower()
            if any(hint in name for hint in RENDER_HINTS):
                matches.append({
                    "path": _relative(child, root),
                    "kind": "directory" if child.is_dir() else "file",
                    "depth": depth,
                })
        candidates.append({
            "path": _safe_path(root),
            "exists": True,
            "max_depth": max_depth,
            "max_entries": max_entries,
            "matches": matches[:120],
            "truncated": len(matches) > 120,
        })
    return {
        "schema": "harness.native-rendering-profile/v1",
        "dependency_posture": "zero-mandatory",
        "execution_policy": "discovery-only; no render command executed",
        "candidate_roots": candidates,
        "summary": {
            "roots": len(candidates),
            "existing_roots": sum(1 for item in candidates if item["exists"]),
            "candidate_matches": sum(len(item["matches"]) for item in candidates),
        },
    }


def _compute_profile() -> dict:
    cpu_count = os.cpu_count() or 0
    gpu_tools = []
    for command in ("nvidia-smi", "rocm-smi", "clinfo"):
        path = shutil.which(command)
        gpu_tools.append({"command": command, "path": path or "", "available": bool(path)})
    return {
        "schema": "harness.compute-profile/v1",
        "dependency_posture": "zero-mandatory",
        "execution_policy": "presence-only; no benchmark or GPU probe executed",
        "local_cpu": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "logical_cores": cpu_count,
            "available": cpu_count > 0,
        },
        "local_gpu": {
            "status": "tool_detected" if any(item["available"] for item in gpu_tools) else "unknown",
            "detection_tools": gpu_tools,
        },
        "remote_compute": {
            "status": "not_configured",
            "env_presence": {
                "HARNESS_REMOTE_COMPUTE_URL": bool(os.environ.get("HARNESS_REMOTE_COMPUTE_URL")),
                "HARNESS_REMOTE_GPU_PROFILE": bool(os.environ.get("HARNESS_REMOTE_GPU_PROFILE")),
            },
        },
        "queue": {
            "status": "local",
            "adapter": "file_or_in_process",
        },
    }


def _storage_profile(roots: list[Path]) -> dict:
    rows = []
    for root in roots:
        exists = root.exists()
        target = root if exists else root.parent
        try:
            usage = shutil.disk_usage(target)
            usage_obj = {
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
            }
            status = "available"
        except OSError as exc:
            usage_obj = {"error": str(exc)}
            status = "unavailable"
        rows.append({
            "path": _safe_path(root),
            "exists": exists,
            "status": status,
            "usage": usage_obj,
        })
    return {
        "schema": "harness.storage-profile/v1",
        "dependency_posture": "zero-mandatory",
        "content_addressed_policy": "sha256-by-artifact",
        "artifact_roots": rows,
        "object_store": {
            "status": "optional_adapter",
            "env_presence": {
                "HARNESS_OBJECT_STORE_URL": bool(os.environ.get("HARNESS_OBJECT_STORE_URL")),
                "HARNESS_OBJECT_STORE_BUCKET": bool(os.environ.get("HARNESS_OBJECT_STORE_BUCKET")),
            },
        },
        "summary": {
            "roots": len(rows),
            "available_roots": sum(1 for row in rows if row["status"] == "available"),
            "total_free_bytes": sum(
                int(row["usage"].get("free_bytes", 0)) for row in rows if isinstance(row["usage"], dict)
            ),
        },
    }


def build_profiles(args) -> dict:
    pubscan_root = Path(args.pubscan_root)
    render_roots = [Path(item) for item in args.render_roots.split(";") if item.strip()]
    storage_roots = [Path(item) for item in args.storage_roots.split(";") if item.strip()]
    obj = {
        "schema": "harness.pubscan-resource-profiles/v1",
        "timestamp_utc": _now(),
        "secret_policy": "presence-only env booleans; no token, key, or credential values emitted",
        "zero_dependency_policy": {
            "mandatory_external_services": 0,
            "installs_performed": 0,
            "external_network_calls": 0,
            "tool_execution": "none by default",
        },
        "pubscan": _pubscan_profiles(
            pubscan_root,
            max_depth=args.max_depth,
            max_entries=args.max_entries,
        ),
        "native_rendering": _native_rendering_profile(
            render_roots,
            max_depth=args.max_depth,
            max_entries=args.max_entries,
        ),
        "compute": _compute_profile(),
        "storage": _storage_profile(storage_roots),
    }
    obj["receipt"] = {
        "schema": "harness.receipt/v1",
        "kind": "profile_bundle",
        "payload_sha256": _sha256_text(json.dumps(obj, sort_keys=True)),
        "verdict": "PROFILED",
    }
    return obj


def render_markdown(obj: dict) -> str:
    lines = [
        "# Pubscan and resource profiles",
        "",
        f"- Schema: `{obj['schema']}`",
        f"- Timestamp UTC: `{obj['timestamp_utc']}`",
        f"- Payload SHA-256: `{obj['receipt']['payload_sha256']}`",
        f"- Zero mandatory external services: `{obj['zero_dependency_policy']['mandatory_external_services']}`",
        "",
        "## Pubscan",
        "",
        f"- Root: `{obj['pubscan']['root']}`",
        f"- Repositories: `{obj['pubscan']['count']}`",
        f"- Profiled entrypoints: `{obj['pubscan']['summary']['profiled_entrypoints']}`",
        f"- Source-only: `{obj['pubscan']['summary']['source_only']}`",
        f"- Unverified: `{obj['pubscan']['summary']['unverified']}`",
        f"- Native-rendering candidates: `{obj['pubscan']['summary']['native_rendering_candidates']}`",
        "",
        "| Repo | Health | Surfaces | Entrypoints | Manifests |",
        "|---|---|---|---:|---:|",
    ]
    for row in obj["pubscan"]["profiles"]:
        lines.append(
            "| {name} | {health} | {surfaces} | {entrypoints} | {manifests} |".format(
                name=row["name"],
                health=row["health"],
                surfaces=", ".join(row["surfaces"]),
                entrypoints=len(row["entrypoints"]),
                manifests=len(row["manifests"]),
            )
        )
    lines.extend([
        "",
        "## Native rendering",
        "",
        f"- Existing roots: `{obj['native_rendering']['summary']['existing_roots']}`",
        f"- Candidate matches: `{obj['native_rendering']['summary']['candidate_matches']}`",
        "",
        "## Compute",
        "",
        f"- Local CPU logical cores: `{obj['compute']['local_cpu']['logical_cores']}`",
        f"- Local GPU status: `{obj['compute']['local_gpu']['status']}`",
        f"- Remote compute status: `{obj['compute']['remote_compute']['status']}`",
        "",
        "## Storage",
        "",
        f"- Available roots: `{obj['storage']['summary']['available_roots']}`",
        f"- Total free bytes across roots: `{obj['storage']['summary']['total_free_bytes']}`",
        "",
    ])
    return "\n".join(lines)


def _store_profile_outputs(
    obj: dict,
    *,
    store_root: str,
    run_id: str = "",
    artifact_paths: list[tuple[str, str]] | None = None,
) -> list[dict]:
    if not store_root:
        return []
    store = FileBackedHarnessStore(Path(store_root))
    outputs = [
        store.put_receipt(
            kind="pubscan_resource_profiles",
            body=obj,
            run_id=run_id,
            verdict="PROFILED",
        )
    ]
    for path_text, label in artifact_paths or []:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pubscan-root", default="C:/dev/public/pubscan")
    parser.add_argument(
        "--render-roots",
        default="C:/dev/public;C:/dev/tools;C:/dev/local-model",
        help="semicolon-separated roots to scan for native rendering candidates",
    )
    parser.add_argument(
        "--storage-roots",
        default="C:/tmp;C:/dev;E:/local-model-run",
        help="semicolon-separated artifact/storage roots to profile",
    )
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--max-entries", type=int, default=2000)
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    obj = build_profiles(args)
    text = json.dumps(obj, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    if args.markdown_out:
        md = Path(args.markdown_out)
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(render_markdown(obj), encoding="utf-8")
    store_outputs = _store_profile_outputs(
        obj,
        store_root=args.store_root,
        run_id=args.run_id,
        artifact_paths=[
            (args.out, "pubscan-resource-profiles-json"),
            (args.markdown_out, "pubscan-resource-profiles-markdown"),
        ],
    )
    if store_outputs:
        obj = {**obj, "store_outputs": store_outputs}
        text = json.dumps(obj, indent=2)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
