"""The README card fits the columns it is drawn in, and says one thing.

A card is a table rendered to SVG: a key column, a value column, and a note
column beside them, with a footnote under the rule. None of the three is
clipped by the renderer, so a sentence that outgrows its column draws over the
one next to it and every other check stays green. These measure the drawing
rather than read the spec.

Everything here settles whether the card fits its columns and matches its
spec. Whether the card is TRUE of what the capability check does to a shell
command is a different question, and tests/test_shell_admission.py settles that
one by driving the code.
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "docs" / "art"
SCRIPTS = ROOT / "scripts"


def _load(name):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CARD = _load("repo_card")


def _cards() -> list[dict]:
    specs = [json.loads(p.read_text(encoding="utf-8"))
             for p in sorted(ART.glob("*.art.json"))]
    return [card for spec in specs for card in spec.get("cards", [])]


def _lines_that_run_long(text: str, label: str, budget: float,
                         limit: int) -> list[str]:
    """Two ways a wrapped column goes wrong, and the second is the one a
    joined-text check misses. Dropping the ending is the obvious one. The other
    is a single token longer than the budget: the wrapper is greedy, so it
    leaves that token alone on its line, the joined text still equals the
    source, and the drawing runs off the page with every check green."""
    drawn = CARD._wrap(text, budget, limit)
    bad = []
    if " ".join(drawn) != " ".join(text.split()):
        bad.append(f"{label} loses its ending")
    for line in drawn:
        width = CARD.text_width(line)
        if width > budget:
            bad.append(f"{label} draws {width:.0f}px into a {budget:.0f}px "
                       f"column: {line!r}")
    return bad


def _card_text_that_overflows(card: dict) -> list[str]:
    """A row holds a key and a value on one unwrapped line each, and a note
    wrapped to two."""
    # Characters, not glyphs, for the key and the value: both of those columns
    # are mono, where a character count is a fair proxy. The note column is
    # proportional, so it is measured with the renderer's own width table.
    key_budget = int((CARD.KEY_W + CARD.GUTTER - 16) / 7.8)
    value_budget = int(CARD.VAL_W / 7.2)
    bad = []
    for field in card["fields"]:
        if len(field["key"]) > key_budget:
            bad.append(f'the key {field["key"]!r} is wider than its column')
        if len(field["value"]) > value_budget:
            bad.append(f'the value {field["value"]!r} is wider than its column')
        bad += _lines_that_run_long(
            field["note"], f'the note under {field["key"]!r}',
            CARD.NOTE_BUDGET, CARD.NOTE_LINES)
    bad += _lines_that_run_long(card["footnote"], "the footnote",
                                CARD.FOOT_BUDGET, CARD.FOOT_LINES)
    return bad


def test_there_is_a_card_to_check():
    assert _cards(), "no spec carries a card"


def test_no_card_text_runs_out_of_its_column():
    for card in _cards():
        assert not _card_text_that_overflows(card), card["file"]


def test_that_card_check_can_actually_fail():
    """A green suite otherwise proves only that the check ran. The third row is
    the greedy-wrap case: one unbreakable token, nothing dropped."""
    control = {
        "fields": [{"key": "k" * 90, "value": "v" * 90, "note": "fine"},
                   {"key": "k", "value": "v", "note": "word " * 200},
                   {"key": "k", "value": "v", "note": "x" * 120}],
        "footnote": "word " * 400,
    }
    assert len(_card_text_that_overflows(control)) == 5


def test_a_card_wears_exactly_one_hot_mark():
    """Verdict-only colour. Two marks and the drawing stops saying which row
    carries the claim; none and the colour is decoration."""
    for card in _cards():
        marked = [f["key"] for f in card["fields"]
                  if f.get("tone", "none") != "none"]
        assert len(marked) == 1, f'{card["file"]} marks {marked}'


def test_a_card_draws_shapes_not_digits():
    """A token count or a byte count is wrong by the next commit, so the value
    column carries the shape of a value rather than a literal that will rot."""
    for card in _cards():
        for field in card["fields"]:
            assert not re.search(r"[0-9a-f]{12,}", field["value"]), field["key"]
            assert not re.search(r"[0-9]{5,}", field["value"]), field["key"]


def test_the_readme_describes_the_card_it_shows():
    """GitHub draws a card as an <img>, and an <img> hides the description the
    SVG carries inside it. The README alt attribute is the whole of what a
    reader who cannot see the card gets, so it has to be the one in the spec."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for card in _cards():
        assert card["alt"] in readme, (
            f'{card["file"]}: the README describes it as something else')
