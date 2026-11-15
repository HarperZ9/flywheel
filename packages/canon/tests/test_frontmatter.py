"""test_frontmatter.py -- R2 Module 1: the constrained frontmatter codec.

The `canon:` key carries `record.to_json()` verbatim as the one authoritative,
lossless carrier of the whole envelope. Every other scalar and the body are a
one-way projection, regenerated on render and never read back. The reader runs
no YAML loader: it anchors to the leading `---` fence, reads only the `canon:`
line, and reconstructs with `json.loads` + `Record.from_dict`.
"""
from __future__ import annotations

import pytest

from canon.frontmatter import (
    FRONTMATTER_KEYS,
    FrontmatterError,
    emit_alias_list,
    emit_frontmatter,
    emit_scalar,
    parse_frontmatter,
    record_from_note,
)
from canon.schema import KIND_PERSONALITY_BLOCK, Provenance, Record, Temporal


def _pb(**over) -> Record:
    data = over.pop("data", {"title": "Voice", "body": "Feature-first."})
    prov = over.pop(
        "provenance",
        Provenance(harness="hermes", source_hash="a" * 64, create_ord=10),
    )
    return Record(
        kind=KIND_PERSONALITY_BLOCK,
        id=over.pop("id", "voice-canon"),
        scope=over.pop("scope", "workspace"),
        data=data,
        provenance=prov,
        temporal=over.pop("temporal", None),
    )


def _rich() -> Record:
    prov = Provenance(
        harness="chatgpt",
        source_hash="b" * 64,
        native_id="native-7",
        session_id="sess-9",
        create_ord=42,
        create_time="2026-01-01T00:00:00Z",
        model_slug="gpt-x",
    )
    data = {"title": "Deep", "body": "line1\nline2", "nested": {"k": [1, 2, {"z": "y"}]}}
    return Record(
        kind=KIND_PERSONALITY_BLOCK,
        id="deep-block",
        scope="global",
        data=data,
        provenance=prov,
        temporal=Temporal(valid_until=99, supersedes="old-id"),
    )


def _keys(fm: str) -> list[str]:
    out = []
    for ln in fm.split("\n"):
        if ln in ("---", ""):
            continue
        out.append(ln.split(":", 1)[0])
    return out


def test_emit_scalar_doubles_single_quotes():
    assert emit_scalar("a'b") == "'a''b'"


def test_emit_alias_list_single_element_flow_seq():
    assert emit_alias_list(["voice-canon"]) == "['voice-canon']"
    assert emit_alias_list(["a'b"]) == "['a''b']"


def test_emit_frontmatter_fixed_key_order():
    fm = emit_frontmatter(_pb(), title="Voice")
    assert _keys(fm) == list(FRONTMATTER_KEYS)


# Root D-28: `FRONTMATTER_KEYS` must actually DRIVE the emission order, not just
# document it. If the emitter hardcodes its own sequence, the constant is a dead
# maintenance trap that can silently diverge. Reorder the constant and the
# emitted block must follow it.
def test_emit_frontmatter_order_is_driven_by_the_constant(monkeypatch):
    import canon.frontmatter as fm_mod

    reordered = ("kind", "canon_schema", "id", "scope", "title", "aliases", "canon")
    monkeypatch.setattr(fm_mod, "FRONTMATTER_KEYS", reordered)
    keys = _keys(fm_mod.emit_frontmatter(_pb(), title="Voice"))
    assert keys == list(reordered)


def test_canon_value_is_single_physical_line():
    fm = emit_frontmatter(_rich(), title="Deep")  # data.body has an embedded newline
    canon_lines = [ln for ln in fm.split("\n") if ln.startswith("canon: '")]
    assert len(canon_lines) == 1
    # the embedded body newline survived as an escaped \n, not a real line break.
    assert "\\n" in canon_lines[0]


def test_parse_frontmatter_reads_only_the_canon_key():
    rec = _pb()
    note = emit_frontmatter(rec, title="Voice") + "# Voice\n\nbody with : colons and 'quotes'\n"
    assert parse_frontmatter(note) == rec.to_dict()


def test_record_from_note_roundtrips_full_envelope():
    rec = _rich()
    note = emit_frontmatter(rec, title="Deep") + "# Deep\n\nline1\nline2\n"
    assert record_from_note(note) == rec


def test_frontmatter_reader_runs_no_yaml_loader():
    # a YAML tag in another scalar or the body must be inert: json.loads never
    # interprets it, so the record reconstructs from the canon JSON alone.
    rec = _pb(data={"title": "T", "body": "!!python/object/apply:[os,system]"})
    note = emit_frontmatter(rec, title="!!python/object/apply:[os,system]")
    assert record_from_note(note) == rec


def test_frontmatter_reader_anchors_to_leading_fence():
    rec = _pb()
    # a body line that is exactly `---` and a fake canon key below it must not
    # open a second frontmatter block or hijack the reconstruction.
    note = (
        emit_frontmatter(rec, title="Voice")
        + "# Voice\n\nbefore\n---\ncanon: 'HIJACK'\n"
    )
    assert record_from_note(note) == rec
