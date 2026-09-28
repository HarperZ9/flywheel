"""The Node lane stager: pinned archives in, a checked stage folder out.

Every archive is checked against its pin in ``packaging/node-lane-payloads.json``
before anything is extracted. A checksum file published next to an archive is a
cross-check: when it disagrees with the pin, or does not list the archive, the
stage refuses. The tests run offline against fixture archives.
"""
from __future__ import annotations

import base64
import copy
import io
import json
import tarfile
import zipfile
from hashlib import sha256, sha512
from pathlib import Path

import pytest

from scripts.frozen_payload_datas import (
    NODE_STAGE_RECEIPT, FreezeInputError, node_lane_stage_datas)
from scripts.stage_node_lanes import StageError, load_manifest, main, stage_node_lanes

REPO = Path(__file__).resolve().parents[1]
NODE_ROOT = "node-v0.0.0-win-x64"


def _hex(data: bytes) -> str:
    return sha256(data).hexdigest()


def _tgz(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _package(name: str, version: str, entry: str) -> dict[str, bytes]:
    return {
        "package/package.json": json.dumps({"name": name, "version": version}).encode(),
        f"package/{entry}": b"// entry\n",
        "package/LICENSE": b"license text\n",
    }


def _fixture(tmp_path: Path) -> tuple[dict, Path]:
    """A manifest and an artifact folder whose pins all agree."""
    art = tmp_path / "artifacts"
    art.mkdir()
    node_exe, license_text = b"fake node binary", b"node license\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{NODE_ROOT}/node.exe", node_exe)
        zf.writestr(f"{NODE_ROOT}/LICENSE", license_text)
        zf.writestr(f"{NODE_ROOT}/npm.cmd", b"not staged")
    (art / "node.zip").write_bytes(buf.getvalue())
    (art / "SHASUMS256.txt").write_text(f"{_hex(buf.getvalue())}  node.zip\n", encoding="utf-8")
    learn = _tgz(_package("@x/learn", "1.6.0", "src/mcp.mjs"))
    (art / "learn.tgz").write_bytes(learn)
    telos = _tgz(_package("project-telos-mcp", "0.4.1", "demo/telos-mcp.mjs"))
    (art / "telos.tgz").write_bytes(telos)
    (art / "TELOS-SUMS.txt").write_text(f"{_hex(telos)} *telos.tgz\n", encoding="utf-8")
    manifest = {
        "schema": "flywheel.node-lane-payloads/v1",
        "node_runtime": {
            "name": "node", "version": "v0.0.0", "platform": "win-x64",
            "url": "https://nodejs.org/dist/v0.0.0/node.zip", "file": "node.zip",
            "sha256": _hex(buf.getvalue()),
            "checksums_url": "https://nodejs.org/dist/v0.0.0/SHASUMS256.txt",
            "checksums_file": "SHASUMS256.txt", "archive_root": NODE_ROOT,
            "members": {"node.exe": _hex(node_exe), "LICENSE": _hex(license_text)}},
        "lanes": [
            {"lane": "learn", "package": "@x/learn", "version": "1.6.0", "source": "npm",
             "url": "https://registry.npmjs.org/learn.tgz", "file": "learn.tgz",
             "integrity": "sha512-" + base64.b64encode(sha512(learn).digest()).decode(),
             "entry": "src/mcp.mjs", "static_tool_names": ["learn_doctor"]},
            {"lane": "telos", "package": "project-telos-mcp", "version": "0.4.1",
             "source": "github-release", "url": "https://github.com/x/telos.tgz",
             "file": "telos.tgz", "sha256": _hex(telos),
             "checksums_url": "https://github.com/x/SUMS", "checksums_file": "TELOS-SUMS.txt",
             "entry": "demo/telos-mcp.mjs", "static_tool_names": ["telos.status"]},
        ],
    }
    return manifest, art


def _stage(tmp_path, manifest, art, **kw):
    return stage_node_lanes(tmp_path / "stage", manifest=manifest, artifact_dir=art,
                            offline=True, **kw)


def test_stage_extracts_node_and_both_lanes_and_writes_a_passing_receipt(tmp_path):
    manifest, art = _fixture(tmp_path)
    receipt = _stage(tmp_path, manifest, art)
    stage = tmp_path / "stage"
    assert (stage / "node" / "node.exe").read_bytes() == b"fake node binary"
    assert (stage / "node" / "LICENSE").is_file()
    assert not (stage / "node" / "npm.cmd").exists()
    assert (stage / "learn" / "src" / "mcp.mjs").is_file()
    assert (stage / "telos" / "demo" / "telos-mcp.mjs").is_file()
    assert receipt["verdict"] == "PASS"
    assert [lane["lane"] for lane in receipt["lanes"]] == ["learn", "telos"]
    assert receipt["node_runtime"]["version"] == "v0.0.0"
    on_disk = json.loads((stage / NODE_STAGE_RECEIPT).read_text(encoding="utf-8"))
    assert on_disk == receipt
    # the fixture holds nothing, so the freeze accepts this folder; the committed
    # manifest holds telos (O-8), so the default freeze refuses it
    assert node_lane_stage_datas(str(stage), held=()) == [(str(stage.resolve()), "node-lanes")]
    with pytest.raises(FreezeInputError, match="held"):
        node_lane_stage_datas(str(stage))


def test_a_telos_archive_that_differs_from_its_pin_refuses(tmp_path):
    manifest, art = _fixture(tmp_path)
    (art / "telos.tgz").write_bytes(_tgz(_package("project-telos-mcp", "0.4.1", "demo/x.mjs")))
    with pytest.raises(StageError, match="telos.tgz sha256"):
        _stage(tmp_path, manifest, art)
    assert not (tmp_path / "stage" / "telos").exists()


def test_a_published_checksum_that_disagrees_with_the_pin_refuses(tmp_path):
    manifest, art = _fixture(tmp_path)
    (art / "TELOS-SUMS.txt").write_text("0" * 64 + "  telos.tgz\n", encoding="utf-8")
    with pytest.raises(StageError, match="TELOS-SUMS.txt"):
        _stage(tmp_path, manifest, art)


def test_a_checksum_file_that_does_not_list_the_archive_refuses(tmp_path):
    manifest, art = _fixture(tmp_path)
    (art / "SHASUMS256.txt").write_text("0" * 64 + "  other.zip\n", encoding="utf-8")
    with pytest.raises(StageError, match="does not list node.zip"):
        _stage(tmp_path, manifest, art)


def test_learn_integrity_mismatch_refuses(tmp_path):
    manifest, art = _fixture(tmp_path)
    manifest["lanes"][0]["integrity"] = "sha512-" + base64.b64encode(b"x" * 64).decode()
    with pytest.raises(StageError, match="learn.tgz integrity"):
        _stage(tmp_path, manifest, art)


def test_a_node_member_that_differs_from_its_pin_refuses(tmp_path):
    manifest, art = _fixture(tmp_path)
    manifest["node_runtime"]["members"]["node.exe"] = "f" * 64
    with pytest.raises(StageError, match="node.exe sha256"):
        _stage(tmp_path, manifest, art)


def test_a_package_whose_version_differs_from_the_pin_refuses(tmp_path):
    manifest, art = _fixture(tmp_path)
    manifest = copy.deepcopy(manifest)
    manifest["lanes"][1]["version"] = "0.2.0"
    with pytest.raises(StageError, match="telos: package.json says project-telos-mcp 0.4.1"):
        _stage(tmp_path, manifest, art)


@pytest.mark.parametrize("member", ["package/../evil.mjs", "/abs.mjs", "other/x.mjs"])
def test_an_archive_member_outside_package_refuses(tmp_path, member):
    manifest, art = _fixture(tmp_path)
    files = _package("@x/learn", "1.6.0", "src/mcp.mjs")
    files[member] = b"x"
    learn = _tgz(files)
    (art / "learn.tgz").write_bytes(learn)
    manifest["lanes"][0]["integrity"] = "sha512-" + base64.b64encode(sha512(learn).digest()).decode()
    with pytest.raises(StageError, match="unsafe archive member"):
        _stage(tmp_path, manifest, art)
    assert not (tmp_path / "evil.mjs").exists()


def test_a_symlink_member_refuses(tmp_path):
    manifest, art = _fixture(tmp_path)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in _package("@x/learn", "1.6.0", "src/mcp.mjs").items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo("package/src/link.mjs")
        link.type, link.linkname = tarfile.SYMTYPE, "../../../outside"
        tar.addfile(link)
    (art / "learn.tgz").write_bytes(buf.getvalue())
    manifest["lanes"][0]["integrity"] = (
        "sha512-" + base64.b64encode(sha512(buf.getvalue()).digest()).decode())
    with pytest.raises(StageError, match="unsafe archive member"):
        _stage(tmp_path, manifest, art)


def test_offline_with_a_missing_archive_refuses_without_fetching(tmp_path):
    manifest, art = _fixture(tmp_path)
    (art / "learn.tgz").unlink()

    def no_network(url, dest):
        raise AssertionError("offline stage fetched " + url)

    with pytest.raises(StageError, match="learn.tgz is not in the artifact folder"):
        _stage(tmp_path, manifest, art, fetch=no_network)


def test_online_stage_fetches_only_the_missing_archives(tmp_path):
    manifest, art = _fixture(tmp_path)
    kept = (art / "learn.tgz").read_bytes()
    (art / "learn.tgz").unlink()
    fetched = []

    def fetch(url, dest):
        fetched.append(url)
        Path(dest).write_bytes(kept)

    stage_node_lanes(tmp_path / "stage", manifest=manifest, artifact_dir=art,
                     offline=False, fetch=fetch)
    assert fetched == ["https://registry.npmjs.org/learn.tgz"]


def test_a_stage_root_holding_other_files_is_never_wiped(tmp_path):
    manifest, art = _fixture(tmp_path)
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "precious.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(StageError, match="not a previous Node lane stage"):
        _stage(tmp_path, manifest, art)
    assert (stage / "precious.txt").read_text(encoding="utf-8") == "keep"


def test_a_previous_stage_is_replaced(tmp_path):
    manifest, art = _fixture(tmp_path)
    _stage(tmp_path, manifest, art)
    (tmp_path / "stage" / "learn" / "stale.mjs").write_text("old", encoding="utf-8")
    _stage(tmp_path, manifest, art)
    assert not (tmp_path / "stage" / "learn" / "stale.mjs").exists()


def test_a_failed_stage_is_marked_and_a_rerun_replaces_it(tmp_path):
    manifest, art = _fixture(tmp_path)
    good = manifest["lanes"][1]["sha256"]
    manifest["lanes"][1]["sha256"] = "0" * 64
    with pytest.raises(StageError):
        _stage(tmp_path, manifest, art)
    with pytest.raises(RuntimeError, match="STAGING"):
        node_lane_stage_datas(str(tmp_path / "stage"))
    manifest["lanes"][1]["sha256"] = good
    assert _stage(tmp_path, manifest, art)["verdict"] == "PASS"


def test_main_writes_a_failing_receipt_the_freeze_refuses(tmp_path, capsys):
    manifest, art = _fixture(tmp_path)
    manifest["lanes"][1]["sha256"] = "0" * 64
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    stage = tmp_path / "stage"
    code = main(["--stage-root", str(stage), "--manifest", str(path),
                 "--artifact-dir", str(art), "--offline"])
    assert code == 1
    report = json.loads(capsys.readouterr().out)
    assert report["verdict"] == "FAIL" and "telos.tgz sha256" in report["error"]
    with pytest.raises(RuntimeError, match="not PASS"):
        node_lane_stage_datas(str(stage))


def test_the_committed_manifest_pins_the_reviewed_releases():
    manifest = load_manifest(REPO / "packaging" / "node-lane-payloads.json")
    node = manifest["node_runtime"]
    assert node["version"] == "v24.21.0" and node["lts"] == "Krypton"
    assert node["sha256"] == "158f7685b44de51f6c0df1d153526cbcd3e1bc739a8dfc607721cef75de9e541"
    assert node["members"]["node.exe"] == (
        "ba4e6d110e8c1592a1ecd390f6b05f3da124b13871a5be62b341a07a853c6c32")
    lanes = {row["lane"]: row for row in manifest["lanes"]}
    assert lanes["telos"]["sha256"] == (
        "9797ea6bacb7a62cee0aee23c2a81b000e51117a5b2bcde4e218d9df81a56264")
    assert lanes["telos"]["tag"] == "v0.4.1" and lanes["telos"]["version"] == "0.4.1"
    assert lanes["learn"]["integrity"].startswith("sha512-n1IPaGKosdu8nwat")
    assert len(lanes["learn"]["static_tool_names"]) == 15
    assert len(lanes["telos"]["static_tool_names"]) == 41


def test_the_manifest_loader_refuses_plain_http_and_unknown_hosts(tmp_path):
    manifest, _ = _fixture(tmp_path)
    for mutate in (lambda m: m["lanes"][0].update(url="http://registry.npmjs.org/learn.tgz"),
                   lambda m: m["node_runtime"].update(url="https://example.com/node.zip")):
        bad = copy.deepcopy(manifest)
        mutate(bad)
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(StageError, match="url"):
            load_manifest(path)
