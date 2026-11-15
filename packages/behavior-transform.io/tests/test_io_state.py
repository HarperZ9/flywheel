import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import os
import pytest

from io_state import (
    normalize_mode,
    normalize_profile,
    profile_for_mode,
    split_io_toggles,
    ON_VALUES,
    OFF_VALUES,
    PROFILE_ALIASES,
)


def test_normalize_mode_on_values():
    for val in ("on", "1", "true", "yes", "ops", "standard"):
        assert normalize_mode(val) == "on", f"expected 'on' for {val!r}"


def test_normalize_mode_off_values():
    for val in ("off", "0", "false", "no", "research", "raw"):
        assert normalize_mode(val) == "off", f"expected 'off' for {val!r}"


def test_normalize_mode_none_returns_default():
    assert normalize_mode(None) is None
    assert normalize_mode(None, "on") == "on"


def test_normalize_mode_invalid_returns_default():
    assert normalize_mode("garbage") is None
    assert normalize_mode("garbage", "off") == "off"


def test_normalize_mode_case_insensitive():
    assert normalize_mode("ON") == "on"
    assert normalize_mode("Research") == "off"


def test_normalize_profile_ops():
    assert normalize_profile("ops") == "ops"
    assert normalize_profile("1") == "ops"
    assert normalize_profile("security") == "ops"


def test_normalize_profile_research():
    assert normalize_profile("research") == "research"
    assert normalize_profile("0") == "research"
    assert normalize_profile("raw") == "research"


def test_normalize_profile_academic():
    assert normalize_profile("academic") == "academic"


def test_normalize_profile_none():
    assert normalize_profile(None) is None


def test_profile_for_mode():
    assert profile_for_mode("on") == "ops"
    assert profile_for_mode("off") == "research"


def test_split_io_toggles_on():
    mode, rest = split_io_toggles(["arg1", "--IO-on", "arg2"])
    assert mode == "on"
    assert rest == ["arg1", "arg2"]


def test_split_io_toggles_off():
    mode, rest = split_io_toggles(["--IO-off", "arg1"])
    assert mode == "off"
    assert rest == ["arg1"]


def test_split_io_toggles_none():
    mode, rest = split_io_toggles(["arg1", "arg2"])
    assert mode is None
    assert rest == ["arg1", "arg2"]


def test_split_io_toggles_last_wins():
    mode, rest = split_io_toggles(["--IO-on", "--IO-off"])
    assert mode == "off"
    assert rest == []


def test_on_values_and_off_values_disjoint():
    assert ON_VALUES & OFF_VALUES == set()


def test_profile_aliases_cover_all_on_off():
    for val in ON_VALUES | OFF_VALUES:
        assert val in PROFILE_ALIASES, f"{val!r} missing from PROFILE_ALIASES"
