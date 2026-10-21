"""Runtime identity in the receipt: the serving stack, GPU, compile mode and capture hooks.

Bar, written before the code (research item 1, 2026-10-21):
- flip each of the 10 runtime fields once: the harness-config hash and the
  eval-receipt seal both change, 10 of 10;
- a missing field reads "unknown", never a guessed default;
- the rerun witness returns DRIFT on an output mismatch only when both runs
  declared deterministic and batch-invariant with every runtime field equal and
  known; any other mismatch is UNVERIFIABLE and names the fields;
- false-success control: a witness that always says DRIFT on a mismatch would
  report DRIFT on the compile-mode case, and this one does not.
"""
from __future__ import annotations

import pytest

from harness import runtime_identity as rt
from harness.code_session import config_hash
from harness.eval_receipt import MATCH, build_eval_receipt, verify_eval_receipt

FULL = {"serving_framework": "vllm", "serving_version": "0.11.2", "gpu_model": "L40S",
        "dtype": "bf16", "compile_mode": "eager", "batch_shape": "1",
        "batch_invariant": True, "deterministic": True, "capture_hooks": [],
        "kernel_stack": "torch 2.10.0+cu128"}
FLIPPED = {"serving_framework": "sglang", "serving_version": "0.11.3", "gpu_model": "H100",
           "dtype": "fp16", "compile_mode": "torch.compile", "batch_shape": "64",
           "batch_invariant": False, "deterministic": False,
           "capture_hooks": ["layer14.q_norm"], "kernel_stack": "torch 2.9.1+cu126"}


def test_ten_fields_and_unknown_default():
    assert len(rt.FIELDS) == 10 and set(rt.FIELDS) == set(FULL)
    blank = rt.runtime_identity(None)
    assert all(blank[f] == rt.UNKNOWN for f in rt.FIELDS)
    partial = rt.runtime_identity({"gpu_model": "L40S"})
    assert partial["gpu_model"] == "L40S" and partial["dtype"] == rt.UNKNOWN


def test_normalized_values_are_strings_only():
    ident = rt.runtime_identity(FULL)
    assert all(isinstance(v, str) for v in ident.values())
    assert ident["batch_invariant"] == "true" and ident["capture_hooks"] == "none"
    hooks = rt.runtime_identity({"capture_hooks": ["b", "a", "a"]})["capture_hooks"]
    assert hooks == "a,b"


def test_unknown_fields_are_refused():
    with pytest.raises(ValueError):
        rt.runtime_identity({"gpu": "L40S"})


class _Agent:
    system, max_tokens, temperature, seed, prefer, backends = "s", 100, 0.0, 1, None, []


class _Ex:
    mode, rules = "auto", None


class _Ledger:
    entries: list = []


class _Session:
    def __init__(self, runtime=None):
        self.agent, self.executor, self.ledger = _Agent(), _Ex(), _Ledger()
        self.max_steps, self.compact_budget, self.test_cmd = 5, 100, None
        self.runtime = runtime


def _config_sha(runtime):
    return config_hash.config_sha256(config_hash.harness_config(_Session(runtime)))


def _receipt(runtime):
    return build_eval_receipt(
        run_id="r", endpoint="e", model_ref="m", tasks=[{"task_id": "t"}], config={},
        judge="j", results=[{"task_id": "t", "verdict": "PASS", "accepted": True}],
        started_utc="s", finished_utc="f", runtime=runtime)


@pytest.mark.parametrize("field", sorted(FULL))
def test_each_field_changes_config_hash_and_receipt_seal(field):
    flipped = dict(FULL, **{field: FLIPPED[field]})
    assert _config_sha(flipped) != _config_sha(FULL), field
    assert _receipt(flipped)["seal"]["hex"] != _receipt(FULL)["seal"]["hex"], field


def test_runtime_is_in_the_config_and_the_receipt():
    assert config_hash.harness_config(_Session(FULL))["runtime"] == rt.runtime_identity(FULL)
    r = _receipt(FULL)
    assert r["runtime"] == rt.runtime_identity(FULL)
    assert verify_eval_receipt(r)["verdict"] == MATCH
    assert verify_eval_receipt(r)["runtime_known"] == "10/10"
    assert verify_eval_receipt(_receipt(None))["runtime_known"] == "0/10"


def test_a_malformed_runtime_block_is_refused():
    r = _receipt(FULL)
    r["runtime"]["gpu_model"] = 4
    from harness.tool_call_receipt import _seal_receipt
    r["seal"] = {"algorithm": "sha256", "hex": ""}
    _seal_receipt(r)
    assert verify_eval_receipt(r)["failure_class"] == "FIELD_CONTRACT_VIOLATION"


def _run(runtime, out):
    return {"runtime": rt.runtime_identity(runtime), "output_sha256": out}


def test_witness_match_when_outputs_agree():
    w = rt.rerun_witness(_run(FULL, "a"), _run(dict(FULL, gpu_model="H100"), "a"))
    assert w["verdict"] == rt.MATCH


def test_witness_drift_only_with_deterministic_matching_runtimes():
    w = rt.rerun_witness(_run(FULL, "a"), _run(FULL, "b"))
    assert w["verdict"] == rt.DRIFT and w["code"] == "output_differs"


@pytest.mark.parametrize("field", sorted(FULL))
def test_witness_unverifiable_when_any_field_differs(field):
    w = rt.rerun_witness(_run(FULL, "a"), _run(dict(FULL, **{field: FLIPPED[field]}), "b"))
    assert w["verdict"] == rt.UNVERIFIABLE
    assert field in w["fields"]


def test_witness_unverifiable_when_runtime_unknown_or_nondeterministic():
    w = rt.rerun_witness(_run(None, "a"), _run(None, "b"))
    assert w["verdict"] == rt.UNVERIFIABLE and w["code"] == "runtime_unknown"
    nd = dict(FULL, deterministic=False)
    w = rt.rerun_witness(_run(nd, "a"), _run(nd, "b"))
    assert w["verdict"] == rt.UNVERIFIABLE and w["code"] == "not_deterministic"


def test_witness_on_two_eval_receipts():
    a = _receipt(FULL)
    b = build_eval_receipt(
        run_id="r2", endpoint="e", model_ref="m", tasks=[{"task_id": "t"}], config={},
        judge="j", results=[{"task_id": "t", "verdict": "FAIL", "accepted": False}],
        started_utc="s", finished_utc="f", runtime=dict(FULL, compile_mode="torch.compile"))
    w = rt.rerun_witness_receipts(a, b)
    assert w["verdict"] == rt.UNVERIFIABLE and w["fields"] == ["compile_mode"]
    assert rt.rerun_witness_receipts(a, _receipt(FULL))["verdict"] == rt.MATCH


def test_false_success_control_naive_witness_would_say_drift():
    a, b = _run(FULL, "a"), _run(dict(FULL, compile_mode="torch.compile"), "b")
    naive = rt.DRIFT if a["output_sha256"] != b["output_sha256"] else rt.MATCH
    assert naive == rt.DRIFT and rt.rerun_witness(a, b)["verdict"] != rt.DRIFT
