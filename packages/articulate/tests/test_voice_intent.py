"""voice intend builds a spec from intent words and samples without keeping
sample text; voice check scores a draft against it and points at the misses."""
import json

import pytest

from articulate import cli, voice_intent
from test_voice_devices import PLAIN, TEMPLATE


def test_builtin_zain_spec_carries_the_stance():
    spec = voice_intent.load_spec("zain")
    for want in ("what-if", "other-shoes", "counter-view", "stance", "anchor", "reader-question"):
        assert spec["wants"][want] >= 1
    assert spec["limits"]["closing-maxim"] == 0
    assert spec["limits"]["house-devices"] == 0


def test_goal_and_stance_words_choose_the_moves():
    spec = voice_intent.build_spec("market a launch", "developers", "blunt, asks what if")
    assert {"anchor", "tool", "stance", "what-if"} <= set(spec["wants"])
    assert "other-shoes" not in spec["wants"]
    assert spec["plan"] and spec["plan"][0].startswith("Open on something")


def test_samples_leave_hashes_and_counts_only():
    spec = voice_intent.build_spec("persuade", "readers", "contrarian", [TEMPLATE, PLAIN])
    blob = json.dumps(spec)
    assert "ferry" not in blob and "Bremerton" not in blob
    assert len(spec["sources"]["samples"]) == 2
    assert spec["sources"]["sample_tells"]["one-line-paragraphs"] == 1
    assert any("Your samples lean on" in step for step in spec["plan"])
    assert spec["limits"]["one-line-paragraphs"] == 0


def test_check_scores_template_below_plain():
    spec = voice_intent.load_spec("zain")
    low, high = voice_intent.check(TEMPLATE, spec), voice_intent.check(PLAIN, spec)
    assert low["score"] < 60 <= high["score"]
    assert high["score"] == 100
    miss = {c["id"]: c for c in low["checks"] if not c["ok"]}
    assert miss["closing-maxim"]["lines"] == [27]
    assert "does not check facts" in low["score_means"]


def test_unknown_spec_is_refused(tmp_path):
    with pytest.raises(ValueError):
        voice_intent.load_spec("nobody")
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema": "other"}', encoding="utf-8")
    with pytest.raises(ValueError):
        voice_intent.load_spec(str(bad))


def test_cli_intend_then_check(tmp_path, capsys):
    spec_path, draft = tmp_path / "spec.json", tmp_path / "post.md"
    draft.write_text(TEMPLATE, encoding="utf-8")
    assert cli.main(["voice", "intend", "--goal", "persuade on X", "--stance", "contrarian",
                     "--out", str(spec_path)]) == 0
    assert "Plan:" in capsys.readouterr().out
    assert cli.main(["voice", "check", str(draft), "--intent", str(spec_path)]) == 0
    out = capsys.readouterr().out
    assert "/100 against 'custom'" in out and "the post ends on a maxim" in out
    assert cli.main(["voice", "check", str(draft), "--intent", "zain", "--min-score", "90"]) == 1
    capsys.readouterr()
    assert cli.main(["voice", "check", str(draft), "--intent", "zain", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["schema"] == voice_intent.CHECK_SCHEMA


def test_cli_intend_needs_a_goal_or_base(capsys):
    assert cli.main(["voice", "intend"]) == 2
    assert "--goal" in capsys.readouterr().err
    assert cli.main(["voice", "intend", "--list"]) == 0
    assert "zain" in capsys.readouterr().out
