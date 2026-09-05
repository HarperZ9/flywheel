"""The roster copy the compiled app renders, pinned to the engine's lane list.

`desktop/lib/views/lanes_view.dart` titles each card from
`laneIdentities[lane.name]` and falls back to the bare lane name and the
registry's one-line role. That fallback is the problem: a lane added to the
engine with no copy in the app still renders a card that looks finished, so the
gap is invisible on screen and nothing in a Dart test can see the Python
registry it drifted from. Six lanes had already drifted out when this was
written.

Nothing here reads the app's opinion of itself. The map is parsed out of the
Dart source and compared to `LANES`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from harness.lanes import LANES

DART = (Path(__file__).resolve().parent.parent / "desktop" / "lib" / "models"
        / "lane_identity.dart")

ENTRY = re.compile(r"^  '(?P<name>[a-z0-9-]+)': LaneIdentity\(\n(?P<body>.*?)\n  \),$",
                   re.S | re.M)
QUOTED = re.compile(r"'((?:[^'\\]|\\.)*)'")


def _field(body: str, key: str) -> str:
    """The value of one field, joining Dart's adjacent-string concatenation."""
    after = body.split(f"{key}:", 1)[1]
    chunk = after.split("',\n", 1)[0] + "'"
    return " ".join(QUOTED.findall(chunk))


def identities() -> dict:
    source = DART.read_text(encoding="utf-8")
    found = {m.group("name"): {k: _field(m.group("body"), k)
                               for k in ("title", "identity", "surface")}
             for m in ENTRY.finditer(source)}
    assert found, f"no entries parsed out of {DART.name}"
    return found


def test_every_lane_the_engine_ships_has_copy_in_the_app():
    assert set(identities()) == set(LANES)


def test_no_entry_names_a_lane_the_engine_dropped():
    # The other direction of the same equality, stated on its own so a failure
    # says which way the drift went: dead copy for a retired lane still renders
    # a title and an identity for something the roster will never list.
    assert set(identities()) - set(LANES) == set()


@pytest.mark.parametrize("field", ["title", "identity", "surface"])
def test_no_field_is_blank(field):
    blank = [name for name, entry in identities().items() if not entry[field].strip()]
    assert blank == []


def test_the_copy_holds_the_shipped_voice():
    # This text ships inside the compiled application, so it is a published
    # surface: no em-dash, and no local path.
    for name, entry in identities().items():
        for field, value in entry.items():
            assert "\u2014" not in value, f"{name}.{field} carries an em-dash"
            assert "C:\\" not in value and "E:\\" not in value, f"{name}.{field}"
