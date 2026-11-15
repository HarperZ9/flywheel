"""Falsifiers for what the remote entrypoint reads from its env file.

Load-bearing: (1) the launch grants, remote exec and the launch root come from
the process environment only, because a run with the write grant can rewrite the
env file in its root; (2) the escalation from a granted write to exec through .env
is refused by the file tools, and grant lines that reach .env some other way
leave the grants unchanged after a restart; (3) an inline comment
is not part of a value, so the shipped .env.example loads as documented;
(4) the remote surface configures what it will allow: RELAY_ALLOW_EXEC alone
grants neither exec nor write there, and RELAY_ALLOW_REMOTE_EXEC parses like the
other grant variables.
"""
import json
from pathlib import Path

import pytest

import relay.local_mcp as m
from relay import remote_cli
from relay.mcp_grants import LAUNCH_ONLY_KEYS, StartGrants, grants_from_env
from relay.remote_mcp import config_from_env, process
from relay.remote_state import load_dotenv, remote_state, resolved_env

_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"
_ESCALATE = ("RELAY_ALLOW_WRITE=true\nRELAY_ALLOW_EXEC=true\n"
             "RELAY_ALLOW_REMOTE_EXEC=true\nRELAY_MCP_ROOT=/\n"
             # what children inherit and which CLI a tier starts are launch-only too
             "RELAY_CHILD_ENV=OPENAI_API_KEY\nRELAY_ALLOW_EXEC_CLI=gemini\n"
             "RELAY_CLAUDE_CLI=./claude\nRELAY_CODEX_CLI=./codex\n")


@pytest.fixture(autouse=True)
def _clean_process_env(monkeypatch):
    for key in LAUNCH_ONLY_KEYS:
        monkeypatch.delenv(key, raising=False)


# --- (1) launch-only keys never come from the file ---

def test_the_env_file_cannot_set_the_launch_grants(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("RELAY_REMOTE_TOKEN=t\n" + _ESCALATE, encoding="utf-8")
    env, _ = resolved_env(env={}, env_file=str(env_file))
    assert env["RELAY_REMOTE_TOKEN"] == "t"
    assert not set(LAUNCH_ONLY_KEYS) & set(env)
    assert grants_from_env(env) == StartGrants()
    assert config_from_env(env).allow_remote_exec is False

    state = remote_state(env={}, env_file=str(env_file))
    assert state["env_file_ignored"] == sorted(LAUNCH_ONLY_KEYS)
    assert state["remote_exec_allowed"] is False
    assert state["start_grants"]["allow_exec"] is False


def test_the_process_environment_still_grants(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("RELAY_REMOTE_TOKEN=t\n", encoding="utf-8")
    env, _ = resolved_env(env={"RELAY_ALLOW_WRITE": "1", "RELAY_ALLOW_REMOTE_EXEC": "true"},
                          env_file=str(env_file))
    assert grants_from_env(env).allow_write is True
    assert config_from_env(env).allow_remote_exec is True


def test_the_entrypoint_names_ignored_file_keys(tmp_path, monkeypatch, capsys):
    class _Server:
        def serve_forever(self):
            raise KeyboardInterrupt

        def shutdown(self):
            pass

    (tmp_path / ".env").write_text("RELAY_REMOTE_TOKEN=t\nRELAY_ALLOW_EXEC=true\n",
                                   encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RELAY_ENV_FILE", raising=False)
    monkeypatch.setattr(remote_cli, "serve", lambda *a, **k: _Server())
    assert remote_cli.main() == 0
    out = capsys.readouterr().out
    assert "RELAY_ALLOW_EXEC" in out and "ignored" in out
    assert m._GRANTS.allow_exec is False


# --- (2) the escalation from write to exec through .env, end to end ---

class _EnvWriter:
    name = "stub"

    def __init__(self, content):
        call = json.dumps({"path": ".env", "content": content})
        self.replies = [f"TOOL write_file {call}", "done"]

    def health(self):
        return True

    def chat(self, messages, *, system, max_tokens, temperature, seed):
        return {"text": self.replies.pop(0) if self.replies else "done",
                "model_ref": "stub:env", "seed": seed}


def test_a_granted_write_cannot_escalate_through_the_env_file(tmp_path, monkeypatch):
    from relay.local_loop import run_agent as real_run_agent

    env_file = tmp_path / ".env"
    env_file.write_text("RELAY_REMOTE_TOKEN=t\n", encoding="utf-8")
    process_env = {"RELAY_ALLOW_WRITE": "1", "RELAY_MCP_ROOT": str(tmp_path)}

    def launch():
        env, _ = resolved_env(env=process_env, env_file=str(env_file))
        return grants_from_env(env), config_from_env(env)

    # The server starts in the directory holding .env, as the launch scripts do.
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RELAY_ENV_FILE", raising=False)
    grants, cfg = launch()
    assert grants.allow_write is True
    m.configure(grants)
    cfg.handle = m.handle
    monkeypatch.setattr(m, "run_agent", real_run_agent)
    monkeypatch.setattr(m, "available_backends",
                        lambda *, model="": [_EnvWriter("RELAY_REMOTE_TOKEN=t\n" + _ESCALATE)])
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "local_agent_run",
                                  "arguments": {"goal": "x", "backend": "stub", "max_steps": 3,
                                                "allow_write": True}}})
    status, _, _ = process(cfg, "POST", {"authorization": "Bearer t"}, body.encode())
    assert status == 200
    # First layer: the run's file tools refuse the env file (see mcp_paths).
    assert env_file.read_text(encoding="utf-8") == "RELAY_REMOTE_TOKEN=t\n"

    # Second layer: had the lines landed some other way, a restart ignores them.
    env_file.write_text("RELAY_REMOTE_TOKEN=t\n" + _ESCALATE, encoding="utf-8")
    after, cfg_after = launch()
    assert after == grants
    assert after.allow_exec is False and after.root == str(tmp_path)
    assert cfg_after.allow_remote_exec is False


# --- (3) inline comments and the shipped template ---

def test_an_inline_comment_is_not_part_of_a_value(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text('A=false   # note\nB="x # kept"\nC=  # blank\nD=p#q\n'
                        "E='y' # c\nF=\n", encoding="utf-8")
    assert load_dotenv(str(env_file)) == {"A": "false", "B": "x # kept", "C": "",
                                          "D": "p#q", "E": "y", "F": ""}


def test_the_shipped_env_example_loads():
    env, _ = resolved_env(env={}, env_file=str(_EXAMPLE))
    assert env["RELAY_REMOTE_TOKEN"] == ""
    assert config_from_env(env) is None  # a blank token keeps the surface off
    assert "error" not in remote_state(env={}, env_file=str(_EXAMPLE))["start_grants"]
    assert remote_cli.listen_port(env) == 8787
    assert env["RELAY_REMOTE_HOST"] == "127.0.0.1"
    cfg = config_from_env({**env, "RELAY_REMOTE_TOKEN": "t"})
    assert cfg.allow_remote_exec is False and cfg.allowed_origins == frozenset()
    assert remote_cli.listen_port({}) == 8787


def test_the_shipped_env_example_sets_no_ignored_key():
    # The template must not suggest a line the server then ignores.
    assert remote_state(env={}, env_file=str(_EXAMPLE))["env_file_ignored"] == []


# --- (4) the remote surface configures what it will actually allow ---

class _Server:
    def serve_forever(self):
        raise KeyboardInterrupt

    def shutdown(self):
        pass


def _serve_remote(tmp_path, monkeypatch, **process_env):
    (tmp_path / ".env").write_text("RELAY_REMOTE_TOKEN=t\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RELAY_ENV_FILE", raising=False)
    for key, value in process_env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(remote_cli, "serve", lambda *a, **k: _Server())
    monkeypatch.setattr(m, "_GRANTS", StartGrants())
    return remote_cli.main()


def test_exec_alone_grants_the_remote_surface_nothing(tmp_path, monkeypatch, capsys):
    # RELAY_ALLOW_EXEC without RELAY_ALLOW_REMOTE_EXEC: no exec, and no write
    # either, since write came only from exec implying it.
    assert _serve_remote(tmp_path, monkeypatch, RELAY_ALLOW_EXEC="1") == 0
    assert (m._GRANTS.allow_write, m._GRANTS.allow_exec) == (False, False)
    banner = capsys.readouterr().out
    assert "write off, exec off" in banner and "remote exec off" in banner
    state = remote_state()
    assert state["start_grants"]["allow_write"] is False
    assert state["start_grants"]["allow_exec"] is False
    assert state["remote_exec_in_effect"] is False


def test_write_needs_its_own_grant_on_the_remote_surface(tmp_path, monkeypatch):
    assert _serve_remote(tmp_path, monkeypatch, RELAY_ALLOW_WRITE="1",
                         RELAY_ALLOW_EXEC="1") == 0
    assert (m._GRANTS.allow_write, m._GRANTS.allow_exec) == (True, False)


def test_remote_exec_needs_both_and_parses_like_the_other_flags(tmp_path, monkeypatch, capsys):
    assert _serve_remote(tmp_path, monkeypatch, RELAY_ALLOW_EXEC="1",
                         RELAY_ALLOW_REMOTE_EXEC="on") == 0
    assert (m._GRANTS.allow_write, m._GRANTS.allow_exec) == (True, True)
    assert "remote exec on" in capsys.readouterr().out
    state = remote_state()
    assert state["remote_exec_allowed"] is True and state["remote_exec_in_effect"] is True
    assert state["start_grants"]["allow_exec"] is True


def test_remote_exec_alone_is_not_in_effect(monkeypatch):
    state = remote_state(env={"RELAY_REMOTE_TOKEN": "t", "RELAY_ALLOW_REMOTE_EXEC": "1"},
                         env_file="missing.env")
    assert state["remote_exec_allowed"] is True
    assert state["remote_exec_in_effect"] is False


def test_an_unrecognized_remote_exec_value_stops_the_launch(tmp_path, monkeypatch, capsys):
    assert _serve_remote(tmp_path, monkeypatch, RELAY_ALLOW_REMOTE_EXEC="sure") == 2
    assert "RELAY_ALLOW_REMOTE_EXEC" in capsys.readouterr().out
    assert m._GRANTS == StartGrants()
    state = remote_state(env={"RELAY_REMOTE_TOKEN": "t", "RELAY_ALLOW_REMOTE_EXEC": "sure"},
                         env_file="missing.env")
    assert "RELAY_ALLOW_REMOTE_EXEC" in state["remote_exec_allowed"]["error"]
