"""The linear-time masks must return exactly what re.sub returns with the
reference patterns they replace. Findings are computed on the masked line, so
any difference here would change a finding and break receipt replay under an
unchanged ruleset fingerprint. The reference patterns are only safe to run on
short input, so the comparison uses short generated strings, and a separate
test holds the masks, and the detector functions that apply them, to a time
budget on long hostile lines."""
import random
import re
import time

from articulate import detector, masking


def _blank(m):
    return " " * (m.end() - m.start())


URL = re.compile(masking.URL_PATTERN)
TAG = re.compile(masking.TAG_PATTERN)
QUOTED = re.compile(masking.QUOTED_PATTERN)

# Pieces chosen to reach every branch of the three scanners. The list holds web
# prefixes and e-mail parts, runs of dots or hyphens, an "@" with no domain, tags,
# each quote kind with its closer, newlines, plus one non-ASCII word character.
ATOMS = list("a1._-@hsp:/ <>\n\"\u201c\u201d\u2018\u2019\u00e9\t+x") + [
    "http://", "https://", "http", "https:/", "a@b.com", "x.y@z.org", "<b>",
    "</i>", "@x.", ".-", "@@", "www.", "e.g.", "\u00e9@\u00e9.\u00e9", "__",
    "a.b", "--", "\r"]

CASES = [
    "mail jo.smith@example.com or visit https://example.com/a?b=c today",
    "a@b.c.-d@e.fg",            # the second match starts inside the first's run
    "-.foo@x.com",              # the local part starts at the first word boundary
    "x.https://y and a@x.http://z",
    "user+tag@example.com",     # "+" is outside the local-part class
    "if a < b then <em>c</em> > d",
    "<>< a >",
    "\u201cHe said \u2018no\u2019 and left.\u201d \u201cunclosed",
    "\"one\" \"two\" \"three",
]


def _check(text):
    assert masking.mask_urls(text) == URL.sub(_blank, text), repr(text)
    spans = masking.url_spans(text)
    assert masking.blank_spans(text, spans) == URL.sub(_blank, text), repr(text)
    assert masking.mask_tags(text) == TAG.sub(_blank, text), repr(text)
    assert masking.mask_quoted(text) == QUOTED.sub(_blank, text), repr(text)


def test_masks_match_reference_on_known_cases():
    for text in CASES:
        _check(text)


def test_masks_match_reference_on_generated_input():
    rng = random.Random(20260923)
    for _ in range(4000):
        _check("".join(rng.choice(ATOMS) for _ in range(rng.randint(0, 60))))


def test_detector_keeps_the_reference_patterns():
    assert detector.URL.pattern == masking.URL_PATTERN
    assert detector.TAG.pattern == masking.TAG_PATTERN
    assert detector.QUOTED.pattern == masking.QUOTED_PATTERN


HOSTILE = [
    "v1." * 10000,
    "1.1.1.1." * 5000,
    ("1.1.1.1." * 5000) + "@",
    "twenty-" * 8000,
    "a@" * 20000,
    # The quadratic tag pattern takes about 0.09 s per call on 10000 unclosed
    # "<", under any budget that is safe on a slow runner. On 40000 it took
    # 1.4 s to 4.4 s, so these lines use 40000. The quote pattern took about
    # 0.4 s on 10000 unclosed curly quotes and 1.7 s on 20000.
    "<a " * 40000,
    ("<a " * 40000) + ">",
    "\u201ca " * 20000,
    "\u2018a " * 20000,
    "\"a\" " * 10000,
    "https://" * 5000,
]

# The masks, plus the detector functions that apply them. Timing the detector
# functions as well catches a call site that goes back to URL.sub, TAG.sub, or
# QUOTED.sub, in addition to a regression inside the masking module.
MASKERS = [masking.mask_urls, masking.mask_tags, masking.mask_quoted,
           detector.strip_markup, detector.mask_quotes]


def test_masks_are_linear_on_hostile_lines():
    # The linear code takes at most about 0.01 s per call on these lines. On
    # each of the seven lines where a reference pattern is quadratic, that
    # pattern took 1.3 s or more per call, so the 0.25 s budget separates them.
    for i, text in enumerate(HOSTILE):
        for fn in MASKERS:
            start = time.perf_counter()
            fn(text)
            elapsed = time.perf_counter() - start
            assert elapsed < 0.25, f"{fn.__name__} on hostile line {i} took {elapsed:.2f}s"
