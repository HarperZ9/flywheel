"""Validate and stage the Studio body runtime for frozen gateway builds."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from scripts.studio_runtime_manifest import (
    BODY_HIDDENIMPORTS,
    ENGINE_DESTINATION,
    LICENSE_DESTINATION,
    MANIFEST_SCHEMA,
    PACKAGE_SECTIONS,
    PAYLOAD_MANIFEST_DESTINATION,
    PAYLOAD_SCHEMA,
    PYTHON_RUNTIME_DIR,
    STUDIO_RUNTIME_MANIFEST_ENV,
    STUDIO_RUNTIME_PAYLOAD_ENV,
    assert_hash,
    contains_source_root,
    expected_hash,
    hiddenimports_from_manifest,
    load_runtime_manifest,
    packaged_manifest,
    section_rows,
    validate_entry_modules,
    validate_manifest_sources,
)
from scripts.studio_runtime_sources import (
    build_manifest_from_source_pins,
    checkout_source_pins,
    load_source_pins,
)
from scripts.studio_runtime_imports import verify_payload_imports


@dataclass(frozen=True)
class StudioRuntimePyInstallerInputs:
    pathex: list[str]
    datas: list[tuple[str, str]]
    hiddenimports: list[str]


def build_studio_runtime_payload(
    manifest_path: Path | str,
    payload_root: Path | str,
    *,
    license_notice_paths: Iterable[Path | str],
) -> dict[str, Any]:
    doc = load_runtime_manifest(manifest_path)
    source_files = validate_manifest_sources(doc)
    notices = [Path(path) for path in license_notice_paths]
    if not notices:
        raise RuntimeError("at least one Studio runtime license notice is required")
    root = Path(payload_root)
    if root.exists() and any(root.iterdir()):
        raise RuntimeError("payload root must be empty before staging")
    root.mkdir(parents=True, exist_ok=True)
    copied = _copy_runtime_sources(root, source_files)
    _copy_license_notices(notices, root / LICENSE_DESTINATION)
    manifest_out = root / PAYLOAD_MANIFEST_DESTINATION
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    manifest_out.write_text(
        json.dumps(packaged_manifest(doc), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = check_studio_runtime_payload(manifest_path, root)
    summary.update({"copied": copied})
    return summary


def check_studio_runtime_payload(
    manifest_path: Path | str,
    payload_root: Path | str,
) -> dict[str, Any]:
    doc = load_runtime_manifest(manifest_path)
    root = Path(payload_root)
    if not root.is_dir():
        raise RuntimeError(f"payload missing: {root}")
    expected = _expected_payload_files(doc)
    for relative in sorted(expected):
        path = root / PurePosixPath(relative)
        if not path.is_file():
            raise RuntimeError(f"payload missing: {relative}")
        assert_hash(path, expected_hash(doc, relative))
    extras = sorted(_observed_payload_files(root) - expected)
    if extras:
        raise RuntimeError(f"payload carries unexpected file: {extras[0]}")
    notices = _license_files(root / LICENSE_DESTINATION)
    packaged = root / PAYLOAD_MANIFEST_DESTINATION
    if not packaged.is_file():
        raise RuntimeError("payload missing packaged Studio runtime manifest")
    packaged_doc = json.loads(packaged.read_text(encoding="utf-8"))
    if contains_source_root(packaged_doc):
        raise RuntimeError("packaged Studio runtime manifest leaks source roots")
    if packaged_doc != packaged_manifest(doc):
        raise RuntimeError("packaged Studio runtime manifest differs from declared source manifest")
    return {
        "schema": PAYLOAD_SCHEMA,
        "payload_root": str(root),
        "file_count": len(expected),
        "license_notice_count": len(notices),
        "manifest_sha256": _file_hash(packaged),
    }


def pyinstaller_studio_runtime_inputs(
    repo: Path | str,
    *,
    env: Mapping[str, str] | None = None,
) -> StudioRuntimePyInstallerInputs:
    source_env = os.environ if env is None else env
    repo_root = Path(repo)
    manifest_path = _required_env_path(source_env, STUDIO_RUNTIME_MANIFEST_ENV, repo_root)
    payload_root = _required_env_path(source_env, STUDIO_RUNTIME_PAYLOAD_ENV, repo_root)
    doc = load_runtime_manifest(manifest_path)
    check_studio_runtime_payload(manifest_path, payload_root)
    datas = _engine_datas(doc, payload_root)
    datas.append((str(payload_root / PAYLOAD_MANIFEST_DESTINATION),
                  PAYLOAD_MANIFEST_DESTINATION.parent.as_posix()))
    datas.extend(_license_datas(payload_root / LICENSE_DESTINATION))
    hidden = sorted(set(BODY_HIDDENIMPORTS) | hiddenimports_from_manifest(doc))
    return StudioRuntimePyInstallerInputs(
        pathex=[str(payload_root / PYTHON_RUNTIME_DIR)],
        datas=sorted(datas),
        hiddenimports=hidden,
    )


def stage_pinned_runtime_payload(
    sources_path: Path | str,
    work_root: Path | str,
    manifest_path: Path | str,
    payload_root: Path | str,
) -> dict[str, Any]:
    pins = load_source_pins(sources_path)
    checkouts = checkout_source_pins(pins, work_root=work_root)
    manifest, notices = build_manifest_from_source_pins(pins, checkout_roots=checkouts)
    output_manifest = Path(manifest_path)
    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    output_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = build_studio_runtime_payload(
        output_manifest, payload_root, license_notice_paths=notices)
    modules = {"studio_engine.engine", "studio_engine.temporal",
               "studio_engine.raster_renderer"}
    for section in PACKAGE_SECTIONS:
        modules.update(manifest[section]["entry_modules"])
    summary["verified_imports"] = verify_payload_imports(payload_root, modules)
    summary["source_refs"] = {
        name: pins["components"][name]["ref"] for name in pins["components"]
    }
    return summary


def _copy_runtime_sources(root: Path, rows: list[tuple[str, Path, Path]]) -> list[str]:
    copied = []
    for section, source_root, rel in rows:
        base = ENGINE_DESTINATION if section == "studio_engine" else PYTHON_RUNTIME_DIR
        destination = root / base / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / rel, destination)
        copied.append((base / rel).as_posix())
    return sorted(copied)


def _expected_payload_files(doc: Mapping[str, Any]) -> set[str]:
    expected = {
        (ENGINE_DESTINATION / rel).as_posix()
        for _s, _r, rel in section_rows(doc, "studio_engine", require_source=False)
    }
    for section in PACKAGE_SECTIONS:
        rows = section_rows(doc, section, require_source=False)
        validate_entry_modules(doc[section], {rel.as_posix() for _, _, rel in rows})
        expected.update((PYTHON_RUNTIME_DIR / rel).as_posix() for _, _, rel in rows)
    return expected


def _observed_payload_files(root: Path) -> set[str]:
    observed = set()
    for base in (root / ENGINE_DESTINATION, root / PYTHON_RUNTIME_DIR):
        if base.exists():
            observed.update(
                path.relative_to(root).as_posix()
                for path in base.rglob("*") if path.is_file())
    return observed


def _engine_datas(doc: Mapping[str, Any], payload_root: Path) -> list[tuple[str, str]]:
    datas = []
    for rel in doc["studio_engine"]["required_files"]:
        source = payload_root / ENGINE_DESTINATION / PurePosixPath(rel)
        destination = ENGINE_DESTINATION / PurePosixPath(rel).parent
        datas.append((str(source), destination.as_posix()))
    return datas


def _license_datas(root: Path) -> list[tuple[str, str]]:
    return [
        (str(path), (LICENSE_DESTINATION / path.relative_to(root).parent).as_posix())
        for path in _license_files(root)
    ]


def _license_files(root: Path) -> list[Path]:
    if not root.is_dir():
        raise RuntimeError("payload missing Studio runtime license notices")
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise RuntimeError("payload missing Studio runtime license notices")
    return files


def _copy_license_notices(notices: list[Path], destination: Path) -> None:
    seen, counts = set(), {}
    destination.mkdir(parents=True, exist_ok=True)
    for index, source in enumerate(notices, start=1):
        if not source.is_file() or source.is_symlink():
            raise RuntimeError(f"license notice is unavailable: {source}")
        counts[source.name.lower()] = counts.get(source.name.lower(), 0) + 1
        name = source.name
        if counts[source.name.lower()] > 1:
            name = f"{index:02d}-{source.name}"
        key = name.lower()
        if key in seen:
            raise RuntimeError(f"duplicate license notice name: {name}")
        seen.add(key)
        shutil.copy2(source, destination / name)


def _required_env_path(env: Mapping[str, str], name: str, repo: Path) -> Path:
    raw = env.get(name)
    if not raw:
        raise RuntimeError(f"missing required Studio body runtime packaging input: {name}")
    path = Path(raw)
    return (repo / path).resolve() if not path.is_absolute() else path.resolve()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build-payload")
    build.add_argument("--manifest", type=Path, required=True)
    build.add_argument("--payload-root", type=Path, required=True)
    build.add_argument("--license-notice", type=Path, action="append", default=[])
    check = sub.add_parser("check-payload")
    check.add_argument("--manifest", type=Path, required=True)
    check.add_argument("--payload-root", type=Path, required=True)
    pinned = sub.add_parser("stage-pinned-payload")
    pinned.add_argument("--sources", type=Path, required=True)
    pinned.add_argument("--work-root", type=Path, required=True)
    pinned.add_argument("--manifest", type=Path, required=True)
    pinned.add_argument("--payload-root", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "build-payload":
        out = build_studio_runtime_payload(
            args.manifest, args.payload_root, license_notice_paths=args.license_notice)
    elif args.command == "check-payload":
        out = check_studio_runtime_payload(args.manifest, args.payload_root)
    else:
        out = stage_pinned_runtime_payload(
            args.sources, args.work_root, args.manifest, args.payload_root)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
