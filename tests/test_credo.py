"""The credo is an artifact, not a vibe: canonical text, stable hash, and
the beliefs that must never silently vanish from it."""

from harness.credo import CREDO, credo_doc


def test_credo_is_content_addressed_and_stable():
    a, b = credo_doc(), credo_doc()
    assert a["sha256"] == b["sha256"]
    assert len(a["sha256"]) == 64
    assert a["schema"] == "flywheel.credo/v1"


def test_the_load_bearing_beliefs_are_present():
    for phrase in ("attain the means", "external check decides acceptance",
                   "receipt a stranger can re-run", "honest null",
                   "Ownership is earned by comprehension",
                   "Learning is woven into the work",
                   "around\n   the work, not the worker"):
        assert phrase in CREDO, f"credo lost: {phrase}"
