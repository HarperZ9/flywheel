"""Freeze inputs for bundling manifest Python lanes into the frozen gateway.

Relay ships as a submodule and Canon has its own context-payload wiring, so both
are handled directly in the spec. Every other manifest lane ships from its
staged, hash-pinned source, and this module derives what PyInstaller needs for
each one: the ``src`` directory to put on the analysis path, and every module in
the pinned package as a hidden import (the child dispatcher imports the lane's
entrypoint dynamically, which static analysis cannot follow on its own).

For each lane it verifies two things before returning inputs. The staged source
manifest hash must equal the pinned manifest row, so a build cannot bundle source
that drifted from the pin. The lane's entrypoint module must resolve from its own
staged ``src`` and not from a shadow elsewhere on the path, so one lane cannot
smuggle another's code into the freeze.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from scripts.build_python_lane_payloads import _verify_source_files

SPEC_HANDLED_LANES = ("relay", "canon")


def _manifest_rows(repo: Path) -> dict[str, dict]:
    manifest = repo / "packaging" / "python-lane-payloads.jsonl"
    rows: dict[str, dict] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[str(row["lane"])] = row
    return rows


def bundled_python_lanes(repo: Path,
                         exclude: tuple[str, ...] = SPEC_HANDLED_LANES) -> list[str]:
    """The manifest lanes bundled through this helper: all but the spec-handled ones."""
    return sorted(set(_manifest_rows(repo)) - set(exclude))


def lane_hidden_imports(row: dict) -> list[str]:
    """Every importable module in the pinned package, from its source.files list."""
    modules: set[str] = set()
    for item in row["component_descriptor"]["source"]["files"]:
        path = str(item["path"])
        if not path.endswith(".py") or not path.startswith("src/"):
            continue
        parts = path[len("src/"):-len(".py")].split("/")
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            modules.add(".".join(parts))
    return sorted(modules)


def _staged_src(source_root: Path, row: dict) -> tuple[Path, Path]:
    checkout = (source_root / f"{row['lane']}-{row['owner_tag']}").resolve()
    return checkout, (checkout / "src").resolve()


def python_lane_freeze_inputs(repo: Path, source_root: Path,
                              exclude: tuple[str, ...] = SPEC_HANDLED_LANES):
    """Return ``(pathex, hiddenimports, receipts)`` for the bundled python lanes.

    Raises RuntimeError on a missing stage, a source-manifest mismatch, or an
    entrypoint module that resolves outside its own staged source."""
    repo = Path(repo).resolve()
    source_root = Path(source_root).resolve()
    rows = _manifest_rows(repo)
    lanes = bundled_python_lanes(repo, exclude)
    staged: dict[str, tuple[dict, Path, Path]] = {}
    for lane in lanes:
        row = rows[lane]
        checkout, src = _staged_src(source_root, row)
        if not src.is_dir():
            raise RuntimeError(f"staged {lane} source missing: {src}")
        staged[lane] = (row, checkout, src)
        value = str(src)
        while value in sys.path:
            sys.path.remove(value)
        sys.path.insert(0, value)
    pathex: list[str] = []
    hiddenimports: list[str] = []
    receipts: list[dict] = []
    for lane, (row, checkout, src) in staged.items():
        expected = row["component_descriptor"]["source"]["manifest_sha256"]
        digest, module_count, total_bytes = _verify_source_files(row, checkout)
        if digest != expected:
            raise RuntimeError(f"staged {lane} source manifest mismatch")
        module = str(row["component_descriptor"]["entrypoint"]["module"])
        spec = importlib.util.find_spec(module)
        origin = Path(spec.origin).resolve() if spec and spec.origin else None
        if origin is None or not origin.is_relative_to(src):
            raise RuntimeError(f"bundled {lane} import shadowed outside {src}")
        pathex.append(str(src))
        hiddenimports.extend(lane_hidden_imports(row))
        receipts.append({
            "lane": lane,
            "owner_commit": row["owner_commit"],
            "source_manifest_sha256": digest,
            "module_count": module_count,
            "bytes": total_bytes,
        })
    return pathex, sorted(set(hiddenimports)), receipts
