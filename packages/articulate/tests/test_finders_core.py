"""The span finders: no length cap, the same spans as the uncapped reference
regexes on known and generated inputs.

The references below are the lazy regexes the finders replace, with the caps
removed. They backtrack on long hostile input, so the comparison runs on short
generated strings; tests/test_comparison_bounds.py checks a time budget on
long input.
"""
import random
import re

from articulate import finders, invariants

ENVS = "|".join(invariants.MATH_ENVS)
REFERENCE = [
    re.compile(r"\$\$.+?\$\$", re.S),
    re.compile(r"\\\[.+?\\\]", re.S),
    re.compile(r"\\\(.+?\\\)", re.S),
    re.compile(r"\\begin\{((?:" + ENVS + r")\*?)\}.*?\\end\{\1\}", re.S),
]
QUOTE = re.compile("\"[^\"\\n]+\"|\u201c[^\u201d\\n]+\u201d")

ATOMS = list("a $\\[]()\n\"\u201c\u201d{}*") + [
    "$$", "\\[", "\\]", "\\(", "\\)", "\\begin{align}", "\\end{align}",
    "\\begin{align*}", "\\end{align*}", "\\begin{proof}", "\\end{proof}",
    "\\begin{itemize}", "\\end{itemize}", "\"\"", "\u201c\u201d"]


def _spans(rx, text):
    return [(m.start(), m.end(), None) for m in rx.finditer(text)]


def _check(text):
    for find, rx in zip(invariants.MATH, REFERENCE):
        assert find(text) == _spans(rx, text), (rx.pattern, text)
    assert finders.quote_spans(text) == _spans(QUOTE, text), text


def test_finders_match_the_uncapped_regexes_on_known_cases():
    for text in ('"" x"', '"a" "b', "$$$$$", "$$a$$ $$b", "\\begin{align}x\\end{align*}",
                 "\u201ca \u201cb\u201d", "\\(a\\) \\(", "\\begin{proof}\\end{proof}"):
        _check(text)


def test_finders_match_the_uncapped_regexes_on_generated_input():
    rng = random.Random(20260923)
    for _ in range(4000):
        _check("".join(rng.choice(ATOMS) for _ in range(rng.randint(0, 40))))
