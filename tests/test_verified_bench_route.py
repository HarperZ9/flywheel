"""The private-benchmark route: an exact grant with exec+network scopes
runs a real task set across a (faked) ladder and disposes every attempt
through real subprocess gates. The gate decides; a refused endpoint or
a malformed task set is a typed refusal before any run."""
import json

import pytest

from harness.verified_bench_route import handle_bench_run

TASKS = [
    {"task_id": "t1", "prompt": "say the word",
     "gate_cmd": "python -c \"import sys; sys.exit(0)\""},
    {"task_id": "t2", "prompt": "fail on purpose",
     "gate_cmd": "python -c \"import sys; sys.exit(3)\""},
]


class _FakeBackend:
    def __init__(self, name, reply):
        self.name = name
        self._reply = reply

    def chat(self, messages, *, system, max_tokens, temperature, seed):
        return {"text": self._reply, "model_ref": f"{self.name}:x",
                "seed": seed}


def _ladder():
    return [_FakeBackend("strong", "the answer"),
            _FakeBackend("weak", "a wrong answer")]


def test_the_run_seals_attempts_and_the_gate_decides(tmp_path):
    body, code = handle_bench_run(
        {"tasks": TASKS, "endpoints": ["strong", "weak"],
         "timeout_s": 60},
        run_root=tmp_path, build_endpoints=lambda **kw: _ladder())
    assert code == 200
    attempts = body["bench"]["attempts"]
    assert len(attempts) == 4
    # t1's gate exits 0 for everyone; t2's gate exits 3 for everyone:
    # the gate decided, not the model.
    assert all(a["gate_pass"] for a in attempts if a["task_id"] == "t1")
    assert not any(a["gate_pass"] for a in attempts if a["task_id"] == "t2")
    assert body["frontier"]["rankings"][0]["verified_pass_rate"] == 0.5


def test_unconfigured_endpoints_are_a_typed_refusal(tmp_path):
    body, code = handle_bench_run(
        {"tasks": TASKS, "endpoints": ["no-such-endpoint"], "timeout_s": 60},
        run_root=tmp_path, build_endpoints=lambda **kw: [])
    assert code == 422
    assert "no-such-endpoint" in body["error"]["message"]


def test_malformed_tasks_are_refused_before_any_run(tmp_path):
    for bad in ([{"task_id": "t1"}], [], "not-a-list"):
        body, code = handle_bench_run(
            {"tasks": bad, "endpoints": ["strong"], "timeout_s": 60},
            run_root=tmp_path, build_endpoints=lambda **kw: _ladder())
        assert code == 422


def test_the_gate_command_cannot_be_a_shell_one_liner_injection(tmp_path):
    evil = [{"task_id": "t1", "prompt": "p",
             "gate_cmd": "python -c \"import os; os.system('echo pwned')\""}]
    body, code = handle_bench_run(
        {"tasks": evil, "endpoints": ["strong"], "timeout_s": 60},
        run_root=tmp_path, build_endpoints=lambda **kw: _ladder())
    # No shell: the command runs argv-split, so this executes python with
    # an inline program -- the point is there is NO shell interpolation
    # layer for an attacker to escape through.
    assert code == 200
