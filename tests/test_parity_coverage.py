"""The coverage control on the matrix, and the control on that control.

`gaps 0` is the most flattering number the parity matrix produces, and a
reader cannot check it, because the row set that bounds it was written here.
`harness/parity_coverage.py` answers that by naming what the peers ship that
no row scores. These tests keep that answer from decaying into a label: an
entry has to say who ships the capability, where it was read, and why this
project did what it did with it.

Split out of test_parity.py when that file reached the length limit. The
module under test is its own module for the same reason.
"""
from harness import parity, parity_peers


def test_every_unscored_entry_says_who_ships_it_and_what_was_decided():
    """A coverage control with a half-filled entry is worse than none.

    Each entry carries a topic, the peers found shipping it, the pages it was
    found on, one of the two dispositions, and a reason. An entry missing the
    reason would look like an answer while saying nothing, and `out-of-frame`
    is exactly where that failure would be convenient.
    """
    from harness.parity_coverage import DISPOSITIONS, UNSCORED
    topics = [e["topic"] for e in UNSCORED]
    assert len(topics) == len(set(topics))
    for entry in UNSCORED:
        assert entry["disposition"] in DISPOSITIONS, entry["topic"]
        assert entry["reason"].strip() and entry["where"].strip()
        assert entry["peers"], entry["topic"]
        for peer in entry["peers"]:
            assert peer in parity_peers.PEER_KEYS, (entry["topic"], peer)


def test_the_unscored_set_is_not_empty_and_not_all_excused():
    """The false-success control on this control.

    An empty set reads as full coverage and would be the cheapest way to make
    the number look good. Marking every topic `out-of-frame` is the second
    cheapest, because the count stays honest while the admission disappears.
    Both are refused here: the set has members and some of them are owed.
    """
    from harness.parity_coverage import ROW_OWED, UNSCORED
    assert len(UNSCORED) >= 8
    assert len(ROW_OWED) >= 1
    assert len(ROW_OWED) < len(UNSCORED), (
        "every topic marked row-owed means no reason was ever written")


def test_an_unscored_topic_is_not_already_a_row():
    """A topic that a row scores is not a hole, and listing it as one would
    inflate the admission instead of the coverage. Checked on the row keys
    with their hyphens dropped, so `plugin-registry` and a topic reading
    "plugin registry" would collide here rather than on the page."""
    from harness.parity_coverage import UNSCORED
    keys = {r["key"].replace("-", " ") for r in parity.ROWS}
    for entry in UNSCORED:
        assert entry["topic"] not in keys, entry["topic"]


def test_the_matrix_summary_carries_the_coverage_counts():
    """`gaps` travels with the denominator that bounds it or not at all."""
    from harness.parity_coverage import ROW_OWED, UNSCORED
    c = parity.parity_matrix()["summary"]["coverage"]
    assert c["unscored_topics"] == len(UNSCORED)
    assert c["row_owed"] == len(ROW_OWED)
    assert c["out_of_frame"] == len(UNSCORED) - len(ROW_OWED)
    assert c["read_on"] == "2026-09-06"
