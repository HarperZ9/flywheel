"""A check command is trusted by what is on disk, not by which tool changed it.

Each case drives a real bound run. A test file rewritten by a shell command,
a patch with a plain `+++ path` header, and a test-runner config that turns
every check into a collect-only run must all leave the final answer failed,
not Done. A native tool run that runs out of steps must not run its check.
"""
import json
import sys
import time

from harness.gateway_agent_binding import freeze_agent_binding
from harness.gateway_agent_execution import run_private_agent
from harness.gateway_agent_trace import AgentTrace
from harness.gateway_completion_outcome import derive_completion
from harness.gateway_operation import canonicalize_operation
from harness.patch_paths import patch_target_paths
from harness.plan_run_snapshot import thaw_json
from tests.test_gateway_operations import JOURNEY, OWNER
from tests.test_gateway_operation_recovery import OPERATION
from tests.test_gateway_run_budget_signals import _drive, _op, _pytest

FAILING = "def test_feature():\n    assert False\n"
PATCH = ("--- tests/test_feature.py\n+++ tests/test_feature.py\n@@ -1,2 +1,2 @@\n"
         " def test_feature():\n-    assert False\n+    pass\n")


def _workspace(tmp_path, *, config=False):
    """A failing test and a check. With `config`, the check reads the
    workspace's own pytest configuration, as an owner's check would."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_feature.py").write_text(FAILING, encoding="utf-8")
    check = (f'"{sys.executable}" -m pytest -q -p no:cacheprovider tests' if config
             else _pytest("tests"))
    return _op(tmp_path, goal="make the feature test pass", test_cmd=check)


def _answer(records):
    report = records[-1]["payload"]["completion"]
    return report["items"][-1], report, derive_completion(records, "completed")


def _tool(name, **args):
    return f"TOOL {name} {json.dumps(args)}"


def test_a_shell_rewrite_of_the_check_is_not_trusted(tmp_path, monkeypatch):
    op = _workspace(tmp_path)
    (tmp_path / "fix.py").write_text(
        "open('tests/test_feature.py', 'w').write('def test_feature():\\n    pass\\n')\n",
        encoding="utf-8")
    run = _tool("run", cmd=f'"{sys.executable}" fix.py')
    error, records, _ = _drive(tmp_path, monkeypatch, op, [run, "The test passes now."])
    answer, report, projected = _answer(records)
    assert error is None
    assert (answer["status"], answer["detail"]) == ("failed", "integrity_not_clean")
    assert projected["verdict"] == "failed"
    # The file the command rewrote is listed, and only as claimed.
    changed = [i for i in report["items"] if i["kind"] == "file"]
    assert [(i["path"], i["status"], i["detail"]) for i in changed] == [
        ("tests/test_feature.py", "claimed", "changed_by_command")]


def test_a_patch_with_a_plain_header_is_listed_and_not_trusted(tmp_path, monkeypatch):
    op = _workspace(tmp_path)
    error, records, _ = _drive(tmp_path, monkeypatch, op,
                               [_tool("apply_patch", patch=PATCH), "Fixed."])
    answer, report, projected = _answer(records)
    assert error is None and (tmp_path / "tests" / "test_feature.py").read_text(
        encoding="utf-8") == "def test_feature():\n    pass\n"
    assert (answer["status"], answer["detail"]) == ("failed", "integrity_not_clean")
    assert report["items"][0]["path"] == "tests/test_feature.py"
    assert report["items"][0]["check"] == "file_hash_recheck"
    assert projected["status"] == "recorded" and projected["verdict"] == "failed"


def test_patch_paths_read_every_header_apply_patch_accepts():
    both = PATCH + "--- a/src/x.py\n+++ b/src/x.py\n@@ -0,0 +1 @@\n+x = 1\n"
    assert patch_target_paths(both) == ["tests/test_feature.py", "src/x.py"]
    assert patch_target_paths("--- a/x.py\n+++ /dev/null\n") == []
    from harness.provenance_trace import _patch_attributions
    from harness.run_review import _patch_paths
    assert _patch_paths(PATCH) == ["tests/test_feature.py"]
    assert [a["path"] for a in _patch_attributions(PATCH)] == ["tests/test_feature.py"]


def test_a_collect_only_pytest_ini_makes_the_check_untrusted(tmp_path, monkeypatch):
    op = _workspace(tmp_path, config=True)
    write = _tool("write_file", path="pytest.ini", content="[pytest]\naddopts = --co\n")
    error, records, _ = _drive(tmp_path, monkeypatch, op, [write, "Done."])
    answer, _, projected = _answer(records)
    assert error is None and records[-1]["payload"]["tests_pass"] is True
    assert (answer["status"], answer["detail"]) == ("failed", "integrity_not_clean")
    assert projected["verdict"] == "failed"


def test_the_pytest_section_of_pyproject_is_watched_and_the_rest_is_not(
        tmp_path, monkeypatch):
    op = _workspace(tmp_path, config=True)
    (tmp_path / "tests" / "test_feature.py").write_text(
        "def test_feature():\n    pass\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8")
    bump = _tool("write_file", path="pyproject.toml",
                 content='[project]\nname = "demo"\nversion = "0.2.0"\n')
    error, records, _ = _drive(tmp_path, monkeypatch, op, [bump, "Bumped."])
    assert error is None and _answer(records)[0]["status"] == "verified"

    other = tmp_path / "second"
    other.mkdir()
    op = _workspace(other, config=True)
    collect = _tool("write_file", path="pyproject.toml",
                    content='[tool.pytest.ini_options]\naddopts = "--co"\n')
    error, records, _ = _drive(other, monkeypatch, op, [collect, "Done."])
    assert error is None and _answer(records)[0]["detail"] == "integrity_not_clean"


def test_a_native_run_that_runs_out_of_steps_never_runs_its_check(tmp_path, monkeypatch):
    op = {"goal": "fix it", "endpoint": "openai", "model": "gpt-6-astra",
          "root": str(tmp_path), "max_steps": 2, "max_tokens": 321, "timeout_s": 15,
          "allow_write": False, "allow_exec": True, "stream": True,
          "tool_protocol": "native", "test_cmd": "pytest -q",
          "data_refs": [], "credential_refs": []}
    sent, ran = [], []

    class Transport:
        def __init__(self, **kwargs):
            pass

        def __call__(self, method, url, headers, body, timeout):
            sent.append(1)
            return 200, {"id": f"resp_{len(sent)}", "model": "gpt-6-astra",
                         "status": "completed", "output": [{
                             "type": "function_call", "id": f"fc_{len(sent)}",
                             "call_id": f"call_{len(sent)}", "name": "list_dir",
                             "arguments": json.dumps({"path": "."})}]}
    monkeypatch.setattr("harness.gateway_agent_native_tools.BoundAgentTransport", Transport)
    monkeypatch.setattr("harness.gateway_agent_native_tools.make_sandboxed_runner",
                        lambda **kw: lambda cmd, root: ran.append(cmd) or (True, "1 passed"))
    state = tmp_path.parent / (tmp_path.name + "_state")
    state.mkdir()
    binding = thaw_json(freeze_agent_binding(canonicalize_operation("agent.run", op), state))
    trace = AgentTrace(state, OWNER, JOURNEY, OPERATION, secrets=("sk-native-fixture-7c1",))
    projection = run_private_agent(op, {"OPENAI_API_KEY": "sk-native-fixture-7c1"}, state,
                                   trace, None, lambda e: None, binding=binding,
                                   deadline=time.monotonic() + 15)
    records = AgentTrace(state, OWNER, JOURNEY, OPERATION).read()
    answer, report, projected = _answer(records)
    assert projection["state"] == "completed" and len(sent) == 2 and ran == []
    assert records[-1]["payload"]["tests_pass"] is False
    assert (answer["status"], answer["check"], answer["detail"]) == (
        "failed", "test_command", "failed")
    assert report["verdict"] == "failed" and projected["verdict"] == "failed"


class _Recorder:
    """An executor whose check run writes a snapshot file, as snapshot tests do."""

    def __init__(self, root):
        self.root, self.calls = root, 0

    def execute(self, name, args, *extra, **kwargs):
        self.calls += 1
        (self.root / "tests" / "snap.txt").write_text(f"run {self.calls}", encoding="utf-8")
        return type("R", (), {"ok": True, "output": "1 passed"})()


def test_files_the_check_itself_writes_are_its_side_effects(tmp_path):
    from harness.check_guard import guard_check
    from harness.integrity import trajectory_integrity
    from harness.local_session import SessionLedger
    (tmp_path / "tests").mkdir()
    ledger = SessionLedger()
    executor = guard_check(_Recorder(tmp_path), root=tmp_path, ledger=ledger,
                           test_cmd="pytest -q")
    for _ in range(3):
        executor.execute("run", {"cmd": "pytest -q"})
    assert trajectory_integrity(ledger) == []
    assert executor.check_side_effects == {"tests/snap.txt"}
    (tmp_path / "tests" / "test_x.py").write_text("def test_x(): pass\n", encoding="utf-8")
    executor.execute("run", {"cmd": "pytest -q"})
    assert [f.kind for f in trajectory_integrity(ledger)] == ["check_files_changed"]
