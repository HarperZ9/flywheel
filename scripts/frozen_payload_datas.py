"""Freeze inputs beyond Python modules, and the check that runs after the freeze.

Four jobs, each fed by the pinned manifest rows in
``packaging/python-lane-payloads.jsonl``:

- Package data. A lane that reads files next to its modules (forum reads
  ``forum/manifests/default-roster.toml`` through ``importlib.resources``) needs
  those files as PyInstaller datas at the same package-relative folder. Every
  non-Python file inside the pinned package path is hashed in the source
  manifest, and each one is checked against its pin again before it becomes a
  data entry.
- Slice trees. A reviewed slice (``payload_slice``) ships part of a package.
  The stager copies the slice files into ``<root>/<lane>-<tag>-slice/src`` so
  the freeze can put that tree on its path and never see the rest of the
  package, whose modules import dependencies the slice excludes.
- The post-freeze slice check. ``PYZ-00.toc`` must list exactly the slice
  modules for a sliced package: an extra module means the freeze reached code
  outside the review, and a missing one means a tool in the slice cannot load.
- The Node-lane stage folder. ``FLYWHEEL_NODE_LANE_STAGE_ROOT`` must name the
  folder ``scripts/stage_node_lanes.py`` staged, holding a passing
  ``node-lane-stage.json`` receipt that lists no held lane (the O-8 hold on
  telos, ``packaging/node-lane-payloads.json``). The freeze ships it as
  ``node-lanes``.
"""
from __future__ import annotations

import argparse
import ast
import json
import shutil
import sys
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

SLICE_SUFFIX = "-slice"
SLICE_MARKER = "slice-stage.json"
SLICE_SCHEMA = "flywheel.python-lane-slice-stage/v1"
NODE_STAGE_ENV = "FLYWHEEL_NODE_LANE_STAGE_ROOT"
NODE_STAGE_RECEIPT = "node-lane-stage.json"
NODE_STAGE_DEST = "node-lanes"
NODE_MANIFEST = Path(__file__).resolve().parents[1] / "packaging" / "node-lane-payloads.json"


class FreezeInputError(RuntimeError):
    pass


def _source(row: dict[str, Any]) -> dict[str, Any]:
    return row["component_descriptor"]["source"]


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def import_root(row: dict[str, Any]) -> str:
    """``src`` for a src layout, ``""`` for a package at the repository root."""
    path = _source(row).get("path")
    if path is None:
        return "src"
    parent = PurePosixPath(str(path)).parent.as_posix()
    root = "" if parent == "." else parent
    if root not in ("", "src"):
        raise FreezeInputError(f"{row.get('lane')}: unsupported source path {path}")
    return root


def package_files(row: dict[str, Any]) -> list[str]:
    """Manifest paths inside the pinned package (all of ``src/`` with no path)."""
    source = _source(row)
    paths = [str(item["path"]) for item in source["files"]]
    if "path" not in source:
        return [path for path in paths if path.startswith("src/")]
    package = str(source["path"]).rstrip("/")
    return [path for path in paths if path.startswith(package + "/")]


def importable_path(row: dict[str, Any], rel: str) -> str:
    """A package path relative to the folder that goes on the import path."""
    root = import_root(row)
    return rel[len(root) + 1:] if root else rel


def package_data_entries(row: dict[str, Any]) -> list[tuple[str, str]]:
    """``(manifest path, bundle folder)`` for each non-Python package file."""
    entries = []
    for rel in package_files(row):
        if not rel.endswith(".py"):
            inner = importable_path(row, rel)
            entries.append((rel, PurePosixPath(inner).parent.as_posix()))
    return sorted(set(entries))


def stage_dirs(source_root: Path, row: dict[str, Any]) -> tuple[Path, Path]:
    """``(verify_root, import_dir)``: manifest paths resolve against the first,
    and the second goes on the freeze's import path."""
    base = Path(source_root) / f"{row['lane']}-{row['owner_tag']}"
    root = import_root(row)
    if row.get("payload_slice"):
        import_dir = Path(f"{base}{SLICE_SUFFIX}") / "src"
        return (import_dir.parent if root else import_dir).resolve(), import_dir.resolve()
    return base.resolve(), (base / root if root else base).resolve()


def lane_package_datas(row: dict[str, Any], verify_root: Path) -> list[tuple[str, str]]:
    """PyInstaller datas for one lane's package data, each file checked against its pin."""
    pins = {str(item["path"]): item["sha256"] for item in _source(row)["files"]}
    root = Path(verify_root).resolve()
    datas = []
    for rel, dest in package_data_entries(row):
        path = (root / rel).resolve()
        if not path.is_relative_to(root):
            raise FreezeInputError(f"{row['lane']}: package data {rel} escapes its stage")
        if not path.is_file() or _hash_file(path) != pins[rel]:
            raise FreezeInputError(
                f"{row['lane']}: package data {rel} missing or hash mismatch with its pin")
        datas.append((str(path), dest))
    return datas


def _slice_base(source_root: Path, row: dict[str, Any]) -> Path:
    base = stage_dirs(source_root, row)[1].parent
    if not base.exists():
        return base
    if not (base / SLICE_MARKER).is_file():
        raise FreezeInputError(
            f"{row['lane']}: {base} exists and is not a slice stage; use a fresh source root")
    shutil.rmtree(base)
    return base


def stage_slice_tree(row: dict[str, Any], checkout: Path, source_root: Path) -> Path:
    """Copy a sliced lane's pinned files from its checkout into a fresh slice tree."""
    base = _slice_base(Path(source_root), row)
    verify_root = stage_dirs(Path(source_root), row)[0]
    checkout = Path(checkout).resolve()
    for item in _source(row)["files"]:
        rel = str(item["path"])
        src = (checkout / rel).resolve()
        dest = (verify_root / rel).resolve()
        if not src.is_relative_to(checkout) or not dest.is_relative_to(base.resolve()):
            raise FreezeInputError(f"{row['lane']}: slice path {rel} escapes its root")
        if not src.is_file() or _hash_file(src) != item["sha256"]:
            raise FreezeInputError(f"{row['lane']}: slice file {rel} does not match its pin")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
    marker = {"schema": SLICE_SCHEMA, "lane": row["lane"],
              "owner_commit": row["owner_commit"],
              "modules": list(row["payload_slice"]["modules"])}
    (base / SLICE_MARKER).write_text(
        json.dumps(marker, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return base


def pyz_module_names(toc_path: Path) -> set[str]:
    """Module names in a PyInstaller ``PYZ-00.toc`` (a Python literal)."""
    data = ast.literal_eval(Path(toc_path).read_text(encoding="utf-8"))
    if not (isinstance(data, tuple) and len(data) == 2 and isinstance(data[1], list)):
        raise FreezeInputError(f"unexpected PYZ table of contents shape: {toc_path}")
    return {str(entry[0]) for entry in data[1]}


def check_pyz_slices(toc_path: Path, rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Refuse a freeze whose PYZ holds more or less of a sliced package than its slice."""
    names = pyz_module_names(toc_path)
    receipts = []
    for row in rows:
        spec = row.get("payload_slice")
        if not spec:
            continue
        modules = set(spec["modules"])
        packages = {module.split(".", 1)[0] for module in modules}
        frozen = {name for name in names if name.split(".", 1)[0] in packages}
        extra, missing = sorted(frozen - modules), sorted(modules - frozen)
        if extra or missing:
            raise FreezeInputError(
                f"{row['lane']}: frozen slice differs from its review; "
                f"outside the slice: {extra}; missing: {missing}")
        receipts.append({"lane": row["lane"], "modules": len(modules)})
    return receipts


def held_node_lanes(manifest: Path = NODE_MANIFEST) -> tuple[str, ...]:
    """The Node lanes the pinned manifest holds out of every freeze."""
    rows = json.loads(Path(manifest).read_text(encoding="utf-8"))["lanes"]
    return tuple(row["lane"] for row in rows if row.get("hold"))


def node_lane_stage_datas(stage_root: str | None, *,
                          held: Iterable[str] | None = None) -> list[tuple[str, str]]:
    """The staged Node lanes as one PyInstaller data folder, or a refusal.

    A receipt that lists a held lane is refused: a hold keeps that lane's
    payload out of every freeze."""
    if not stage_root:
        raise FreezeInputError(
            f"{NODE_STAGE_ENV} must point to the staged Node lanes "
            "(run scripts/stage_node_lanes.py first)")
    root = Path(stage_root).resolve()
    if not root.is_dir():
        raise FreezeInputError(f"Node lane stage folder missing: {root}")
    receipt = root / NODE_STAGE_RECEIPT
    try:
        document = json.loads(receipt.read_text(encoding="utf-8"))
        verdict = document.get("verdict")
        staged = {str(row.get("lane")) for row in document.get("lanes") or ()}
    except (OSError, ValueError, AttributeError) as exc:
        raise FreezeInputError(f"Node lane stage has no readable {NODE_STAGE_RECEIPT}: {exc}") from exc
    if verdict != "PASS":
        raise FreezeInputError(f"Node lane stage receipt verdict is {verdict!r}, not PASS")
    blocked = sorted(staged & set(held_node_lanes() if held is None else held))
    if blocked:
        raise FreezeInputError(f"Node lane stage lists held lanes {blocked}; a held lane "
                               "never enters a freeze (restage without --include-held)")
    return [(str(root), NODE_STAGE_DEST)]


def _manifest_rows(repo: Path) -> list[dict[str, Any]]:
    manifest = Path(repo) / "packaging" / "python-lane-payloads.jsonl"
    return [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a frozen PYZ against reviewed slices.")
    parser.add_argument("--toc", required=True, help="path to build/<name>/PYZ-00.toc")
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv)
    try:
        receipts = check_pyz_slices(Path(args.toc), _manifest_rows(Path(args.repo)))
    except (OSError, ValueError, SyntaxError, FreezeInputError) as exc:
        print(json.dumps({"verdict": "FAIL", "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"verdict": "PASS", "slices": receipts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
