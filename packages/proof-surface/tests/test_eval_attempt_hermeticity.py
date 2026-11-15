"""Eval-attempt hermeticity disclosure: hosted-model calls carry receipts.

Harvest of dogfood passes 0137/0138 (SAIR competition cluster): the executable
fixture records `external_model_calls: 0` and rejects an external-model claim
without a receipt; the judge-repo adapter keeps hosted calls fenced and counts
them. Portable rule: an attempt that DISCLOSES its hosted-model usage is
machine-checkable both ways -- a hermetic claim (0 calls) citing a provider
receipt is a contradiction, and a nonzero count without a receipt reference is
an external-model claim with no evidence.
"""

from __future__ import annotations

from proof_surface.eval_attempt import (
    build_eval_attempt_packet,
    validate_eval_attempt_packet,
)

_HEX = "a" * 64


def _packet(**attempt_extra):
    attempt = {
        "attempt_id": "a-1",
        "prompt_ref": "prompt:p-1",
        "model_ref": "model:m-1",
        "replay_ref": "replay:r-1",
    }
    attempt.update(attempt_extra)
    return build_eval_attempt_packet(
        sources=[{"ref": "run:e-1", "sha256": _HEX}],
        benchmark={
            "benchmark_ref": "bench:sair-stage1",
            "task_id": "t-7",
            "authority_receipt": "authority:judge-repo",
        },
        attempt=attempt,
        result={"outcome": "correct"},
        boundaries={
            "had_ground_truth": False,
            "had_internet": False,
            "had_tools": False,
        },
        claim="c",
        scope="s",
        packet_id="ea-herm",
    )


def test_hermetic_attempt_with_zero_calls_validates():
    packet = _packet(external_model_calls=0)
    assert packet["attempt"]["external_model_calls"] == 0
    assert validate_eval_attempt_packet(packet) == []


def test_disclosed_calls_with_receipt_validate():
    packet = _packet(
        external_model_calls=3,
        provider_receipt_ref="receipt:provider-batch-9 (redacted)",
    )
    assert validate_eval_attempt_packet(packet) == []


def test_undisclosed_attempt_stays_valid():
    # Absent disclosure is the legacy shape; the gate binds only when the
    # attempt speaks.
    packet = _packet()
    assert "external_model_calls" not in packet["attempt"]
    assert validate_eval_attempt_packet(packet) == []


def test_external_calls_without_receipt_are_rejected():
    # The 0137 fixture rule: an external-model claim without a receipt is an
    # assertion with no evidence surface.
    packet = _packet(external_model_calls=2)
    assert any(
        "provider_receipt_ref" in issue.path
        for issue in validate_eval_attempt_packet(packet)
    )


def test_hermetic_claim_citing_a_provider_receipt_is_rejected():
    # 0 hosted calls AND a provider receipt is a contradiction.
    packet = _packet(external_model_calls=0, provider_receipt_ref="receipt:provider-1")
    assert any(
        "external_model_calls" in issue.path
        for issue in validate_eval_attempt_packet(packet)
    )


def test_receipt_without_a_disclosed_count_is_rejected():
    # A provider receipt with no call count is undisclosed external usage.
    packet = _packet(provider_receipt_ref="receipt:provider-1")
    assert any(
        "external_model_calls" in issue.path
        for issue in validate_eval_attempt_packet(packet)
    )


def test_negative_or_boolean_counts_are_rejected():
    negative = _packet(external_model_calls=-1)
    assert any(
        "external_model_calls" in issue.path
        for issue in validate_eval_attempt_packet(negative)
    )
    boolean = _packet(external_model_calls=True)
    assert any(
        "external_model_calls" in issue.path
        for issue in validate_eval_attempt_packet(boolean)
    )
