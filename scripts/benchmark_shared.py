"""Vocabulary shared by the two renderings of the benchmark record.

The page and the text document are generated from one record by two
renderers. Anything both of them say lives here, so they cannot disagree
about what "partial" prints as, how many suites ran, or how a paragraph is
wrapped. Nothing in this module reads a file or scores anything.
"""

from __future__ import annotations

import html
import textwrap
from typing import Any

# How a peer declaration prints: the css class, then the word. `None` prints
# as its own word rather than as a blank, because a blank cell in a table of
# absences is read as an absence and that is exactly the claim it cannot make.
CELL = {True: ("yes", "ships"), False: ("no", "no"),
        "partial": ("part", "part"), None: ("unread", "unread")}

# The width the README already wraps its prose to.
WIDTH = 79


def unread_note(summary: dict[str, Any], rows: int, drawn_as: str = "") -> str:
    """What the unread rows do to the star count, in the tense that is true.

    While rows are unread the sentence has to say a star is being withheld, so
    a reader does not take the star count for a finished number. Once the count
    reaches zero that wording describes an empty set and reads as if reading is
    still owed, so the claim flips to the stronger one the record supports. It
    goes back on its own the moment a row or a peer is added.

    Both renderers call this. The page and the text document said it in two
    hand-written copies, which is how one of them ends up making a claim the
    other has already stopped making. `drawn_as` is where the page names the
    cell it prints for an unread peer, and it is dropped at zero because no
    cell is drawn that way when nothing is unread.
    """
    held = len(summary["undetermined"])
    head = "rows carry at least one peer surface nobody here has read"
    if held:
        return (f"{held} {head}{drawn_as}, and a star is withheld from every "
                "one of them, so the starred count moves up as the reading is "
                "done and not before.")
    return (f"0 {head}, so no star is being withheld for want of reading "
            f"across all {rows}. Adding a row or a peer puts cells back in "
            "that state until they are read.")


def coverage_note(summary: dict[str, Any]) -> str:
    """What the row set leaves out, printed wherever the gap count is.

    A reader who sees no gaps will take the row set for the field. It is not:
    the rows were chosen here, so an unscored capability produces no gap no
    matter who ships it. Both renderers call this for the same reason they
    both call `unread_note`, which is that a sentence written twice is a
    sentence that stops being true in one of its copies.
    """
    c = summary["coverage"]
    return (f"{len(summary['gaps'])} rows where a peer declares a capability "
            "this repository does not have. That count is bounded by the row "
            f"set, which was chosen here, so the {c['unscored_topics']} "
            "capability areas found in the peers' own page indexes on "
            f"{c['read_on']} that no row scores are published with it: "
            f"{c['row_owed']} where a row is owed and {c['out_of_frame']} "
            "left out on purpose with the reason written down, in "
            "harness/parity_coverage.py.")


def lede(report: dict[str, Any]) -> str:
    """The opening paragraph, with the suite count taken from the record.

    Written as a function rather than a constant because the count is a
    number like any other, and a hand-typed count is the first thing to go
    stale when a suite is added.
    """
    return (f"{len(report['suites'])} suites run with no model endpoint and no "
            "network, so anyone with the repo gets these numbers back. They "
            "measure what the engine does with a recorded situation, not how "
            "clever a model is. The capability question needs a live endpoint "
            "and is answered further down, where the interval still includes "
            "zero and the instrument that produced it is retired.")


def esc(value: Any) -> str:
    """Escape a record value for HTML, quotes included.

    Every string on the page comes out of a JSON record or out of a peer
    declaration somebody typed, so all of it goes through here. It lives in
    the shared module because three renderers were each carrying their own
    copy, and an escaper that exists in three places is an escaper that can
    be fixed in one of them.
    """
    return html.escape(str(value), quote=True)


def wrap(text: str) -> str:
    """Reflow a paragraph to the width the rest of the README already uses."""
    return textwrap.fill(text, width=WIDTH, break_long_words=False,
                         break_on_hyphens=False)
