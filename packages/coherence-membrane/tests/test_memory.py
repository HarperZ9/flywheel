# tests/test_memory.py
from __future__ import annotations

import json
import pytest
from pathlib import Path

from coherence_membrane.memory import (
    CriterionRef, PerceiveRef, MemoryRecord, MEMORY_TYPES,
)


def _rec(**kw):
    base = dict(id="m1", type="fact", claim="the sky is blue", tags=("color",))
    base.update(kw)
    return MemoryRecord(**base)


def test_record_rejects_unknown_type():
    with pytest.raises(ValueError):
        _rec(type="nonsense")


def test_identity_is_deterministic_and_excludes_created():
    a = _rec(created="2026-06-20T00:00:00+00:00")
    b = _rec(created="2099-01-01T00:00:00+00:00")
    assert a.identity_sha256 == b.identity_sha256          # created is volatile
    assert len(a.identity_sha256) == 64                    # full-width sha256


def test_identity_changes_with_claim():
    assert _rec().identity_sha256 != _rec(claim="the sky is red").identity_sha256


def test_to_dict_from_dict_roundtrip():
    r = _rec(criterion_ref=CriterionRef("origin", "v1", (("k", "v"),)),
             perceive_ref=PerceiveRef("read_file", (("path", "/x"),)),
             created="2026-06-20T00:00:00+00:00")
    back = MemoryRecord.from_dict(r.to_dict())
    assert back == r


import dataclasses

from coherence_membrane.memory import MemoryStore


def test_remember_and_get():
    s = MemoryStore()
    s.remember(_rec(id="a"))
    assert s.get("a").claim == "the sky is blue"
    assert s.get("missing") is None


def test_remember_rejects_duplicate_id():
    s = MemoryStore()
    s.remember(_rec(id="a"))
    with pytest.raises(ValueError):
        s.remember(_rec(id="a"))


def test_remember_node_digest_is_record_identity():
    s = MemoryStore()
    r = _rec(id="a")
    s.remember(r)
    assert s.graph.nodes["a"].digest == r.identity_sha256
    assert s.graph.nodes["a"].kind == "memory"


def test_remember_with_supersedes_edge():
    s = MemoryStore()
    s.remember(_rec(id="old", claim="v1"))
    s.remember(_rec(id="new", claim="v2"), parents=("old",), edge_type="supersedes")
    assert s.graph.nodes["new"].parents == ("old",)
    assert s.graph.nodes["new"].edge_type == "supersedes"


from coherence_membrane.provenance import VALID, BROKEN


def test_verify_clean_store_is_valid():
    s = MemoryStore()
    s.remember(_rec(id="a"))
    assert s.verify().verdict == VALID


def test_verify_detects_record_content_tamper():
    s = MemoryStore()
    s.remember(_rec(id="a", claim="original"))
    # tamper: swap the stored record for a different-content one under the same id
    s.records["a"] = _rec(id="a", claim="TAMPERED")
    v = s.verify()
    assert v.verdict == BROKEN
    assert any("a" in r for r in v.reasons)


def test_verify_pinned_manifest_catches_insertion():
    s = MemoryStore()
    s.remember(_rec(id="a"))
    pin = s.graph.manifest()
    s.remember(_rec(id="b"))  # inserted after pin
    assert s.verify(pinned_manifest=pin).verdict == BROKEN


def test_save_load_roundtrip(tmp_path):
    s = MemoryStore()
    s.remember(_rec(id="old", claim="v1"))
    s.remember(_rec(id="new", claim="v2"), parents=("old",), edge_type="supersedes")
    p = tmp_path / "mem.json"
    s.save(p)
    back = MemoryStore.load(p)
    assert back.get("new").claim == "v2"
    assert back.graph.nodes["new"].parents == ("old",)
    assert back.verify().verdict == VALID


def test_verify_detects_edge_tamper():
    """Tampering an edge_type in place must be detected as BROKEN."""
    s = MemoryStore()
    s.remember(_rec(id="old", claim="v1"))
    s.remember(_rec(id="new", claim="v2"), parents=("old",), edge_type="supersedes")
    # tamper: replace the node with one that has a different edge_type
    n = s.graph.nodes["new"]
    s.graph.nodes["new"] = dataclasses.replace(n, edge_type="derived-from")
    assert s.verify().verdict == BROKEN


def test_verify_detects_delete_via_manifest():
    """Deleting a node after pinning manifest must be detected as BROKEN."""
    s = MemoryStore()
    s.remember(_rec(id="a"))
    s.remember(_rec(id="b"))
    pin = s.graph.manifest()
    del s.graph.nodes["b"]
    assert s.verify(pinned_manifest=pin).verdict == BROKEN


def test_load_handedited_record_is_broken(tmp_path):
    s = MemoryStore()
    s.remember(_rec(id="a", claim="original"))
    p = tmp_path / "mem.json"
    s.save(p)
    data = json.loads(Path(p).read_text(encoding="utf-8"))
    for rec in data["records"]:
        if rec["id"] == "a":
            rec["claim"] = "HAND-EDITED"  # node digest unchanged → mismatch
    Path(p).write_text(json.dumps(data), encoding="utf-8")
    assert MemoryStore.load(p).verify().verdict == BROKEN
