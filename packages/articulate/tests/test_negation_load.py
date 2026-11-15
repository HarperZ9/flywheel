"""The negation-load check: calibration, lexicon, clause split, rules, readers, CLI."""
import json

import pytest

from articulate import cli, negation_entries, negation_load as nl

# Two career cards from the site, read 2026-10-23. The first spends most of its
# clauses on what the extension lacks; the second says what the preset is.
DAYLIGHT_CARD = (
    "Built a browser extension that shows the sourced evidence behind replies on nine "
    "platforms: X, YouTube, Reddit, Facebook, Instagram, Bluesky, Threads, TikTok and "
    "Mastodon. Each sign shows its measured precision or \"not measured yet\", and none "
    "calls an account a bot. No server, account or analytics, no data sold or shared, and "
    "saved evidence chains verify offline. Version 3.1.0, released October 23, 2026 under "
    "AGPL-3.0-only, ships reproducible packages with signed checksums and a full-source git "
    "bundle. No Mozilla-signed build exists yet, and the campaign lens is not yet measured.")
ELDER_CARD = (
    "Built and maintained an ENBSeries preset with a layered design: weather presets set the "
    "atmosphere, and stackable overlays adjust style, lighting, effects and post-processing "
    "over a fixed baseline. It ships 38 atmosphere presets for the KreatE weather system, "
    "with updates from April 2024 to February 2026. ENBSeries and the required mods belong "
    "to their authors.")
COPY = nl.rule_for(rule="copy")


def test_calibration_daylight_card_fails_and_elder_card_passes():
    day, elder = nl.score(DAYLIGHT_CARD), nl.score(ELDER_CARD)
    assert day["score"] >= COPY["fail"], day
    assert nl.verdict(day["score"], COPY) == "fail"
    assert elder["score"] < COPY["warn"], elder
    assert nl.verdict(elder["score"], COPY) == "ok"


def test_daylight_card_virtue_phrases_are_reported_and_leave_the_score_alone():
    s = nl.score(DAYLIGHT_CARD)
    assert {"sourced evidence", "evidence chains", "verify offline", "reproducible",
            "signed checksums"} <= set(s["virtue"])
    plain = DAYLIGHT_CARD.replace("reproducible ", "").replace("sourced ", "")
    assert nl.score(plain)["score"] == s["score"]


@pytest.mark.parametrize("clause", [
    "The tool does not edit files.", "It never sends text anywhere.",
    "There is no server here.", "Signing is not yet done.",
    "The score doesn't prove quality.", "Runs without a network.",
    "The parser isn't complete.", "The model can't see your files.",
    "Works on Windows only.", "Support is limited to English.",
    "The campaign lens is not measured.", "This is an honest null.",
])
def test_each_negation_marker_counts(clause):
    assert nl.negating(clause), clause


@pytest.mark.parametrize("clause", [
    "The extension shows the source behind each reply.",
    "Licensed AGPL-3.0-only for every release.",
    "It is the only checker that reads Fountain screenplays.",
    "Merged 37 pull requests across 30 repositories, with 17 closed without merge and 14 "
    "open, counted from the GitHub API on October 23.",
    "Read No. 5 in the series.",
])
def test_plain_statements_do_not_count(clause):
    assert not nl.negating(clause), clause


def test_a_list_keeps_its_last_item_and_clauses_split_at_and():
    assert len(nl.clauses("It reads Markdown, HTML, and JSON files.")) == 1
    assert len(nl.clauses("Weather presets set the atmosphere, and stackable overlays "
                          "adjust the style.")) == 2
    assert len(nl.clauses("It runs offline; it keeps no logs.")) == 2


def test_titles_and_urls_are_not_scored():
    s = nl.score("The Sandbox Was Never Just a Box, September 2026. Compared public "
                 "security reports. harperz9.github.io/the-sandbox-was-never-just-a-box.html")
    assert s["negation_clauses"] == 0


def test_thresholds_warn_at_30_and_fail_at_50():
    assert nl.verdict(0.29, COPY) == "ok"
    assert nl.verdict(0.30, COPY) == "warn"
    assert nl.verdict(0.50, COPY) == "fail"
    fiction = nl.rule_for(rule="fiction")
    assert nl.verdict(0.50, fiction) == "warn" and nl.verdict(0.65, fiction) == "fail"


def test_profiles_pick_the_rule():
    assert nl.rule_for("readme")["name"] == "copy"
    assert nl.rule_for("narrative")["name"] == "fiction"
    assert nl.rule_for("literary-fiction")["name"] == "fiction"
    assert nl.rule_for("readme", rule="fiction")["name"] == "fiction"
    with pytest.raises(ValueError):
        nl.rule_for(rule="lenient")


LWD = """@node dock.open
speaker: KEEL
nar: The tide is out and the barges lie on their sides in the brown mud of the dock.
line: No. I never go out there, not at night, not without a lamp, not for you.
opt: "Ask Keel why not, and do not let it go." -> dock.why
"""


def test_fiction_rule_skips_character_speech_and_scores_narration():
    found = negation_entries.entries(LWD, "act1/dock.lwd")
    kinds = {e["kind"] for e in found}
    assert {"narration", "dialogue", "choice"} <= kinds
    fiction = nl.assess(found, nl.rule_for(rule="fiction"))
    assert [r["kind"] for r in fiction] == ["narration"]
    copy = nl.assess(found, COPY)
    speech = [r for r in copy if r["kind"] == "dialogue"]
    assert speech and speech[0]["verdict"] == "fail"


def test_markdown_reader_labels_skips_code_and_groups_short_items():
    md = ("# Tool\n\n## Install\n\nInstall the package with pip and run the check on a "
          "folder of notes.\n\n```\nnot code that counts, never\n```\n\n- No server.\n"
          "- No account.\n- No telemetry.\n")
    found = negation_entries.entries(md, "README.md")
    assert found[0]["label"] == "Install"
    assert not any("code that counts" in e["text"] for e in found)
    lists = [e for e in found if e["kind"] == "list"]
    assert lists and lists[0]["text"].count(";") == 2
    assert nl.score(lists[0]["text"])["score"] == 1.0


def test_html_reader_reads_blocks_and_skips_script():
    page = ("<h3>Card</h3><p>Shows the source behind each reply on nine platforms.</p>"
            "<script>var s = 'never counted here at all';</script>")
    found = negation_entries.entries(page, "cv.html")
    assert [e["text"] for e in found] == ["Shows the source behind each reply on nine platforms."]
    assert found[0]["label"] == "Card"


def test_json_film_lines_and_js_ui_strings():
    film = json.dumps({"slug": "x", "segments": [{"key": "row0", "lines": [
        "Every dot is one number.", "It does not learn anything new."]}]})
    seg = [e for e in negation_entries.entries(film, "film.json") if e["kind"] == "segment"]
    assert seg and "does not learn" in seg[0]["text"]
    js = "const a = 'No account, no server, and nothing leaves this browser';\nf(x);"
    strings = negation_entries.entries(js, "popup.js")
    assert strings and strings[0]["line"] == 1


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_cli_gate_fails_on_the_daylight_card_and_passes_on_the_elder_card(tmp_path, capsys):
    bad = _write(tmp_path, "daylight.md", DAYLIGHT_CARD + "\n")
    good = _write(tmp_path, "elder.md", ELDER_CARD + "\n")
    assert cli.main(["negation", bad, "--gate"]) == 1
    assert "fail" in capsys.readouterr().out
    assert cli.main(["negation", good, "--gate"]) == 0
    capsys.readouterr()
    assert cli.main(["negation", str(tmp_path), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["fail"] == 1 and report["summary"]["ok"] == 1
