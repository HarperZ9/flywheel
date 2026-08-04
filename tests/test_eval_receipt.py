"""Tests for the sealed eval-run receipt (build + verify + emit).

Socketless and model-free: the receipt is a pure data structure, so these
exercise the seal discipline directly. The falsifier has teeth -- a tampered
result, a tampered dataset digest, and a count-contract violation must each be
refused, and the body must never carry a float or an absolute path.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from harness.eval_receipt import (
    MATCH,
    SCHEMA,
    TAMPERED,
    UNVERIFIABLE,
    build_eval_receipt,
    emit_eval_receipt,
    verify_eval_receipt,
)
from harness.tool_call_receipt import _seal_receipt


def _sample(**overrides) -> dict:
    tasks = [
        {"task_id": "add_two", "oracle_cmd": "pytest", "prompt": "add"},
        {"task_id": "max_of_three", "oracle_cmd": "pytest", "prompt": "max"},
    ]
    results = [
        {"task_id": "add_two", "verdict": "PASS", "accepted": True},
        {"task_id": "max_of_three", "verdict": "UNVERIFIABLE", "accepted": False},
    ]
    kw = dict(
        run_id="eval-stub-abc",
        endpoint="stub",
        model_ref="stub:model",
        tasks=tasks,
        config={"n": 2, "domain": "code", "selection": "first-n"},
        judge="code oracle (pytest, offline)",
        results=results,
        started_utc="2026-01-01T00:00:00+00:00",
        finished_utc="2026-01-01T00:00:01+00:00",
    )
    kw.update(overrides)
    return build_eval_receipt(**kw)


def _walk(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)
    else:
        yield obj


def test_build_produces_sealed_object():
    r = _sample()
    assert r["schema"] == SCHEMA
    assert r["seal"]["algorithm"] == "sha256"
    assert len(r["seal"]["hex"]) == 64
    # the task list is a digest + a count, never the tasks themselves
    assert set(r["dataset"].keys()) == {"sha256", "n"}
    assert r["dataset"]["n"] == "2"          # string, not int
    assert r["n_results"] == "2"


def test_seal_round_trips_to_match():
    v = verify_eval_receipt(_sample())
    assert v["verdict"] == MATCH
    assert v["failure_class"] == ""


def test_seal_is_deterministic():
    assert _sample()["seal"]["hex"] == _sample()["seal"]["hex"]


def test_tampered_result_verdict_is_refused():
    r = _sample()
    r["results"][0]["verdict"] = "FAIL"      # flip an outcome
    v = verify_eval_receipt(r)
    assert v["verdict"] == TAMPERED
    assert v["failure_class"] == "SEAL_MISMATCH"


def test_tampered_dataset_sha_is_refused():
    r = _sample()
    r["dataset"]["sha256"] = "0" * 64        # well-formed hex, but not the sealed one
    v = verify_eval_receipt(r)
    assert v["verdict"] == TAMPERED
    assert v["failure_class"] == "SEAL_MISMATCH"


def test_one_flipped_hex_char_of_seal_is_refused():
    r = _sample()
    hx = list(r["seal"]["hex"])
    hx[0] = "0" if hx[0] != "0" else "1"     # a single corrupted byte
    r["seal"]["hex"] = "".join(hx)
    v = verify_eval_receipt(r)
    assert v["verdict"] == TAMPERED
    assert v["failure_class"] == "SEAL_MISMATCH"


def test_wrong_schema_is_unverifiable():
    r = _sample()
    r["schema"] = "flywheel.not-an-eval/v1"
    v = verify_eval_receipt(r)
    assert v["verdict"] == UNVERIFIABLE
    assert v["failure_class"] == "MALFORMED"


def test_count_contract_violation_is_caught():
    # add a result so len(results) != dataset n, then RE-SEAL so the seal check
    # passes and the field-contract check is the one that must catch it.
    r = _sample()
    r["results"].append({"task_id": "extra", "verdict": "PASS", "accepted": "true"})
    _seal_receipt(r)
    v = verify_eval_receipt(r)
    assert v["verdict"] == UNVERIFIABLE
    assert v["failure_class"] == "FIELD_CONTRACT_VIOLATION"
    assert "result count" in v["detail"]


def test_malformed_seal_hex_is_unverifiable():
    r = _sample()
    r["seal"]["hex"] = "short"
    v = verify_eval_receipt(r)
    assert v["verdict"] == UNVERIFIABLE
    assert v["failure_class"] == "DIGEST_MALFORMED"


def test_non_dict_is_unverifiable():
    v = verify_eval_receipt(None)
    assert v["verdict"] == UNVERIFIABLE
    assert v["failure_class"] == "MALFORMED"


def test_receipt_body_carries_no_float():
    r = _sample(config={"n": 2, "temperature": 0.0, "top_p": 1.0})
    for leaf in _walk(r):
        assert not isinstance(leaf, float), f"a float leaked into the receipt: {leaf!r}"


def test_receipt_body_carries_no_absolute_path():
    r = _sample()
    abspath = re.compile(r"^[A-Za-z]:[\\/]")
    for leaf in _walk(r):
        if isinstance(leaf, str):
            assert not abspath.match(leaf), f"a drive-letter path leaked: {leaf!r}"
            assert not leaf.startswith("/"), f"a posix abs path leaked: {leaf!r}"
            assert "\\" not in leaf, f"a windows path separator leaked: {leaf!r}"


def test_bools_are_serialized_as_strings():
    r = _sample()
    assert r["results"][0]["accepted"] == "true"
    assert r["results"][1]["accepted"] == "false"


def test_prev_link_is_carried_and_well_formed_checked():
    first = _sample(run_id="eval-1")
    from harness.tool_call_receipt import _canonical_bytes, _sha256_hex
    probe = dict(first)
    probe["seal"] = {"algorithm": "sha256", "hex": ""}
    prev = _sha256_hex(_canonical_bytes(probe))
    second = _sample(run_id="eval-2", prev_receipt_sha256=prev)
    assert second["prev_receipt_sha256"] == prev
    assert verify_eval_receipt(second)["verdict"] == MATCH
    # a malformed prev link is refused even with a valid seal
    bad = _sample(run_id="eval-3", prev_receipt_sha256="not-a-hash")
    _seal_receipt(bad)
    v = verify_eval_receipt(bad)
    assert v["verdict"] == UNVERIFIABLE
    assert v["failure_class"] == "DIGEST_MALFORMED"


def test_emit_writes_a_file_and_reloads_to_match(tmp_path: Path):
    r = _sample()
    path = emit_eval_receipt(r, tmp_path / "eval")
    assert path is not None and path.exists()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert verify_eval_receipt(loaded)["verdict"] == MATCH


def test_emit_swallows_a_bad_dir(tmp_path: Path):
    r = _sample()
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("a file where the receipts dir wants a parent")
    assert emit_eval_receipt(r, blocker / "sub") is None
