"""The parity matrix must be able to fail: rows are audited against the
repo at read time, known gaps stay visible as ABSENT, and competitor cells
are labeled declarations. A matrix that can only say WITNESSED is theater."""

from harness import parity, parity_peers


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
            "witnesses": [("module", "harness/does_not_exist.py")]}
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
    # A starred row must be witnessed here and read as absent at EVERY peer.
    # "partial" is a declaration and None is an unread surface, so a row
    # carrying either one cannot support the sentence the star stands for.
    by_key = {r["key"]: r for r in doc["rows"]}
    for key in s["uniquely_witnessed"]:
        assert by_key[key]["flywheel"] == "WITNESSED"
        assert all(v is False
                   for v in by_key[key]["competitors"].values()), key


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


def test_the_0_3_11_capability_families_stay_on_the_matrix():
    """The boundary, grant, measurement, and governance work shipped after
    the July declaration. A matrix that quietly drops one of these rows
    reports a smaller tool than the one that ships, which is the same
    defect as overclaiming and is why these keys are pinned here."""
    doc = parity.parity_matrix()
    by_key = {r["key"]: r for r in doc["rows"]}
    for key in ("agent-boundary-audit", "isolation-probe",
                "credential-exposure-scan", "two-authority-kill-switch",
                "per-action-operator-grant", "signed-receipt-external-anchor",
                "formal-proof-oracle", "native-acceleration-with-fallback",
                "autonomy-tiers-and-decision-records", "accepted-lesson-loop",
                "private-verified-benchmarks", "paired-uplift-measurement",
                "phone-access-own-tunnel"):
        assert by_key[key]["flywheel"] == "WITNESSED", key


def test_every_row_key_is_unique():
    # Two rows sharing a key shadow each other in every by-key view, so one
    # of them would go unread while still counting toward the totals.
    keys = [r["key"] for r in parity.ROWS]
    assert len(keys) == len(set(keys))


def test_a_peer_cell_is_one_of_the_four_declared_values():
    # A typo reads as neither True nor False and would quietly land in the
    # bucket that suppresses the star, which is the failure this checks for
    # from the other side: a matrix that silently under-reports is still a
    # matrix nobody can trust.
    for key, cells in parity_peers.DECLARATIONS.items():
        for name, value in cells.items():
            assert name in parity_peers.PEER_KEYS, (key, name)
            assert value in parity_peers.VALUES, (key, name, value)


def test_every_row_has_a_column_for_every_peer():
    """A row added without declarations would read as five absences.

    `declarations_for` fills a missing cell with UNREAD rather than False, so
    the star is already suppressed, but silence is not the same as having
    looked. This fails the moment a row or a peer is added without the other
    side being written."""
    assert parity_peers.undeclared_rows(r["key"] for r in parity.ROWS) == []
    row_keys = {r["key"] for r in parity.ROWS}
    assert set(parity_peers.DECLARATIONS) <= row_keys
    for key, cells in parity_peers.DECLARATIONS.items():
        assert set(cells) == set(parity_peers.PEER_KEYS), key


def test_a_partial_or_unread_cell_cannot_earn_a_star():
    """The falsifier for the rule that shipped 27 stars on a five-peer table.

    The old rule was `not any(cell is True)`, so a capability every peer
    part-ships counted as one no peer declares, and so did one nobody had
    read. Both shapes are built here against a real witness and neither may
    come back starred."""
    original = parity.ROWS
    parity.ROWS = original + [
        {"key": "all-partial", "desc": "x",
         "witnesses": [("module", "harness/parity.py")]},
        {"key": "all-unread", "desc": "x",
         "witnesses": [("module", "harness/parity.py")]}]
    declared = dict(parity_peers.DECLARATIONS)
    declared["all-partial"] = {p: parity_peers.PART
                               for p in parity_peers.PEER_KEYS}
    original_declarations = parity_peers.DECLARATIONS
    parity_peers.DECLARATIONS = declared
    try:
        doc = parity.parity_matrix()
        by_key = {r["key"]: r for r in doc["rows"]}
        assert by_key["all-partial"]["flywheel"] == "WITNESSED"
        assert by_key["all-unread"]["flywheel"] == "WITNESSED"
        starred = set(doc["summary"]["uniquely_witnessed"])
        assert "all-partial" not in starred
        assert "all-unread" not in starred
        assert "all-unread" in doc["summary"]["undetermined"]
    finally:
        parity.ROWS = original
        parity_peers.DECLARATIONS = original_declarations


def test_every_peer_column_is_named_and_dated_on_the_document():
    """The page prints a peer set we chose. It has to say which, and when
    each column was read, or "against the field" is a claim about a field
    the reader cannot see."""
    doc = parity.parity_matrix()
    assert [p["key"] for p in doc["peers"]] == list(parity_peers.PEER_KEYS)
    assert len(set(parity_peers.PEER_KEYS)) == len(parity_peers.PEER_KEYS)
    for peer in doc["peers"]:
        assert peer["label"] and peer["source"]
        assert peer["read_on"] <= doc["declared_on"]
    assert doc["declared_on"] == max(p["read_on"] for p in doc["peers"])


def test_the_table_and_the_audit_are_separate_modules():
    """The rows moved out of parity.py so the table can grow past the file
    gate. parity.ROWS must stay the same object either way, or the
    monkeypatch above stops reaching what parity_matrix reads."""
    from harness import parity_rows
    assert parity.ROWS is parity_rows.ROWS


def test_every_note_belongs_to_a_row_and_every_row_is_accounted_for():
    """The ratchet that replaced a comment sitting above the wrong row.

    Prose keyed by a row key cannot drift onto its neighbour, and a row whose
    cells carry no reasoning fails here rather than reaching a published
    matrix. The twelve in UNDOCUMENTED are a shortfall this freezes rather than
    blesses: that set may lose members and may never gain one.
    """
    from harness.parity_peer_notes import NOTES, UNDOCUMENTED
    keys = {r["key"] for r in parity.ROWS}
    assert set(NOTES) <= keys, "a note names a row that does not exist"
    assert UNDOCUMENTED <= keys
    assert not set(NOTES) & UNDOCUMENTED
    assert keys == set(NOTES) | UNDOCUMENTED, "a row with no audit trail"
    assert len(UNDOCUMENTED) <= 12
    assert all(note.strip() for note in NOTES.values())
    assert "task-isolation" in NOTES


def test_the_two_halves_of_the_note_set_never_answer_for_the_same_row():
    """A key in both files would be resolved by a merge and by nothing else.

    `NOTES` is `{**_EARLY, **_BOUNDARY}`. A row written up in both places
    would keep the second note and drop the first without a word, so the
    reasoning a reader sees would depend on which file they opened. Rows
    move between the two only by being moved, never by being duplicated.
    """
    from harness.parity_peer_notes import NOTES, _EARLY
    from harness.parity_peer_notes_boundary import NOTES as BOUNDARY
    assert not set(_EARLY) & set(BOUNDARY), "a row is written up twice"
    assert len(NOTES) == len(_EARLY) + len(BOUNDARY)
