"""Lesson library: quarantine-first, admission on receipts, cascade, rollback."""
import json

import pytest

from harness import self_improve_bench as bench
from harness.evidence_json import canonical_sha256
from harness.self_improve_library import ADMITTED, QUARANTINED, LessonLibrary

GOOD = {"schema": "flywheel.harness-edit-receipt/v1", "decision": "ADOPT",
        "parent_digest": "p", "adopted_digest": "a", "adopted_components": ["scripts/x.py"],
        "attribution": [], "heldout": {"point": 0.5, "interval": [0.2, 0.8]},
        "policy": {"min_point": 0.0, "min_lower": 0.0}}


def sealed(**over):
    body = {**GOOD, **over}
    return {**body, "seal_sha256": canonical_sha256(body)}


def lesson(lib, receipt, name="l", parents=None):
    return lib.add(cue=name, lesson=name, components=["scripts/x.py"], source_task=name,
                   receipt_seal=receipt["seal_sha256"], parents=parents)


def test_lessons_enter_quarantined_and_admit_on_match():
    lib, r = LessonLibrary(), sealed()
    lid = lesson(lib, r)
    assert lib.status(lid) == QUARANTINED and lib.served() == []
    assert lib.admit(lid, r) and lib.status(lid) == ADMITTED
    assert [s["id"] for s in lib.served()] == [lid]


def test_unsupported_or_foreign_receipts_do_not_admit():
    lib = LessonLibrary()
    weak = sealed(heldout={"point": 0.1, "interval": [-0.2, 0.4]})
    lid = lesson(lib, weak)
    assert not lib.admit(lid, weak) and lib.status(lid) == QUARANTINED
    with pytest.raises(ValueError):
        lib.admit(lid, sealed())


def test_quarantine_cascades_to_descendants():
    lib = LessonLibrary()
    r1, r2, r3 = sealed(reason="1"), sealed(reason="2"), sealed(reason="3")
    a = lesson(lib, r1, "a")
    lib.admit(a, r1)
    b = lesson(lib, r2, "b", parents=[a])
    lib.admit(b, r2)
    c = lesson(lib, r3, "c", parents=[b])
    lib.admit(c, r3)
    assert set(lib.quarantine(a, "bad premise")) == {a, b, c}
    assert lib.served() == []


def test_child_of_quarantined_parent_is_refused():
    lib = LessonLibrary()
    r1, r2 = sealed(reason="1"), sealed(reason="2")
    a = lesson(lib, r1, "a")
    b = lesson(lib, r2, "b", parents=[a])
    assert not lib.admit(b, r2)
    with pytest.raises(KeyError):
        lesson(lib, r2, "c", parents=["nope"])


def test_rollback_restores_and_quarantines_later_lessons():
    lib = LessonLibrary()
    v0 = lib.commit_version(bench.base_tree(), receipt_seal="base")
    r = sealed()
    lid = lesson(lib, r)
    lib.admit(lid, r)
    lib.commit_version(bench.make_tree({"abs"}), receipt_seal=r["seal_sha256"], lessons=[lid])
    assert lib.incumbent() == bench.make_tree({"abs"})
    assert lib.rollback(v0, "regression on recheck") == [lid]
    assert lib.incumbent() == bench.base_tree() and lib.served() == []
    with pytest.raises(IndexError):
        lib.rollback(9, "x")


def test_chain_detects_history_edits(tmp_path):
    lib, r = LessonLibrary(), sealed()
    lib.commit_version(bench.base_tree(), receipt_seal="base")
    lib.admit(lesson(lib, r), r)
    path = lib.save(tmp_path / "lib.json")
    assert LessonLibrary.load(path).served() == lib.served()
    doc = json.loads(path.read_text())
    doc["journal"][1]["event"] = "admit"
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError):
        LessonLibrary.load(path)


def test_empty_library_has_no_incumbent():
    with pytest.raises(LookupError):
        LessonLibrary().incumbent()
