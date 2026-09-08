"""Cache hits supply candidates, never final acceptance decisions."""
from dataclasses import replace
from pathlib import Path

import pytest

from harness.cache import ReceiptCache
from harness.loop import run_loop
from harness.oracle import PytestOracle
from harness.output_contract import TABLE, new_contract
from harness.policy import Decision, default_harness_gate
from harness.proposer import ProposerOutput, prompt_hash
from harness.task import Retrieved, load_task
from harness.transitive_witness import UNVERIFIABLE

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"
WRONG = "def add(a, b):\n    return a * b\n"


class CountingProposer:
    def __init__(self, text, model_ref="counting-stub"):
        self.text = text
        self.model_ref = model_ref
        self.calls = 0

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        self.calls += 1
        return ProposerOutput(text=self.text, model_ref=self.model_ref,
                              seed=seed, prompt_hash=prompt_hash(prompt),
                              cache="live")


@pytest.fixture
def task(tmp_path):
    return load_task(TASK_DIR, workdir=tmp_path / "w")


def test_default_cache_hit_still_runs_current_policy(task, tmp_path):
    cache = ReceiptCache(tmp_path / "cache")
    run_loop(task, CountingProposer(CORRECT), PytestOracle(),
             envelopes_dir=tmp_path / "env", cache=cache)

    blocked = default_harness_gate(allowed_roots=[str(tmp_path / "other-root")])
    result = run_loop(task, CountingProposer(WRONG), PytestOracle(),
                      envelopes_dir=tmp_path / "env", cache=cache,
                      policy=blocked)

    assert result.cache_hit is True
    assert result.accepted is False
    assert result.oracle is None
    assert result.policy.decision == Decision.BLOCK
    assert result.policy.reason_code == "workdir_outside_allowed_roots"


def test_default_cache_hit_still_runs_output_contract(task, tmp_path):
    cache = ReceiptCache(tmp_path / "cache")
    contract = new_contract([
        {"name": "total", "authority": TABLE, "source": "ledger"}
    ])
    authorities = {"ledger": lambda answer: 2}
    extract = lambda _: {"total": {"value": 1, "source": "ledger"}}

    first = run_loop(task, CountingProposer(CORRECT), PytestOracle(),
                     envelopes_dir=tmp_path / "env", cache=cache,
                     output_contract=contract, output_authorities=authorities,
                     output_extract=extract)
    assert first.accepted is False
    assert first.output["release"] == "HOLD"

    result = run_loop(task, CountingProposer(WRONG), PytestOracle(),
                      envelopes_dir=tmp_path / "env", cache=cache,
                      output_contract=contract,
                      output_authorities=authorities,
                      output_extract=extract)

    assert result.cache_hit is True
    assert result.accepted is False
    assert result.oracle is not None
    assert result.output["release"] == "HOLD"


def test_default_cache_hit_still_runs_grounding_recheck(task, tmp_path):
    citing = replace(task, retrieved=[
        Retrieved(source="missing-ancestor", receipt="envelope")
    ])
    cache = ReceiptCache(tmp_path / "cache")
    run_loop(citing, CountingProposer(CORRECT), PytestOracle(),
             envelopes_dir=tmp_path / "env", cache=cache)

    result = run_loop(citing, CountingProposer(WRONG), PytestOracle(),
                      envelopes_dir=tmp_path / "env", cache=cache,
                      grounding_recheck=True)

    assert result.cache_hit is True
    assert result.accepted is False
    assert result.grounding["verdict"] == UNVERIFIABLE
    assert result.grounding["verdicts"]["missing-ancestor"] == UNVERIFIABLE


def test_proof_addressed_hit_misses_when_retrieved_knowledge_changes(task, tmp_path):
    cache = ReceiptCache(tmp_path / "cache")
    with_a = replace(task, retrieved=[Retrieved(source="src", receipt="v1")])
    run_loop(with_a, CountingProposer(CORRECT), PytestOracle(),
             envelopes_dir=tmp_path / "env", cache=cache,
             proof_addressed=True)

    p2 = CountingProposer(CORRECT)
    with_b = replace(task, retrieved=[Retrieved(source="src", receipt="v2")])
    result = run_loop(with_b, p2, PytestOracle(),
                      envelopes_dir=tmp_path / "env", cache=cache,
                      proof_addressed=True)

    assert result.cache_hit is False
    assert p2.calls == 1


def test_oracle_environment_change_misses_instead_of_serving_stale_pass(
        task, tmp_path, monkeypatch):
    test_file = Path(task.workdir) / "tests" / "test_solution.py"
    test_file.write_text(
        "import os\n"
        "from solution import add\n"
        "def test_add():\n"
        "    assert add(1, 2) == 3\n"
        "def test_timezone():\n"
        "    assert os.environ.get('TZ') == 'UTC'\n",
        encoding="utf-8")
    cache = ReceiptCache(tmp_path / "cache")

    monkeypatch.setenv("TZ", "UTC")
    first = run_loop(task, CountingProposer(CORRECT), PytestOracle(),
                     envelopes_dir=tmp_path / "env", cache=cache)
    assert first.accepted is True

    monkeypatch.setenv("TZ", "US/Pacific")
    p2 = CountingProposer(CORRECT)
    result = run_loop(task, p2, PytestOracle(),
                      envelopes_dir=tmp_path / "env", cache=cache)

    assert result.cache_hit is False
    assert p2.calls == 1
    assert result.accepted is False
    assert result.oracle.rc != 0


def test_header_shaped_task_content_does_not_collapse_prompt_key(task, tmp_path):
    cache = ReceiptCache(tmp_path / "cache")
    task.prompt = "X-Request-Id: implement add(a,b)"
    run_loop(task, CountingProposer(CORRECT), PytestOracle(),
             envelopes_dir=tmp_path / "env", cache=cache)

    task.prompt = "X-Request-Id: implement multiply(a,b)"
    p2 = CountingProposer(WRONG)
    result = run_loop(task, p2, PytestOracle(),
                      envelopes_dir=tmp_path / "env", cache=cache)

    assert result.cache_hit is False
    assert p2.calls == 1
    assert result.accepted is False
    assert result.envelope.candidate == WRONG
