"""Falsifiers for the harness-config hash: flip each setting once (x-likes item 5, part A).

Bar, written before the code: every flip that changes what the model is sent
or what the loop allows changes the hash (no misses); a flip outside the
covered list (the user's own words) leaves it equal (no false changes).
"""
import json
import sys

import pytest

from harness.code_session import config_hash
from harness.code_session.backends import build_agent
from harness.code_session.hooks import HookEntry, Hooks
from harness.code_session.print_mode import result_object
from harness.code_session.rules import Rules
from harness.code_session.session import new_session
from tests.test_code_session import _bare_runner

WRITE = 'TOOL write_file {"path": "a.txt", "content": "hi"}'
BLOCK = f'"{sys.executable}" -c "import sys; sys.exit(2)"'


class Recording:
    name = "script"

    def __init__(self, model="script-1"):
        self.model, self.requests, self.replies = model, [], [WRITE, "done", "done", "done"]

    def health(self):
        return True

    def chat(self, messages, *, system, max_tokens, temperature, seed):
        self.requests.append(json.dumps([messages, system, max_tokens, temperature, seed],
                                        sort_keys=True, default=str))
        return {"text": self.replies.pop(0), "model_ref": f"script:{self.model}", "seed": seed}


def _run(tmp_path, flip=None, prompt="write a.txt", model="script-1"):
    root = tmp_path / "w"
    root.mkdir(parents=True)
    backend = Recording(model)
    s = new_session(build_agent([backend]), str(root), mode="auto", runner=_bare_runner)
    if flip:
        flip(s)
    result = s.turn(prompt)
    observed = {"requests": backend.requests, "wrote": (root / "a.txt").exists(),
                "steps": result.steps, "tests_pass": result.tests_pass}
    return s, result, observed


def _hooks(s):
    s.set_hooks(Hooks(entries=[HookEntry("PreToolUse", "write_file", BLOCK, "test")], cwd=s.root))


FLIPS = {
    "mode": lambda s: s.set_mode("plan"),
    "rules": lambda s: s.set_rules(Rules(deny=["write_file:*"])),
    "hooks": _hooks,
    "max_steps": lambda s: setattr(s, "max_steps", 1),
    "compact_budget": lambda s: setattr(s, "compact_budget", 5),
    "max_tokens": lambda s: setattr(s.agent, "max_tokens", 99),
    "temperature": lambda s: setattr(s.agent, "temperature", 0.7),
    "seed": lambda s: setattr(s.agent, "seed", 7),
    "prefer": lambda s: setattr(s.agent, "prefer", "script"),
    "system": lambda s: setattr(s.agent, "system", s.agent.system + "\nBe brief."),
    "test_cmd": lambda s: setattr(s, "test_cmd", f'"{sys.executable}" -c "pass"'),
}


@pytest.mark.parametrize("field", sorted(FLIPS))
def test_each_covered_flip_changes_the_hash(tmp_path, field):
    base, _r, seen = _run(tmp_path / "base")
    flipped, _r2, seen2 = _run(tmp_path / "flip", FLIPS[field])
    assert base.config_sha256 and flipped.config_sha256
    assert flipped.config_sha256 != base.config_sha256, field
    assert seen2 != seen or field in ("prefer", "compact_budget"), field


def test_the_answering_model_is_in_the_hash(tmp_path):
    a, _r, _s = _run(tmp_path / "a")
    b, _r2, _s2 = _run(tmp_path / "b", model="script-2")
    assert a.config_sha256 != b.config_sha256


def test_the_version_is_in_the_hash(tmp_path, monkeypatch):
    a, _r, _s = _run(tmp_path / "a")
    monkeypatch.setattr(config_hash, "_version", lambda: "9.9.9")
    b, _r2, _s2 = _run(tmp_path / "b")
    assert a.config_sha256 != b.config_sha256


def test_the_users_words_do_not_change_the_hash(tmp_path):
    a, _r, seen = _run(tmp_path / "a", prompt="write a.txt")
    b, _r2, seen2 = _run(tmp_path / "b", prompt="please write a.txt now")
    assert seen != seen2 and a.config_sha256 == b.config_sha256


def test_the_hash_is_on_the_ledger_once_and_in_the_result(tmp_path):
    s, result, _ = _run(tmp_path)
    s.backend = s.agent.backends[0]
    s.agent.backends[0].replies = ["again"]
    s.turn("and again")
    entries = [e for e in s.ledger.entries if e.kind == "harness_config"]
    assert len(entries) == 1 and entries[0].meta["sha256"] == s.config_sha256
    config = json.loads(entries[0].content)
    assert config["schema"] == config_hash.SCHEMA and config["answered"] == [["script", "script-1"]]
    assert result_object(s, result)["harness_config_sha256"] == s.config_sha256
    assert s.ledger.verify()


def test_a_mid_session_mode_change_records_a_new_config(tmp_path):
    s, _r, _ = _run(tmp_path)
    first = s.config_sha256
    s.agent.backends[0].replies = ["fine"]
    s.set_mode("plan")
    s.turn("look only")
    assert s.config_sha256 != first
    assert [e.kind for e in s.ledger.entries].count("harness_config") == 2
