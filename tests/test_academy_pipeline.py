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
