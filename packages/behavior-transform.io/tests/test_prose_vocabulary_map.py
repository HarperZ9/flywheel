import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest

from prose_vocabulary_map import (
    ProseCalibration,
    CALIBRATIONS,
    ENGLISH_CORE,
    ENGLISH_EXPANSION,
    SPANISH,
    FRENCH,
    GERMAN,
    JAPANESE,
    MANDARIN,
    RUSSIAN,
    ARABIC,
    KOREAN,
    HINDI,
    ABBREVIATIONS,
    OBFUSCATIONS,
    apply_calibration,
    stats,
)


def test_prose_calibration_frozen():
    c = ProseCalibration("test", "calibrated", "en", "tier1", "prose")
    with pytest.raises(AttributeError):
        c.trigger = "changed"


def test_prose_calibration_fields():
    c = ProseCalibration("exploit", "finding", "en", "tier1", "prose", "note")
    assert c.trigger == "exploit"
    assert c.calibrated == "finding"
    assert c.language == "en"
    assert c.tier == "tier1"
    assert c.scope == "prose"
    assert c.note == "note"


def test_calibrations_total_count():
    assert len(CALIBRATIONS) > 200


def test_english_core_nonempty():
    assert len(ENGLISH_CORE) > 50


def test_english_expansion_nonempty():
    assert len(ENGLISH_EXPANSION) > 40


def test_multilingual_coverage():
    assert len(SPANISH) >= 5
    assert len(FRENCH) >= 5
    assert len(GERMAN) >= 5
    assert len(JAPANESE) >= 3
    assert len(MANDARIN) >= 3
    assert len(RUSSIAN) >= 3
    assert len(ARABIC) >= 3
    assert len(KOREAN) >= 3
    assert len(HINDI) >= 3


def test_abbreviations_nonempty():
    assert len(ABBREVIATIONS) >= 10


def test_obfuscations_nonempty():
    assert len(OBFUSCATIONS) >= 10


def test_apply_calibration_clean_text():
    text, count = apply_calibration("the weather is sunny today")
    assert text == "the weather is sunny today"
    assert count == 0


def test_apply_calibration_returns_count():
    text, count = apply_calibration("the exploit was found")
    assert count >= 1
    assert "exploit" not in text.lower() or "vulnerability" in text.lower()


def test_stats_keys():
    s = stats()
    assert "total_entries" in s
    assert "by_language" in s
    assert "by_tier" in s
    assert "by_scope" in s
    assert s["total_entries"] == len(CALIBRATIONS)


def test_stats_languages():
    s = stats()
    assert "en" in s["by_language"]
    assert s["by_language"]["en"] > 100


def test_stats_tiers():
    s = stats()
    assert "tier1" in s["by_tier"]
    assert "tier2" in s["by_tier"]


def test_all_entries_have_required_fields():
    for c in CALIBRATIONS:
        assert c.trigger, f"empty trigger in {c}"
        assert c.calibrated, f"empty calibrated in {c}"
        assert c.language, f"empty language in {c}"
        assert c.tier in ("tier1", "tier2"), f"invalid tier in {c}"
        assert c.scope in ("prose", "abbrev", "obfusc"), f"invalid scope in {c}"
