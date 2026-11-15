"""Falsifiers for the server's own files inside a run's root.

Load-bearing: (1) an MCP run's file tools neither read nor write the env file
the remote entrypoint reads (RELAY_ENV_FILE or .env), which holds the bearer
token and OAuth secrets; (2) they do not write into the run store
(RELAY_RUN_ROOT), the session store (RELAY_SESSION_DIR) or any ``.git``
directory, where a hook or a config line runs code the next time git runs;
(3) every write tool is covered, edit_plan's per-op files included, and a link
does not step around the check; (4) on Windows a name ending in a dot or a
space, or naming a stream, is refused, because it opens another spelling of the
same file; (5) the MCP server wires this in and records it in the binding,
while ordinary files in the same run are still written.
"""
import json
import os

import pytest

import relay.local_mcp as m
from relay.local_session import SessionLedger
from relay.local_tools import ToolGate
from relay.mcp_grants import StartGrants
from relay.mcp_paths import GuardedExecutor, protected_paths, refusal


@pytest.fixture
def tree(tmp_path):
    (tmp_path / ".env").write_text("RELAY_REMOTE_TOKEN=secret-token\n", encoding="utf-8")
    (tmp_path / "runs").mkdir()
    (tmp_path / "sessions").mkdir()
    (tmp_path / ".git" / "hooks").mkdir(parents=True)
    (tmp_path / "src").mkdir()
    return tmp_path


def _env(tree, **extra):
    return {"RELAY_ENV_FILE": str(tree / ".env"), "RELAY_RUN_ROOT": str(tree / "runs"),
            "RELAY_SESSION_DIR": str(tree / "sessions"), **extra}


def _ex(tree, env=None):
    return GuardedExecutor(root=str(tree), gate=ToolGate(allow_write=True),
                           protected=protected_paths(env if env is not None else _env(tree)))


# --- (1) the env file ---

def test_the_env_file_is_neither_read_nor_written(tree):
    ex = _ex(tree)
    read = ex.execute("read_file", {"path": ".env"})
    assert read.ok is False and "secret-token" not in read.output
    wrote = ex.execute("write_file", {"path": ".env", "content": "RELAY_ALLOW_EXEC=1\n"})
    assert wrote.ok is False and wrote.output.startswith("[gate]")
    assert (tree / ".env").read_text(encoding="utf-8") == "RELAY_REMOTE_TOKEN=secret-token\n"


def test_the_default_env_file_is_the_working_directory_one(tree, monkeypatch):
    monkeypatch.chdir(tree)
    ex = _ex(tree, env={})
    assert ex.execute("read_file", {"path": ".env"}).ok is False
    assert ex.execute("write_file", {"path": ".env", "content": "x"}).ok is False
    assert ex.execute("write_file", {"path": "ok.txt", "content": "x"}).ok is True


# --- (2) stores and .git ---

@pytest.mark.parametrize("target", ["runs/r1.json", "sessions/s.jsonl", ".git/hooks/pre-commit",
                                    ".git/config", "src/.git/config", "runs"])
def test_server_stores_and_git_are_not_written(tree, target):
    res = _ex(tree).execute("write_file", {"path": target, "content": "#!/bin/sh\nid\n"})
    assert res.ok is False and res.output.startswith("[gate]"), res.output


def test_ordinary_files_are_still_written(tree):
    ex = _ex(tree)
    assert ex.execute("write_file", {"path": "src/a.py", "content": "x = 1\n"}).ok is True
    assert ex.execute("write_file", {"path": ".gitignore", "content": ".env\n"}).ok is True
    assert ex.execute("read_file", {"path": "src/a.py"}).output == "x = 1\n"


def test_unset_stores_protect_nothing_extra(tree):
    ex = _ex(tree, env={"RELAY_ENV_FILE": str(tree / ".env")})
    assert ex.execute("write_file", {"path": "runs/r1.json", "content": "{}"}).ok is True
    assert ex.execute("write_file", {"path": "sessions/s", "content": "{}"}).ok is True


# --- (3) every write tool, and links ---

@pytest.mark.parametrize("name,args", [
    ("edit_file", {"path": ".env", "old": "secret-token", "new": "x"}),
    ("edit_lines", {"path": ".env", "start": 1, "end": 1, "new": "x"}),
    ("apply_diff", {"path": ".env", "diff": "@@ -1 +1 @@\n-a\n+b\n"}),
    ("edit_plan", {"ops": [{"path": "src/a.py", "old": "", "new": "x"},
                           {"path": ".git/hooks/post-checkout", "old": "", "new": "id"}]}),
])
def test_every_write_tool_is_covered(tree, name, args):
    res = _ex(tree).execute(name, args)
    assert res.ok is False and res.output.startswith("[gate]"), res.output
    assert "secret-token" in (tree / ".env").read_text(encoding="utf-8")


def test_a_link_to_a_protected_path_is_refused(tree):
    try:
        os.symlink(tree / ".env", tree / "notes.txt")
        os.symlink(tree / ".git", tree / "meta", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this platform or account cannot create a link")
    ex = _ex(tree)
    assert ex.execute("read_file", {"path": "notes.txt"}).ok is False
    assert ex.execute("write_file", {"path": "notes.txt", "content": "x"}).ok is False
    assert ex.execute("write_file", {"path": "meta/hooks/pre-push", "content": "x"}).ok is False


# --- (4) Windows alternate spellings ---

@pytest.mark.parametrize("path", [".env.", ".env ", ".env::$DATA", "src/a.py:stream",
                                  "src./a.py"])
def test_windows_alternate_spellings_are_refused(tree, path):
    prot = protected_paths(_env(tree))
    assert refusal(str(tree), prot, "write_file", {"path": path}, windows=True)
    assert refusal(str(tree), prot, "write_file", {"path": "src/a.py"}, windows=True) is None


# --- (5) wired into the MCP server ---

class _Scripted:
    name = "stub"

    def __init__(self, calls):
        self.replies = [f"TOOL {n} {json.dumps(a)}" for n, a in calls] + ["done"]

    def health(self):
        return True

    def chat(self, messages, *, system, max_tokens, temperature, seed):
        return {"text": self.replies.pop(0) if self.replies else "done",
                "model_ref": "stub:paths", "seed": seed}


def test_the_mcp_run_guards_the_env_file_and_records_it(tree, monkeypatch):
    from relay.local_loop import run_agent as real_run_agent

    ledgers = []

    class _Recorded(SessionLedger):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            ledgers.append(self)

    for key, value in _env(tree).items():
        monkeypatch.setenv(key, value)
    calls = [("read_file", {"path": ".env"}),
             ("write_file", {"path": ".env", "content": "RELAY_ALLOW_EXEC=1\n"}),
             ("write_file", {"path": "ok.txt", "content": "fine"})]
    monkeypatch.setattr(m, "run_agent", real_run_agent)
    monkeypatch.setattr(m, "SessionLedger", _Recorded)
    monkeypatch.setattr(m, "available_backends", lambda *, model="": [_Scripted(calls)])
    monkeypatch.setattr(m, "_GRANTS", StartGrants(allow_write=True, root=str(tree)))
    res = m.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": "local_agent_run",
                               "arguments": {"goal": "g", "backend": "stub", "max_steps": 5,
                                             "allow_write": True}}})
    body = json.loads(res["result"]["content"][0]["text"])
    text = " ".join(e.content for e in ledgers[0].entries)
    assert "secret-token" not in text
    assert (tree / ".env").read_text(encoding="utf-8") == "RELAY_REMOTE_TOKEN=secret-token\n"
    assert (tree / "ok.txt").read_text(encoding="utf-8") == "fine"
    protected = body["request_binding"]["protected"]
    assert os.path.normcase(os.path.realpath(tree / ".env")) in protected["no_read"]
    assert ".git" in protected["no_write_names"]
