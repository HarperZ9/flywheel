"""The disclosure statement (PLAN section 5.4, ARTICULATE-PLAN step 4).

It never lists a model as an author; it refuses a no-tool claim when the log
records assistance; it takes its verb from the recorded task; it refuses to
leave out a recorded assistance entry; and input methods stay out unless the
writer includes them. These tests guard those lines.
"""
import pytest

from articulate import disclose

ASSIST = {"seq": 3, "kind": "assist", "tool": "Claude Code", "verb": "generated",
          "sections": ["the patch and its tests"], "model": "as declared"}
EDIT = {"seq": 4, "kind": "assist", "tool": "articulate", "version": "0.4.2", "verb": "edited",
        "sections": ["whole document"]}
PEOPLE = {"authors": [{"name": "Maria Lopez",
                       "roles": ["Conceptualization", "Writing – original draft"]}]}


def test_the_verb_comes_from_the_recorded_task():
    s = disclose.build([ASSIST, EDIT], PEOPLE)
    assert "Generated with Claude Code" in s and "Edited with articulate 0.4.2" in s
    assert "assisted" not in s.lower().replace("assisted-by", "")


def test_a_model_never_holds_an_authorship_role():
    for name in ("Claude", "ChatGPT", "GPT-5", "Gemini", "Articulate"):
        with pytest.raises(disclose.DisclosureRefused):
            disclose.build([ASSIST], {"authors": [{"name": name, "roles": ["Software"]}]})


def test_unknown_credit_roles_are_refused():
    with pytest.raises(disclose.DisclosureRefused):
        disclose.build([], {"authors": [{"name": "Maria", "roles": ["Vibes"]}]})


def test_a_no_tool_claim_is_refused_when_assistance_is_recorded():
    with pytest.raises(disclose.DisclosureRefused):
        disclose.build([ASSIST], PEOPLE, claim="No AI was used in this work.")
    # Without a recorded assist the writer may state what they like; the tool
    # itself never writes that sentence.
    s = disclose.build([], PEOPLE)
    assert "no ai" not in s.lower()


def test_a_recorded_assist_cannot_be_left_out():
    with pytest.raises(disclose.DisclosureRefused):
        disclose.build([ASSIST, EDIT], PEOPLE, omit=(4,))


def test_the_pip_form_never_writes_a_co_author_trailer():
    s = disclose.build([ASSIST], PEOPLE, template="pip")
    assert "Assisted-by: Claude Code" in s and "Generated: the patch and its tests" in s
    assert "co-authored-by" not in s.lower()


def test_input_methods_stay_out_unless_included():
    dictation = {"seq": 5, "kind": "input_method", "method": "dictation",
                 "sections": ["whole document"]}
    assert "dictation" not in disclose.build([dictation], PEOPLE)
    assert "dictation" in disclose.build([dictation], PEOPLE, include=("input_method",))


def test_a_tool_task_must_name_an_author_who_checked_it():
    contrib = dict(PEOPLE, tool_tasks=[{"task": "drafted the abstract", "checked_by": "Nobody"}])
    with pytest.raises(disclose.DisclosureRefused):
        disclose.build([ASSIST], contrib)


# People whose names share a word with a product. A substring filter refused
# every one of them with a message that said they were not a person.
PEOPLE_NAMES = ("Aisha Khan", "Aidan Murphy", "Ai Weiwei", "Aiko Tanaka", "Claude Shannon",
                "Claudette Colvin", "Jean-Claude Martin", "Gabriela Mistral", "Grokhovsky",
                "Priya Gemini")


@pytest.mark.parametrize("name", PEOPLE_NAMES)
def test_a_person_who_shares_a_word_with_a_product_is_never_refused(name):
    s = disclose.build([ASSIST], {"authors": [{"name": name, "roles": ["Software"]}]})
    assert f"- {name}: Software." in s


def test_a_product_name_with_a_version_is_refused_and_type_person_is_honoured():
    for name in ("Claude 3.5 Sonnet", "GPT-4o", "an AI assistant", "ChatGPT"):
        with pytest.raises(disclose.DisclosureRefused):
            disclose.build([], {"authors": [{"name": name, "roles": ["Software"]}]})
    s = disclose.build([], {"authors": [{"name": "Claude", "type": "person",
                                         "roles": ["Software"]}]})
    assert "- Claude: Software." in s
    with pytest.raises(disclose.DisclosureRefused):
        disclose.build([], {"authors": [{"name": "Helper", "type": "tool", "roles": ["Software"]}]})


@pytest.mark.parametrize("claim", ["Written without any AI tools.", "I did not use any AI.",
                                   "No tools were used.", "Entirely human."])
def test_listed_no_tool_phrases_are_refused(claim):
    with pytest.raises(disclose.DisclosureRefused):
        disclose.build([ASSIST], PEOPLE, claim=claim)


@pytest.mark.parametrize("claim", ["The survey needed no aid from the lab.",
                                   "The chamber held no air after the pump ran."])
def test_ordinary_sentences_are_not_no_tool_claims(claim):
    assert claim in disclose.build([ASSIST], PEOPLE, claim=claim)
