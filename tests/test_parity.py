"""The parity matrix must be able to fail: rows are audited against the
repo at read time, known gaps stay visible as ABSENT, and competitor cells
are labeled declarations. A matrix that can only say WITNESSED is theater."""

from harness import parity


def test_shipped_capabilities_are_witnessed():
    doc = parity.parity_matrix()
    by_key = {r["key"]: r for r in doc["rows"]}
    for key in ("any-provider-routing", "receipt-on-every-answer",
                "integrity-guard", "staged-workflows", "plugin-registry",
                "durable-memory-recall", "workspace-sandbox",
                "projected-world-hash", "loop-closure-audit",
                "plugin-marketplace"):
        assert by_key[key]["flywheel"] == "WITNESSED", key


def test_known_gaps_stay_visible_as_absent():
    doc = parity.parity_matrix()
    by_key = {r["key"]: r for r in doc["rows"]}
    for key in ("lsp-diagnostics-references", "oauth-keychain"):
        assert by_key[key]["flywheel"] == "ABSENT", key
        assert key in doc["summary"]["gaps"]


def test_matrix_can_fail_on_a_missing_witness():
    # A fabricated row with a nonexistent witness must audit ABSENT.
    fake = {"key": "fabricated", "desc": "x",
            "witnesses": [("module", "harness/does_not_exist.py")],
            "codex": False, "cursor": False, "claude-code": False}
    original = parity.ROWS
    parity.ROWS = original + [fake]
    try:
        doc = parity.parity_matrix()
        row = next(r for r in doc["rows"] if r["key"] == "fabricated")
        assert row["flywheel"] == "ABSENT"
    finally:
        parity.ROWS = original


def test_declarations_are_labeled_and_dated():
    doc = parity.parity_matrix()
    assert "not measurements" in doc["note"]
    assert doc["declared_on"] == parity.DECLARED_ON
    s = doc["summary"]
    assert s["witnessed"] + s["absent"] == len(doc["rows"])
    # Unique rows must actually be witnessed and unclaimed by the field.
    by_key = {r["key"]: r for r in doc["rows"]}
    for key in s["uniquely_witnessed"]:
        assert by_key[key]["flywheel"] == "WITNESSED"
        assert not any(v is True
                       for v in by_key[key]["competitors"].values())
