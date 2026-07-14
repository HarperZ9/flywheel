"""Deterministic web snapshots (landscape import 8, the Kage pattern,
zero-dep): a cited source is frozen as the exact bytes that were read,
content-addressed — the hash IS the receipt, the archive re-checkable
offline forever. Same bytes, same hash, same path: idempotent by
construction. An unreachable source is a named error, never an empty
archive pretending."""

from harness.web_snapshot import SCHEMA, snapshot_url


def _runner(status=200, body=b"<html>evidence</html>",
            ctype="text/html"):
    def run(url):
        return status, {"Content-Type": ctype}, body, url
    return run


def test_the_bytes_are_frozen_content_addressed(tmp_path):
    doc = snapshot_url("https://example.org/paper", tmp_path,
                       runner=_runner())
    assert doc["schema"] == SCHEMA
    assert len(doc["sha256"]) == 64
    assert doc["bytes"] == 21
    assert doc["content_type"] == "text/html"
    saved = tmp_path / f"{doc['sha256']}.bin"
    assert saved.is_file()
    assert saved.read_bytes() == b"<html>evidence</html>"


def test_idempotent_same_bytes_same_archive(tmp_path):
    a = snapshot_url("https://example.org/x", tmp_path, runner=_runner())
    b = snapshot_url("https://example.org/x", tmp_path, runner=_runner())
    assert a["sha256"] == b["sha256"]
    assert len(list(tmp_path.glob("*.bin"))) == 1


def test_http_failure_is_a_named_error_not_an_empty_archive(tmp_path):
    doc = snapshot_url("https://example.org/gone", tmp_path,
                       runner=_runner(status=404, body=b"nope"))
    assert "error" in doc
    assert "404" in doc["error"]
    assert list(tmp_path.glob("*.bin")) == []
