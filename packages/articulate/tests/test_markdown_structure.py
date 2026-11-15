"""Markdown structure is not prose.

A table delimiter row, an indented code block, TOML front matter and a proper
name were reported as writing devices. Agents then rewrote tables as `|-|-|` to
quiet the em-dash rule. These tests pin the structure masks in the check layer
and confirm that the same devices in prose still fire.
"""
import json

from articulate import checkext, edit_hook, editor, house, receipt
from articulate.cli import main as cli_main
from articulate.mcp_server import do_check, do_score

PROSE = ("The crew logged every reading by hand and checked each one twice. Then "
         "they compared the two sheets, marked each gap in red, and sent the copy "
         "to the office before noon on Friday.\n\n")


def _cats(text, **kw):
    r = checkext.check_text(text, **kw)
    return [(f["category"], f["match"]) for t in ("high", "medium", "low") for f in r[t]]


def _emdash(text):
    return [m for c, m in _cats(text) if c == "em-dash"]


# Table delimiter rows ------------------------------------------------------

SEPARATORS = [
    "|---|---|",
    "| --- | --- |",
    "|:---|---:|",
    "| :--- | :---: | ---: |",
    "---|---",
    "|-----------|:----------:|---|",
]


def test_table_delimiter_rows_are_not_em_dashes():
    for sep in SEPARATORS:
        cols = sep.strip("|").count("|") + 1
        head = "| " + " | ".join("H%d" % i for i in range(cols)) + " |"
        row = "| " + " | ".join("v%d" % i for i in range(cols)) + " |"
        text = PROSE + head + "\n" + sep + "\n" + row + "\n"
        assert _emdash(text) == [], sep
        assert checkext.check_text(text)["gate"] == "ok", sep


def test_em_dash_inside_a_table_cell_still_fires():
    text = PROSE + "| A | B |\n|---|---|\n| x — y | z |\n"
    assert _emdash(text) == ["—"]
    text = PROSE + "| A | B |\n|---|---|\n| x --- y | z |\n"
    assert _emdash(text) == ["---"]


def test_em_dash_in_prose_still_fires():
    assert _emdash(PROSE + "This works — mostly.\n") == ["—"]
    assert _emdash(PROSE + "This works --- mostly.\n") == ["---"]


def test_table_fix_keeps_texture_score_of_the_prose():
    plain = PROSE + "| A | B |\n| x | y |\n"
    table = PROSE + "| A | B |\n|---|---|\n| x | y |\n"
    assert (checkext.check_text(table)["texture_score"]
            == checkext.check_text(plain)["texture_score"])


# Other structure ------------------------------------------------------------

def test_toml_front_matter_is_not_prose():
    text = "+++\ntitle = \"Notes — draft\"\n+++\n\n" + PROSE
    assert _emdash(text) == []


def test_indented_code_block_is_not_prose():
    text = PROSE + "    x = a --- b  # —\n    y = 2\n\nMore text follows here.\n"
    assert _emdash(text) == []


def test_indented_list_continuation_is_still_prose():
    text = PROSE + "- item one\n\n    A continuation — of the item.\n"
    assert _emdash(text) == ["—"]


def test_proper_names_are_not_register_words():
    for line in ("The Transformative AI Fund pays for two reviewers.",
                 "She works at Robust Intelligence in the city.",
                 "We applied to the Pivotal Software grant last year."):
        assert [m for c, m in _cats(PROSE + line + "\n") if c == "register-word"] == [], line


def test_register_words_in_prose_and_headings_still_fire():
    assert ("register-word", "transformative") in _cats(
        PROSE + "This is a transformative approach to the work.\n")
    assert any(c == "register-word" for c, _ in _cats(
        PROSE + "# A Transformative Approach To Robust Systems\n"))
    # A capital at the start of a sentence is not evidence of a name.
    assert ("register-word", "Transformative") in _cats(
        PROSE + "Transformative AI tools change the plan for the year.\n")


def test_masks_keep_match_and_snippet_verbatim():
    text = PROSE + "|---|---|\nThe Robust Labs team found a robust result — twice.\n"
    r = checkext.check_text(text)
    hits = r["high"] + r["medium"]
    assert hits
    for f in hits:
        assert text[f["start"]:f["end"]] == f["match"]
        assert "Robust Labs" in f["snippet"]


# Every surface ---------------------------------------------------------------

TABLE_DOC = PROSE + "| Name | Role |\n|---|---|\n| Ana | lead |\n"


def test_cli_check_gate_passes_a_table(tmp_path, capsys):
    p = tmp_path / "t.md"
    p.write_text(TABLE_DOC, encoding="utf-8")
    assert cli_main(["check", str(p), "--gate"]) in (0, None)
    assert "em-dash" not in capsys.readouterr().out


def test_per_paragraph_view_drops_the_separator():
    blocks = checkext.analyze_blocks(TABLE_DOC)
    assert all(b["counts"]["high"] == 0 for b in blocks)
    assert blocks[-1]["snippet"].startswith("| Name | Role |\n|---|---|")


def test_mcp_check_and_score_drop_the_separator():
    assert do_check(TABLE_DOC)["hits"] == []
    assert do_score(TABLE_DOC)["hard_hits"] == 0


def test_edit_hook_editor_and_house_drop_the_separator():
    assert edit_hook.style_notes(TABLE_DOC) == []
    assert editor.assess(TABLE_DOC)["high"] == []
    assert house.style_notes(TABLE_DOC) == []


def test_receipt_matches_and_records_the_mask():
    rec = receipt.make_receipt(TABLE_DOC, per_span=True)
    assert rec["gate"] == "ok"
    assert rec["structure"] == checkext.STRUCTURE_VERSION
    assert receipt.verify_receipt(json.loads(json.dumps(rec)), TABLE_DOC)[0] == "Match"


def test_receipt_without_structure_field_replays_the_old_way():
    rec = receipt.make_receipt(TABLE_DOC)
    old = dict(rec)
    del old["structure"]
    r = checkext.check_text(TABLE_DOC, structure=False)
    old.update(gate=r["gate"], clean=r["clean"], verdict=r["verdict"],
               texture_score=r["texture_score"], findings=receipt._normalize(r, None),
               counts={k: len(r[k]) for k in ("high", "medium", "low")})
    assert receipt.verify_receipt(old, TABLE_DOC)[0] == "Match"


def test_receipt_with_unknown_structure_version_is_unverifiable():
    rec = receipt.make_receipt(TABLE_DOC)
    rec["structure"] = "markdown/999"
    assert receipt.verify_receipt(rec, TABLE_DOC)[0] == "Unverifiable"


def test_untouched_text_gives_byte_identical_results():
    text = PROSE + "It is crucial to delve into this.\n"
    assert checkext.check_text(text) == checkext.check_text(text, structure=False)
    assert "structure" not in receipt.make_receipt(text)


# Inline math (markdown/2) -------------------------------------------------

MATH_LINES = ["Let $a---b$ be the gap between the two readings.",
              "The bound $$x -- y$$ holds for every reading on the sheet.",
              "Let $a—b$ be the gap between the two readings."]


def test_inline_math_is_not_prose():
    for line in MATH_LINES:
        assert _emdash(PROSE + line + "\n") == [], line


def test_display_math_block_is_not_prose():
    doc = PROSE + "$$\na --- b\n$$\n\n" + PROSE
    assert _emdash(doc) == []


def test_prices_are_not_math():
    # A dollar amount is not a math span, so the prose between two prices is checked.
    for line in ("The kit costs $5 — and the spare costs $10 at the shop.",
                 "Prices run $5—$10 for each sheet at the shop.",
                 "We paid $5 — then $10 — for the two sheets."):
        assert _emdash(PROSE + line + "\n"), line


def test_escaped_dollars_and_code_are_not_math():
    assert _emdash(PROSE + r"The fee is \$5 — or \$10 with the spare." + "\n")


def test_math_receipt_matches_and_old_version_replays_without_math():
    doc = PROSE + "Let $a---b$ be the gap between the two readings.\n"
    rec = receipt.make_receipt(doc)
    assert rec["structure"] == checkext.STRUCTURE_VERSION == "markdown/2"
    assert receipt.verify_receipt(json.loads(json.dumps(rec)), doc)[0] == "Match"
    # A receipt made by 0.14.0 names markdown/1, which had no math mask.
    r = checkext.check_text(doc, structure="markdown/1")
    assert [f["match"] for f in r["high"] if f["category"] == "em-dash"]
    old = dict(rec, structure="markdown/1", gate=r["gate"], clean=r["clean"],
               verdict=r["verdict"], texture_score=r["texture_score"],
               findings=receipt._normalize(r, None),
               counts={k: len(r[k]) for k in ("high", "medium", "low")})
    assert receipt.verify_receipt(old, doc)[0] == "Match"


# Names at the start of a sentence (markdown/2) ----------------------------

def test_a_name_seen_mid_sentence_is_a_name_at_sentence_start():
    doc = PROSE + ("She works at Robust Intelligence in the city.\n\n"
                   "Robust Intelligence builds models for the office.\n")
    assert [m for c, m in _cats(doc) if c == "register-word"] == []


def test_a_capital_at_sentence_start_alone_is_still_not_a_name():
    doc = PROSE + "Robust Intelligence builds models for the office.\n"
    assert any(c == "register-word" for c, _ in _cats(doc))
    doc = PROSE + ("She works at Robust Intelligence in the city.\n\n"
                   "Robust systems need care in the field every day.\n")
    assert ("register-word", "Robust") in _cats(doc)
