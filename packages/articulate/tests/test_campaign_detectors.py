"""Promotional-template and persona-bio checks: hits, hard negatives, banned features."""
import pytest

from articulate import campaign_persona as persona
from articulate import campaign_promo as promo


def labels(text):
    return {f["label"] for f in promo.check(text)}


def test_hype_opener_and_claim_spec_pattern():
    text = "sir... they just dropped a coding model that runs LOCALLY on a laptop at 125 tokens/sec"
    got = labels(text)
    assert "hype opener: address word" in got
    assert "hype opener: drop announcement" in got
    assert "claim and spec number" in got
    assert promo.assess(text)["template"]


def test_launch_copy_formulas_each_name_their_pattern():
    text = ("We spent the last two years building the best solution for people buying data. "
            "Data is the fundamental bottleneck for AI progress, and Quarry will be the infra "
            "that solves it.")
    got = labels(text)
    assert {"launch formula: we spent the last N years", "launch formula: the best solution",
            "launch formula: fundamental bottleneck",
            "launch formula: the infra that solves it"} <= got


def test_finding_shape_matches_detector_records_and_names_a_cost():
    f = promo.check("Introducing Ember, Northlake's first model: a fast local model.")[0]
    for key in ("line", "col", "start", "end", "category", "label", "match", "rule_id", "tier",
                "weight", "cost"):
        assert key in f
    assert f["category"] == "promo" and f["rule_id"].startswith("promo/")
    assert len(f["cost"]) > 20


def test_press_release_voice_without_disclosure_is_flagged():
    text = "Northlake launches Ember, its first model: a local coding assistant."
    assert "endorsement without disclosure" in labels(text)


@pytest.mark.parametrize("marker", ["#ad", "Paid partnership.", "Disclosure: I advise them."])
def test_disclosure_marker_suppresses_the_endorsement_finding(marker):
    text = f"{marker} Northlake launches Ember, its first model. You need to try it."
    assert "endorsement without disclosure" not in labels(text)


@pytest.mark.parametrize("text", [
    "Benchmarked the 7B model at 125 tokens/sec on an M3 Max, batch size 1, 4-bit quant.",
    "ok this new local model is good at refactors. ran it on my old laptop, slow but it worked.",
    "Sir please share the link of this model, I want to try in my laptop.",
    "We shipped v2 of our CSV parser today. It handles quoted newlines now.",
    "The NASA dataset has 14 GB of telemetry; we sampled 1% for the first pass.",
    "このモデル、ノートPCでも普通に動いた。",
])
def test_hard_negative_posts_are_not_templates(text):
    assert not promo.assess(text)["template"]


def test_persona_slots_parse_the_stock_grammar():
    p = persona.parse("Age 42, still young at heart, passionate about Candle Making. "
                      "Crypto is the future. | Cat person.")
    assert set(p["slot_types"]) == {"age", "hobby", "token", "tagline"}
    assert "<hobby>" in p["frame"] and "42" not in p["frame"]


@pytest.mark.parametrize("place", ["Lisbon", "Gambia", "Dhaka", "Ohio", "Lagos", "Kyiv"])
def test_place_never_changes_the_verdict_or_frame(place):
    base = persona.assess("A Recruiter in Lisbon, stacking WBTC like a pro. Here for the memes.")
    other = persona.assess(f"A Recruiter in {place}, stacking WBTC like a pro. Here for the memes.")
    assert other["score"] == base["score"] and other["template"] == base["template"]
    assert other["frame"] == base["frame"]


@pytest.mark.parametrize("bio", [
    "Protocol engineer working on Bitcoin fee estimation. Papers in the pinned post.",
    "Small business owner in Accra. We accept $BTC and cash. Mostly cash.",
    "Software developer from Lagos. I like learn new framework and share my progress.",
    "東京でエンジニアをしています。週末は山登り。",
    "مهندس برمجيات من عمّان. أحب القراءة والقهوة.",
    "Cat person, coffee person, spreadsheet person. Accountant in Ohio.",
])
def test_hard_negative_bios_are_not_templates(bio):
    assert not persona.assess(bio)["template"]


def test_platform_parameter_changes_the_slot_floor():
    bio = "A Consultant in Dubai, stacking BTC like a pro. Here for the memes."
    assert persona.assess(bio, "x")["template"]
    assert not persona.assess(bio, "linkedin")["template"]
    assert persona.assess(bio, "nonsense")["platform"] == "generic"
