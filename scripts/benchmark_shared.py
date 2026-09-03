"""Vocabulary shared by the two renderings of the benchmark record.

The page and the text document are generated from one record by two
renderers. Anything both of them say lives here, so they cannot disagree
about what "partial" prints as, how many suites ran, or how a paragraph is
wrapped. Nothing in this module reads a file or scores anything.
"""

from __future__ import annotations

import textwrap
from typing import Any

# How a competitor declaration prints: the css class, then the word.
CELL = {True: ("yes", "ships"), False: ("no", "no"), "partial": ("part", "part")}

# The width the README already wraps its prose to.
WIDTH = 79


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


def wrap(text: str) -> str:
    """Reflow a paragraph to the width the rest of the README already uses."""
    return textwrap.fill(text, width=WIDTH, break_long_words=False,
                         break_on_hyphens=False)
