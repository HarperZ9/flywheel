"""Selected large inputs stay within the existing three-second case budget.

These inputs come from the integrity branch's MEANING_ADVERSARIAL corpus.
The check measures this host and these cases; it does not prove a complexity
bound or cover every input. It imports no protection or editor modules.
"""
import time

import pytest

from articulate import meaning


CASES = [
    ("unclosed-quote", '"' + "x" * 40000),
    ("repeated-quote-openers", "\u201ca " * 20000),
    ("unclosed-display-math", "\\[" * 20000),
    ("unclosed-environments", "\\begin{align}" * 5000),
    ("unbalanced-url-closers", "http://x" + ")" * 40000),
    ("url-citation-tail", "http://x" + "[1]" * 13000),
    ("numeric-digits", "1" * 40000),
    ("scope-lookahead", "up to " * 8000 + "5"),
    ("modal-negation", "do not have to " * 4000),
    ("quantifier-lookahead", "at all  " * 8000 + "times"),
    ("sentence-start-names", "A " * 20000),
    ("unfinished-citations", "Smith and " * 8000 + "(2020)"),
]


@pytest.mark.parametrize("name,text", CASES, ids=[name for name, _ in CASES])
def test_comparison_selected_large_inputs_finish_within_budget(name, text):
    started = time.perf_counter()
    report = meaning.compare(text, text[:len(text) // 2])
    elapsed = time.perf_counter() - started
    assert report["schema"] == "articulate/meaning/v2"
    assert elapsed < 3.0, f"{name}: {elapsed:.2f}s exceeded the 3.0s case budget"
