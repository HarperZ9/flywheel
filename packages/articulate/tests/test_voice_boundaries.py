"""Boundaries of the series and voice features, enforced in code.

No new module reaches the network, starts a process or names an AI-authorship
detector service. No report carries a single score to optimize. A stored voice
profile has no effect on polish. Every report string passes the writing check
with no em dash.
"""
import ast
import importlib
import pathlib
import re

import pytest

import articulate
from voice_fixtures import SCAFFOLD_ESSAY, VARIED, templated_docs

PKG = pathlib.Path(articulate.__file__).resolve().parent
NEW = ["corpus_features", "corpus", "titles", "voice", "voice_store", "wordlists",
       "interview", "restructure", "authorship", "corpus_receipt", "cli_corpus",
       "voice_tools", "voice_identity", "voice_apply", "house", "house_spec",
       "house_settings", "house_tools", "house_hook", "cli_house"]
BANNED_IMPORTS = {"socket", "subprocess", "urllib", "http", "requests", "httpx", "ssl",
                  "asyncio", "multiprocessing", "ftplib", "smtplib", "anthropic", "openai",
                  "backends", "claude_cli", "editor", "editing"}
DETECTOR_SERVICES = re.compile(r"(?i)gptzero|originality\.ai|copyleaks|zerogpt|turnitin|"
                               r"sapling|winston|hive moderation|writer\.com/ai-content|"
                               r"undetectable|humanize|ai[_ -]?detector(?!_consulted)|detect_ai")


def _imports(mod):
    tree = ast.parse((PKG / f"{mod}.py").read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                names.add(node.module.split(".")[0])
            else:
                names |= {node.module.split(".")[0]} if node.module else {a.name for a in node.names}
    return names


@pytest.mark.parametrize("mod", NEW)
def test_new_modules_import_no_network_process_or_model(mod):
    assert not _imports(mod) & BANNED_IMPORTS, mod


@pytest.mark.parametrize("mod", NEW)
def test_new_modules_name_no_detector_service(mod):
    source = (PKG / f"{mod}.py").read_text(encoding="utf-8")
    assert not DETECTOR_SERVICES.search(source), mod


def test_scan_catches_a_planted_import(tmp_path):
    tree = ast.parse("import socket\nfrom urllib import request\n")
    found = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert "socket" in found and DETECTOR_SERVICES.search("call gptzero here")


SCORE_KEYS = {"score", "humanness", "human_score", "ai_probability", "ai_score",
              "detector_score", "distance", "total_distance"}


def _reports():
    from articulate import corpus, house, interview, restructure, titles, voice
    profile = voice.build_profile([t for _, _, t in VARIED])
    return {
        "corpus": corpus.analyze_corpus(templated_docs()),
        "titles": titles.workshop([d["text"].splitlines()[0][2:] for d in templated_docs()]),
        "interview": interview.questions(SCAFFOLD_ESSAY),
        "restructure": restructure.propose(SCAFFOLD_ESSAY),
        "voice": voice.compare(SCAFFOLD_ESSAY, profile),
        "house": house.transform(SCAFFOLD_ESSAY)["receipt"],
    }


def _keys(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _keys(v)
    elif isinstance(value, list):
        for v in value:
            yield from _keys(v)


def test_no_report_carries_a_score_and_each_says_no_detector():
    for name, report in _reports().items():
        assert not set(_keys(report)) & SCORE_KEYS, name
        assert report["ai_detector_consulted"] is False, name


def test_report_strings_carry_no_em_dash_and_pass_the_style_rules():
    from articulate import check_text, corpus, interview, voice
    reports = _reports()
    prose = [f["reader_cost"] + " " + f["direction"] + " " + f["scope"]
             for f in reports["corpus"]["findings"]]
    prose += [q["question"] for q in reports["interview"]["questions"]]
    prose += voice.describe(voice.build_profile([t for _, _, t in VARIED]))
    prose += [reports["voice"]["scope"], reports["corpus"]["scope"]]
    text = "\n\n".join(sorted(set(prose)))
    assert "—" not in text
    result = check_text(text)
    assert not result["high"], [f["match"] for f in result["high"]]
    _ = (corpus, interview)


def test_polish_is_unaffected_by_a_stored_voice_profile(monkeypatch, tmp_path):
    from articulate import editing, voice, voice_store
    text = "We really wait for the rain. It comes in March and we leave."
    monkeypatch.setenv("ARTICULATE_VOICE_DIR", str(tmp_path / "empty"))
    before = editing.run_edit(text, "polish", backend="none")
    voice_store.save(voice.build_profile([t for _, _, t in VARIED]), "mine", tmp_path / "full")
    monkeypatch.setenv("ARTICULATE_VOICE_DIR", str(tmp_path / "full"))
    after = editing.run_edit(text, "polish", backend="none")
    for key in ("text", "attempts", "refused", "gate"):
        assert before.get(key) == after.get(key), key
    assert before.get("stop_reason") == after.get("stop_reason")


def test_editing_never_imports_the_voice_or_corpus_modules():
    for mod in ("editing", "editor", "host_edit", "prompts"):
        assert not _imports(mod) & {"voice", "voice_store", "corpus", "corpus_features"}, mod
