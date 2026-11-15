"""Voice sheets, the parsers, blind attribution and the audit report."""
import json

import pytest

from articulate import dialogue, dialogue_attrib, dialogue_parse, dialogue_sheet


def rec(speaker, text, **extra):
    return dict({"speaker": speaker, "text": text, "file": "t.lwd", "line": 1, "node": None,
                 "group": "act1", "gate": None}, **extra)


SALVOR = {"name": "TUB", "register": {"level": "plain", "words": ["salvage"]},
          "sentence_length": {"min": 1, "max": 8}, "never": ["okay"],
          "never_patterns": [{"re": r"\bI\b", "msg": "never says I"}],
          "questions": "never",
          "knowledge": {"unknown": [{"terms": ["works order"], "why": "the harbourmaster's",
                                     "unless_gate": ["works.order"]}]},
          "region": {"markers": ["I'll not"]}, "tics": ["tide"]}


def sheet_checks(text, sheet=SALVOR, **extra):
    return {f["check"] for f in dialogue_sheet.check_line(rec("TUB", text, **extra), sheet)}


def test_register_flags_learned_words_but_not_trade_words():
    assert "register" in sheet_checks("That's an insufficient consideration.")
    assert "register" not in sheet_checks("Salvage. Copper. Rope.")
    assert "register" not in sheet_checks("Everybody knows.")


def test_never_words_and_patterns():
    assert "never" in sheet_checks("Okay, then.")
    assert "never-pattern" in sheet_checks("I saw it.")
    # Words quoted from someone else are not the character's own.
    assert "never-pattern" not in sheet_checks('He wrote, "I saw it." Ask him.')


def test_sentence_length_outliers():
    assert "sentence-length" in sheet_checks(
        "The ferry came in on the flood with every lamp on the quay out and nobody at the rail.")
    assert "sentence-length" not in sheet_checks("Ferry's in. Lamps out.")


def test_questions_rule_both_ways():
    assert "questions" in sheet_checks("Where were you?")
    asker = {"name": "GORM", "questions": "only"}
    assert "questions" in sheet_checks("You were on the quay.", asker)
    assert "questions" not in sheet_checks("And were you on the quay?", asker)


def test_contractions_rule():
    full = {"name": "SORLE", "contractions": False}
    assert "contractions" in sheet_checks("It's cold in the stokehold.", full)
    assert "contractions" not in sheet_checks("It is cold in the stokehold.", full)


def test_knowledge_leak_and_its_gate():
    assert "knowledge-leak" in sheet_checks("Ask about the works order.")
    assert "knowledge-leak" not in sheet_checks("Ask about the works order.",
                                                gate="when: has(works.order)")


def test_sheet_loading_and_validation(tmp_path):
    (tmp_path / "tub.json").write_text(json.dumps(dict(SALVOR, aliases=["MERROW"])))
    (tmp_path / "_project.json").write_text(json.dumps({"theme_words": ["truth"]}))
    sheets, project = dialogue_sheet.load_dir(str(tmp_path))
    assert set(sheets) == {"TUB", "MERROW"} and project["theme_words"] == ["truth"]
    (tmp_path / "bad.json").write_text(json.dumps({"name": "X", "register": {"level": "posh"}}))
    with pytest.raises(ValueError, match="register.level"):
        dialogue_sheet.load_dir(str(tmp_path))


def test_usage_rates():
    lines = [rec("TUB", "Tide's out."), rec("TUB", "I'll not go."), rec("TUB", "Rope.")]
    u = dialogue_sheet.usage(lines, SALVOR)
    assert u["tic_lines"] == pytest.approx(1 / 3) and u["region_lines"] == pytest.approx(1 / 3)


def test_lwd_parser_reads_named_and_default_speakers_and_gates():
    text = ("@node quay.keel.start\nspeaker: KEEL\nline: The Board is wet.\n"
            "line: WENNA: She's not dark. {when: has(met.wenna), once}\nnar: The rain.\n")
    out = dialogue_parse.parse(text, "act1/quay.lwd")
    assert [(r["speaker"], r["text"]) for r in out] == [("KEEL", "The Board is wet."),
                                                         ("WENNA", "She's not dark.")]
    assert out[1]["gate"] == "when: has(met.wenna), once" and out[0]["node"] == "quay.keel.start"


def test_colon_and_play_parsers():
    assert dialogue_parse.detect("ANNA: Hello.\nBEN: Hi.\n") == "colon"
    play = "HIGGINS. Why not? [He turns]\nGo on.\n\nLIZA.\nAh-ah-ah-ow!\n"
    out = dialogue_parse.parse(play)
    assert [(r["speaker"], r["text"]) for r in out] == [("HIGGINS", "Why not? Go on."),
                                                         ("LIZA", "Ah-ah-ah-ow!")]


def _corpus():
    """Two speakers with different vocabularies and one who talks like both."""
    sailor = ["The tide is on the turn, lads.", "Haul the rope and mind the tide.",
              "Rope and tide, lads, rope and tide.", "Mind the tide on the mud, lads."]
    clerk = ["The ledger must be audited by Friday.", "Please file the ledger in triplicate.",
             "The audit of the ledger is overdue.", "Kindly countersign the ledger."]
    out = []
    for i in range(30):
        out.append(rec("SAILOR", sailor[i % 4]))
        out.append(rec("CLERK", clerk[i % 4]))
        out.append(rec("BLAND", (sailor if i % 2 else clerk)[i % 4]))
    return out


def test_attribution_separates_distinct_voices_and_exposes_a_generic_one():
    att = dialogue_attrib.attribute(_corpus(), min_lines=20)
    assert att["chance"] == pytest.approx(1 / 3, abs=0.001)
    sp = att["speakers"]
    assert sp["SAILOR"]["accuracy"] > 0.5 and sp["CLERK"]["accuracy"] > 0.5
    assert sp["BLAND"]["accuracy"] < sp["SAILOR"]["accuracy"]
    lo, hi = sp["SAILOR"]["interval"]
    assert 0 <= lo <= sp["SAILOR"]["accuracy"] <= hi <= 1


def test_attribution_needs_two_speakers():
    att = dialogue_attrib.attribute([rec("A", "x y z")] * 30, min_lines=20)
    assert att["speakers"] == {} and att["chance"] is None


def test_wilson_interval():
    lo, hi = dialogue_attrib.wilson(8, 10)
    assert 0.49 < lo < 0.5 and 0.94 < hi < 0.95
    assert dialogue_attrib.wilson(0, 0) == (0.0, 1.0)


def test_audit_scores_gate_and_tables():
    lines = _corpus() + [rec("SAILOR", "You want me cruel. Cruel is easy; anyone could prove "
                                       "it. I am logic.", group="act2")]
    report = dialogue.audit(lines, {"SAILOR": {"name": "SAILOR", "never": ["logic"]}},
                            min_lines=20)
    top = dialogue.worst(report, 1)[0]
    assert top["group"] == "act2" and top["score"] >= 8
    assert report["groups"]["act2"]["epigram_lines"] == 1
    verdict = dialogue.gate(report)
    assert not verdict["passed"] and any("never" in r for r in verdict["reasons"])
    assert dialogue.gate(report, max_epigram_rate=0.5, fail_checks=())["passed"]
    table = dialogue.summary_table(report)
    assert "SAILOR" in table and "chance for attribution" in table
