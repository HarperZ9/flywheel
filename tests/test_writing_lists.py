"""The word lists are data with one home, re-exported for compatibility."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_writing as CW  # noqa: E402
import writing_lists as WL  # noqa: E402


def test_lists_live_in_the_data_module_and_reexport():
    for name in ("MARKETING", "BANNED", "PHRASAL", "MODAL_HEDGE"):
        data = getattr(WL, name)
        assert isinstance(data, tuple) and data
        assert getattr(CW, name) is data, f"{name} re-export broken"


def test_every_entry_is_lowercase_and_stripped():
    for name in ("MARKETING", "BANNED", "PHRASAL", "MODAL_HEDGE"):
        for entry in getattr(WL, name):
            assert entry == entry.lower().strip(), entry


def test_no_entry_is_duplicated_across_lists():
    seen: dict = {}
    for name in ("MARKETING", "BANNED", "PHRASAL", "MODAL_HEDGE"):
        for entry in getattr(WL, name):
            assert entry not in seen, f"{entry} in both {seen.get(entry)} and {name}"
            seen[entry] = name
