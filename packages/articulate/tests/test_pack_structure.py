"""The structure rule pack: the specimens of 2026-11-15 and one planted pair
per detector (a minimal positive and a near miss that differs by one feature).

Specimen B is a reply that passed the checker with a texture score of 0 and
that its reader then read back as a list of faults. The expected findings are
the reader's, span by span. The counterpart is the reply the reader accepted.
Names and figures in both fixtures are changed; the sentence shapes are kept.
"""
import pathlib

import pytest

from articulate import checkext, domains

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "structure"
SPECIMEN_B = (FIXTURES / "specimen_b.txt").read_text(encoding="utf-8")
COUNTERPART = (FIXTURES / "counterpart.txt").read_text(encoding="utf-8")


def run(text, profile="chat"):
    return checkext.check_text(text, profile=domains.load_profile(profile))


def hits(text, category, profile="chat"):
    """(tier, rule id, matched text) for one category."""
    r = run(text, profile)
    return [(tier.upper(), f["rule_id"], f["match"]) for tier in ("high", "medium", "low")
            for f in r[tier] if f["category"] == category]


def structure(text, profile="chat"):
    r = run(text, profile)
    return [f for tier in ("high", "medium", "low") for f in r[tier]
            if f["category"].startswith("structure-")]


# --- Specimen B: every finding the reader named, with its span ---------------

EXPECTED_B = [
    ("structure-anaphora", "HIGH", "One points at a line", "back to you."),
    ("structure-triad", "HIGH", "One points at a line", "back to you."),
    ("structure-parallel", "HIGH", '"His last sentence is the useful part" is a setup',
     "reads like a stamp."),
    ("structure-pin", "HIGH", "Your prose rules name each of them.", "each of them."),
    ("structure-pin", "MEDIUM", "The cause is mine.", "The cause is mine."),
    ("structure-pin", "HIGH", "Here is the Marsh message said plainly.", "said plainly."),
    ("structure-parataxis", "HIGH", "One points at a line", "four times today."),
    ("structure-parataxis", "MEDIUM", "The cause is mine.", "The cause is mine."),
    ("structure-parataxis", "MEDIUM", "He does want counterexamples.", "counterexamples."),
    ("structure-landing", "MEDIUM", "I wrote the third in nearly the same words",
     "four times today."),
    ("structure-landing", "HIGH", "Whether Marsh hears from you again", "is up to you."),
]


@pytest.mark.parametrize("category,tier,starts,ends", EXPECTED_B)
def test_specimen_b_finding(category, tier, starts, ends):
    found = hits(SPECIMEN_B, category)
    assert any(t == tier and m.startswith(starts) and m.endswith(ends) for t, _r, m in found), found


def test_specimen_b_is_blocked_under_chat():
    r = run(SPECIMEN_B)
    assert r["gate"] == "blocked" and r["verdict"] == "flagged" and not r["clean"]


def test_specimen_b_spans_index_the_text():
    for f in structure(SPECIMEN_B):
        assert SPECIMEN_B[f["start"]:f["end"]] == f["match"], f["rule_id"]


def test_specimen_b_local_opener_measure():
    cadence = run(SPECIMEN_B)["cadence"]
    assert cadence["repetitive_openers"] is False      # the whole-document ratio, as published
    assert cadence["longest_opener_run"] == 3
    assert cadence["repeated_openers_in_a_row"] is True


def test_a_quoted_sentence_is_a_mention_and_no_pointer():
    assert hits(SPECIMEN_B, "structure-pointer") == []


def test_counterpart_passes():
    r = run(COUNTERPART)
    assert structure(COUNTERPART) == []
    assert r["gate"] == "ok" and r["clean"]
    assert r["cadence"]["repeated_openers_in_a_row"] is False


# --- Specimen A: the stock sentences the reader quoted back -------------------

def test_specimen_a_pointer_sentences():
    text = ("The editor wrote back this morning with four sentences about the entry. "
            "His last sentence is the useful part. He asks for counterexamples only.\n")
    assert [(t, r) for t, r, _m in hits(text, "structure-pointer")] == [
        ("HIGH", "structure-pointer/meta")]
    text = ("The sweep found one failure in 140 lines. "
            "That agrees with what your own study concluded.\n")
    assert [(t, r) for t, r, _m in hits(text, "structure-pointer")] == [
        ("HIGH", "structure-pointer/judge")]


# --- the author's own voice: the pack does not run ---------------------------

OWN_VOICE = ("Keep the well. Water is patience. Water is memory. Water is care.\n\n"
             "Straight up.\n")


def test_own_voice_profiles_raise_no_structure_finding():
    assert structure(OWN_VOICE, "chat"), "the control must be a real positive under chat"
    for profile in ("author-voice", "narrative", "essay", "flavored"):
        assert structure(OWN_VOICE, profile) == [], profile
        assert structure(SPECIMEN_B, profile) == [], profile


def test_only_chat_lists_the_pack():
    listed = [name for name in domains.names()
              if "structure" in domains.load_profile(name).get("rule_packs", ())]
    assert listed == ["chat"]
    assert domains.load_profile("chat")["slop"] == "flavored"


# --- planted controls: a minimal positive and a near miss per detector ------

CONTROLS = [
    # 1. anaphora: three openers gate, two report, a broken run is silent
    ("structure-anaphora", "Keys open doors. Keys rust in rain. Keys get lost in coats.\n",
     ["HIGH"]),
    ("structure-anaphora", "Keys open doors. Keys rust in rain. Most get lost in coats.\n",
     ["LOW"]),
    ("structure-anaphora", "Keys open doors. Rust takes some. Keys get lost in coats.\n", []),
    ("structure-anaphora", "The door sticks. The key turns. The lock holds.\n", []),
    ("structure-anaphora", "The first run failed. The first fix was wrong. The first "
                           "report said so.\n", ["HIGH"]),
    # 2. parallel frames: the same skeleton three times, and the label frame
    ("structure-parallel", "The parser reads the file. The lexer splits the tokens. "
                           "The checker reports the errors.\n", ["HIGH"]),
    ("structure-parallel", "The parser reads the file. The lexer splits the tokens. "
                           "Errors come out of the checker when a rule fails.\n", []),
    ("structure-parallel", "A lexer is a scanner for words. Its parser is a reader of "
                           "phrases, more or less. The tree they build is a record of both.\n",
     ["HIGH"]),
    ("structure-parallel", "A lexer is a scanner for words. Its parser reads phrases, more "
                           "or less. The tree they build is a record of both.\n", []),
    # 3. rule of three: exactly three parallel sentences, or three short items
    ("structure-triad", "Keys open doors. Keys rust in rain. Keys get lost in coats.\n",
     ["HIGH"]),
    ("structure-triad", "Keys open doors. Keys rust in rain. Keys get lost in coats. "
                        "Keys cost little.\n", []),
    ("structure-triad", "It checks spelling, sentence length, and passive voice.\n", ["LOW"]),
    ("structure-triad", "It checks spelling, grammar, sentence length, and passive voice.\n",
     []),
    # 4. paragraph pinning: only as the first sentence of a paragraph
    ("structure-pin", "Here is the plan in short. We ship the fix on Monday, after the "
                      "cache test passes on both machines.\n", ["HIGH"]),
    ("structure-pin", "We ship the fix on Monday, after the cache test passes on both "
                      "machines. Here is the plan in short.\n", []),
    ("structure-pin", "Two things here:\n\n- the cache\n- the lock\n", ["HIGH"]),
    ("structure-pin", "The cause is small. A timer fired twice because the lock was taken "
                      "late. The second call then read a half-written file.\n", ["MEDIUM"]),
    ("structure-pin", "The cause is a timer that fired twice. The lock was taken late, so "
                      "the second call read a half-written file. Both calls then wrote.\n",
     []),
    # 5. parataxis: a link word at the start of one sentence breaks the run
    ("structure-parataxis", "The build failed at noon. The cache was stale. Nobody had "
                            "cleared it.\n", ["HIGH"]),
    ("structure-parataxis", "The build failed at noon. The cache was stale because nobody "
                            "had cleared it since the last release went out on Friday.\n", []),
    ("structure-parataxis", "The build failed at noon. The cache was stale. So nobody "
                            "trusted the result.\n", []),
    # 6. pointer sentences and summary beats
    ("structure-pointer", "The count came back at 40. That matters.\n", ["HIGH"]),
    ("structure-pointer", "The count came back at 40. That matters to the two teams who "
                          "size their queues from it every week.\n", []),
    ("structure-pointer", "Each team keeps its own copy. That is the silo.\n", ["MEDIUM"]),
    ("structure-pointer", "Each team keeps its own copy. That is the silo the audit named "
                          "in its second finding.\n", []),
    # 7. landing sentences: a hand-back gates at the end of a paragraph and reports
    #    one tier lower before it; the same sentence with no hand-back is silent
    ("structure-landing", "The patch is ready and the tests pass on both machines. Whether "
                          "it ships today is up to you.\n", ["HIGH"]),
    ("structure-landing", "Whether it ships today is up to you. The patch is ready and the "
                          "tests pass on both machines.\n", ["MEDIUM"]),
    ("structure-landing", "Whether it ships today turns on the cache run. The patch is ready "
                          "and the tests pass on both machines.\n", []),
    ("structure-landing", "The patch is ready and the tests pass on both machines. Their "
                          "decision was to ship it on Monday.\n", []),
    ("structure-landing", "The patch touches the cache loader, which is the oldest file in "
                          "the tree. It adds a lock around the write, and it drops the "
                          "retry that hid the fault. Both machines ran the suite twice, "
                          "once cold and once warm. The fault did not come back.\n",
     ["MEDIUM"]),
    ("structure-landing", "The patch touches the cache loader, which is the oldest file in "
                          "the tree. It adds a lock around the write, and it drops the "
                          "retry that hid the fault. Both machines ran the suite twice, "
                          "once cold and once warm, and the fault did not come back.\n", []),
]


@pytest.mark.parametrize("category,text,tiers", CONTROLS)
def test_planted_control(category, text, tiers):
    assert [t for t, _r, _m in hits(text, category)] == tiers


def test_a_finding_can_span_wrapped_lines():
    text = "Keys open doors. Keys rust\nin rain. Keys get lost in coats.\n"
    (tier, rule, match), = hits(text, "structure-anaphora")
    assert (tier, rule) == ("HIGH", "structure-anaphora/run")
    assert match == text.strip()


def test_lists_headings_quotes_and_code_are_not_paragraphs():
    text = ("# Keys open doors\n\n- Keys open doors.\n- Keys rust in rain.\n- Keys get lost.\n\n"
            "> Keys open doors. Keys rust in rain. Keys get lost.\n\n"
            "```\nKeys open doors. Keys rust in rain. Keys get lost.\n```\n")
    assert structure(text) == []


# --- the MCP check and score tools take a profile ---------------------------

def test_mcp_check_reaches_the_structure_rules_through_a_profile():
    from articulate import local_mcp, mcp_server
    plain = mcp_server.do_check(SPECIMEN_B)
    assert plain["clean"] and "profile" not in plain          # the 2026-11-15 result, unchanged
    chat = mcp_server.do_check(SPECIMEN_B, None, "chat")
    assert chat["verdict"] == "flagged" and chat["gate"] == "blocked" and chat["profile"] == "chat"
    assert {h["category"] for h in chat["hits"]} >= {
        "structure-anaphora", "structure-parallel", "structure-triad", "structure-pin",
        "structure-parataxis", "structure-landing"}
    assert chat["cadence"]["repeated_openers_in_a_row"] is True
    assert mcp_server.do_score(SPECIMEN_B, "chat")["hard_hits"] == len(chat["hits"])
    for tool in local_mcp.TOOLS[:2]:
        assert tool["name"] in ("check", "score")
        assert tool["inputSchema"]["properties"]["profile"]["type"] == "string"
    called = local_mcp._call({"name": "check", "arguments": {"text": SPECIMEN_B, "profile": "chat"}})
    assert not called.get("isError") and '"gate":"blocked"' in called["content"][0]["text"]


def test_mcp_check_names_an_unknown_profile():
    from articulate import local_mcp
    called = local_mcp._call({"name": "check", "arguments": {"text": "x", "profile": "nope"}})
    assert called["isError"] and "unknown profile" in called["content"][0]["text"]


def test_house_notes_carry_the_structure_rules():
    from articulate import house
    notes = {n["category"] for n in house.style_notes(SPECIMEN_B)}
    assert {"style/structure-anaphora", "style/structure-pin", "style/structure-landing"} <= notes
    assert house.style_notes(COUNTERPART) == []
    revise = {n["category"] for n in house.revision_findings(SPECIMEN_B)}
    assert "style/structure-triad" in revise
