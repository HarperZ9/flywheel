"""The academy pipeline: a curriculum DERIVED from the live codebase, not
written beside it. Each lesson pins its source docstring by hash (doc rot
breaks the lesson visibly), names an executable check against the running
gateway, and orders itself in a prerequisite arc from foundations to
composition. Abstraction-first ordering follows the codebase-to-tutorial
shape published by Zachary Huang (PocketFlow Tutorial-Codebase-Knowledge,
MIT); the receipts are ours."""

from harness.academy_pipeline import academy_curriculum, derive_lessons


def test_curriculum_is_a_valid_arc():
    cur = academy_curriculum()
    assert cur["schema"] == "flywheel.academy-curriculum/v1"
    lessons = cur["lessons"]
    assert len(lessons) >= 6
    seen = set()
    for l in lessons:
        for p in l["prereqs"]:
            assert p in seen, f"{l['id']} lists prereq {p} not yet taught"
        seen.add(l["id"])


def test_every_lesson_teaches_from_its_live_source():
    for l in academy_curriculum()["lessons"]:
        assert l["present"] is True, l["id"]
        assert len(l["teach"]) > 40, l["id"]
        assert len(l["source_sha256"]) == 64
        assert l["source_module"].startswith("harness.")


def test_every_lesson_names_an_executable_check():
    for l in academy_curriculum()["lessons"]:
        chk = l["check"]
        assert chk["method"] in ("GET", "POST")
        assert chk["path"].startswith("/api/")
        assert chk["expect"], l["id"]


def test_rotted_source_reads_absent_never_fabricated():
    fake = [{"id": "ghost", "title": "Ghost", "source_module":
             "harness.does_not_exist_xyz", "prereqs": [],
             "check": {"method": "GET", "path": "/api/x", "expect": "x"}}]
    out = derive_lessons(fake)
    assert out[0]["present"] is False
    assert out[0]["teach"] == ""


def test_completion_flow_is_wired_to_existing_receipts():
    cur = academy_curriculum()
    flow = cur["completion_flow"]
    assert "/api/explain" in flow and "/api/retention" in flow


def test_completion_binds_a_passed_receipt_to_a_lesson(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    from harness.academy_pipeline import academy_complete
    from harness.store import put_entity
    passed = put_entity("comprehension", {"passed": True, "files": ["x"]})
    r = academy_complete("store", passed["eid"])
    assert r["bound"] is True
    assert r["lesson_id"] == "store"
    assert len(r["lesson_source_sha256"]) == 64
    assert r["chain_hash"]


def test_completion_refuses_an_unknown_lesson(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    from harness.academy_pipeline import academy_complete
    from harness.store import put_entity
    passed = put_entity("comprehension", {"passed": True})
    r = academy_complete("no-such-lesson", passed["eid"])
    assert r["bound"] is False and "unknown lesson" in r["reason"]


def test_completion_refuses_a_failed_or_missing_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    from harness.academy_pipeline import academy_complete
    from harness.store import put_entity
    failed = put_entity("comprehension", {"passed": False})
    r = academy_complete("store", failed["eid"])
    assert r["bound"] is False and "did not pass" in r["reason"]
    r2 = academy_complete("store", "no-such-eid")
    assert r2["bound"] is False and "no such" in r2["reason"]
