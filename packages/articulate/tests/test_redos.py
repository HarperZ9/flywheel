"""Regex-safety edge cases: the detector runs over arbitrary, possibly adversarial
documents, so no pattern may blow up on a crafted input. A catastrophic-backtracking
regression would hang a CI gate, which is an availability incident."""
import time

import articulate
from articulate import profiles

ADVERSARIAL = [
    "a" * 40000,
    "not " * 8000,
    "You can " * 4000,
    ("is not " * 4000) + "it is",
    ("word, " * 8000) + "and word",
    (" " * 40000) + "x",
    "a b " * 12000,
    "".join("<b>x</b>" for _ in range(5000)),
    "```\n" + ("x" * 40000) + "\n```",
    ("cutting-edge " * 6000),
    # A long run of word characters mixed with dots or hyphens, with no "@". The
    # e-mail alternative of the URL mask used to retry every word boundary in the
    # run and rescan the rest of it each time: 14 s to 68 s per check_text call.
    "v1." * 10000,
    "1.1.1.1." * 5000,
    "twenty-" * 8000,
    # The same run with an "@" at the end and no domain after it. A fix that
    # only skips lines without "@" would still take about 40 s here.
    ("1.1.1.1." * 5000) + "@",
    # Unclosed "<": the tag mask rescanned to the end of the line from each one.
    # On 10000 of them the old code stayed under the 3 s budget, so a regression
    # would pass. On 40000 it took 13 s to 26 s per check_text call, and the
    # fixed code takes about 0.35 s.
    "<a " * 40000,
]


# The genre layer adds quote-masking, the fiction lexicon, and the Fountain
# classifier. Each runs over arbitrary input too, so they get the same budget.
GENRE_ADVERSARIAL = [
    '"' + ("x" * 40000),                       # an unterminated quote
    ("could not " * 5000) + "help but stop",   # the catenative near the lookbehind
    ("INT. " * 8000) + "ROOM",                 # slugline prefix repeated
    ("shivers ran down her spine " * 2000),    # the fiction lexicon, at length
    ("a mix of joy and " * 4000) + "fear washed over her",
    # Unclosed curly quotes: the dialogue mask rescanned to the end of the line
    # from each opening mark. On 10000 of them the old code took 3.3 s to 5.0 s
    # per check_text call, too close to the budget to fail reliably. On 20000 it
    # took 14 s to 21 s, and the fixed code takes under 0.5 s.
    "\u201ca " * 20000,
    "\u2018a " * 20000,
]


def test_no_catastrophic_backtracking():
    prof = profiles.load("flavored")
    for i, text in enumerate(ADVERSARIAL):
        start = time.perf_counter()
        articulate.check_text(text, profile=prof)
        elapsed = time.perf_counter() - start
        assert elapsed < 3.0, f"adversarial input {i} took {elapsed:.2f}s (possible ReDoS)"


def test_genre_patterns_are_bounded():
    for name in ("literary-fiction", "screenplay", "poetry", "memoir"):
        prof = profiles.load(name)
        for i, text in enumerate(ADVERSARIAL + GENRE_ADVERSARIAL):
            start = time.perf_counter()
            articulate.check_text(text, profile=prof)
            elapsed = time.perf_counter() - start
            assert elapsed < 3.0, f"{name} input {i} took {elapsed:.2f}s (possible ReDoS)"


# detect_injection runs over the full untrusted document on every editor call, so
# its patterns get the same wall-clock budget as the check_text passes.
INJECTION_ADVERSARIAL = [
    ("ignore " * 8000) + "instructions",
    ("you are now " * 5000) + "a",
    ("reveal " * 8000) + "the system prompt",
    ("System: " * 4000),
    ("no restrictions " * 5000),
    ("respond " * 8000) + "approved",
]


def test_detect_injection_is_bounded():
    from articulate import detector
    for i, text in enumerate(INJECTION_ADVERSARIAL + ADVERSARIAL):
        start = time.perf_counter()
        detector.detect_injection(text)
        elapsed = time.perf_counter() - start
        assert elapsed < 3.0, f"detect_injection input {i} took {elapsed:.2f}s (possible ReDoS)"


def test_empty_and_whitespace_are_clean():
    prof = profiles.load("flavored")
    for text in ("", "\n\n\n", "   ", "\t\t"):
        r = articulate.check_text(text, profile=prof)
        assert r["clean"] is True and r["gate"] == "ok"
