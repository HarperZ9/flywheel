"""CLI host edits round-trip without a second model account."""
import json

import pytest

from articulate import cli


def test_plan_submit_roundtrip(tmp_path, capsys):
    source = tmp_path / "draft.txt"
    rewrite = tmp_path / "rewrite.txt"
    source.write_text("We really shipped 3 fixes.", encoding="utf-8")
    rewrite.write_text("We shipped 3 fixes.", encoding="utf-8")
    assert cli.main(["plan", str(source)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["backend"] == "host"
    assert cli.main(["submit", str(source), str(rewrite), "--plan", plan["plan_id"],
                     "--model", "scripted-host"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["text"] == "We shipped 3 fixes."
    assert result["gate_after"] == "ok"
    assert result["receipt"]["backend"] == "host"
    assert result["receipt"]["model"] == "scripted-host"
    assert source.read_text(encoding="utf-8") == "We really shipped 3 fixes."


@pytest.mark.parametrize("goal", ["judge", "fix", "polish"])
def test_no_model_cli_is_successful_and_records_backend(tmp_path, capsys, goal):
    source = tmp_path / "draft.txt"
    source.write_text("We really shipped 3 fixes.", encoding="utf-8")
    assert cli.main([goal, str(source), "--backend", "none", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    assert result["backend"] == "none"
    assert result["receipt"]["backend"] == "none"


def test_submit_wrong_original_does_not_write_output(tmp_path, capsys):
    source = tmp_path / "draft.txt"
    rewrite = tmp_path / "rewrite.txt"
    dest = tmp_path / "accepted.txt"
    source.write_text("We shipped 3 fixes.", encoding="utf-8")
    rewrite.write_text("We shipped 3 fixes.", encoding="utf-8")
    assert cli.main(["plan", str(source)]) == 0
    plan = json.loads(capsys.readouterr().out)
    source.write_text("We shipped 4 fixes.", encoding="utf-8")
    assert cli.main(["submit", str(source), str(rewrite), "--plan", plan["plan_id"],
                     "--out", str(dest)]) == 2
    assert not dest.exists()


def test_plan_honors_declared_profile(tmp_path, capsys):
    source = tmp_path / "draft.txt"
    source.write_text("writing-profile: narrative\nThe rain fell.", encoding="utf-8")
    assert cli.main(["plan", str(source)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["profile"]["no_em_dash"] is False
    assert plan["profile"]["slop"] == "off"


def test_plan_mode_wins_over_profile_inference(tmp_path, capsys):
    source = tmp_path / "README.md"
    source.write_text("The rain fell.", encoding="utf-8")
    assert cli.main(["plan", str(source), "--mode", "narrative/narrate"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["mode"] == "narrative/narrate"
    assert plan["profile"]["editor"]["run_fix_by_default"] is False
