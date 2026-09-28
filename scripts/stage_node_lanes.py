"""Stage the Node lanes (learn, telos) and a portable Node runtime for the freeze.

The frozen gateway ships this folder as ``_internal/node-lanes``
(``scripts/frozen_payload_datas.py`` refuses to freeze without it)::

    <stage>/node/node.exe, LICENSE     Node LTS, from the pinned nodejs.org zip
    <stage>/learn/...                   @harperz9/learn, from the pinned npm tarball
    <stage>/telos/...                   project-telos-mcp, from the pinned GitHub release,
                                        only with --include-held (see below)
    <stage>/node-lane-stage.json        the receipt; the freeze requires verdict PASS

Every input is pinned in ``packaging/node-lane-payloads.json``. An archive is
checked against its pin before anything is extracted. The published checksum
file next to an archive (nodejs.org ``SHASUMS256.txt``, the telos release
``SHA256SUMS.txt``) must agree with the pin; it comes from the same release, so
it is a cross-check and never the trust root.

Archives come from ``--artifact-dir`` when present there (the default is a
``<stage>-downloads`` folder beside the stage, never inside it, since the whole
stage ships). ``--offline`` refuses to download a missing one.

A row with a ``hold`` field is skipped and listed under ``held`` in the receipt,
unless ``--include-held`` is passed. telos carries the O-8 hold: its release
contents are under review, so no freeze or installer stages it by default, and
``scripts/frozen_payload_datas.py`` refuses a stage that lists a held lane.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts._node_lane_archive import (  # noqa: E402
    StageError, check_integrity, check_sha256, cross_check, extract_npm_tgz,
    extract_zip_members, fetch as https_fetch, sha256_file, tree_bytes)

SCHEMA = "flywheel.node-lane-payloads/v1"
RECEIPT_SCHEMA = "flywheel.node-lane-stage/v1"
RECEIPT = "node-lane-stage.json"
REPO = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO / "packaging" / "node-lane-payloads.json"
ALLOWED_HOSTS = ("https://nodejs.org/dist/", "https://registry.npmjs.org/",
                 "https://github.com/")
Fetch = Callable[[str, Path], None]


def _check_url(value: Any, where: str) -> None:
    if not isinstance(value, str) or not value.startswith(ALLOWED_HOSTS):
        raise StageError(f"{where} url must be https on {', '.join(ALLOWED_HOSTS)}")


def load_manifest(path: Path) -> dict[str, Any]:
    """Read the pinned manifest and refuse a malformed or off-host entry."""
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise StageError(f"manifest schema is not {SCHEMA}")
    node = manifest["node_runtime"]
    for key in ("url", "checksums_url"):
        _check_url(node.get(key), f"node_runtime {key}")
    for row in manifest["lanes"]:
        _check_url(row.get("url"), f"{row.get('lane')} url")
        if row.get("checksums_url"):
            _check_url(row["checksums_url"], f"{row['lane']} checksums_url")
        if not (row.get("sha256") or row.get("integrity")):
            raise StageError(f"{row.get('lane')} has no sha256 or integrity pin")
    return manifest


def _artifact(art: Path, name: str, url: str, offline: bool, fetch: Fetch) -> Path:
    path = art / name
    if path.is_file():
        return path
    if offline:
        raise StageError(f"{name} is not in the artifact folder and the stage is offline")
    art.mkdir(parents=True, exist_ok=True)
    fetch(url, path)
    return path


def _prepare_stage(stage: Path) -> None:
    """Empty a previous stage; refuse a folder that holds anything else."""
    if stage.exists():
        entries = list(stage.iterdir())
        if entries and not (stage / RECEIPT).is_file():
            raise StageError(f"{stage} is not a previous Node lane stage; refusing to empty it")
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    # Until the PASS receipt replaces it, the folder is marked as a stage in
    # progress: the freeze refuses it and a re-run may empty it.
    _write_receipt(stage, {"schema": RECEIPT_SCHEMA, "verdict": "STAGING"})


def _write_receipt(stage: Path, receipt: dict) -> None:
    (stage / RECEIPT).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")


def _stage_node(node: dict, stage: Path, art: Path, offline: bool, fetch: Fetch) -> dict:
    archive = _artifact(art, node["file"], node["url"], offline, fetch)
    check_sha256(archive, node["sha256"], node["file"])
    sums = _artifact(art, node["checksums_file"], node["checksums_url"], offline, fetch)
    cross_check(sums, node["file"], node["sha256"])
    extract_zip_members(archive, node["archive_root"], node["members"], stage / "node")
    files, size = tree_bytes(stage / "node")
    return {"version": node["version"], "platform": node["platform"],
            "archive_sha256": node["sha256"], "members": dict(node["members"]),
            "files": files, "bytes": size}


def _check_package(row: dict, folder: Path) -> None:
    try:
        meta = json.loads((folder / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StageError(f"{row['lane']}: package.json unreadable: {exc}") from exc
    found = (meta.get("name"), meta.get("version"))
    if found != (row["package"], row["version"]):
        raise StageError(f"{row['lane']}: package.json says {found[0]} {found[1]}, "
                         f"the pin says {row['package']} {row['version']}")
    if not (folder / row["entry"]).is_file():
        raise StageError(f"{row['lane']}: entry {row['entry']} is missing")


def _stage_lane(row: dict, stage: Path, art: Path, offline: bool, fetch: Fetch) -> dict:
    archive = _artifact(art, row["file"], row["url"], offline, fetch)
    if row.get("integrity"):
        check_integrity(archive, row["integrity"], row["file"])
    if row.get("sha256"):
        check_sha256(archive, row["sha256"], row["file"])
    if row.get("checksums_url"):
        sums = _artifact(art, row["checksums_file"], row["checksums_url"], offline, fetch)
        cross_check(sums, row["file"], row["sha256"])
    tmp = stage / f".{row['lane']}.partial"
    extract_npm_tgz(archive, tmp)
    _check_package(row, tmp)
    tmp.replace(stage / row["lane"])
    files, size = tree_bytes(stage / row["lane"])
    return {"lane": row["lane"], "package": row["package"], "version": row["version"],
            "source": row["source"], "archive_sha256": sha256_file(archive),
            "entry": row["entry"], "files": files, "bytes": size}


def held_rows(manifest: dict) -> list[dict]:
    """The manifest rows under a hold, as {lane, hold}."""
    return [{"lane": row["lane"], "hold": str(row["hold"])}
            for row in manifest["lanes"] if row.get("hold")]


def stage_node_lanes(stage_root: Path, *, manifest: dict, artifact_dir: Path,
                     offline: bool = False, fetch: Fetch = https_fetch,
                     include_held: bool = False) -> dict:
    """Stage every pinned input into ``stage_root`` and return the PASS receipt.

    A held row is skipped unless ``include_held``; the receipt lists it."""
    stage, art = Path(stage_root), Path(artifact_dir)
    _prepare_stage(stage)
    node = _stage_node(manifest["node_runtime"], stage, art, offline, fetch)
    rows = [row for row in manifest["lanes"] if include_held or not row.get("hold")]
    lanes = [_stage_lane(row, stage, art, offline, fetch) for row in rows]
    staged = {lane["lane"] for lane in lanes}
    receipt = {
        "schema": RECEIPT_SCHEMA, "verdict": "PASS",
        "manifest_sha256": _canonical_sha256(manifest),
        "node_runtime": node, "lanes": lanes,
        "held": [row for row in held_rows(manifest) if row["lane"] not in staged],
        "total_bytes": node["bytes"] + sum(lane["bytes"] for lane in lanes),
    }
    _write_receipt(stage, receipt)
    return receipt


def _canonical_sha256(value: Any) -> str:
    blob = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _write_failure(stage: Path, error: str) -> None:
    """Leave a FAIL receipt so a later freeze refuses this folder."""
    try:
        if stage.exists() and (not any(stage.iterdir()) or (stage / RECEIPT).is_file()):
            shutil.rmtree(stage)
        if not stage.exists():
            stage.mkdir(parents=True)
            _write_receipt(stage, {"schema": RECEIPT_SCHEMA, "verdict": "FAIL", "error": error})
    except OSError as exc:
        print(f"could not write the failing receipt: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage-root", required=True)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--artifact-dir", default=None,
                        help="archive folder; default <stage-root>-downloads")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--include-held", action="store_true",
                        help="also stage rows under a hold (the freeze refuses the result)")
    args = parser.parse_args(argv)
    stage = Path(args.stage_root).resolve()
    art = Path(args.artifact_dir).resolve() if args.artifact_dir else Path(
        str(stage) + "-downloads")
    try:
        receipt = stage_node_lanes(stage, manifest=load_manifest(Path(args.manifest)),
                                   artifact_dir=art, offline=args.offline,
                                   include_held=args.include_held)
    except (StageError, OSError, ValueError, KeyError) as exc:
        error = f"{type(exc).__name__}: {exc}"
        _write_failure(stage, error)
        print(json.dumps({"verdict": "FAIL", "error": error}, sort_keys=True))
        return 1
    print(json.dumps({"verdict": "PASS", "stage": str(stage),
                      "total_bytes": receipt["total_bytes"],
                      "lanes": {lane["lane"]: lane["version"] for lane in receipt["lanes"]},
                      "held": [row["lane"] for row in receipt["held"]],
                      "node": receipt["node_runtime"]["version"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
