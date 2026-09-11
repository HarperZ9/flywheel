"""Build wheel/source payload evidence for first-party Python lane sidecars."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from hashlib import sha256
from pathlib import Path, PureWindowsPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.evidence_json import canonical_sha256

MANIFEST = ROOT / "packaging" / "python-lane-payloads.jsonl"
DEFAULT_SOURCE_ROOT = Path(
    os.environ.get(
        "FLYWHEEL_PYTHON_LANE_SOURCE_ROOT",
        "D:/fw-ship-sweep-20260910/all-lanes-payloads/sources",
    )
)
SCHEMA = "flywheel.python-lane-payload-build-manifest/v1"

FIXTURES = {
    "gather": {"tool": "gather.docs", "workflow": "read synthetic local document"},
    "crucible": {"tool": "crucible.assess", "workflow": "assess synthetic thesis and measurements"},
    "index": {"tool": "index.map", "workflow": "map a tiny synthetic Python workspace"},
    "forum": {"tool": "forum.route", "workflow": "route a synthetic verification request"},
    "plexus": {"tool": "plexus_plan", "workflow": "plan a built-in interop target"},
    "mneme": {"tool": "mneme.remember+mneme.recall", "workflow": "store and recall synthetic memory"},
    "canon": {"tool": "canon.validate", "workflow": "validate a synthetic canon record"},
}


class PayloadBuildError(RuntimeError):
    pass


def _drive(value: str | Path) -> str:
    text = str(value).replace("\\", "/")
    return PureWindowsPath(text).drive.upper()


def _reject_c_source(path: str | Path, label: str) -> None:
    if _drive(path) == "C:":
        raise PayloadBuildError(f"C: source roots are not allowed ({label}: {path})")


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PayloadBuildError(f"line {number}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise PayloadBuildError(f"line {number}: row is not an object")
        rows.append(row)
    return rows


def _hash_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _canonical_digest(value: Any) -> str:
    return "sha256:" + canonical_sha256(value)


def _source_dir(row: dict[str, Any], source_root: Path) -> Path:
    if row.get("local_source_root"):
        _reject_c_source(str(row["local_source_root"]), f"{row['lane']} local_source_root")
        return Path(str(row["local_source_root"]))
    return source_root / f"{row['lane']}-{row['owner_tag']}"


def _verify_source_files(row: dict[str, Any], source_dir: Path) -> tuple[str, int, int]:
    files = row["component_descriptor"]["source"]["files"]
    module_count = 0
    total_bytes = 0
    for item in files:
        path = source_dir / item["path"]
        if not path.is_file():
            raise PayloadBuildError(f"{row['lane']}: missing source file {path}")
        got_hash = _hash_file(path)
        if got_hash != item["sha256"]:
            raise PayloadBuildError(f"{row['lane']}: hash mismatch for {item['path']}")
        size = path.stat().st_size
        if size != int(item["bytes"]):
            raise PayloadBuildError(f"{row['lane']}: byte count mismatch for {item['path']}")
        total_bytes += size
        if item["path"].endswith(".py"):
            module_count += 1
    return _canonical_digest(files), module_count, total_bytes


def _copy_notices(row: dict[str, Any], source_dir: Path, notices_root: Path) -> list[dict[str, Any]]:
    lane_dir = notices_root / row["lane"]
    lane_dir.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, Any]] = []
    for notice in row["owner_project"]["license_files"]:
        src = source_dir / notice["path"]
        if not src.is_file():
            raise PayloadBuildError(f"{row['lane']}: missing notice {src}")
        if _hash_file(src) != notice["sha256"]:
            raise PayloadBuildError(f"{row['lane']}: notice hash mismatch for {notice['path']}")
        dest = lane_dir / Path(notice["path"]).name
        shutil.copyfile(src, dest)
        copied.append({
            "path": str(dest.as_posix()),
            "source_path": notice["path"],
            "sha256": _hash_file(dest),
            "bytes": dest.stat().st_size,
        })
    return copied


def _write_descriptor(row: dict[str, Any], descriptor_root: Path) -> Path:
    descriptor_root.mkdir(parents=True, exist_ok=True)
    path = descriptor_root / f"{row['lane']}.json"
    path.write_text(
        json.dumps(row["component_descriptor"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _wheel_summary(wheel: Path) -> dict[str, Any]:
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
    metadata = [name for name in names if name.endswith(".dist-info/METADATA")]
    record = [name for name in names if name.endswith(".dist-info/RECORD")]
    licenses = [name for name in names if "dist-info/licenses/" in name.lower() or name.upper().endswith("LICENSE")]
    modules = [name for name in names if name.endswith(".py")]
    return {
        "filename": wheel.name,
        "path": str(wheel.as_posix()),
        "sha256": _hash_file(wheel),
        "bytes": wheel.stat().st_size,
        "metadata": metadata,
        "record": record,
        "license_entries": licenses,
        "module_file_count": len(modules),
    }


def _build_wheel(row: dict[str, Any], source_dir: Path, out: Path, builder_python: str) -> dict[str, Any]:
    before = {path.name for path in (out / "wheels").glob("*.whl")}
    env = os.environ.copy()
    for name in ("TMP", "TEMP", "TMPDIR"):
        env[name] = str(out / "tmp")
    env["PIP_CACHE_DIR"] = str(out / "pip-cache")
    env["PYTHONPYCACHEPREFIX"] = str(out / "pycache")
    (out / "tmp").mkdir(parents=True, exist_ok=True)
    (out / "pip-cache").mkdir(parents=True, exist_ok=True)
    (out / "pycache").mkdir(parents=True, exist_ok=True)
    cmd = [
        builder_python,
        "-m",
        "build",
        "--wheel",
        "--no-isolation",
        "--outdir",
        str(out / "wheels"),
        str(source_dir),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
    if proc.returncode != 0:
        raise PayloadBuildError(
            f"{row['lane']}: wheel build failed with {proc.returncode}: {proc.stdout}{proc.stderr}"
        )
    after = {path.name for path in (out / "wheels").glob("*.whl")}
    new_names = sorted(after - before)
    if not new_names:
        # build may replace an identically named wheel; bind the expected project name.
        project = str(row["owner_project"]["name"]).replace("-", "_").lower()
        new_names = sorted(name for name in after if name.lower().startswith(project))
    if len(new_names) != 1:
        raise PayloadBuildError(f"{row['lane']}: expected one built wheel, got {new_names!r}")
    summary = _wheel_summary(out / "wheels" / new_names[0])
    summary["build_stdout_sha256"] = "sha256:" + sha256(proc.stdout.encode("utf-8")).hexdigest()
    summary["build_stderr_sha256"] = "sha256:" + sha256(proc.stderr.encode("utf-8")).hexdigest()
    return summary


def build_payloads(args: argparse.Namespace) -> dict[str, Any]:
    source_root = Path(args.source_root)
    _reject_c_source(source_root, "source-root")
    out = Path(args.out)
    wheels = out / "wheels"
    descriptors = out / "descriptors"
    notices = out / "notices"
    for path in (out, wheels, descriptors, notices):
        path.mkdir(parents=True, exist_ok=True)
    lanes: list[dict[str, Any]] = []
    for row in _load_manifest(Path(args.manifest)):
        lane = str(row["lane"])
        source_dir = _source_dir(row, source_root)
        closure, module_count, total_bytes = _verify_source_files(row, source_dir)
        descriptor_path = _write_descriptor(row, descriptors)
        lane_entry = {
            "lane": lane,
            "version": row["owner_project"]["version"],
            "source_root": str(source_dir.as_posix()),
            "owner_commit": row["owner_commit"],
            "source_closure_sha256": closure,
            "source_file_count": row["component_descriptor"]["source"]["file_count"],
            "source_bytes": total_bytes,
            "module_file_count": module_count,
            "component_descriptor_sha256": row["component_descriptor_sha256"],
            "descriptor_path": str(descriptor_path.as_posix()),
            "descriptor_file_sha256": _hash_file(descriptor_path),
            "notice_files": _copy_notices(row, source_dir, notices),
            "hidden_imports": row["hidden_imports"],
            "fixture": FIXTURES[lane],
        }
        if not args.skip_wheel_build:
            lane_entry["wheel"] = _build_wheel(row, source_dir, out, args.builder_python)
        lanes.append(lane_entry)
    receipt = {
        "schema": SCHEMA,
        "verdict": "PASS",
        "manifest": str(Path(args.manifest).as_posix()),
        "source_root": str(source_root.as_posix()),
        "output_root": str(out.as_posix()),
        "wheel_build": {"skipped": bool(args.skip_wheel_build), "builder_python": args.builder_python},
        "lanes": lanes,
    }
    receipt_path = out / "python-lane-payload-build-manifest.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt["receipt_path"] = str(receipt_path.as_posix())
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    parser.add_argument("--out", required=True)
    parser.add_argument("--builder-python", default=sys.executable)
    parser.add_argument("--skip-wheel-build", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = build_payloads(args)
    except PayloadBuildError as exc:
        print(json.dumps({"verdict": "FAIL", "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"verdict": "PASS", "receipt_path": receipt["receipt_path"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
