"""Falsifiers for ambient repo-map context (parity with Copilot's @workspace
auto-context: the model gets the codebase's shape without asking for it first).

Load-bearing: (1) --agent folds a real repo map into the system prompt so the
model can act without first calling the repo_map tool; (2) --no-repo-map opts
out cleanly; (3) the map is bounded (never unbounded context growth on a huge
tree); (4) it never crashes on a test double lacking .system (the same guard
pattern as conventions); (5) the map reflects the REAL --root, not a hardcoded path.
"""
from relay import local_agent_cli as cli


class _Live:
    def live_backend(self):
        return object()


def _base_kwargs():
    return {"final": "done", "steps": 1, "entries": 1, "checkpoint": "c" * 32,
            "verified": True, "accepted": True, "check_passed": None,
            "integrity": {"clean": True, "flag_count": 0},
            "review": {"reviewability": 1.0, "edited_unread": [], "unverified_edits": [],
                      "failed_calls": 0},
            "risk": {"demands": []}}


def test_coding_agent_folds_a_real_repo_map_into_the_system_prompt(tmp_path, monkeypatch):
    (tmp_path / "app.py").write_text("def handler():\n    pass\n", encoding="utf-8")
    seen = {}
    monkeypatch.setattr(cli, "_all_backends", lambda args: [])
    monkeypatch.setattr(cli, "LocalAgent",
                        lambda *a, **k: type("A", (), {"system": "base"})())
    agent = cli._coding_agent(type("Args", (), {
        "backend": "auto", "max_tokens": 512, "temperature": 0.0, "seed": 0,
        "system": "", "root": str(tmp_path), "no_repo_map": False,
        "serve_url": "", "ollama_url": "", "model": "",
    })())
    assert "app.py" in agent.system and "handler" in agent.system
    assert agent.system.startswith("base")   # appended, never replaces the base prompt


def test_no_repo_map_flag_opts_out_cleanly(tmp_path):
    monkeypatch_args = type("Args", (), {
        "backend": "auto", "max_tokens": 512, "temperature": 0.0, "seed": 0,
        "system": "", "root": str(tmp_path), "no_repo_map": True,
        "serve_url": "http://127.0.0.1:1", "ollama_url": "http://127.0.0.1:2", "model": "",
    })()
    agent = cli._coding_agent(monkeypatch_args)
    assert "Repo map" not in agent.system


def test_repo_map_is_bounded_not_unbounded_growth(tmp_path):
    for i in range(200):
        (tmp_path / f"m{i}.py").write_text(f"def f{i}():\n    pass\n", encoding="utf-8")
    args = type("Args", (), {
        "backend": "auto", "max_tokens": 512, "temperature": 0.0, "seed": 0,
        "system": "", "root": str(tmp_path), "no_repo_map": False,
        "serve_url": "http://127.0.0.1:1", "ollama_url": "http://127.0.0.1:2", "model": "",
    })()
    agent = cli._coding_agent(args)
    assert len(agent.system) < 6000   # bounded even against a 200-file tree


def test_reflects_the_real_root_not_a_hardcoded_path(tmp_path):
    (tmp_path / "unique_marker_xyz.py").write_text("x = 1\n", encoding="utf-8")
    args = type("Args", (), {
        "backend": "auto", "max_tokens": 512, "temperature": 0.0, "seed": 0,
        "system": "", "root": str(tmp_path), "no_repo_map": False,
        "serve_url": "http://127.0.0.1:1", "ollama_url": "http://127.0.0.1:2", "model": "",
    })()
    assert "unique_marker_xyz" in cli._coding_agent(args).system


def test_does_not_crash_on_an_agent_double_without_system(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "_all_backends", lambda args: [])
    monkeypatch.setattr(cli, "LocalAgent", lambda *a, **k: object())   # no .system
    args = type("Args", (), {
        "backend": "auto", "max_tokens": 512, "temperature": 0.0, "seed": 0,
        "system": "", "root": str(tmp_path), "no_repo_map": False,
        "serve_url": "", "ollama_url": "", "model": "",
    })()
    cli._coding_agent(args)   # must not raise


def test_cli_agent_path_exits_cleanly_for_a_double_without_system(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "_build_agent", lambda args: object())   # no .system, no backend probe

    rc = cli.main(["do the thing", "--agent", "--root", str(tmp_path)])

    assert rc == 1
    assert "no local backend" in capsys.readouterr().err


def test_cli_agent_path_exits_cleanly_for_a_live_double_without_send(monkeypatch, tmp_path, capsys):
    D = type("D", (), {"live_backend": lambda self: object()})
    monkeypatch.setattr(cli, "_build_agent", lambda args: D())

    rc = cli.main(["task", "--agent", "--root", str(tmp_path)])

    assert rc == 1
    assert "missing send" in capsys.readouterr().err


def test_cli_agent_path_initializes_system_for_a_live_double_without_system(monkeypatch, tmp_path):
    (tmp_path / "seen_module.py").write_text("def f():\n    pass\n", encoding="utf-8")
    captured = {}

    class LiveNoSystem:
        def live_backend(self):
            return object()

        def send(self, message):
            captured["system"] = self.system
            return {"content": [{"type": "text", "text": "done"}], "backend": "stub"}

    monkeypatch.setattr(cli, "_build_agent", lambda args: LiveNoSystem())

    rc = cli.main(["do the thing", "--agent", "--root", str(tmp_path)])

    assert rc == 0
    assert "seen_module" in captured["system"]


def test_cli_agent_run_end_to_end_uses_coding_agent(monkeypatch, tmp_path):
    (tmp_path / "seen_module.py").write_text("def f():\n    pass\n", encoding="utf-8")
    captured = {}

    class _Live2:
        system = "base"

        def live_backend(self):
            return object()

        def send(self, message):
            raise AssertionError("run_agent is patched in this test")
    monkeypatch.setattr(cli, "_build_agent", lambda args: _Live2())
    monkeypatch.setattr(cli, "run_agent",
                        lambda agent, goal, *a, **k: (captured.update(system=agent.system),
                                                      _base_kwargs())[1])
    rc = cli.main(["do the thing", "--agent", "--root", str(tmp_path)])
    assert rc == 0
    assert "seen_module" in captured["system"]
