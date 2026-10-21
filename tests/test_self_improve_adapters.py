"""Command-line executor and editor adapters, argv presets, contrast selection."""
import sys

import pytest

from harness.self_improve_adapters import (
    CommandEditor, CommandExecutor, ContrastSelector, codex_argv, opencode_argv,
)
from harness.self_improve_loop import EditContext, Rollout

AGENT = ("import pathlib,sys; ws=pathlib.Path(sys.argv[1]); "
         "p=(ws/'harness'/'systemprompt.md').read_text(); "
         "(ws/'answer.txt').write_text(p.strip()+'|'+(ws/'ledger.csv').read_text())")
EDIT = ("import pathlib,sys; ws=pathlib.Path(sys.argv[1]); "
        "f=ws/'harness'/'systemprompt.md'; f.write_text(f.read_text()+'edited\\n'); "
        "print('notes: '+sys.argv[2])")


def test_command_executor_runs_agent_in_fresh_workspace():
    ex = CommandExecutor([sys.executable, "-c", AGENT, "{workdir}", "{prompt}"])
    r = ex.execute({"prompt": "go", "files": {"ledger.csv": "rows"}},
                   {"systemprompt.md": "be exact\n"}, "base1")
    assert r.delivered and r.output == "be exact|rows" and r.label == "base1"


def test_command_executor_marks_failures_undelivered():
    ex = CommandExecutor([sys.executable, "-c", "import sys; sys.exit(3)"])
    r = ex.execute({"prompt": "go"}, {"systemprompt.md": "x"}, "b")
    assert not r.delivered


def test_unsafe_task_file_is_refused():
    ex = CommandExecutor([sys.executable, "-c", "pass"])
    with pytest.raises(ValueError):
        ex.execute({"files": {"../out.txt": "x"}}, {"systemprompt.md": "x"}, "b")


def test_command_editor_harvests_edited_tree():
    ed = CommandEditor([sys.executable, "-c", EDIT, "{workdir}", "{prompt}"],
                       mission=lambda ctx: f"improve {ctx.label}")
    ctx = EditContext({"id": "t"}, "inv1", "INV", {"systemprompt.md": "v0\n"},
                      [Rollout("base1", "out")])
    prop = ed.propose(ctx)
    assert prop.tree == {"systemprompt.md": "v0\nedited\n"}
    assert "improve inv1" in prop.notes


def test_command_editor_failure_raises():
    ed = CommandEditor([sys.executable, "-c", "import sys; sys.exit(1)"],
                       mission=lambda ctx: "x")
    with pytest.raises(ValueError):
        ed.propose(EditContext({"id": "t"}, "inv1", "INV", {"systemprompt.md": "v"}, []))


def test_argv_presets():
    oc = opencode_argv("ollama/qwen3:8b")
    assert oc[:3] == ["opencode", "run", "{prompt}"] and "ollama/qwen3:8b" in oc
    cx = codex_argv("qwen3:8b", local_provider="ollama")
    assert cx[:3] == ["codex", "exec", "--skip-git-repo-check"]
    assert "--oss" in cx and cx[-1] == "{prompt}"
    assert "--oss" not in codex_argv("gpt-x")


def test_contrast_selector_is_label_independent():
    sel = ContrastSelector(lambda task, r: float(len(r.output)))
    a = {"agg1": Rollout("agg1", "xx"), "agg2": Rollout("agg2", "yy")}
    b = {"agg2": Rollout("agg2", "xx"), "agg1": Rollout("agg1", "yy")}
    pick_a, _, _ = sel.choose({}, a)
    pick_b, _, _ = sel.choose({}, b)
    assert a[pick_a].output == b[pick_b].output


def test_contrast_selector_skips_undelivered():
    sel = ContrastSelector(lambda task, r: 1.0)
    finals = {"a": Rollout("a", "x", delivered=False), "b": Rollout("b", "y")}
    pick, _, scores = sel.choose({}, finals)
    assert pick == "b" and scores["a"] is None
