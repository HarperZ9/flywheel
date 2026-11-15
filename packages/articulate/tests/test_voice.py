"""The author-voice profile holds aggregates only, says what it holds in plain
words, and compares a draft against the author's own measured range without
writing a word in the author's name."""
import importlib
import json
import re

import pytest

from voice_fixtures import VARIED, templated_doc


def voice():
    return importlib.import_module("articulate.voice")


SAMPLES = [text for _, _, text in VARIED]


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.split()) >= 4]


def test_profile_holds_no_sample_sentence():
    blob = json.dumps(voice().build_profile(SAMPLES))
    for sample in SAMPLES:
        for sentence in _sentences(sample):
            assert sentence not in blob, sentence


def test_profile_drops_names_of_people_and_places():
    profile = voice().build_profile(SAMPLES)
    vocab = set(profile.get("vocabulary", {}).get("words", []))
    for name in ("doreen", "luis", "gerald", "tacoma", "everett", "olympia", "safeway"):
        assert name not in vocab
    blob = json.dumps(profile)
    for name in ("Doreen", "Luis", "Gerald", "Olympia"):
        assert name not in blob


def test_profile_records_sources_as_hashes_and_counts():
    profile = voice().build_profile(SAMPLES)
    assert profile["schema"] == "articulate/voice-profile/v1"
    src = profile["sources"]
    assert len(src["samples"]) == 4
    assert all(set(s) == {"sha256", "words"} for s in src["samples"])
    assert src["indicative_only"] is True
    assert src["total_words"] < 5000


def test_no_vocabulary_option_omits_the_field():
    assert "vocabulary" not in voice().build_profile(SAMPLES, vocabulary=False)


def test_profile_has_every_designed_field():
    profile = voice().build_profile(SAMPLES)
    for key in ("sources", "rhythm", "openings", "argument", "function_words", "per_sample"):
        assert key in profile
    assert profile["argument"]["first_person_per_1k"] > 10


def test_describe_speaks_every_field_in_words():
    v = voice()
    profile = v.build_profile(SAMPLES)
    lines = v.describe(profile)
    text = "\n".join(lines)
    for key in profile:
        if key == "schema":
            continue
        assert key in text, key
    assert "—" not in text


def test_compare_places_draft_inside_or_outside_the_range():
    v = voice()
    profile = v.build_profile(SAMPLES)
    report = v.compare(templated_doc(0), profile)
    fp = next(f for f in report["features"] if f["feature"] == "first_person_per_1k")
    assert fp["verdict"] == "below"
    assert set(fp) == {"feature", "low", "high", "value", "verdict"}
    inside = v.compare(SAMPLES[0], profile)
    fp = next(f for f in inside["features"] if f["feature"] == "first_person_per_1k")
    assert fp["verdict"] == "inside"


def test_compare_has_no_total_distance_and_ends_with_its_limit():
    v = voice()
    report = v.compare(templated_doc(0), v.build_profile(SAMPLES))
    assert not {"score", "distance", "total", "similarity"} & set(report)
    assert report["scope"].startswith("Places each feature of the draft")
    assert report["ai_detector_consulted"] is False


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


FIRST_PERSON = re.compile(r"\b(?:I|me|my|mine|myself)\b")


def test_compare_never_emits_author_attributed_text():
    """No sentence of the draft, no sample sentence and no first-person sentence
    appears anywhere in the compare report: it gives ranges and line numbers."""
    v = voice()
    draft = SAMPLES[1] + "\n\n" + templated_doc(0)
    report = v.compare(draft, v.build_profile(SAMPLES))
    for s in _strings(report):
        assert not FIRST_PERSON.search(s), s
        for sentence in _sentences(draft) + [x for t in SAMPLES for x in _sentences(t)]:
            assert sentence not in s


def test_compare_locates_long_stretches_without_the_author():
    v = voice()
    long_draft = "\n\n".join(templated_doc(i) for i in range(4)) * 2
    report = v.compare(long_draft, v.build_profile(SAMPLES))
    kinds = {loc["kind"] for loc in report["locations"]}
    assert "no-first-person-stretch" in kinds
    for loc in report["locations"]:
        assert set(loc) == {"kind", "line_start", "line_end", "measure"}


def test_compare_replays_from_the_same_inputs():
    v = voice()
    profile = v.build_profile(SAMPLES)
    assert v.compare(SAMPLES[2], profile) == v.compare(SAMPLES[2], profile)


def test_build_profile_needs_text():
    with pytest.raises(ValueError):
        voice().build_profile([])


def test_ranges_stay_within_what_each_measure_allows():
    v = voice()
    rows = [{"concession_per_1k": 0.0, "opens_with_i_share": 0.98},
            {"concession_per_1k": 1.34, "opens_with_i_share": 1.0}]
    assert v._range({"per_sample": rows}, "concession_per_1k")[0] == 0.0
    assert v._range({"per_sample": rows}, "opens_with_i_share")[1] == 1.0
    profile = v.build_profile(SAMPLES)
    for row in v.compare(SAMPLES[0], profile)["features"]:
        assert row["low"] >= 0, row
        if row["feature"].endswith("_share"):
            assert row["high"] <= 1, row
