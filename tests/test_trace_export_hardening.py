"""Export hardening (7.5, I8): a compressed rollout is decompressed before
redaction (or omitted, never mangled); a zip is protected like the folder; an
existing folder, a link on the path and a folder behind a junction are
refused before presence is used; Claude Code's dash-encoded home folder is
redacted; a partial export is recorded; the verifier refuses hostile paths
and links and prints control characters escaped."""
import json
import os
import subprocess
import sys

import pytest

from codex_fixtures import FAKE_MAGIC, FakeZstd, codex_tree
from delete_fixtures import OWNER
from export_fixtures import planted
from harness import trace_export, trace_zstd
from harness.trace_custody_ledger import CustodyLedger
from harness.trace_export import ExportError, Redactor, export, export_digest
from harness.trace_export_verify import main as verify_main, verify
from harness.trace_import_codex import plan_codex
from harness.trace_import_core import run_import
from harness.trace_presence import confirm
from harness.trace_witness import MemorySink
from import_fixtures import link_dir


@pytest.fixture
def world(tmp_path, monkeypatch):
    with planted(tmp_path, monkeypatch) as (home, refs):
        yield home, tmp_path


def _export(home, out, **options):
    ref = confirm(home / "state", OWNER, "export", export_digest(out, options), "export")
    return export(home, OWNER, out, ref, sink=MemorySink(), **options)


def _with_compressed_rollout(home, base, monkeypatch):
    monkeypatch.setattr(trace_zstd, "module", lambda: FakeZstd())
    run_import(home, plan_codex(home, root=codex_tree(base)))


def test_a_compressed_rollout_is_decompressed_then_redacted(world, monkeypatch):
    home, base = world
    _with_compressed_rollout(home, base, monkeypatch)
    report = _export(home, base / "out")
    assert report["state"] == "EXPORTED", report
    manifest = json.loads((base / "out" / "manifest.json").read_text())
    exported = b"".join((base / "out" / f["path"]).read_bytes() for f in manifest["files"]
                        if f["store"] == "IM")
    assert FAKE_MAGIC not in exported
    assert b'"response_item"' in exported


def test_without_zstd_a_redacted_export_omits_the_rollout_and_says_why(world, monkeypatch):
    home, base = world
    _with_compressed_rollout(home, base, monkeypatch)
    monkeypatch.setattr(trace_zstd, "module", lambda: None)
    _export(home, base / "out")
    manifest = json.loads((base / "out" / "manifest.json").read_text())
    assert any("compressed rollout not decompressed" in o["reason"]
               for o in manifest["omissions"])
    _export(home, base / "raw", redact=False)
    raw = list((base / "raw" / "stores" / "IM").glob("*.jsonl.zst"))
    assert raw and raw[0].read_bytes().startswith(FAKE_MAGIC)


def test_a_zip_is_protected_before_it_is_filled(world, monkeypatch):
    home, base = world
    protected = []
    real = trace_export.protect
    monkeypatch.setattr(trace_export, "protect",
                        lambda target, **k: protected.append((target, k)) or real(target, **k))
    report = _export(home, base / "out", zip=True)
    archive = base / "out.zip"
    assert report["path"] == str(archive) and verify(archive) == ("MATCH", [])
    assert (archive, {"directory": False}) in protected


def test_an_existing_folder_or_zip_is_refused_before_presence_is_used(world):
    home, base = world
    (base / "empty").mkdir()
    ref = confirm(home / "state", OWNER, "export", export_digest(base / "empty", {}), "x")
    with pytest.raises(ExportError) as refused:
        export(home, OWNER, base / "empty", ref, sink=MemorySink())
    assert refused.value.code == "DESTINATION_EXISTS"
    (base / "taken.zip").write_bytes(b"x")
    with pytest.raises(ExportError):
        _export(home, base / "taken", zip=True)
    assert [e for e in CustodyLedger(home, OWNER).entries() if e["kind"] == "export"] == []


def test_a_junction_on_the_destination_path_is_refused(world):
    home, base = world
    target = base / "real"
    target.mkdir()
    if not link_dir(base / "hop", target):
        pytest.skip("cannot create a junction here")
    with pytest.raises(ExportError) as refused:
        _export(home, base / "hop" / "out")
    assert refused.value.code == "DESTINATION_LINK"
    if not link_dir(base / "into-home", home / "state"):
        pytest.skip("cannot create a junction here")
    with pytest.raises(ExportError):
        _export(home, base / "into-home" / "out")


def test_the_dash_encoded_home_folder_is_redacted():
    from pathlib import Path
    import re
    encoded = re.sub(r"[^A-Za-z0-9]", "-", str(Path.home()))
    redactor = Redactor(None, OWNER, {"redact": True, "redact_personal": False,
                                      "stable_tags": False})
    line = json.dumps({"rel": f"projects/{encoded}-dev-demo/abc.jsonl"})
    assert encoded not in redactor.line(line)
    assert "projects/~-dev-demo" in redactor.line(line)


def test_a_partial_export_is_recorded_in_the_ledger(world, monkeypatch):
    home, base = world

    def fail(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(trace_export, "_write", fail)
    report = _export(home, base / "out")
    assert report["state"] == "INCOMPLETE"
    entry = CustodyLedger(home, OWNER).entries()[-1]
    assert entry["kind"] == "export" and entry["fields"]["reason_code"] == "OSError"


def test_the_verifier_refuses_hostile_trace_paths_and_links(world, capsys):
    home, base = world
    out = base / "out"
    _export(home, out)
    manifest = json.loads((out / "manifest.json").read_text())
    manifest["traces"][0]["path"] = "stores/S1/\x1b[2Jevil.jsonl"
    (out / "manifest.json").write_text(json.dumps(manifest))
    code, reasons = verify(out)
    assert code == "UNVERIFIABLE"
    assert verify_main([str(out)]) == 2
    assert "\x1b" not in capsys.readouterr().out
    fresh = base / "fresh"
    _export(home, fresh)
    outside = base / "elsewhere"
    outside.mkdir()
    if link_dir(fresh / "stores" / "linked", outside):
        assert verify(fresh)[0] == "UNVERIFIABLE"


def test_printed_reasons_escape_control_characters(tmp_path, capsys):
    folder = tmp_path / "x"
    folder.mkdir()
    (folder / "manifest.json").write_text(json.dumps({"files": [], "root_sha256": "0"}))
    (folder / "note\x07.txt").write_bytes(b"x") if os.name != "nt" else None
    done = subprocess.run([sys.executable, "-I", "-S", trace_export.__file__.replace(
        "trace_export.py", "trace_export_verify.py"), str(folder)], capture_output=True)
    assert b"\x07" not in done.stdout and b"\x1b" not in done.stdout
