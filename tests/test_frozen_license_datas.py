"""The frozen engine ships the license text of everything it redistributes.

The engine folder carries the Python runtime, OpenSSL through that runtime and
twelve lanes frozen from pinned source. Before this module only Canon's license
travelled with its code, so the installer redistributed eleven lanes and the
Python runtime with no license text beside them. These checks hold the freeze
inputs to one rule: every shipped component brings its text, each lane's text
matches the hash its manifest row pins, and a missing text stops the freeze.
"""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from scripts.frozen_license_datas import (
    INCORPORATED_DEST, LANE_LICENSE_DEST, PYTHON_LICENSE_DEST,
    incorporated_license_files, python_lane_license_datas,
    python_runtime_license_datas)
from scripts.frozen_payload_datas import FreezeInputError

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "packaging" / "python-lane-payloads.jsonl"
SPEC = REPO / "packaging" / "flywheel-gateway.spec"


def _digest(data: bytes) -> str:
    return "sha256:" + sha256(data).hexdigest()


def _fake_repo(tmp_path: Path, rows: list[dict]) -> Path:
    repo = tmp_path / "repo"
    (repo / "packaging").mkdir(parents=True)
    (repo / "packaging" / "python-lane-payloads.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return repo


def _row(lane: str, tag: str, text: bytes, *, path: str = "LICENSE",
         payload_slice: bool = False) -> dict:
    row = {"lane": lane, "owner_tag": tag,
           "owner_project": {"license_files": [
               {"path": path, "sha256": _digest(text), "bytes": len(text)}]}}
    if payload_slice:
        row["payload_slice"] = {"modules": []}
    return row


def _stage(source_root: Path, lane: str, tag: str, text: bytes) -> Path:
    base = source_root / f"{lane}-{tag}"
    base.mkdir(parents=True, exist_ok=True)
    (base / "LICENSE").write_bytes(text)
    return base / "LICENSE"


def test_runtime_ships_the_python_license_and_the_incorporated_texts(tmp_path):
    (tmp_path / "LICENSE.txt").write_text("PSF LICENSE AGREEMENT\n", encoding="utf-8")
    incorporated = tmp_path / "incorporated"
    incorporated.mkdir()
    (incorporated / "expat.txt").write_text("expat\n", encoding="utf-8")
    datas = python_runtime_license_datas(tmp_path, incorporated_dir=incorporated)
    assert (str(tmp_path / "LICENSE.txt"), PYTHON_LICENSE_DEST) in datas
    assert (str(incorporated / "expat.txt"), INCORPORATED_DEST) in datas


def test_runtime_refuses_a_build_python_without_its_license(tmp_path):
    incorporated = tmp_path / "incorporated"
    incorporated.mkdir()
    (incorporated / "expat.txt").write_text("expat\n", encoding="utf-8")
    with pytest.raises(FreezeInputError, match="LICENSE.txt"):
        python_runtime_license_datas(tmp_path, incorporated_dir=incorporated)


def test_runtime_refuses_an_empty_incorporated_folder(tmp_path):
    (tmp_path / "LICENSE.txt").write_text("PSF\n", encoding="utf-8")
    empty = tmp_path / "incorporated"
    empty.mkdir()
    with pytest.raises(FreezeInputError, match="incorporated"):
        python_runtime_license_datas(tmp_path, incorporated_dir=empty)


def test_each_lane_license_ships_under_its_lane_folder(tmp_path):
    text = b"Functional Source License\n"
    repo = _fake_repo(tmp_path, [_row("gather", "v1.8.2", text),
                                 _row("calibrate-pro", "v2.0.0", text, payload_slice=True)])
    source_root = tmp_path / "stage"
    gather = _stage(source_root, "gather", "v1.8.2", text)
    # A sliced lane freezes from "<lane>-<tag>-slice"; its license stays in the checkout.
    calibrate = _stage(source_root, "calibrate-pro", "v2.0.0", text)
    (source_root / "calibrate-pro-v2.0.0-slice" / "src").mkdir(parents=True)
    datas = python_lane_license_datas(repo, source_root)
    assert (str(gather.resolve()), f"{LANE_LICENSE_DEST}/gather") in datas
    assert (str(calibrate.resolve()), f"{LANE_LICENSE_DEST}/calibrate-pro") in datas


def test_a_lane_license_that_drifted_from_its_pin_stops_the_freeze(tmp_path):
    repo = _fake_repo(tmp_path, [_row("forum", "v1.14.0", b"pinned text\n")])
    _stage(tmp_path / "stage", "forum", "v1.14.0", b"edited text\n")
    with pytest.raises(FreezeInputError, match="forum"):
        python_lane_license_datas(repo, tmp_path / "stage")


def test_a_missing_lane_license_stops_the_freeze(tmp_path):
    repo = _fake_repo(tmp_path, [_row("mneme", "v0.4.2", b"text\n")])
    (tmp_path / "stage" / "mneme-v0.4.2").mkdir(parents=True)
    with pytest.raises(FreezeInputError, match="mneme"):
        python_lane_license_datas(repo, tmp_path / "stage")


def test_a_license_path_outside_the_checkout_is_refused(tmp_path):
    text = b"text\n"
    repo = _fake_repo(tmp_path, [_row("plexus", "v0.2.2", text, path="../LICENSE")])
    (tmp_path / "stage" / "plexus-v0.2.2").mkdir(parents=True)
    (tmp_path / "stage" / "LICENSE").write_bytes(text)
    with pytest.raises(FreezeInputError, match="escapes"):
        python_lane_license_datas(repo, tmp_path / "stage")


def test_a_lane_row_without_a_license_file_is_refused(tmp_path):
    row = _row("chorus", "v0.3.1", b"text\n")
    row["owner_project"]["license_files"] = []
    repo = _fake_repo(tmp_path, [row])
    with pytest.raises(FreezeInputError, match="chorus"):
        python_lane_license_datas(repo, tmp_path / "stage")


def test_every_manifest_lane_pins_a_license_file():
    rows = [json.loads(line) for line in MANIFEST.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    assert len(rows) == 12
    for row in rows:
        assert row["owner_project"]["license_files"], row["lane"]


def test_the_incorporated_texts_cover_the_python_components_the_engine_ships():
    files = incorporated_license_files()
    names = {path.stem for path in files}
    assert {"expat", "zlib", "libmpdec", "mersenne-twister", "siphash24",
            "strtod-and-dtoa", "cfuhash", "asyncio"} <= names
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert text.startswith("Source: Python 3.12 documentation"), path.name
        assert len(text.splitlines()) < 300, path.name


def test_the_gateway_spec_freezes_the_license_datas():
    text = SPEC.read_text(encoding="utf-8")
    assert "from scripts.frozen_license_datas import frozen_license_datas" in text
    assert "*license_datas," in text
