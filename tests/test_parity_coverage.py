"""The coverage control on the matrix, and the control on that control.

`gaps 0` is the most flattering number the parity matrix produces, and a
reader cannot check it, because the row set that bounds it was written here.
`harness/parity_coverage.py` answers that by naming what the peers ship that
no row scores. These tests keep that answer from decaying into a label: an
entry has to say who ships the capability, where it was read, and why this
project did what it did with it.

There are now two ways to defeat the control rather than one. `out-of-frame`
excuses a topic, and `scored` claims a row already covers it. The second is
the cheaper of the two, because it empties the owed list without any work
happening, so a scored entry has to name a row key that resolves against the
live row set.

Split out of test_parity.py when that file reached the length limit. The
module under test is its own module for the same reason.
"""
from harness import parity, parity_peers


def test_every_topic_says_who_ships_it_and_what_was_decided():
    """A coverage control with a half-filled entry is worse than none.

    Each entry carries a topic, the peers found shipping it, the pages it was
    found on, one of the three dispositions, and a reason. An entry missing
    the reason would look like an answer while saying nothing, and
    `out-of-frame` is exactly where that failure would be convenient.
    """
    from harness.parity_coverage import DISPOSITIONS, TOPICS
    topics = [e["topic"] for e in TOPICS]
    assert len(topics) == len(set(topics))
    for entry in TOPICS:
        assert entry["disposition"] in DISPOSITIONS, entry["topic"]
        assert entry["reason"].strip() and entry["where"].strip()
        assert entry["peers"], entry["topic"]
        for peer in entry["peers"]:
            assert peer in parity_peers.PEER_KEYS, (entry["topic"], peer)


def test_a_scored_topic_names_a_row_that_exists():
    """The false-success control on the newer half of this module.

    Marking a topic `scored` removes it from the admission the page prints.
    Nothing stops an entry from naming a row that was never written, and the
    owed count would fall to zero on the strength of a string. Every key is
    resolved against the live row set here, and two entries cannot point at
    one row, which would let a single row retire two admissions.
    """
    from harness.parity_coverage import SCORED
    keys = {r["key"] for r in parity.ROWS}
    named = [row for _, row in SCORED]
    for topic, row in SCORED:
        assert row in keys, f"{topic} claims a row that does not exist: {row}"
    assert len(named) == len(set(named)), "two topics claim the same row"


def test_the_topic_set_is_not_empty_and_not_all_excused():
    """The false-success control on this control.

    An empty set reads as full coverage and would be the cheapest way to make
    the number look good. Marking every topic `out-of-frame` is the second
    cheapest, because the count stays honest while the admission disappears.
    Both are refused here.

    The bounds only ratchet one way. Thirteen topics were found on 2026-09-06
    and nine were scored the same day, so a later edit that drops a topic or
    un-scores a row has to say so out loud rather than letting the published
    counts fall on their own.
    """
    from harness.parity_coverage import SCORED, TOPICS, UNSCORED
    assert len(TOPICS) >= 13
    assert len(SCORED) >= 9
    assert len(UNSCORED) >= 1
    excused = [e for e in UNSCORED if e["disposition"] == "out-of-frame"]
    assert len(excused) < len(TOPICS), (
        "every topic is excused, which is an admission that admits nothing")


def test_a_topic_is_scored_exactly_when_a_row_covers_it():
    """The two halves have to agree in both directions.

    A topic still listed as unscored while a row scores it inflates the
    admission, which reads as humility and is a false statement about the
    matrix. Checked on the row keys with their hyphens dropped, so
    `plugin-registry` and a topic reading "plugin registry" would collide here
    rather than on the page.
    """
    from harness.parity_coverage import SCORED, UNSCORED
    loose = {r["key"].replace("-", " ") for r in parity.ROWS}
    for entry in UNSCORED:
        assert entry["topic"] not in loose, entry["topic"]
        assert "row" not in entry, entry["topic"]
    assert SCORED, "no topic has been scored, so no row was ever written"


def test_the_matrix_summary_carries_the_coverage_counts():
    """`gaps` travels with the denominator that bounds it or not at all."""
    from harness.parity_coverage import ROW_OWED, SCORED, TOPICS, UNSCORED
    c = parity.parity_matrix()["summary"]["coverage"]
    assert c["topics"] == len(TOPICS)
    assert c["scored"] == len(SCORED)
    assert c["row_owed"] == len(ROW_OWED)
    assert c["out_of_frame"] == len(UNSCORED) - len(ROW_OWED)
    assert c["topics"] == c["scored"] + c["row_owed"] + c["out_of_frame"]
    assert c["read_on"] == "2026-09-06"
