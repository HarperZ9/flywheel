"""The editor never invents the author's experience and never drops an
AI-assistance disclosure. Author-supplied text binds to the edit plan."""
import base64
import importlib
import json

import pytest

ORIGINAL = ("The county held the vote in 2019. The measure failed by a wide margin.\n\n"
            "Turnout was low across the district.")
INVENTED = "I watched the vote fail in 2019 from the back of the room."


def guard():
    return importlib.import_module("articulate.meaning_guard")


def authorship():
    return importlib.import_module("articulate.authorship")


def host():
    return importlib.import_module("articulate.host_edit")


def test_invented_anecdote_is_retained_as_the_original():
    rewrite = ORIGINAL.replace("Turnout was low across the district.",
                               "Turnout was low across the district. " + INVENTED)
    out = guard().guard_rewrite(ORIGINAL, rewrite)
    assert out["text"] == ORIGINAL
    assert any("added-first-person" in r for item in out["refused"] for r in item["reasons"])


def test_the_same_sentence_supplied_by_the_author_passes():
    rewrite = ORIGINAL.replace("Turnout was low across the district.",
                               "Turnout was low across the district. " + INVENTED)
    out = guard().guard_rewrite(ORIGINAL, rewrite, author_text=INVENTED)
    assert out["text"] == rewrite


def test_third_person_to_first_person_on_the_same_content_passes():
    old = "The author found the minutes in a box at the clerk's office."
    new = "I found the minutes in a box at the clerk's office."
    assert authorship().novel_first_person(old, new) == []
    assert guard().guard_rewrite(old, new)["text"] == new


def test_novel_first_person_names_the_sentence():
    assert authorship().novel_first_person("Turnout was low.", "Turnout was low. " + INVENTED) == [INVENTED]


DISCLOSED = ORIGINAL + "\n\nDrafted with Claude from the record and checked by the author."


@pytest.mark.parametrize("change", [
    lambda t: t.replace("\n\nDrafted with Claude from the record and checked by the author.", ""),
    lambda t: t.replace("Drafted with Claude", "Written"),
])
def test_disclosure_removal_or_rewording_is_retained(change):
    out = guard().guard_rewrite(DISCLOSED, change(DISCLOSED))
    assert out["text"] == DISCLOSED
    assert out["refused"]


def test_disclosure_is_a_protected_span_kind():
    spans = guard().protected_spans(DISCLOSED)
    assert any(s["kind"] == "disclosure" for s in spans)


def _settings(plan_id):
    encoded = plan_id.rsplit(".", 1)[0]
    return json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))


def _v1_plan(text):
    h = host()
    settings = _settings(h.edit_plan(text)["plan_id"])
    for key in ("author_text_sha256", "voice_profile_sha256", "voice_name"):
        settings.pop(key)
    settings["schema"] = "articulate/edit-plan/v1"
    return h._token(text, settings)


def test_v1_plan_still_verifies():
    h = host()
    plan = _v1_plan(ORIGINAL)
    out = h.edit_submit(ORIGINAL, ORIGINAL.replace("wide", "large"), plan)
    assert out["ok"] and out["text"] != ORIGINAL


def test_v2_plan_binds_author_text():
    h = host()
    plan = h.edit_plan(ORIGINAL, author_text=INVENTED)
    assert _settings(plan["plan_id"])["schema"] == "articulate/edit-plan/v2"
    rewrite = ORIGINAL.replace("Turnout was low across the district.",
                               "Turnout was low across the district. " + INVENTED)
    out = h.edit_submit(ORIGINAL, rewrite, plan["plan_id"], author_text=INVENTED)
    assert out["text"] == rewrite
    assert out["receipt"]["author_text_sha256"].startswith("sha256:")


def test_wrong_author_text_hash_is_refused():
    h = host()
    plan = h.edit_plan(ORIGINAL, author_text=INVENTED)
    with pytest.raises(ValueError, match="author text"):
        h.edit_submit(ORIGINAL, ORIGINAL, plan["plan_id"], author_text="something else")


def test_author_text_on_a_plan_without_it_is_refused():
    h = host()
    plan = h.edit_plan(ORIGINAL)
    with pytest.raises(ValueError, match="author text"):
        h.edit_submit(ORIGINAL, ORIGINAL, plan["plan_id"], author_text=INVENTED)


def test_unknown_plan_schema_is_refused():
    h = host()
    settings = _settings(h.edit_plan(ORIGINAL)["plan_id"])
    settings["schema"] = "articulate/edit-plan/v9"
    with pytest.raises(ValueError, match="unknown plan schema"):
        h.edit_submit(ORIGINAL, ORIGINAL, h._token(ORIGINAL, settings))


def test_rewrite_instructions_forbid_invented_experience():
    from articulate import prompts
    text = prompts.rewrite_instructions("no findings")
    assert "Never add a personal experience, memory, place, date or feeling" in text
    assert "[author: ...]" in text
