"""S14 adapters: export keeps metadata and drops the encrypted directory;
delete removes every spool file."""
from harness import trace_spool_adapters as adapters
from harness.capture_hooks import spool


def test_export_carries_metadata_and_never_the_protected_directory(tmp_path):
    spool.write_failure(tmp_path, "claude-code", "stop", "s-1", "p-1", "TOKEN_MISSING")
    spool.note_suppression(tmp_path, "codex", "s-2", "C:/work/secret-project")
    records = adapters.export_records(tmp_path)
    assert {r["kind"] for r in records} == {"failure", "suppression"}
    assert all("cwd_protected" not in r for r in records)
    assert "secret-project" not in repr(records)


def test_delete_removes_every_spool_file(tmp_path):
    spool.write_failure(tmp_path, "claude-code", "stop", "s-1", None, "TIMEOUT")
    spool.note_suppression(tmp_path, "codex", "s-2", "C:/work")
    assert adapters.delete_all(tmp_path)["removed"] == 3
    assert not any(p.is_file() for p in spool.spool_dir(tmp_path).parent.rglob("*"))
