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


def test_gap_list_reflects_the_audit_not_a_hardcoded_story():
    doc = parity.parity_matrix()
    by_key = {r["key"]: r for r in doc["rows"]}
    # secure-credentials closed the last declared gap; the list must agree
    # with the per-row audit, whatever it says.
    assert by_key["secure-credentials"]["flywheel"] == "WITNESSED"
    for key in doc["summary"]["gaps"]:
        assert by_key[key]["flywheel"] == "ABSENT"


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


def test_a_called_but_undefined_route_audits_absent():
    """The falsifier for the bug that shipped: `ref in src` counted a CALL
    site as a witness, so `live-agent-stream` reported WITNESSED on the
    strength of `self._sse_agent(...)` while no such method existed and the
    route raised AttributeError on first use."""
    src = "        return self._sse_agent(req, goal, endpoint)\n"
    assert parity._route_witnessed("_sse_agent", src) is False


def test_a_defined_route_handler_audits_witnessed():
    src = "    def _sse_agent(self, req, goal, endpoint):\n        return 1\n"
    assert parity._route_witnessed("_sse_agent", src) is True
    assert parity._route_witnessed(
        "_sse_agent", "    async def _sse_agent(self):\n        pass\n") is True


def test_an_http_path_needs_a_dispatch_not_a_mention():
    """A path named only in a comment or a docstring is not a served route."""
    assert parity._route_witnessed(
        "/api/x", "# the /api/x route is planned\n") is False
    assert parity._route_witnessed(
        "/api/x", '        if p == "/api/x":\n') is True
