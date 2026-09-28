"""SP-25, EN-C13: exports leave custody in plaintext, so credentials are
redacted by default. A planted fake credential is absent by default and
present with no_redact; home paths become ~; tags differ between two exports
and match with stable tags; a gateway trace with a catalog hit is exported
unchanged and listed with its hit counts."""
import json

import pytest

from delete_fixtures import OWNER
from export_fixtures import EMAIL, TOKEN, export_bytes, home_text, planted
from harness.trace_export import export, export_digest
from harness.trace_presence import confirm
from harness.trace_redact import placeholder_tags
from harness.trace_witness import MemorySink


@pytest.fixture
def world(tmp_path, monkeypatch):
    with planted(tmp_path, monkeypatch) as (home, refs):
        yield home, refs, tmp_path


def _export(home, out, **options):
    ref = confirm(home / "state", OWNER, "export", export_digest(out, options), "export")
    return export(home, OWNER, out, ref, sink=MemorySink(), **options)


def test_a_fake_credential_is_absent_by_default_and_present_without_redaction(world):
    home, _, base = world
    _export(home, base / "a")
    _export(home, base / "b", redact=False)
    assert TOKEN.encode() not in export_bytes(base / "a")
    assert b"[REDACTED:github_token:" in export_bytes(base / "a")
    assert TOKEN.encode() in export_bytes(base / "b")
    manifest = json.loads((base / "a" / "manifest.json").read_text())
    assert manifest["redaction"]["mode"]["credentials"] is True
    assert manifest["redaction_counts"]["github_token"] >= 1


def test_home_paths_become_a_tilde(world):
    home, refs, base = world
    _export(home, base / "a")
    text = (base / "a" / "stores" / "CT" / f"{refs['turn']}.jsonl").read_text(encoding="utf-8")
    assert home_text() not in text and json.dumps(home_text())[1:-1] not in text
    assert "look in ~ for the notes" in text


def test_tags_differ_between_exports_and_match_with_stable_tags(world):
    home, _, base = world
    for name, stable in (("a", False), ("b", False), ("c", True), ("d", True)):
        _export(home, base / name, stable_tags=stable)
    tags = {n: placeholder_tags(export_bytes(base / n).decode("utf-8", "replace"))
            for n in "abcd"}
    assert tags["a"] and tags["a"] != tags["b"]
    assert tags["c"] == tags["d"]


def test_a_trace_with_a_catalog_hit_is_exported_unchanged_and_listed(world):
    home, refs, base = world
    _export(home, base / "a", redact_personal=True)
    trace_file = base / "a" / "stores" / "S1" / f"{refs['trace']}.jsonl"
    assert EMAIL in trace_file.read_text(encoding="utf-8")
    manifest = json.loads((base / "a" / "manifest.json").read_text())
    listed = {t["item_ref"]: t for t in manifest["unredacted_traces"]}
    assert listed[refs["trace"]]["counts"]["email"] == 1
    assert "unredacted" in (base / "a" / "README.txt").read_text()
