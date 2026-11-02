"""Datapipe gates: robots rules, the terms gate, the licence check, the change log and the export manifest."""
import json

import pytest

from harness.datapipe import access, diffuse, filecheck
from harness.datapipe.access import GateError, SourceRecord
from harness.datapipe.schema import Column as C, Table, to_records, validate, write_jsonl

TERMS = b"<html><body>All data on this site is released under CC0 1.0 Universal.</body></html>"


class FakeWeb:
    def __init__(self, pages):
        self.pages, self.urls = pages, []

    def get(self, url, limit=None):
        self.urls.append(url)
        body = self.pages.get(url)
        return (200, body, url) if body is not None else (404, b"", url)


def _record():
    return SourceRecord("src", "A table", "https://example.org/data", "direct", "2026-10-31")


def test_robots_longest_match_wins_and_allow_wins_a_tie():
    rules = access.parse_robots("User-agent: *\nDisallow: /data/\nAllow: /data/open/\nDisallow: /x$\n")
    assert not access.robots_allowed(rules, "/data/private.csv")
    assert access.robots_allowed(rules, "/data/open/table.csv")
    assert not access.robots_allowed(rules, "/x") and access.robots_allowed(rules, "/xy")
    assert access.robots_allowed(access.parse_robots("User-agent: other\nDisallow: /\n"), "/anything")


def test_terms_gate_needs_the_quote_in_the_saved_page(tmp_path):
    web = FakeWeb({"https://example.org/terms": TERMS})
    rec = _record()
    assert not access.read_terms(web, rec, tmp_path, "https://example.org/terms", "cc0-1.0", "released under CC BY 4.0", "yes")
    assert rec.basis == "unknown" and "quote not found" in rec.notes
    assert access.read_terms(web, rec, tmp_path, "https://example.org/terms", "cc0-1.0", "released under CC0 1.0 Universal", "yes")
    assert rec.basis == "read" and rec.problems(tmp_path) == []
    (tmp_path / rec.terms_snapshot).write_bytes(TERMS.replace(b"CC0", b"CC-BY"))
    assert "terms snapshot hash differs" in rec.problems(tmp_path)


def test_fetch_refuses_basis_read_without_evidence(tmp_path):
    rec = _record()
    rec.basis = "read"
    with pytest.raises(GateError):
        access.gated_fetch(FakeWeb({}), rec, tmp_path, "https://example.org/data.csv", "data.csv")


def test_fetch_records_hash_and_writes_source_files(tmp_path):
    web = FakeWeb({"https://example.org/data.csv": b"a,b\n1,2\n"})
    rec = _record()
    path = access.gated_fetch(web, rec, tmp_path, "https://example.org/data.csv", "data.csv")
    assert path.read_bytes() == b"a,b\n1,2\n"
    assert rec.files[0]["sha256"] == access.sha256_bytes(b"a,b\n1,2\n")
    assert (tmp_path / "SHA256SUMS").read_text(encoding="utf8").startswith(rec.files[0]["sha256"])


def test_licence_must_agree_with_its_quote():
    assert filecheck.licence_in_quote("cc0-1.0", "released into the public domain under CC0")
    assert filecheck.licence_in_quote("cc-by-4.0", "Creative Commons Attribution 4.0 (CC BY 4.0)")
    assert not filecheck.licence_in_quote("cc-by-4.0", "Creative Commons Attribution-ShareAlike 4.0 (CC BY-SA 4.0)")
    assert not filecheck.licence_in_quote("cc-by-sa-4.0", "Creative Commons Attribution 4.0 (CC BY 4.0)")


def test_change_log_reverts_and_refuses_an_edit_outside_it():
    t = Table("t", "s", [C("x", "num")], [["1"], ["2"]], "f", "0", "unknown", "unknown")
    log = filecheck.ChangeLog()
    log.apply(t, 1, 0, "3", "typo", "check_range")
    log.revert(t)
    assert t.rows == [["1"], ["2"]]
    log.apply(t, 1, 0, "3", "typo", "check_range")
    t.rows[1][0] = "4"
    with pytest.raises(ValueError):
        log.revert(t)


def test_records_validate_and_export_catches_a_tampered_file(tmp_path):
    web = FakeWeb({"https://example.org/terms": TERMS})
    rec = _record()
    rec.date = "2026-10-31"
    assert access.read_terms(web, rec, tmp_path / "src", "https://example.org/terms", "cc0-1.0", "released under CC0 1.0 Universal", "yes")
    rec.terms_read_at = "2026-10-31T00:00:00+00:00"
    t = Table("t", "src", [C("x", "num", "m", "length")], [["1.5"], ["2.5"]], "data.csv", "ab" * 32, "cc0-1.0", "read")
    recs = list(to_records(t))
    assert recs and all(validate(r) == [] for r in recs)
    assert "schema differs" in validate(dict(recs[0], schema="other/1"))
    write_jsonl(recs, tmp_path / "src.jsonl")
    out = tmp_path / "out"
    res = diffuse.export({"src": (rec, tmp_path / "src")}, {"src": tmp_path / "src.jsonl"}, out, "c0de", ["test"], today="2026-10-31")
    assert [e["records"] for e in res["manifest"]["included"]] == [2] and res["blocked"] == []
    assert diffuse.verify_export(out) == []
    (out / "src.jsonl").write_text("{}\n", encoding="utf8")
    assert diffuse.verify_export(out) == ["src.jsonl hash differs"]
    assert json.loads((out / "BLOCKLIST.json").read_text(encoding="utf8")) == []
