"""When commands may write in the project, and what each backend is told.

No command starts here. The bubblewrap argv and the Seatbelt profile are pure
functions, so what a Linux or macOS host would enforce is asserted from any
host; the decision to open a project is asserted with injected paths.
"""
import json
from pathlib import Path

import pytest

from harness.code_session import cli
from harness.code_session.backends import build_agent
from harness.code_session.session import new_session
from harness.machine_policy import Policy
from harness.posix_sandbox import build, bwrap_argv, describe
from harness.sandbox_policy import sbpl_profile
from harness.workspace_run import WRITES_ENV, Workspace, finish, open_workspace

HOOKS = (("dir", "/w/.git/hooks"), ("file", "/w/.mcp.json"))


def _pairs(argv, flag):
    return [(argv[i + 1], argv[i + 2]) for i, word in enumerate(argv) if word == flag]


def test_bwrap_binds_guarded_paths_read_only_over_the_writable_root():
    argv = bwrap_argv("bwrap", "/w", "/s", "make", write_protected=HOOKS)
    assert ("/w", "/w") in _pairs(argv, "--bind")
    closed = _pairs(argv, "--ro-bind")
    assert ("/w/.git/hooks", "/w/.git/hooks") in closed and ("/w/.mcp.json", "/w/.mcp.json") in closed
    assert argv.index("/w/.git/hooks") > argv.index("--bind")   # later binds win


def test_bwrap_with_a_closed_root_binds_only_the_scratch_writable():
    argv = bwrap_argv("bwrap", "/w", "/s", "make", root_writable=False)
    assert _pairs(argv, "--bind") == [("/s", "/s")]
    assert ("/", "/") in _pairs(argv, "--ro-bind")
    assert describe("bwrap", "/w", "/s", root_writable=False).writable == ("/s",)
    assert describe("bwrap", "/w", "/s").writable == ("/w", "/s")


def test_bwrap_default_argv_is_what_it_was():
    plain = bwrap_argv("bwrap", "/w", "/s", "ls")
    assert plain == bwrap_argv("bwrap", "/w", "/s", "ls", root_writable=True, write_protected=())
    assert plain[plain.index("--tmpfs") + 2:plain.index("--chdir")] == [
        "--bind", "/w", "/w", "--bind", "/s", "/s"]


def test_seatbelt_denies_guarded_paths_after_the_allow():
    profile = sbpl_profile("/w", "/s", write_protected=HOOKS)
    allow, deny = profile.index("(allow file-write*"), profile.rindex("(deny file-write*")
    assert deny > allow                                 # Seatbelt takes the last match
    assert '(subpath "/w/.git/hooks")' in profile[deny:]
    assert '(literal "/w/.mcp.json"))' in profile[deny:]


def test_seatbelt_with_a_closed_root_allows_only_the_scratch():
    profile = sbpl_profile("/w", "/s", root_writable=False)
    assert '(subpath "/s")' in profile and '(subpath "/w")' not in profile
    assert sbpl_profile("/w", "/s") == sbpl_profile("/w", "/s", root_writable=True,
                                                    write_protected=())


def test_build_passes_the_workspace_to_both_backends():
    assert "/w/.git/hooks" in build("bwrap", "bwrap", "/w", "/s", "ls", write_protected=HOOKS)
    assert "/w/.git/hooks" in build("seatbelt", "sandbox-exec", "/w", "/s", "ls",
                                    write_protected=HOOKS)[2]


def _open(tmp_path, **kw):
    root = tmp_path / "proj"
    root.mkdir(exist_ok=True)
    args = {"environ": {}, "policy": Policy(), "home": tmp_path / "home",
            "flywheel_home": tmp_path / "state", **kw}
    return open_workspace(root, **args)


def test_a_plain_project_is_opened(tmp_path):
    space = _open(tmp_path)
    assert space.writable and space.reason == ""
    assert space.posix() == {"root_writable": True, "write_protected": ()}


def test_an_administrator_pin_closes_it_and_outranks_the_environment(tmp_path):
    pinned = Policy(pins={"allow_workspace_writes": False}, path="/etc/flywheel/policy.json")
    space = _open(tmp_path, policy=pinned, environ={WRITES_ENV: "1"})
    assert not space.writable and "machine-wide policy" in space.reason
    assert space.posix() == {"root_writable": False, "write_protected": ()}


def test_a_broken_policy_file_pins_writes_closed(tmp_path):
    from harness.machine_policy import load_policy
    path = tmp_path / "policy.json"
    path.write_text("{not json", encoding="utf-8")
    broken = load_policy(path, owner=lambda p: None)
    assert broken.pinned("allow_workspace_writes") is False
    assert not _open(tmp_path, policy=broken).writable


@pytest.mark.parametrize("value", ["0", "false", "off", "No"])
def test_the_user_can_keep_the_project_read_only(tmp_path, value):
    space = _open(tmp_path, environ={WRITES_ENV: value})
    assert not space.writable and WRITES_ENV in space.reason


def test_a_root_holding_the_home_or_flywheel_state_is_not_opened(tmp_path):
    assert "home folder" in _open(tmp_path, home=tmp_path / "proj" / "me").reason
    assert "home folder" in _open(tmp_path, home=tmp_path / "proj").reason
    assert "state folder" in _open(tmp_path, flywheel_home=tmp_path / "proj" / ".fw").reason
    inside = open_workspace(tmp_path / "state" / "x", environ={}, policy=Policy(),
                            home=tmp_path / "home", flywheel_home=tmp_path / "state")
    assert not inside.writable
    drive = open_workspace(Path(tmp_path.anchor), environ={}, policy=Policy(),
                           home=tmp_path / "home", flywheel_home=tmp_path / "state")
    assert not drive.writable


def test_kernel_paths_name_only_what_exists_and_never_a_git_config(tmp_path):
    space = _open(tmp_path)
    root = space.root
    (root / ".git" / "hooks").mkdir(parents=True)
    (root / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (root / ".mcp.json").write_text("{}", encoding="utf-8")
    assert space.kernel_paths() == (("dir", str(root / ".git" / "hooks")),
                                    ("file", str(root / ".mcp.json")))
    assert Workspace(root, False, "closed").kernel_paths() == ()


def test_finish_reports_a_guarded_change_as_a_refused_run(tmp_path):
    from harness import workspace_guard
    space = _open(tmp_path)
    before = workspace_guard.snapshot(space.root)
    (space.root / ".mcp.json").write_text("{}", encoding="utf-8")
    ok, out = finish(space, before, True, "[exit 0]\ndone\n")
    assert not ok and out.startswith("[exit 0]\ndone\n[refused]")
    assert ".mcp.json: added, removed" in out
    assert finish(space, before, False, "[blocked] command denied: x") == (
        False, "[blocked] command denied: x")


class _Script:
    name, model = "script", "script-1"

    def __init__(self, replies):
        self.replies = list(replies)

    def health(self):
        return True

    def chat(self, messages, *, system, max_tokens, temperature, seed):
        return {"text": self.replies.pop(0), "model_ref": "script:script-1", "seed": seed}


def _session(tmp_path, mode, approver, calls):
    def runner(cmd, root):
        calls.append(cmd)
        return True, "[exit 0]\n[workspace writable: guarded paths unchanged]"
    replies = ['TOOL run {"cmd": "npm install"}', "Done."]
    return new_session(build_agent([_Script(replies)]), str(tmp_path), mode=mode,
                       approver=approver, runner=runner)


@pytest.mark.parametrize("mode,answer,ran", [
    ("plan", "yes", False), ("ask", "no", False), ("ask", "yes", True),
    ("edit", "no", False), ("auto", "no", True)])
def test_a_writing_command_waits_for_the_mode_before_it_runs(tmp_path, mode, answer, ran):
    calls, asked = [], []

    def approver(name, args):
        asked.append(name)
        return answer
    session = _session(tmp_path, mode, approver, calls)
    session.turn("install the packages")
    assert (calls == ["npm install"]) is ran
    assert asked == ([] if mode in ("plan", "auto") else ["run"])
    assert session.ledger.verify()


def test_a_write_capable_run_is_on_the_ledger_with_its_workspace_line(tmp_path):
    calls = []
    session = _session(tmp_path, "auto", None, calls)
    session.turn("install the packages")
    kinds = [entry.kind for entry in session.ledger.entries]
    assert "tool_call" in kinds and "tool_result" in kinds
    results = [entry.content for entry in session.ledger.entries if entry.kind == "tool_result"]
    assert any("[workspace writable: guarded paths unchanged]" in text for text in results)
    decisions = [json.loads(e.content) for e in session.ledger.entries if e.kind == "approval"]
    assert decisions and decisions[0]["class"] == "exec" and decisions[0]["tool"] == "run"


def test_the_session_runner_adds_the_workspace_line(monkeypatch, tmp_path):
    import harness.sandboxed_runner as sr
    seen = {}

    def fake(cmd, root, **kw):
        seen.update(kw)
        return True, "[exit 0]\n"
    monkeypatch.setattr(sr, "sandboxed_run", fake)
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "state"))
    root = tmp_path / "proj"
    root.mkdir()
    ok, out = cli._runner()("make", str(root))
    assert ok and out == "[exit 0]\n[workspace writable: guarded paths unchanged]"
    assert seen["workspace"].writable and seen["scratch_home"] is True


def test_a_background_job_is_given_a_read_only_project(monkeypatch, tmp_path):
    import harness.sandboxed_runner as sr
    from harness.code_session.background import Job, JobTable
    seen = {}

    def fake(cmd, root, **kw):
        seen.update(kw)
        return True, "[exit 0]"
    monkeypatch.setattr(sr, "sandboxed_run", fake)
    ok, out = JobTable(str(tmp_path))._sandboxed(Job("bg1", "npm run dev", 0.0))
    assert ok and "[workspace read-only: background jobs cannot write" in out
    assert seen["workspace"].writable is False
