"""SP-36: the verifier refuses unsafe member paths before opening anything,
and reads a zip in memory under caps, never extracting it."""
import hashlib
import json
import zipfile

import pytest

from harness import trace_export_verify as verifier
from harness.trace_export_manifest import root_digest

BAD = ["C:/Windows/win.ini", "/etc/passwd", "../outside.txt", "stores/../../x.jsonl",
       "D:relative.txt", "//server/share/x", "\\\\server\\share\\x", "\\\\?\\C:\\x",
       "\\\\.\\PhysicalDrive0", "stores/S1/a.jsonl:stream", "stores/CON", "stores/nul.txt",
       "stores/com1.jsonl", "LPT9", "stores\\S1\\a.jsonl"]


def _write_export(folder, files: dict, extra_entries=()):
    folder.mkdir(parents=True, exist_ok=True)
    entries = []
    for rel, data in files.items():
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        entries.append({"path": rel, "sha256": hashlib.sha256(data).hexdigest(),
                        "bytes": len(data), "store": "CT", "item_ref": "x"})
    entries += list(extra_entries)
    manifest = {"schema": "flywheel.trace-export/v1", "files": entries, "traces": [],
                "lineage": []}
    manifest["root_sha256"] = root_digest(manifest)
    (folder / "manifest.json").write_text(json.dumps(manifest))
    return folder


@pytest.mark.parametrize("bad", BAD)
def test_an_unsafe_member_path_is_unverifiable(tmp_path, bad):
    folder = _write_export(tmp_path / "e", {"stores/CT/a.jsonl": b"{}\n"},
                           [{"path": bad, "sha256": "0" * 64, "bytes": 1, "store": "CT",
                             "item_ref": "y"}])
    code, reasons = verifier.verify(folder)
    assert code == "UNVERIFIABLE" and any("unsafe path" in r for r in reasons), (bad, reasons)


def test_a_valid_export_in_a_zip_verifies_in_memory(tmp_path):
    folder = _write_export(tmp_path / "e", {"stores/CT/a.jsonl": b'{"a":1}\n'})
    archive = tmp_path / "e.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in folder.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(folder).as_posix())
    assert verifier.verify(archive) == ("MATCH", [])


def _zip_with(tmp_path, members: dict):
    archive = tmp_path / "big.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return archive


def test_a_zip_over_the_ratio_cap_is_unverifiable_without_extraction(tmp_path):
    archive = _zip_with(tmp_path, {"manifest.json": b"{}", "stores/CT/z.jsonl": b"0" * 4_000_000})
    before = sorted(p.name for p in tmp_path.iterdir())
    code, reasons = verifier.verify(archive)
    assert code == "UNVERIFIABLE" and any("ratio" in r for r in reasons)
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_a_zip_over_the_member_cap_is_unverifiable(tmp_path, monkeypatch):
    monkeypatch.setattr(verifier, "MAX_MEMBERS", 3)
    archive = _zip_with(tmp_path, {f"m{i}.txt": b"x" for i in range(5)})
    code, reasons = verifier.verify(archive)
    assert code == "UNVERIFIABLE" and any("members" in r for r in reasons)


def test_a_zip_over_the_total_size_cap_is_unverifiable(tmp_path, monkeypatch):
    monkeypatch.setattr(verifier, "MAX_TOTAL", 10)
    archive = _zip_with(tmp_path, {"manifest.json": b"{}", "a.txt": b"abcdefghijkl"})
    code, reasons = verifier.verify(archive)
    assert code == "UNVERIFIABLE" and any("size" in r for r in reasons)
