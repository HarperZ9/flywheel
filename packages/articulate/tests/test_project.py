"""The project config: discovery, profile globs, terminology rules on every
surface, allowed and freeze terms, and loud failure on a malformed file.

Each terminology rule has a positive case, a negative case, and a control
(code spans and URLs are masked; --config none turns the rules off), so a pass
cannot come from a rule that fires everywhere or nowhere.
"""
import io
import json
import os
import sys

import pytest

from articulate import checkext, cli, host_edit, lsp_server, profiles, project, receipt

CONFIG = {
    "version": 1,
    "profiles": {"notes/**": "essay", "*.txt": "readme", "ui/*.txt": "ux-microcopy"},
    "terminology": {
        "banned": [{"term": "whitelist", "suggestion": "allowlist",
                    "reason": "inclusive language"}],
        "preferred": [{"use": "sign in", "instead_of": ["log in", "login"]}],
        "allowed": ["leverage"],
    },
    "freeze": ["Articulate"],
}
BANNED_TEXT = "Add the host to the whitelist before you deploy.\n"


@pytest.fixture()
def work(tmp_path):
    os.makedirs(tmp_path / "notes" / "deep")
    os.makedirs(tmp_path / "ui")
    (tmp_path / project.CONFIG_NAME).write_text(json.dumps(CONFIG), encoding="utf-8")
    return str(tmp_path)


def _write(work, rel, text):
    p = os.path.join(work, rel)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)
    return p


def _rules(result):
    return {f["rule_id"]: f for f in result["high"] + result["medium"] + result["low"]}


def _check(work, text, rel="a.md"):
    path = _write(work, rel, text)
    return checkext.check_text(text, profile=project.resolve(
        path, text, cfg=project.for_path(path))[1])


def test_discovery_walks_up_and_can_be_turned_off(work):
    deep = _write(work, "notes/deep/x.md", "text\n")
    assert project.discover(deep) == os.path.join(work, project.CONFIG_NAME)
    assert project.for_path(deep, "none") is None


def test_glob_profile_sits_between_the_in_file_tag_and_the_path(work):
    cfg = project.for_path(os.path.join(work, "a.md"))
    assert project.resolve(os.path.join(work, "notes/deep/x.md"), "", cfg=cfg)[0] == "essay"
    assert project.resolve(os.path.join(work, "b.txt"), "", cfg=cfg)[0] == "readme"
    tagged = "<!-- writing-profile: chat -->\n"
    assert project.resolve(os.path.join(work, "notes/x.md"), tagged, cfg=cfg)[0] == "chat"
    assert project.resolve(os.path.join(work, "notes/x.md"), tagged, profile="commit",
                           cfg=cfg)[0] == "commit"
    assert project.resolve(os.path.join(work, "a.md"), "", cfg=cfg)[0] == profiles.DEFAULT


def test_glob_can_name_a_domain_profile(work):
    path = _write(work, "ui/strings.txt", "button: Save and continue to the next step\n")
    name, prof = project.resolve(path, "", cfg=project.for_path(path))
    assert name == "ux-microcopy" and prof["rule_packs"] == ("ux-microcopy",)


def test_banned_term_fires_with_its_suggestion_and_gates(work):
    r = _check(work, BANNED_TEXT)
    f = _rules(r)["terminology/banned/whitelist"]
    assert f["tier"] == "HIGH" and "allowlist" in f["label"] and f["match"] == "whitelist"
    assert r["gate"] == "blocked"
    assert "terminology/banned/whitelist" not in _rules(
        _check(work, "Add the host to the allowlist before you deploy.\n"))


def test_terms_in_code_and_urls_are_masked(work):
    r = _check(work, "Set `whitelist = true` per https://example.com/whitelist today.\n")
    assert not any(k.startswith("terminology/") for k in _rules(r))


def test_preferred_form_fires_on_each_variant(work):
    r = _check(work, "Log in first. Then use the login page.\n")
    hits = [f for f in r["medium"] if f["rule_id"] == "terminology/preferred/sign-in"]
    assert [h["match"] for h in hits] == ["Log in", "login"]
    assert "terminology/preferred/sign-in" not in _rules(_check(work, "Sign in first.\n"))


def test_match_case_is_honored():
    term = {"banned": [{"term": "API", "match_case": True}]}
    prof = project.apply_payload(profiles.load("flavored"), {"terminology": term})
    assert "terminology/banned/api" in _rules(checkext.check_text("Call the API.\n", profile=prof))
    assert "terminology/banned/api" not in _rules(checkext.check_text("A rapid api.\n", profile=prof))


def test_allowed_term_clears_a_vocabulary_rule_but_not_a_device(work):
    plain = checkext.check_text("We leverage caching.\n", profile=profiles.load("flavored"))
    assert any(f["category"] == "corporate-verb" for f in plain["high"])
    assert not any(f["category"] == "corporate-verb" for f in _check(work, "We leverage caching.\n")["high"])
    device = _check(work, "This does not leverage caching, but speed.\n")
    assert device["gate"] == "blocked"


@pytest.mark.parametrize("patch,needle", [
    ({"colour": 1}, "unknown key"),
    ({"profiles": {"*.md": "no-such-profile"}}, "no-such-profile"),
    ({"terminology": {"banned": [{"term": "x"}], "allowed": ["x"]}}, "both flagged and allowed"),
    ({"terminology": {"banned": [{"term": "x", "severity": "fatal"}]}}, "severity"),
    ({"options": {"nope": {"a": 1}}}, "no such rule pack"),
    ({"options": {"ux-microcopy": {"case": "upper"}}}, "must be one of"),
    ({"options": {"plain-language": {"max_grade": "eight"}}}, "must be float"),
    ({"freeze": "Articulate"}, "freeze"),
    ({"version": 2}, "version"),
    ({"protect": {"quotes": False}}, "protected spans are always on"),
])
def test_malformed_config_fails_loudly(work, patch, needle):
    path = _write(work, "bad.json", json.dumps(dict(CONFIG, **patch)))
    with pytest.raises(project.ConfigError) as info:
        project.load(path)
    assert needle in str(info.value) and "bad.json" in str(info.value)


def test_pack_options_reach_the_pack(work):
    text = "button: Go to my list\n"
    path = _write(work, "ui/a.txt", text)
    assert "ux-length" in {f["category"] for f in _check(work, text, "ui/a.txt")["medium"]}
    cfg_path = _write(work, "opts.json", json.dumps(
        dict(CONFIG, options={"ux-microcopy": {"button_max_words": 6}})))
    prof = project.resolve(path, text, cfg=project.load(cfg_path))[1]
    assert "ux-length" not in {f["category"] for f in checkext.check_text(text, profile=prof)["medium"]}


def test_cli_check_text_json_sarif_and_gate_use_the_config(work, capsys):
    path = _write(work, "a.md", BANNED_TEXT)
    assert cli.main(["check", path, "--gate"]) == 1
    assert "[HIGH terminology/banned/whitelist]" in capsys.readouterr().out
    assert cli.main(["check", path, "--gate", "--config", "none"]) == 0
    capsys.readouterr()
    cli.main(["check", path, "--json", "--spans"])
    res = json.loads(capsys.readouterr().out)["results"][0]
    assert "terminology/banned/whitelist" in _rules(res)
    assert "terminology/banned/whitelist" in _rules(res["blocks"][0])
    cli.main(["check", path, "--sarif"])
    sarif = json.loads(capsys.readouterr().out)
    assert "terminology/banned/whitelist" in {r["ruleId"] for r in sarif["runs"][0]["results"]}


@pytest.mark.parametrize("cmd", [["check"], ["score"], ["receipt"], ["fix", "--backend", "none"],
                                 ["polish", "--backend", "none"], ["plan"],
                                 ["judge", "--backend", "none"]])
def test_malformed_config_exits_2_with_file_and_reason(work, capsys, cmd):
    path = _write(work, "a.md", BANNED_TEXT)
    bad = _write(work, "broken.json", "{not json")
    assert cli.main(cmd[:1] + [path] + cmd[1:] + ["--config", bad]) == 2
    err = capsys.readouterr().err
    assert "broken.json" in err and "not valid JSON" in err


def test_stdin_discovers_the_config_from_the_working_directory(work, capsys, monkeypatch):
    monkeypatch.chdir(work)
    monkeypatch.setattr(sys, "stdin", io.StringIO(BANNED_TEXT))
    assert cli.main(["check", "--gate"]) == 1
    assert "terminology/banned/whitelist" in capsys.readouterr().out


def test_lsp_reports_terms_and_a_broken_config(work):
    path = _write(work, "a.md", BANNED_TEXT)
    uri = "file:///" + path.replace("\\", "/").lstrip("/")
    codes = {d["code"] for d in lsp_server.build_diagnostics(BANNED_TEXT, uri)}
    assert "terminology/banned/whitelist" in codes
    bad = _write(work, "broken.json", "{not json")
    diags = lsp_server.build_diagnostics(BANNED_TEXT, uri, config=bad)
    assert diags[0]["code"] == "config" and "broken.json" in diags[0]["message"]
    assert "terminology/banned/whitelist" not in {d["code"] for d in diags}


def test_receipt_embeds_the_rules_and_replays_them(work):
    cfg = project.for_path(os.path.join(work, "a.md"))
    rec = receipt.make_receipt(BANNED_TEXT, "flavored", config=cfg, per_span=True)
    assert rec["project_rules"]["terminology"]["banned"][0]["term"] == "whitelist"
    assert rec["project_rules_sha256"] == project.payload_sha256(rec["project_rules"])
    assert "terminology/banned/whitelist" in {f["rule_id"] for f in rec["findings"]}
    assert receipt.verify_receipt(rec, BANNED_TEXT)[0] == "Match"
    edited = json.loads(json.dumps(rec))
    edited["project_rules"]["terminology"]["banned"] = []
    assert receipt.verify_receipt(edited, BANNED_TEXT)[0] == "Unverifiable"
    edited["project_rules_sha256"] = project.payload_sha256(edited["project_rules"])
    assert receipt.verify_receipt(edited, BANNED_TEXT)[0] == "Drift"


def test_cli_receipt_uses_the_config_and_verifies(work, capsys):
    path = _write(work, "a.md", BANNED_TEXT)
    assert cli.main(["receipt", path]) == 0
    rec = json.loads(capsys.readouterr().out)
    assert "project_rules" in rec and rec["gate"] == "blocked"
    rec_path = _write(work, "r.json", json.dumps(rec))
    assert cli.main(["verify", rec_path, path]) == 0
    assert "Match" in capsys.readouterr().out


def test_edit_plan_binds_terminology_and_freeze_terms(work, capsys):
    text = "Articulate keeps the whitelist short.\n"
    path = _write(work, "a.md", text)
    assert cli.main(["plan", path]) == 0
    plan = json.loads(capsys.readouterr().out)
    settings = host_edit.plan_settings(text, plan["plan_id"])
    assert settings["schema"] == host_edit.PLAN_V3 and settings["freeze_terms"] == ["Articulate"]
    assert settings["profile"]["terminology"]["banned"][0]["term"] == "whitelist"
    assert any(f["rule_id"] == "terminology/banned/whitelist" for f in plan["findings_before"])
    out = host_edit.edit_submit(text, "The tool keeps the allowlist short.\n", plan["plan_id"])
    assert out["text"] == text and "term protected spans changed" in out["refused"][0]["reasons"]


def test_config_command_shows_what_applies(work, capsys):
    assert cli.main(["config", os.path.join(work, "notes", "x.md"), "--json"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["profile"] == "essay" and info["profile_source"].startswith("config glob 'notes/**'")
    assert info["terminology"]["banned"] == ["whitelist"] and info["freeze"] == ["Articulate"]
    assert info["config"] == os.path.join(work, project.CONFIG_NAME)
    assert cli.main(["config", os.path.join(work, "a.md")]) == 0
    out = capsys.readouterr().out
    assert "[config] profile: flavored (path inference)" in out
    assert "[config] preferred terms: sign in for log in, login" in out
    assert cli.main(["config", os.path.join(work, "a.md"), "--config", "none", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["config"] is None


def test_edit_under_a_mode_still_binds_the_project_rules(work, capsys):
    path = _write(work, "a.md", BANNED_TEXT)
    assert cli.main(["plan", path, "--mode", "memo/argue"]) == 0
    settings = host_edit.plan_settings(BANNED_TEXT, json.loads(capsys.readouterr().out)["plan_id"])
    assert settings["profile"]["terminology"]["banned"][0]["term"] == "whitelist"
    assert cli.main(["plan", path, "--mode", "memo/argue", "--config", "none"]) == 0
    settings = host_edit.plan_settings(BANNED_TEXT, json.loads(capsys.readouterr().out)["plan_id"])
    assert settings["mode"] == "memo/argue" and "terminology" not in settings["profile"]
