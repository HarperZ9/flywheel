"""I8: an owner export anyone can verify. MATCH for a fresh export; DRIFT
naming the file for a flipped byte or a broken trace chain; UNVERIFIABLE
naming a removed file; custody bytes other than the ledger unchanged; a
destination inside FLYWHEEL_HOME or under a sync root refused; presence
required; one ledger entry and one witness event."""
import json
import subprocess
import sys

import pytest

from delete_fixtures import OWNER
from export_fixtures import planted
from harness import trace_export_manifest as manifest_mod
from harness.trace_custody_ledger import CustodyLedger
from harness.trace_export import ExportError, export, export_digest
from harness.trace_export_verify import verify
from harness.trace_presence import PresenceError, confirm
from harness.trace_witness import MemorySink


@pytest.fixture
def world(tmp_path, monkeypatch):
    with planted(tmp_path, monkeypatch) as (home, refs):
        yield home, refs, tmp_path / "exported"


def _export(home, out, sink=None, **options):
    digest = export_digest(out, options)
    ref = confirm(home / "state", OWNER, "export", digest, "export")
    return export(home, OWNER, out, ref, sink=sink or MemorySink(), **options)


def test_a_fresh_export_verifies_and_runs_its_own_verifier(world):
    home, refs, out = world
    sink = MemorySink()
    report = _export(home, out, sink)
    assert report["state"] == "EXPORTED" and report["verify"] == "MATCH", report
    assert verify(out) == ("MATCH", [])
    done = subprocess.run([sys.executable, str(out / "verify.py"), str(out)],
                          capture_output=True, text=True)
    assert done.returncode == 0 and done.stdout.startswith("MATCH")
    manifest = json.loads((out / "manifest.json").read_text())
    assert {t["item_ref"] for t in manifest["traces"]} == {refs["trace"]}
    assert (out / "stores" / "CT" / f"{refs['turn']}.jsonl").is_file()
    assert "does_not_prove" in manifest and (out / "README.txt").is_file()
    entry = CustodyLedger(home, OWNER).entries()[-1]
    assert entry["kind"] == "export" and entry["fields"]["root_digest"] == manifest["root_sha256"]
    assert [e["kind"] for e in sink.read()] == ["export"]


def test_a_flipped_byte_gives_drift_naming_the_file(world):
    home, refs, out = world
    _export(home, out)
    target = out / "stores" / "CT" / f"{refs['turn']}.jsonl"
    raw = bytearray(target.read_bytes())
    raw[5] ^= 0x01
    target.write_bytes(bytes(raw))
    code, reasons = verify(out)
    assert code == "DRIFT" and any(f"stores/CT/{refs['turn']}.jsonl" in r for r in reasons)


def test_a_removed_file_is_unverifiable_and_named(world):
    home, refs, out = world
    _export(home, out)
    (out / "stores" / "S1" / f"{refs['trace']}.jsonl").unlink()
    code, reasons = verify(out)
    assert code == "UNVERIFIABLE" and any(refs["trace"] in r for r in reasons)


def test_a_broken_trace_chain_is_drift_even_with_matching_hashes(world):
    home, refs, out = world
    _export(home, out)
    rel = f"stores/S1/{refs['trace']}.jsonl"
    lines = (out / rel).read_bytes().splitlines()
    record = json.loads(lines[-1])
    record["payload"]["final"] = "rewritten"
    lines[-1] = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    (out / rel).write_bytes(b"\n".join(lines) + b"\n")
    manifest_mod.rehash(out)  # an attacker who also fixes the manifest
    code, reasons = verify(out)
    assert code == "DRIFT" and any(rel in r and "chain" in r for r in reasons)


def test_custody_bytes_other_than_the_ledger_are_unchanged(world):
    home, _, out = world
    digest = export_digest(out, {})
    ref = confirm(home / "state", OWNER, "export", digest, "export")

    def snapshot():
        skip = ("custody-ledger", "presence")
        return {p.relative_to(home).as_posix(): p.read_bytes() for p in home.rglob("*")
                if p.is_file() and not any(s in p.parts for s in skip)}
    before = snapshot()
    export(home, OWNER, out, ref, sink=MemorySink())
    assert snapshot() == before


def test_destinations_inside_custody_or_under_a_sync_root_are_refused(world, monkeypatch):
    home, _, out = world
    with pytest.raises(ExportError) as inside:
        _export(home, home / "exports")
    assert inside.value.code == "DESTINATION_IN_CUSTODY"
    onedrive = out.parent / "OneDrive - Example"
    onedrive.mkdir()
    monkeypatch.setenv("OneDriveCommercial", str(onedrive))
    with pytest.raises(ExportError) as synced:
        _export(home, onedrive / "export")
    assert synced.value.code == "DESTINATION_SYNC_ROOT"
    assert not (onedrive / "export").exists()


def test_presence_is_required_and_nothing_is_written_without_it(world):
    home, _, out = world
    with pytest.raises(PresenceError):
        export(home, OWNER, out, "prs_" + "0" * 32, sink=MemorySink())
    assert not out.exists()
    other = confirm(home / "state", OWNER, "export", export_digest(out, {"redact": False}), "x")
    with pytest.raises(PresenceError):
        export(home, OWNER, out, other, sink=MemorySink())
