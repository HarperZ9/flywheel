"""Falsifiers for architect mode: plan with one backend, implement with another.

The break these tests catch: adding --architect must not bypass the current
_coding_agent path that injects project context, and it must fail loud when the
requested planning backend is unavailable instead of silently running without a
plan.
"""

import types

import pytest

from relay.local_agent import BackendError


def _accepted_result():
    return {"final": "done", "steps": 1, "entries": 1, "checkpoint": "c" * 32,
            "verified": True, "accepted": True, "check_passed": None,
            "integrity": {"clean": True, "flag_count": 0},
            "review": {"reviewability": 1.0, "edited_unread": [], "unverified_edits": [],
                       "failed_calls": 0},
            "risk": {"demands": []}}


class _Planner:
    def __init__(self, text="", backend="claude-plan", raise_on_send=None):
        self.text = text
        self.backend = backend
        self.raise_on_send = raise_on_send
        self.sent = []

    def send(self, message):
        self.sent.append(message)
        if self.raise_on_send:
            raise self.raise_on_send
        return {"content": [{"type": "text", "text": self.text}], "backend": self.backend}


def test_plan_asks_to_plan_not_implement():
    from relay.architect import plan

    planner = _Planner("1. add a helper\n2. wire it in")

    result = plan(planner, "add caching to fetch()")

    assert "do not write code" in planner.sent[0].lower()
    assert "do not" in planner.sent[0].lower() and "tool" in planner.sent[0].lower()
    assert "add caching to fetch()" in planner.sent[0]
    assert result == {"text": "1. add a helper\n2. wire it in", "backend": "claude-plan"}


def test_with_plan_folds_the_proposal_into_the_goal_not_over_it():
    from relay.architect import with_plan

    goal = "add caching to fetch()"

    out = with_plan(goal, {"text": "1. add a helper", "backend": "claude-plan"})

    assert out.startswith(goal)
    assert "1. add a helper" in out
    assert "claude-plan" in out
    assert "adapt" in out.lower()


def test_empty_plan_response_does_not_crash_or_fabricate_content():
    from relay.architect import plan, with_plan

    result = plan(_Planner(""), "x")
    out = with_plan("x", result)

    assert result["text"] == ""
    assert out.startswith("x")


def test_failing_planner_raises_past_plan_uncaught():
    from relay.architect import plan

    with pytest.raises(BackendError):
        plan(_Planner(raise_on_send=BackendError("all backends down")), "x")


def test_cli_without_architect_leaves_goal_untouched_and_does_not_build_a_planner(monkeypatch, tmp_path):
    from relay import local_agent_cli as cli

    class LiveAgent:
        system = "base"

        def live_backend(self):
            return object()

        def send(self, message):
            raise AssertionError("run_agent is patched")

    seen = {}
    monkeypatch.setattr(cli, "_build_agent", lambda args: LiveAgent())
    monkeypatch.setattr(cli, "LocalAgent", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("planner should not be constructed without --architect")))
    monkeypatch.setattr(cli, "run_agent",
                        lambda agent, goal, *a, **k: (seen.update(goal=goal),
                                                      _accepted_result())[1])

    rc = cli.main(["do the thing", "--agent", "--root", str(tmp_path)])

    assert rc == 0
    assert seen["goal"] == "do the thing"


def test_cli_architect_folds_plan_into_goal_after_current_context_setup(monkeypatch, tmp_path):
    from relay import local_agent_cli as cli

    (tmp_path / "seen_module.py").write_text("def f():\n    pass\n", encoding="utf-8")

    class CodingAgent:
        system = "base"

        def live_backend(self):
            return object()

        def send(self, message):
            raise AssertionError("run_agent is patched")

    class PlanningAgent:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        def live_backend(self):
            return object()

        def send(self, message):
            return {"content": [{"type": "text", "text": "1. rename the function"}],
                    "backend": "claude-plan"}

    seen = {}
    monkeypatch.setattr(cli, "_build_agent", lambda args: CodingAgent())
    monkeypatch.setattr(cli, "LocalAgent", PlanningAgent)
    monkeypatch.setattr(cli, "run_agent",
                        lambda agent, goal, *a, **k: (seen.update(goal=goal,
                                                                  system=agent.system),
                                                      _accepted_result())[1])

    rc = cli.main(["do the thing", "--agent", "--root", str(tmp_path),
                   "--architect", "claude-plan"])

    assert rc == 0
    assert "do the thing" in seen["goal"]
    assert "rename the function" in seen["goal"]
    assert "claude-plan" in seen["goal"]
    assert "seen_module" in seen["system"]


def test_cli_architect_with_dead_planner_fails_loud_not_silently_skipped(monkeypatch, tmp_path, capsys):
    from relay import local_agent_cli as cli

    class CodingAgent:
        system = "base"

        def live_backend(self):
            return object()

        def send(self, message):
            raise AssertionError("run_agent should not run when planner is dead")

    class DeadPlanner:
        def __init__(self, *args, **kwargs):
            pass

        def live_backend(self):
            return None

    monkeypatch.setattr(cli, "_build_agent", lambda args: CodingAgent())
    monkeypatch.setattr(cli, "LocalAgent", DeadPlanner)
    monkeypatch.setattr(cli, "run_agent", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("run_agent should not run when planner is dead")))

    rc = cli.main(["do the thing", "--agent", "--root", str(tmp_path),
                   "--architect", "codex-plan"])

    assert rc == 1
    assert "--architect backend 'codex-plan' is not healthy" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("label", "argv"),
    [
        ("no_agent_prompt", ["do the thing", "--architect", "claude-plan"]),
        ("health", ["--health", "--architect", "claude-plan"]),
        ("mcp", ["--mcp", "--architect", "claude-plan"]),
        ("view", ["--view", "{tmp}/run.jsonl", "--architect", "claude-plan"]),
        ("verify_cert", ["--verify-cert", "{tmp}/run.rvc", "--architect", "claude-plan"]),
        ("bisect", ["--bisect", "{tmp}/run.jsonl", "--check", "pytest -q",
                    "--architect", "claude-plan"]),
        ("probe_injection", ["--probe-injection", "--architect", "claude-plan"]),
        ("watch", ["--watch", "--root", "{tmp}", "--architect", "claude-plan"]),
        ("best_of", ["do the thing", "--agent", "--root", "{tmp}",
                     "--architect", "claude-plan", "--best-of", "2"]),
    ],
)
def test_cli_rejects_architect_outside_plain_single_run_agent_before_dispatch(
        label, argv, monkeypatch, tmp_path, capsys):
    from relay import local_agent_cli as cli

    (tmp_path / "run.jsonl").write_text("{}", encoding="utf-8")
    (tmp_path / "run.rvc").write_text("{}", encoding="utf-8")
    rendered = [part.replace("{tmp}", str(tmp_path)) for part in argv]
    calls = []

    def forbidden(name):
        def fail(*args, **kwargs):
            calls.append(name)
            raise AssertionError(f"{name} should not run for unsupported architect mode")
        return fail

    monkeypatch.setattr(cli, "_run_best_of", forbidden("_run_best_of"))
    monkeypatch.setattr(cli, "_run_agentic", forbidden("_run_agentic"))
    monkeypatch.setattr(cli, "_run_watch", forbidden("_run_watch"))
    monkeypatch.setattr(cli, "_build_agent", forbidden("_build_agent"))
    monkeypatch.setattr(cli, "_all_backends", forbidden("_all_backends"))
    monkeypatch.setattr(cli, "LocalAgent", forbidden("LocalAgent"))
    monkeypatch.setitem(__import__("sys").modules, "relay.local_mcp",
                        types.SimpleNamespace(serve=forbidden("local_mcp.serve")))
    monkeypatch.setitem(__import__("sys").modules, "relay.injection_probe",
                        types.SimpleNamespace(probe=forbidden("injection_probe.probe")))
    monkeypatch.setitem(__import__("sys").modules, "relay.run_view",
                        types.SimpleNamespace(load_run=forbidden("run_view.load_run"),
                                              render=forbidden("run_view.render"),
                                              verify_edges=forbidden("run_view.verify_edges")))
    monkeypatch.setitem(__import__("sys").modules, "relay.cert",
                        types.SimpleNamespace(verify_cert=forbidden("cert.verify_cert")))
    monkeypatch.setitem(__import__("sys").modules, "relay.bisect",
                        types.SimpleNamespace(bisect_run=forbidden("bisect.bisect_run")))
    monkeypatch.setitem(__import__("sys").modules, "relay.local_session",
                        types.SimpleNamespace(SessionLedger=type(
                            "FakeSessionLedger", (), {"load": staticmethod(lambda *a, **k: {})})))

    rc = cli.main(rendered)

    assert rc == 2
    assert calls == []
    err = capsys.readouterr().err
    assert "--architect" in err and "plain single-run --agent" in err
