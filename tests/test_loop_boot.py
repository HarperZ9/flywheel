"""run_loop boot stage falsifier (harness/loop.py with harness/boot.py).

run_loop builds a boot packet itself when a caller passes boot_root and no
packet, and the runner in harness/cli.py reaches that branch through
`--boot ROOT`. The branch once called a name the module never bound, so every
boot_root call raised NameError before the proposer ran. These tests pin the
wiring: the boot stage leads the chain, its receipt lands in the envelope, a
MATCH packet hydrates the prompt the proposer sees, and boot_budget and the
task id reach boot() as its budget and focus.

The index lane is stubbed out so the tests do not spawn an MCP server. They
do not prove the context envelope the lane would add, only the loop wiring.
"""
from pathlib import Path

import pytest

import harness.boot as boot_mod
from harness.loop import run_loop
from harness.oracle import StubOracle
from harness.proposer import StubProposer
from harness.task import load_task

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"


class RecordingProposer(StubProposer):
    """StubProposer that keeps every prompt it was asked to answer."""

    def __init__(self, canned: str):
        super().__init__(canned)
        self.prompts: list[str] = []

    def generate(self, prompt, **kw):
        self.prompts.append(prompt)
        return super().generate(prompt, **kw)


@pytest.fixture(autouse=True)
def lane_calls(monkeypatch):
    """Stub the index lane and record the (budget, focus) boot() hands it."""
    calls: list[tuple[int, str]] = []

    def fake(root, budget, focus):
        calls.append((budget, focus))
        return None

    monkeypatch.setattr(boot_mod, "_safe_context_envelope", fake)
    return calls


def _workspace(root: Path, marker: str = "1") -> Path:
    (root / "harness").mkdir(parents=True)
    (root / "harness" / "mod.py").write_text(f"X = {marker}\n")
    (root / "STATE.md").write_text("# STATE\n\n## Phase: boot test\n")
    return root


def _run(tmp_path, **kw):
    task = load_task(TASK_DIR, workdir=tmp_path / "w")
    proposer = RecordingProposer(CORRECT)
    result = run_loop(task, proposer, StubOracle(passed=True),
                      envelopes_dir=tmp_path / "env", witness_recheck=False,
                      **kw)
    return task, proposer, result


def test_boot_root_adds_boot_stage_and_hydrates_prompt(tmp_path, lane_calls):
    ws = _workspace(tmp_path / "ws")
    expected = boot_mod.boot(ws, budget=1500, focus="example_pass")
    lane_calls.clear()
    task, proposer, r = _run(tmp_path, boot_root=ws)
    assert lane_calls == [(1500, task.task_id)]
    first = r.envelope.chain[0]
    assert first["stage"] == "boot"
    assert first["verdict"] == "MATCH"
    assert first["outputs_hash"] == expected.root_hash
    assert r.envelope.injected_context["root_hash"] == expected.root_hash
    (prompt,) = proposer.prompts
    assert prompt.startswith("[ground]")
    assert f"root_hash={expected.root_hash}" in prompt
    assert prompt.endswith(task.prompt)
    assert r.accepted


def test_missing_boot_root_is_unverifiable_and_leaves_prompt(tmp_path):
    task, proposer, r = _run(tmp_path, boot_root=tmp_path / "absent")
    first = r.envelope.chain[0]
    assert first["stage"] == "boot"
    assert first["verdict"] == "UNVERIFIABLE"
    assert r.envelope.injected_context["failure_code"] == "missing_root"
    assert proposer.prompts == [task.prompt]


def test_boot_budget_and_focus_reach_boot(tmp_path, lane_calls):
    # No packet boot() builds fits in 10 tokens, so the boot stage must come
    # back DRIFT and the prompt must stay unhydrated. A call that drops or
    # hard-codes the budget, or drops focus, fails here.
    ws = _workspace(tmp_path / "ws")
    task, proposer, r = _run(tmp_path, boot_root=ws, boot_budget=10)
    assert lane_calls == [(10, task.task_id)]
    assert r.envelope.chain[0]["verdict"] == "DRIFT"
    assert r.envelope.injected_context["failure_code"] == "budget_exceeded"
    assert proposer.prompts == [task.prompt]


def test_explicit_boot_packet_takes_precedence_over_boot_root(tmp_path):
    given = boot_mod.boot(_workspace(tmp_path / "a", "1"), budget=1500)
    other = boot_mod.boot(_workspace(tmp_path / "b", "2"), budget=1500)
    assert given.root_hash != other.root_hash
    _, _, r = _run(tmp_path, boot_packet=given, boot_root=tmp_path / "b")
    assert r.envelope.chain[0]["outputs_hash"] == given.root_hash
