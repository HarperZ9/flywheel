"""`flywheel behavior-check`: replay scripted sessions on two builds and compare.

Every session here talks to the scripted model in harness.behavior_check.model;
no test reaches a real model server.
"""
import json
import shutil
import urllib.request
from pathlib import Path

import pytest

from harness.behavior_check import cli, compare
from harness.behavior_check.check import behavior_check, render, seal_receipt
from harness.behavior_check.model import ScriptedModel
from harness.behavior_check.run import clean_env, command, load_scenarios
from harness.hash_chain import seal

ROOT = Path(__file__).resolve().parent.parent
FAST = ["read_small", "todo_list"]


def _copy_build(dest: Path) -> Path:
    shutil.copytree(ROOT / "harness", dest / "harness",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(ROOT / "pyproject.toml", dest / "pyproject.toml")
    return dest


def test_the_same_build_twice_matches(tmp_path):
    report = behavior_check(str(ROOT), str(ROOT), only=FAST, work=str(tmp_path), jobs=2)
    assert report["verdict"] == "MATCH", render(report)
    assert [r["verdict"] for r in report["scenarios"]] == ["MATCH", "MATCH"]
    assert all(r["model_requests"][0] > 0 for r in report["scenarios"])
    assert report["first_divergence"] is None


def test_a_planted_change_drifts_and_names_the_first_diverging_event(tmp_path):
    build = _copy_build(tmp_path / "planted")
    policy = build / "harness" / "code_session" / "policy.py"
    text = policy.read_text(encoding="utf-8")
    assert 'marks = {"pending": "[ ]"' in text
    policy.write_text(text.replace('marks = {"pending": "[ ]"', 'marks = {"pending": "[-]"'),
                      encoding="utf-8")
    report = behavior_check(str(ROOT), str(build), only=FAST, work=str(tmp_path), jobs=2)
    assert report["verdict"] == "DRIFT"
    first = report["first_divergence"]
    assert first["scenario"] == "todo_list"
    assert first["stream"] == "requests" and first["index"] == 1
    assert "[ ] add a line" in first["a"] and "[-] add a line" in first["b"]
    assert {r["scenario"]: r["verdict"] for r in report["scenarios"]} == {
        "read_small": "MATCH", "todo_list": "DRIFT"}
    assert "first divergence: scenario todo_list, stream requests" in render(report)


def test_the_cli_exits_one_on_drift_and_writes_a_sealed_receipt(tmp_path, capsys):
    build = _copy_build(tmp_path / "b")
    backends = build / "harness" / "code_session" / "backends.py"
    backends.write_text(backends.read_text(encoding="utf-8").replace(
        "Read before you change anything", "Read before you change things"), encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    code = cli.main([str(ROOT), str(build), "--scenario", "read_small", "--json",
                     "--work", str(tmp_path), "--receipt", str(receipt)])
    out = json.loads(capsys.readouterr().out)
    assert code == 1 and out["verdict"] == "DRIFT"
    assert out["first_divergence"]["path"] == ".messages[0].content"
    sealed = json.loads(receipt.read_text(encoding="utf-8"))
    assert sealed["receipt_sha256"] == seal(sealed, digest_key="receipt_sha256")["receipt_sha256"]
    assert sealed["receipt_sha256"] == out["receipt_sha256"]


def test_a_folder_that_is_not_a_build_is_refused(tmp_path, capsys):
    assert cli.main([str(ROOT), str(tmp_path)]) == 2
    assert "not a Flywheel source tree" in capsys.readouterr().err


def test_normalization_masks_only_paths_ids_times_and_hashes_over_them():
    rules = compare.load_rules()
    run = {"masks": {"workspace": "/tmp/bc-1/home/ws", "flywheel_home": "/tmp/bc-1/fwhome"},
           "streams": {"requests": ["read /tmp/bc-1/home/ws/a.py at 2026-10-15T08:53:29Z"],
                       "events": [{"session_id": "x", "seconds": 1.5, "ledger_head": "ab",
                                   "output": 'META {"mtime_ns":1792079592124533700} '
                                             "20261015-085329-85a260 run-0123456789ab"},
                                  {"output": "a changed tool result", "steps": 3}],
                       "files": [["a.py", "ff"]], "exit": 0, "ledger": ["user"]}}
    out = compare.normalize(run, rules)
    assert out["requests"] == ["read <workspace>/a.py at <TIMESTAMP>"]
    event = out["events"][0]
    assert event["session_id"] == "<SESSION_ID>" and event["seconds"] == "<DURATION>"
    assert event["output"] == 'META {"mtime_ns":0} <SESSION_ID> <RUN_ID>'
    assert out["events"][1] == {"output": "a changed tool result", "steps": 3}
    assert out["files"] == [["a.py", "ff"]]


def test_first_difference_points_at_the_field():
    found = compare.first_difference({"m": [{"c": "abc"}, 1]}, {"m": [{"c": "abd"}, 1]})
    assert found["path"] == ".m[0].c" and found["a"].endswith("abc")
    assert compare.diverge("s", *[{k: v for k, v in zip(compare.STREAMS, (
        [], [], [], 0, ["user", x]))} for x in ("save", "tool_call")])["index"] == 1


def test_the_session_is_pinned_to_the_scripted_model():
    argv = command(str(ROOT), load_scenarios()[0], "python")
    assert argv[argv.index("--backend") + 1] == "codex"
    assert argv[argv.index("--providers") + 1] == "codex"
    env = clean_env({"OLLAMA_HOST": "x", "OPENAI_API_KEY": "real", "ANTHROPIC_API_KEY": "k",
                     "CODEX_BASE_URL": "https://api.openai.com/v1", "FLYWHEEL_HOME": "h",
                     "PATH": "p"})
    assert env == {"PATH": "p"}


def test_the_scripted_model_records_bodies_and_repeats_its_last_reply():
    with ScriptedModel(["one", "two"]) as model:
        replies = []
        for i in range(3):
            req = urllib.request.Request(model.base_url + "/chat/completions",
                                         data=json.dumps({"n": i}).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                replies.append(json.load(resp)["choices"][0]["message"]["content"])
    assert replies == ["one", "two", "two"]
    assert model.requests == [{"n": 0}, {"n": 1}, {"n": 2}]


def test_scenarios_cover_the_tool_and_permission_paths():
    names = {s["name"] for s in load_scenarios()}
    assert {"read_small", "write_new", "edit_existing", "run_command", "todo_list",
            "permission_rule_deny", "hook_block", "multi_step_search", "plan_mode"} <= names
    with pytest.raises(ValueError):
        ScriptedModel(["x"], host="0.0.0.0")
    assert seal_receipt({"schema": "flywheel.behavior-check/v1", "verdict": "MATCH"})[
        "schema"] == "flywheel.behavior-check-receipt/v1"
