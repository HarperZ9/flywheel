"""house/2: the brief that replaced house/1 after the evaluation found house/1
made a model without tools claim checks it never ran. These tests hold the
constraints that fix in the brief text itself, for every tuning, and keep
house/1 receipts verifiable.

Fixtures: tests/house_fixtures.py and tests/house1_receipts.json (receipts made
by the house/1 code at a27d341)."""
import itertools
import json
import pathlib
import re

import pytest

from articulate import house, house_settings, house_spec
from house_fixtures import (HOUSE1_INDUCING, LIFE_GAP_REPLY, RESIDUE_REPLY, DASH_REPLY,
                            UNTAKEN_ACTION_SENTENCES)

HERE = pathlib.Path(__file__).parent


def _all_briefs(version=None):
    spec = house.spec(version)
    keys = list(spec["tuning"])
    for combo in itertools.product(*[spec["tuning"][k]["values"] for k in keys]):
        settings = house_settings.resolve(environ={}, overrides=dict(zip(keys, combo)))
        yield dict(zip(keys, combo)), house.brief(settings, version), settings


def test_current_version_is_house_2_and_house_1_stays_packaged():
    assert house_spec.CURRENT == "house/2" and house.spec()["version"] == "house/2"
    assert house_spec.versions() == ["house/1", "house/2"]
    assert house.spec("house/1")["version"] == "house/1"
    with pytest.raises(ValueError):
        house.spec("house/9")


def test_each_version_has_its_own_fingerprint():
    assert house.fingerprint(version="house/1") != house.fingerprint(version="house/2")
    assert house.fingerprint() == house.fingerprint(version="house/2")
    frozen = json.loads((HERE / "house1_receipts.json").read_text(encoding="utf-8"))
    assert house.fingerprint(version="house/1") == frozen["residue"]["house_fingerprint"]


def test_house_1_receipts_still_verify():
    frozen = json.loads((HERE / "house1_receipts.json").read_text(encoding="utf-8"))
    for name, text in (("residue", RESIDUE_REPLY), ("dash", DASH_REPLY)):
        assert frozen[name]["house_version"] == "house/1"
        assert house.verify_receipt(frozen[name], text) == ("Match", "output and edits re-derive")
        assert house.verify_receipt(frozen[name], text + " More.")[0] == "Drift"


def test_a_receipt_naming_an_unknown_version_is_unverifiable():
    rec = dict(house.transform(RESIDUE_REPLY)["receipt"], house_version="house/9")
    verdict, detail = house.verify_receipt(rec, RESIDUE_REPLY)
    assert verdict == "Unverifiable" and "house/1, house/2" in detail


def test_versions_share_one_edit_list():
    """A house/1 receipt replays on the current transform only while the edit
    list is the same. A change to it needs its own replay path."""
    one, two = house.spec("house/1"), house.spec("house/2")
    assert one["residue"] == two["residue"]


def test_house_1_holds_the_lines_that_induced_untaken_actions():
    """The regression this version fixes, kept visible: house/1 modelled the
    report of actions a model without tools never took."""
    text = house.brief(version="house/1")
    assert all(p in text for p in HOUSE1_INDUCING)


@pytest.mark.parametrize("phrase", HOUSE1_INDUCING)
def test_no_house_2_brief_models_an_untaken_action(phrase):
    for tuning, text, _ in _all_briefs():
        assert phrase not in text, tuning
        # No line hands the model a sample first-person action report.
        assert not re.search(r"\bI (?:read|ran|checked|tested|opened|changed)\b", text), tuning


def test_every_house_2_brief_ties_first_person_and_checks_to_tool_results():
    for tuning, text, _ in _all_briefs():
        low = text.lower()
        assert "tool result" in low, tuning
        if tuning["first_person"] == "actions":
            assert 'use "i" only for actions this session\'s tool results show you took' in low
            assert "without narrating checks" in low


def test_the_brief_forbids_every_verb_the_regression_fixture_used():
    text = house.brief().lower()
    forbidden = re.search(r"never say you ([^.]*?) anything", text).group(1)
    named = set(re.findall(r"[a-z]+", forbidden)) - {"or"}
    assert {verb for verb, _ in UNTAKEN_ACTION_SENTENCES} <= named
    for verb, sentence in UNTAKEN_ACTION_SENTENCES:
        assert sentence.startswith("I ") and verb in named


def test_every_house_2_brief_refuses_to_invent_a_life_and_marks_the_gap():
    for tuning, text, _ in _all_briefs():
        low = text.lower()
        assert "write about the person's life or as them" in low, tuning
        assert "use only facts they gave you" in low, tuning
        assert "mark each missing fact as a gap, [your detail:" in low, tuning
        assert "and ask for it." in low, tuning


def test_the_house_2_brief_is_the_wording_that_passed_the_reader_gate():
    """0.8.0 ships the first house/2 wording: life line last, "use only facts
    they gave you". It passed both ship gates (18 : 9, p = 0.12). The variant
    that named what not to invent failed the reader gate and does not ship."""
    text = house.brief()
    lines = text.splitlines()
    assert lines[-1] == ("Asked to write about the person's life or as them, use only facts "
                         "they gave you. Mark each missing fact as a gap, [your detail: when "
                         "you started], and ask for it.")
    assert "invent no event" not in text.lower()


def test_the_gap_shape_the_brief_asks_for_makes_no_human_claim():
    assert "[your detail:" in LIFE_GAP_REPLY and LIFE_GAP_REPLY.rstrip().endswith("?")
    assert house.human_claims(LIFE_GAP_REPLY) == []
    out = house.transform(LIFE_GAP_REPLY)
    assert out["text"] == LIFE_GAP_REPLY and out["edits"] == []


def test_default_length_asks_for_completeness_and_only_terse_asks_for_short():
    lines = house.spec()["tuning"]["length"]["lines"]
    assert "completeness comes before brevity" in lines["default"].lower()
    assert "stop when the answer is complete" not in house.brief().lower()
    for name in ("default", "full"):
        assert not re.search(r"\b(?:short|brief|one or two sentences|concise)\b", lines[name], re.I), name
    assert "one or two sentences" in lines["terse"]


def test_every_house_2_session_context_fits_the_ceiling():
    for tuning, _, settings in _all_briefs():
        assert len(house_spec.session_context(settings)) <= house.BRIEF_CEILING, tuning
