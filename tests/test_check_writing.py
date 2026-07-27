import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_writing as CW  # noqa: E402


def test_strip_code_removes_fenced_blocks():
    t = "before\n```python\nx = 1  # utilize leverage\n```\nafter"
    out = CW.strip_code(t)
    assert "utilize" not in out
    assert "before" in out and "after" in out


def test_strip_code_removes_inline_backticks_and_math():
    assert "utilize" not in CW.strip_code("run `utilize()` now")
    assert "alpha" not in CW.strip_code("the value $\\alpha$ holds")


def test_sentences_split_on_terminal_punctuation_only():
    t = "One sentence wraps\nacross a line. Two is here! Three?"
    s = CW.sentences(t)
    assert len(s) == 3
    assert "wraps across a line" in s[0]


def test_count_words_counts_word_tokens():
    assert CW.count_words("one two three") == 3
    assert CW.count_words("code `ignored` after strip is on caller") == 7
