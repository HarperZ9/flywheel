#!/usr/bin/env python3
"""Build one-file executables for local harness entrypoints."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "artifacts" / "exe"
WORK = ROOT / "artifacts" / ".pyinstaller"
DEFAULT_SERVE_PYTHON = "E:/local-model-run/venv/Scripts/python.exe"
DEFAULT_TOOLS = "index,forum,gather,crucible,telos,aleph,mneme,relay,plexus,pubscan,local-model"


def _build(name: str, entry: str, *, python: str, hidden: list[str] | None = None) -> None:
    cmd = [
        python,
        "-m",
        "PyInstaller",
        "--onefile",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(DIST),
        "--workpath",
        str(WORK / name),
        "--name",
        name,
        entry,
    ]
    for h in hidden or []:
        cmd.extend(["--hidden-import", h])
    print(f"[build] {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=ROOT)
    if proc.returncode != 0:
        raise RuntimeError(f"pyinstaller failed for {name} ({proc.returncode})")


def _py_path(raw: str | None) -> str:
    if not raw:
        return sys.executable
    explicit = str(Path(raw).expanduser().resolve())
    if not Path(explicit).exists():
        raise FileNotFoundError(f"python executable not found: {explicit}")
    return explicit


def _has_modules(python: str) -> bool:
    probe = (
        "import torch,transformers,peft,bitsandbytes; "
        "import importlib.util; "
        "print('ok')"
    )
    proc = subprocess.run([python, "-c", probe], capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[warn] torch stack unavailable via {python}:")
        print(proc.stderr.strip())
        return False
    return True


def _has_pyinstaller(python: str) -> bool:
    probe = "import PyInstaller"
    proc = subprocess.run([python, "-c", probe], capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[warn] PyInstaller unavailable via {python}:")
        print(proc.stderr.strip())
        return False
    return True


def _write_cmd_wrapper(name: str) -> Path:
    path = DIST / f"{name}.cmd"
    path.write_text(
        "\n".join(
            [
                "@echo off",
                "setlocal",
                'if not defined LOCAL_HARNESS_REPO set "LOCAL_HARNESS_REPO=%~dp0..\\.."',
                f'"%~dp0{name}.exe" %*',
                "exit /b %ERRORLEVEL%",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _emit_endpoint_profiles(args: argparse.Namespace) -> Path:
    path = DIST / "model_endpoint_profiles.local.json"
    markdown = DIST / "model_endpoint_profiles.local.md"
    command = [
        sys.executable,
        "scripts/run_model_endpoint_profiles.py",
        "--models",
        "14B,32B",
        "--serve-url-14b",
        args.serve_url_14b,
        "--serve-url-32b",
        args.serve_url_32b,
        "--serve-runtime-32b",
        args.serve_runtime_32b,
        "--out",
        str(path),
        "--markdown-out",
        str(markdown),
    ]
    print(f"[profiles] {' '.join(command)}")
    proc = subprocess.run(command, cwd=ROOT)
    if proc.returncode != 0:
        raise RuntimeError(f"endpoint profile generation failed ({proc.returncode})")
    return path


def _emit_executable_manifest(args: argparse.Namespace) -> Path:
    path = DIST / "harness_executable_manifest.local.json"
    markdown = DIST / "harness_executable_manifest.local.md"
    command = [
        sys.executable,
        "scripts/run_harness_cli.py",
        "manifest",
        "--store-root",
        args.store_root,
        "--out",
        str(path),
        "--markdown-out",
        str(markdown),
    ]
    print(f"[manifest] {' '.join(command)}")
    proc = subprocess.run(command, cwd=ROOT)
    if proc.returncode != 0:
        raise RuntimeError(f"executable manifest generation failed ({proc.returncode})")
    return path


def _emit_tool_contract(args: argparse.Namespace) -> Path:
    path = DIST / "tool_integration_contract.local.json"
    markdown = DIST / "tool_integration_contract.local.md"
    command = [
        sys.executable,
        "scripts/run_tool_integration_contract.py",
        "--tools",
        args.tools,
        "--base-root",
        args.tool_base_root,
        "--package-root",
        str(DIST),
        "--out",
        str(path),
        "--markdown-out",
        str(markdown),
    ]
    for tool_root in args.tool_root:
        command.extend(["--tool-root", tool_root])
    print(f"[tools] {' '.join(command)}")
    proc = subprocess.run(command, cwd=ROOT)
    if proc.returncode != 0:
        raise RuntimeError(f"tool integration contract generation failed ({proc.returncode})")
    return path


def _emit_runtime_contract(args: argparse.Namespace) -> Path:
    path = DIST / "runtime_activation_contract.local.json"
    markdown = DIST / "runtime_activation_contract.local.md"
    command = [
        sys.executable,
        "scripts/run_runtime_activation_contract.py",
        "--package-root",
        str(DIST),
        "--repo-root",
        str(ROOT),
        "--store-root",
        args.store_root,
        "--model-run-root",
        args.model_run_root,
        "--log-root",
        args.log_root,
        "--out",
        str(path),
        "--markdown-out",
        str(markdown),
    ]
    print(f"[runtime] {' '.join(command)}")
    proc = subprocess.run(command, cwd=ROOT)
    if proc.returncode != 0:
        raise RuntimeError(f"runtime activation contract generation failed ({proc.returncode})")
    return path


def _emit_codex_mcp_contract(args: argparse.Namespace) -> Path:
    path = DIST / "codex_mcp_launch_contract.local.json"
    markdown = DIST / "codex_mcp_launch_contract.local.md"
    command = [
        sys.executable,
        "scripts/run_codex_mcp_launch_contract.py",
        "--codex-config",
        args.codex_config,
        "--tools",
        args.codex_mcp_tools,
        "--observation",
        "index=TRANSPORT_CLOSED|active Codex MCP wrapper may require host reload after source/config repair",
        "--out",
        str(path),
        "--markdown-out",
        str(markdown),
    ]
    print(f"[codex-mcp] {' '.join(command)}")
    proc = subprocess.run(command, cwd=ROOT)
    if proc.returncode != 0:
        raise RuntimeError(f"Codex MCP launch contract generation failed ({proc.returncode})")
    return path


def _emit_architecture_report(args: argparse.Namespace, *, release_manifest_path: Path) -> Path:
    path = DIST / "harness_architecture_report.local.json"
    markdown = DIST / "harness_architecture_report.local.md"
    command = [
        sys.executable,
        "scripts/run_harness_architecture_report.py",
        "--dist",
        str(DIST),
        "--release-manifest",
        str(release_manifest_path),
        "--package-doctor",
        str(DIST / "package-doctor-generated-after-bundle.json"),
        "--out",
        str(path),
        "--markdown-out",
        str(markdown),
    ]
    print(f"[architecture] {' '.join(command)}")
    proc = subprocess.run(command, cwd=ROOT)
    if proc.returncode != 0:
        raise RuntimeError(f"harness architecture report generation failed ({proc.returncode})")
    return path


def _write_release_manifest(args: argparse.Namespace, *, profiles_path: Path, built: list[str], skipped: list[str]) -> Path:
    manifest = {
        "schema": "harness.local-executable-release/v1",
        "created_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "repo_root": str(ROOT),
        "dist_root": str(DIST),
        "dependency_posture": {
            "runtime": "zero mandatory hosted services; local model serving uses configured local Python/runtime",
            "build": "PyInstaller is a build-time dependency only",
        },
        "executables": [
            {
                "name": name,
                "path": str(DIST / f"{name}.exe"),
                "cmd_wrapper": str(DIST / f"{name}.cmd") if name == "local-harness" else "",
                "exists": (DIST / f"{name}.exe").exists(),
            }
            for name in built
        ],
        "skipped": skipped,
        "local_models": {
            "endpoint_profiles": str(profiles_path),
            "serve_python": args.serve_python,
            "serve_url_14b": args.serve_url_14b,
            "serve_url_32b": args.serve_url_32b,
            "serve_runtime_32b": args.serve_runtime_32b,
            "offload_runtime": args.serve_runtime_32b == "cpu-offload",
        },
        "tool_integration": {
            "contract": str(DIST / "tool_integration_contract.local.json"),
            "tools": args.tools,
            "base_root": args.tool_base_root,
            "root_overrides": args.tool_root,
        },
        "executable_manifest": {
            "json": str(DIST / "harness_executable_manifest.local.json"),
            "markdown": str(DIST / "harness_executable_manifest.local.md"),
        },
        "architecture_report": {
            "json": str(DIST / "harness_architecture_report.local.json"),
            "markdown": str(DIST / "harness_architecture_report.local.md"),
        },
        "codex_mcp": {
            "contract": str(DIST / "codex_mcp_launch_contract.local.json"),
            "tools": args.codex_mcp_tools,
            "codex_config": args.codex_config,
        },
        "runtime_activation": {
            "contract": str(DIST / "runtime_activation_contract.local.json"),
            "store_root": args.store_root,
            "model_run_root": args.model_run_root,
            "log_root": args.log_root,
        },
        "operator_notes": [
            "Run local-harness.cmd manifest to inspect the packaged command surface.",
            "Set LOCAL_HARNESS_REPO if the artifacts/exe folder is moved away from the repo checkout.",
            "Use local-harness.cmd readiness model-endpoints with the emitted profile settings before starting local serve.",
        ],
    }
    path = DIST / "local-harness-release.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-harness", action="store_true",
                    help="skip the full local-harness executable")
    ap.add_argument("--skip-agent", action="store_true",
                    help="skip the local-agent executable")
    ap.add_argument("--skip-serve", action="store_true",
                    help="skip the optional heavy local-serve executable")
    ap.add_argument("--serve-python", default=DEFAULT_SERVE_PYTHON,
                    help="python interpreter used for the torch-backed serve executable")
    ap.add_argument("--serve-url-14b", default="http://127.0.0.1:8765")
    ap.add_argument("--serve-url-32b", default="http://127.0.0.1:8768")
    ap.add_argument("--serve-runtime-32b", default="cpu-offload")
    ap.add_argument("--tools", default=DEFAULT_TOOLS)
    ap.add_argument("--tool-base-root", default="C:/dev/public")
    ap.add_argument("--tool-root", action="append", default=["aleph=C:/dev/aleph", "local-model=C:/dev/local-model"])
    ap.add_argument("--codex-config", default="C:/Users/Zain/.codex/config.toml")
    ap.add_argument("--codex-mcp-tools", default="index,forum,gather,crucible,telos")
    ap.add_argument("--store-root", default="C:/tmp/harness_file_store")
    ap.add_argument("--model-run-root", default="E:/local-model-run")
    ap.add_argument("--log-root", default="C:/tmp/local_model_serve_logs")
    ap.add_argument("--package", action="store_true",
                    help="assemble a local release bundle after building")
    ap.add_argument("--package-version", default=datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
    args = ap.parse_args()

    DIST.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    serve_python = _py_path(args.serve_python)
    built: list[str] = []
    skipped: list[str] = []

    if not _has_pyinstaller(sys.executable):
        raise RuntimeError(f"PyInstaller unavailable via {sys.executable}")
    if not args.skip_harness:
        _build("local-harness", str(ROOT / "scripts" / "local_harness_entry.py"), python=sys.executable)
        _write_cmd_wrapper("local-harness")
        built.append("local-harness")
    else:
        skipped.append("local-harness")
    if not args.skip_agent:
        _build("local-agent", str(ROOT / "scripts" / "local_agent_entry.py"), python=sys.executable)
        built.append("local-agent")
    else:
        skipped.append("local-agent")
    if not args.skip_serve:
        if not _has_pyinstaller(serve_python):
            print("[warn] serve skipped: PyInstaller unavailable for serve-python interpreter")
            skipped.append("local-serve:missing_pyinstaller")
        elif not _has_modules(serve_python):
            print("[warn] serve skipped: required serve stack not available in that interpreter")
            skipped.append("local-serve:missing_modules")
        else:
            _build("local-serve", str(ROOT / "scripts" / "local_serve_entry.py"),
                   python=serve_python, hidden=[
                       "transformers",
                       "bitsandbytes",
                       "torch",
                       "peft",
                   ])
            built.append("local-serve")
    else:
        skipped.append("local-serve")

    _emit_executable_manifest(args)
    profiles_path = _emit_endpoint_profiles(args)
    _emit_tool_contract(args)
    _emit_runtime_contract(args)
    _emit_codex_mcp_contract(args)
    manifest_path = _write_release_manifest(args, profiles_path=profiles_path, built=built, skipped=skipped)
    _emit_architecture_report(args, release_manifest_path=manifest_path)
    print(f"[ok] executables in {DIST}")
    print(f"[ok] release manifest {manifest_path}")
    if args.package:
        package_command = [
            sys.executable,
            "scripts/package_local_harness_release.py",
            "--version",
            args.package_version,
        ]
        if not args.skip_serve and "local-serve" in built:
            package_command.append("--include-serve")
        print(f"[package] {' '.join(package_command)}")
        proc = subprocess.run(package_command, cwd=ROOT)
        if proc.returncode != 0:
            raise RuntimeError(f"release package assembly failed ({proc.returncode})")
    if not args.skip_serve:
        print("[note] local-serve bundle is intentionally heavy because it includes torch/transformers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
