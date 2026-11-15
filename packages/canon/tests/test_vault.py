"""test_vault.py -- R2 Module 2: the one-record note codec.

A note is a whole-file markdown projection of one canonical record. The
frontmatter `canon:` key carries `record.to_json()` verbatim as the single
authoritative, lossless carrier; the `#`+body, the `## canon links` trailer,
and the flat scalars are a one-way projection, regenerated on render and never
read back. The filename derives from record identity (`scope/id`) via a fixed
slug+digest, never from body content. `render_note` refuses a record it cannot
faithfully project; `ingest_note` reconstructs from the JSON and runs the
validator.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import replace

import pytest

from canon.schema import (
    KIND_EPISODIC_MEMORY,
    KIND_PERSONALITY_BLOCK,
    Provenance,
    Record,
    Temporal,
)
from canon.frontmatter import emit_frontmatter, record_from_note
from canon.vault import (
    NoteRefused,
    VaultError,
    _slugify,
    derive_note_name,
    emit_links,
    ingest_note,
    render_note,
)

from ._helpers import RECORD_FILES, load_record

_DOMAIN = "canon-vault/v1\n"


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


def _ep(**over) -> Record:
    data = {
        "layer": "L1",
        "text": over.pop("text", "a fact"),
        "source_ids": over.pop("source_ids", []),
        "extractor": "fact-v2",
        "criterion": "stated",
    }
    prov = Provenance(harness="mneme", source_hash="b" * 64, create_ord=5)
    return Record(
        kind=KIND_EPISODIC_MEMORY,
        id=over.pop("id", "mem-x"),
        scope=over.pop("scope", "global"),
        data=data,
        provenance=prov,
        temporal=over.pop("temporal", Temporal()),
    )


def _digest(record_key: str) -> str:
    return hashlib.sha256((_DOMAIN + record_key).encode("utf-8")).hexdigest()[:16]


def _split_body(note: str) -> tuple[str, str]:
    """Return (frontmatter-including-close-fence, everything below it)."""
    first = note.index("---\n")
    close = note.index("\n---\n", first + 4) + len("\n---\n")
    return note[:close], note[close:]


# 9
def test_slugify_charset_is_lowercase_alnum_dash():
    assert _slugify("voice-canon") == "voice-canon"
    for raw in ["../../evil", "Foo Bar", "mem/000123", "C:\\Windows\\x", "caf\u00e9", "MEMORY"]:
        s = _slugify(raw)
        assert re.fullmatch(r"[a-z0-9-]*", s), f"{raw!r} -> {s!r}"
        assert "." not in s and "/" not in s and "\\" not in s


# 10
def test_derive_note_name_is_scope_slug_digest():
    rec = load_record(RECORD_FILES["personality-block"])  # workspace/voice-canon
    name = derive_note_name(rec)
    assert name.startswith("workspace/")
    stem = name[len("workspace/"):]
    assert stem.endswith(".md")
    slug, _, digest = stem[:-3].rpartition("-")
    assert slug == "voice-canon"
    assert digest == _digest("workspace/voice-canon")


# 11
def test_derive_note_name_empty_slug_fallback():
    rec = _pb(id="...")
    stem = derive_note_name(rec).split("/", 1)[1]
    assert stem.startswith("note-")
    assert stem == f"note-{_digest('workspace/...')}.md"


# 12
def test_derive_note_name_windows_reserved_defused():
    for rid in ["CON", "com1", "nul"]:
        stem = derive_note_name(_pb(id=rid)).split("/", 1)[1][:-3]
        assert stem != rid.lower()
        assert re.search(r"-[0-9a-f]{16}$", stem)


# 13
def test_derive_note_name_case_variants_distinct():
    a = derive_note_name(_pb(id="Foo"))
    b = derive_note_name(_pb(id="foo"))
    assert a != b
    assert a == a.lower() and b == b.lower()


# 14
def test_render_note_personality_block_body():
    rec = _pb(data={"title": "Voice", "body": "Feature-first.\nSecond line."})
    note = render_note(rec)
    assert "\n---\n# Voice\n\nFeature-first.\nSecond line.\n" in note
    assert "## canon links" not in note
    assert record_from_note(note) == rec

    sup = _pb(temporal=Temporal(supersedes="old-voice"))
    note2 = render_note(sup)
    assert "## canon links" in note2
    assert "- Supersedes: [[old-voice]]" in note2


# 15
def test_render_note_each_kind_body():
    adr = load_record(RECORD_FILES["adr-decision"])
    a = render_note(adr)
    assert "# Name the container canon; give it a standalone repo\n" in a
    assert "\n**Status:** accepted\n" in a
    assert "\n## Context\n\nThe container is a net-new" in a
    assert "\n## Decision\n\nName it canon." in a
    assert "\n## Consequences\n\n- Container code stays out of project-docs.\n- F0 schema" in a

    ep = load_record(RECORD_FILES["episodic-memory"])
    e = render_note(ep)
    assert "# Memory mem-000123\n" in e
    assert "\n**Layer:** L1\n" in e
    assert "- Sources: [[turn-0007]], [[turn-0009]]" in e

    per = load_record(RECORD_FILES["synthesized-persona-l3"])
    p = render_note(per)
    assert "# Persona persona-operator-0004\n" in p
    assert "\n**Layer:** L3\n" in p
    assert "- Supersedes: [[persona-operator-0003]]" in p
    assert "- Sources: [[mem-000123]], [[mem-000188]], [[mem-000201]]" in p

    rr = load_record(RECORD_FILES["research-artifact-ref"])
    r = render_note(rr)
    assert "# Memory-bank substrate survey\n" in r
    assert "\n**Locator:** gather://corpus/2026-08/substrate-survey.md\n" in r
    assert "\n**Media type:** text/markdown\n" in r
    assert "**Artifact hash:** " + ("e" * 62) in r
    assert "## canon links" not in r  # no temporal, no source_ids


# 16
def test_render_note_refuses_bare_cr():
    with pytest.raises(NoteRefused):
        render_note(_pb(data={"title": "Voice", "body": "has\rcr"}))
    with pytest.raises(NoteRefused):
        render_note(_pb(data={"title": "ti\rtle", "body": "ok"}))


# 16a -- Root A: render is the fail-closed choke point. A bare LF (not CR) in
# the id or the derived title makes the frontmatter scalar multi-line; render
# must refuse it as NoteRefused, not let a raw FrontmatterError escape.
def test_render_note_refuses_bare_lf_in_id_or_title():
    with pytest.raises(NoteRefused):
        render_note(_pb(id="voice\ncanon"))
    with pytest.raises(NoteRefused):
        render_note(_pb(data={"title": "ti\ntle", "body": "ok"}))


# 16b -- Root A: a non-JSON-serializable value in data cannot ride the canon:
# carrier. render must refuse it as NoteRefused, not let a raw TypeError escape
# from record.to_json().
def test_render_note_refuses_non_json_serializable_data():
    with pytest.raises(NoteRefused):
        render_note(_pb(data={"title": "Voice", "body": "ok", "extra": {1, 2}}))


# 16c -- Root A: derive_note_name slugifies the id, so a non-string (or empty)
# id must fail closed as a VaultError, not crash unicodedata.normalize with a
# raw TypeError. The mirror calls this before render, so the guard belongs here.
def test_derive_note_name_refuses_non_string_or_empty_id():
    with pytest.raises(VaultError):
        derive_note_name(_pb(id=None))
    with pytest.raises(VaultError):
        derive_note_name(_pb(id=""))


# 16d -- Root D-33: `consequences` is not type-checked by the validator, so an
# adr-decision carrying a non-list `consequences` passes validation and reaches
# `_body_adr`, which iterates it. A truthy non-list (int, str, dict) crashes the
# body emitter with a raw TypeError. render must refuse it as NoteRefused, not
# let a bare TypeError escape the fail-closed choke point.
def test_render_note_refuses_non_list_consequences():
    adr = load_record(RECORD_FILES["adr-decision"])
    bad = replace(adr, data={**adr.data, "consequences": 5})
    with pytest.raises(NoteRefused):
        render_note(bad)


# 16e -- Root D-33: `source_ids` is type-checked as a list only for the two
# memory kinds; on a personality-block it is unvalidated, so a truthy non-list
# passes validation and reaches `emit_links`, which iterates it -- a raw
# TypeError. render must refuse it as NoteRefused.
def test_render_note_refuses_non_list_source_ids():
    with pytest.raises(NoteRefused):
        render_note(_pb(data={"title": "Voice", "body": "ok", "source_ids": 5}))


# 16f -- Root D-33: a NaN (or Infinity) in data survives `json.dumps` as a
# non-portable bareword and never equals itself, so the carrier would round-trip
# to a record that silently fails the fidelity verdict. render must refuse it up
# front so the `canon:` carrier is always strict, portable JSON.
def test_render_note_refuses_nan_in_data():
    with pytest.raises(NoteRefused):
        render_note(_pb(data={"title": "Voice", "body": "ok", "n": float("nan")}))
    with pytest.raises(NoteRefused):
        render_note(_pb(data={"title": "Voice", "body": "ok", "n": float("inf")}))


# 16g -- Root D-25: a wikilink-hostile id cannot ride inside `[[...]]`, so a link
# to it falls back to a safe `{slug}-{digest}` token. That token resolves only if
# the target note advertises it as an alias -- otherwise the link dangles. The
# hostile-id note must carry its own fallback token in `aliases`.
def test_hostile_id_note_advertises_fallback_link_token_alias():
    from canon.vault import _link_token

    a = _pb(id="topic#v2")  # '#' is wikilink-hostile
    token = _link_token("topic#v2")
    assert token != "topic#v2"  # a real fallback token, not the id verbatim
    note = render_note(a)
    assert f"'{token}'" in note  # advertised as an alias so [[token]] resolves


# 17
def test_render_note_refuses_research_ref_with_temporal():
    rr = load_record(RECORD_FILES["research-artifact-ref"])
    bad = rr.with_temporal(Temporal(supersedes="x"))
    with pytest.raises(NoteRefused):
        render_note(bad)


# 18
def test_ingest_note_roundtrips_all_kinds_zero_record_drop():
    for path in RECORD_FILES.values():
        rec = load_record(path)
        assert ingest_note(render_note(rec)) == rec


# 19
def test_ingest_note_runs_validator():
    rr = load_record(RECORD_FILES["research-artifact-ref"])
    injected = rr.with_temporal(Temporal(supersedes="x"))
    # emit_frontmatter does not validate, so it will happily carry the bad JSON.
    note = emit_frontmatter(injected, title="x") + "# x\n"
    with pytest.raises(VaultError):
        ingest_note(note)

    # a canon: JSON that from_dict rejects (wrong schema) raises VaultError.
    broken = (
        "---\n"
        "canon: '{\"canon_schema\": \"wrong/v9\", \"kind\": \"personality-block\"}'\n"
        "---\n# x\n"
    )
    with pytest.raises(VaultError):
        ingest_note(broken)


# 20
def test_ingest_note_reconstructs_from_json_not_body():
    rec = _pb(data={"title": "Voice", "body": "ORIGINALBODY"})
    note = render_note(rec)
    fm, body = _split_body(note)
    tampered = fm + body.replace("ORIGINALBODY", "TAMPERED-BY-HAND")
    assert "ORIGINALBODY" in fm  # the JSON carrier is untouched
    assert ingest_note(tampered) == rec


# 21
def test_emit_links_only_from_record_relations():
    per = load_record(RECORD_FILES["synthesized-persona-l3"])
    links = emit_links(per)
    assert "- Supersedes: [[persona-operator-0003]]" in links
    assert "- Sources: [[mem-000123]], [[mem-000188]], [[mem-000201]]" in links

    plain = _pb(data={"title": "T", "body": "see [[ghost]] in prose"})
    assert emit_links(plain) == ""

    hostile = _ep(source_ids=["ok-id", "bad]id"])
    hl = emit_links(hostile)
    assert "[[ok-id]]" in hl
    assert "bad]id" not in hl
    for tok in re.findall(r"\[\[([^\]]*)\]\]", hl):
        assert re.fullmatch(r"[a-z0-9-]+", tok), tok
