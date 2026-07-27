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


def test_list_sizes_are_pinned_against_silent_retype():
    # The Phase 1 lists were moved, not retyped. These pins are the automated
    # backstop: a dropped or fat-fingered entry changes a count and fails here.
    assert len(WL.MARKETING) == 26
    assert len(WL.BANNED) == 34
    assert len(WL.PHRASAL) == 12
    assert len(WL.MODAL_HEDGE) == 6
