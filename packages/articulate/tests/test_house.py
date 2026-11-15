"""The house voice: a published spec, a brief generated from it, and a
deterministic transform with an exact-edit verifier, a meaning guard and a
receipt.

Every fixture is synthetic (tests/house_fixtures.py)."""
import json
import re

import pytest

from articulate import house, house_settings
from house_fixtures import (ACTION_REPLY, CONTENT_OFFER, DASH_REPLY, DISCLOSURE_REPLY,
                            HUMAN_CLAIM_REPLY, RESIDUE_CLEAN, RESIDUE_REPLY)


def test_spec_is_versioned_and_states_its_provenance():
    spec = house.spec()
    assert spec["schema"] == "articulate/house-voice/v1"
    assert spec["version"] == "house/2"
    prov = spec["provenance"]
    assert prov["person_writing_used"] is False
    assert prov["detector_tuned"] is False
    assert prov["research"], "the spec names the research it rests on"


def test_brief_is_generated_from_the_spec_and_fits_its_ceiling():
    text = house.brief()
    assert text.startswith("Articulate house voice, house/2.")
    assert len(text) <= house.BRIEF_CEILING == 1500
    assert "model's voice" in text
    assert "—" not in text
    for line in house.spec()["brief"]["lines"]:
        assert line.startswith("@") or line in text


def test_brief_and_spec_make_no_human_claim():
    assert house.human_claims(house.brief()) == []
    spec_text = json.dumps(house.spec()["brief"])
    assert house.human_claims(spec_text) == []


def test_tuning_keys_change_brief_lines_and_nothing_else():
    base = house.brief()
    terse = house.brief(house_settings.resolve(environ={}, overrides={"length": "terse"}))
    assert terse != base
    changed = set(terse.split("\n")) ^ set(base.split("\n"))
    lines = house.spec()["tuning"]["length"]["lines"]
    assert changed == {lines["default"], lines["terse"]} - {""}


def test_residue_opener_and_closer_sentences_are_deleted():
    out = house.transform(RESIDUE_REPLY)
    assert out["text"] == RESIDUE_CLEAN
    rules = {e["rule"] for e in out["receipt"]["edits"]}
    assert rules <= {"residue", "residue-paragraph"} and rules


def test_a_sentence_with_content_is_never_deleted():
    out = house.transform(CONTENT_OFFER)
    assert out["text"] == CONTENT_OFFER
    assert out["receipt"]["edits"] == []


def test_em_dashes_become_commas_outside_protected_spans():
    out = house.transform(DASH_REPLY)
    assert "failed twice, both times" in out["text"]
    assert "keep — this dash" in out["text"]
    assert "keeps its dash — exactly" in out["text"]
    assert "https://example.com/a—b" in out["text"]


def test_disclosure_survives_byte_for_byte():
    out = house.transform(DISCLOSURE_REPLY)
    assert out["text"].startswith("Drafted with help from Claude and edited by the author.\n")
    assert "Great question" not in out["text"]


def test_human_claim_is_a_note_and_never_an_edit():
    out = house.transform(HUMAN_CLAIM_REPLY)
    assert out["text"] == HUMAN_CLAIM_REPLY
    notes = [n for n in out["notes"] if n["category"] == "house/human-claim"]
    assert notes and notes[0]["line"] == 1
    assert out["receipt"]["human_claim_notes"] == len(notes)


def test_session_action_first_person_is_not_a_human_claim():
    assert house.human_claims(ACTION_REPLY) == []


def test_a_tampered_candidate_fails_the_exact_edit_verifier():
    out = house.transform(RESIDUE_REPLY)
    edits = out["edits"]
    assert house.verify_edits(RESIDUE_REPLY, out["text"], edits)["ok"] is True
    tampered = out["text"].replace("rose", "fell", 1)
    verdict = house.verify_edits(RESIDUE_REPLY, tampered, edits)
    assert verdict["ok"] is False and verdict["reasons"]


def test_an_undeclared_rule_or_a_content_deletion_fails_the_verifier():
    text = "Great question! The answer is 4."
    bogus = [{"rule": "residue", "start": text.index("The"), "end": len(text), "new": ""}]
    assert house.verify_edits(text, "Great question! ", bogus)["ok"] is False
    unknown = [{"rule": "rewrite", "start": 0, "end": 5, "new": "Fine"}]
    assert house.verify_edits(text, "Fine question! The answer is 4.", unknown)["ok"] is False


def test_off_returns_the_input_unchanged_with_a_receipt_saying_so():
    settings = house_settings.resolve(environ={"ARTICULATE_HOUSE_VOICE": "off"})
    out = house.transform(RESIDUE_REPLY, settings)
    assert out["text"] == RESIDUE_REPLY
    assert out["receipt"]["mode"] == "off" and out["receipt"]["edits"] == []


def test_receipt_shape_and_replay():
    out = house.transform(RESIDUE_REPLY)
    rec = out["receipt"]
    assert rec["schema"] == "articulate/house-receipt/v2"
    assert rec["house_version"] == "house/2"
    assert rec["ai_detector_consulted"] is False
    assert rec["house_fingerprint"].startswith("sha256:")
    assert "scope" in rec and rec["timing_ms"] >= 0
    assert not set(rec) & {"score", "humanness", "ai_probability"}
    assert house.verify_receipt(rec, RESIDUE_REPLY)[0] == "Match"
    assert house.verify_receipt(rec, RESIDUE_REPLY + " Extra.")[0] == "Drift"
    assert house.verify_receipt({"schema": "other"}, RESIDUE_REPLY)[0] == "Unverifiable"


def test_receipt_holds_no_text_from_the_reply():
    rec = json.dumps(house.transform(RESIDUE_REPLY)["receipt"])
    for phrase in ("Great question", "hope this helps", "make_key"):
        assert phrase not in rec


def test_stream_transform_matches_the_whole_transform():
    chunks = [RESIDUE_REPLY[i:i + 17] for i in range(0, len(RESIDUE_REPLY), 17)]
    streamed = "".join(house.transform_stream(chunks))
    assert streamed == house.transform(RESIDUE_REPLY)["text"]


def test_stream_never_splits_inside_a_code_fence():
    text = "Intro line.\n\n```\na — b\n\nc — d\n```\n\nDone — here."
    chunks = [text[i:i + 5] for i in range(0, len(text), 5)]
    out = "".join(house.transform_stream(chunks))
    assert "a — b\n\nc — d" in out and "Done, here." in out


def test_meaning_guard_holds_for_every_fixture():
    from articulate import meaning
    for text in (RESIDUE_REPLY, DASH_REPLY, DISCLOSURE_REPLY, HUMAN_CLAIM_REPLY, ACTION_REPLY):
        out = house.transform(text)
        assert out["refused"] == []
        report = meaning.compare(text, out["text"])
        assert not meaning.blocking(report), text[:30]


def test_house_on_human_control_prose_deletes_nothing_outside_the_list():
    prose = ("The river rose four feet in a night. By morning the mill road was under water, "
             "and the ferry ran on the hour.\n\nNobody in the valley had seen it that high since 1931.")
    out = house.transform(prose)
    assert out["text"] == prose and out["edits"] == []


def test_banned_tics_are_listed_and_each_maps_to_a_style_rule_or_house_check():
    tics = house.spec()["banned_tics"]
    assert {t["id"] for t in tics} >= {"em-dash", "sycophantic-opener", "assistant-closer",
                                       "antithesis", "emoji"}
    assert all(t["checked_by"] for t in tics)


def test_new_spec_text_uses_no_detector_language():
    raw = json.dumps(house.spec()).lower()
    assert not re.search(r"gptzero|originality|undetectable|humaniz|pass as human", raw)


# Review findings (2026-10-01): a dash that is not between two words on one
# line marks an attribution, a placeholder or a bullet. A comma there changes
# what the reader sees, so the dash rule leaves it alone.
@pytest.mark.parametrize("text", [
    "A quote worth keeping.\n— Ada Lovelace",
    "— Ada Lovelace",
    "- — a bullet with a dash",
    "| name | value |\n|---|---|\n| a | — |",
    "Wait—\nthen go.",
    "It ends with —",
    "Before.\n\n—\n\nAfter.",
    "> — quoted attribution",
])
def test_dash_at_a_line_edge_or_in_a_cell_is_left_alone(text):
    out = house.transform(text)
    assert out["text"] == text
    assert [e for e in out["edits"] if e["rule"] == "dash"] == []


def test_dash_between_two_words_still_becomes_a_comma():
    out = house.transform("The cache — once warm — answers fast.")
    assert out["text"] == "The cache, once warm, answers fast."
    assert house.verify_edits("The cache — once warm — answers fast.", out["text"],
                              out["edits"])["ok"]


def test_verifier_refuses_a_dash_edit_at_a_line_start():
    original = "— Ada Lovelace"
    edit = {"rule": "dash", "start": 0, "end": 2, "new": ", "}
    verdict = house.verify_edits(original, ", Ada Lovelace", [edit])
    assert not verdict["ok"]


@pytest.mark.parametrize("text", ["Great question!", "Hope this helps!"])
def test_a_reply_made_only_of_residue_is_kept_whole(text):
    out = house.transform(text)
    assert out["text"] == text
    assert out["refused"] == ["the edits would leave no text"]
    chunks = [text[i:i + 4] for i in range(0, len(text), 4)]
    assert "".join(house.transform_stream(chunks)) == text


def test_stream_matches_whole_transform_on_residue_only_paragraphs():
    text = "Great question!\n\nHope this helps!"
    whole = house.transform(text)["text"]
    assert whole.strip()
    chunks = [text[i:i + 4] for i in range(0, len(text), 4)]
    assert "".join(house.transform_stream(chunks)) == whole


def test_stream_matches_whole_transform_when_an_opener_paragraph_leads():
    text = "Great question!\n\nThe answer is four.\n\nHope this helps!"
    chunks = [text[i:i + 3] for i in range(0, len(text), 3)]
    assert "".join(house.transform_stream(chunks)) == house.transform(text)["text"] \
        == "The answer is four."
