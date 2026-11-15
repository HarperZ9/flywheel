"""Competition-attempt packet validator: the certificate ladder cannot inflate.

Harvest of the SAIR competition dogfood cluster (0136 pattern, 0137 hermetic
fixture, 0138 source-pinned judge-repo adapter, 0139 fenced Stage-2 rung).
Every gate ships a negative fixture that MUST reject.
"""

from __future__ import annotations

import copy

from proof_surface.competition_attempt import (
    PACKET_VERSION,
    validate_competition_attempt_packet,
)

_HEX64 = "a" * 64
_HEX40 = "b" * 40


def _valid_packet() -> dict:
    return {
        "version": PACKET_VERSION,
        "packet_id": "comp-1",
        "claim": "the stage-1 attempt passed the pinned judge",
        "scope": "one challenge, one judge revision",
        "sources": [{"ref": "run:comp-1", "sha256": _HEX64}],
        "challenge": {
            "challenge_ref": "challenge:sair-2026",
            "stage": "stage-1",
            "judge_repo": {
                "repo_ref": "github:example/judge",
                "head_sha": _HEX40,
                "observed_files": 12,
                "files_digest": _HEX64,
            },
        },
        "attempt": {
            "attempt_id": "att-1",
            "model_ref": "model:m-1",
            "external_model_calls": 0,
        },
        "answer_extraction": {
            "method": "boxed",
            "extracted_ref": "answers/final.txt",
            "injection_checked": True,
        },
        "certificate_layers": [
            {
                "layer": "informal-model-output",
                "status": "EXECUTED",
                "evidence_ref": "transcript:att-1",
            },
            {
                "layer": "machine-checked-proof",
                "status": "UNAVAILABLE_FENCED",
                "probe_evidence": "probe:lean-toolchain-missing exit=127",
            },
            {
                "layer": "judge-verdict",
                "status": "EXECUTED",
                "evidence_ref": "judge:run-9",
                "passing": True,
            },
        ],
        "verdicts": {
            "overall": "MATCH",
            "cited_layers": ["informal-model-output", "judge-verdict"],
        },
        "uncertainty": ["single judge revision observed"],
        "decision_summary": {
            "decision": "approve",
            "reason": "the evidence matched every checked claim within tolerance",
            "confidence": "high",
            "missing_evidence": [],
            "next_action": "proceed",
        },
    }


def _mutate(packet: dict, fn) -> dict:
    clone = copy.deepcopy(packet)
    fn(clone)
    return clone


def test_valid_packet_validates_clean():
    assert validate_competition_attempt_packet(_valid_packet()) == []


def test_forged_head_sha_shape_is_rejected():
    for forged in ("deadbeef", "B" * 40, "g" * 40, _HEX64, 42, None):
        bad = _mutate(
            _valid_packet(),
            lambda p, f=forged: p["challenge"]["judge_repo"].update({"head_sha": f}),
        )
        issues = validate_competition_attempt_packet(bad)
        assert any("head_sha" in issue.path for issue in issues), forged


def test_judge_repo_observation_fields_are_gated():
    zero_files = _mutate(
        _valid_packet(),
        lambda p: p["challenge"]["judge_repo"].update({"observed_files": 0}),
    )
    assert any(
        "observed_files" in issue.path
        for issue in validate_competition_attempt_packet(zero_files)
    )
    bad_digest = _mutate(
        _valid_packet(),
        lambda p: p["challenge"]["judge_repo"].update({"files_digest": "nope"}),
    )
    assert any(
        "files_digest" in issue.path
        for issue in validate_competition_attempt_packet(bad_digest)
    )


def test_fenced_layer_without_probe_evidence_is_rejected():
    bad = _mutate(
        _valid_packet(),
        lambda p: p["certificate_layers"][1].pop("probe_evidence", None),
    )
    assert any(
        "probe_evidence" in issue.path
        for issue in validate_competition_attempt_packet(bad)
    )


def test_fenced_layer_may_not_carry_a_passing_result():
    bad = _mutate(
        _valid_packet(),
        lambda p: p["certificate_layers"][1].update({"passing": True}),
    )
    assert any(
        "passing" in issue.path for issue in validate_competition_attempt_packet(bad)
    )


def test_tier_inflation_is_rejected():
    # The verdict cites machine-checked-proof while only weaker layers executed.
    bad = _mutate(
        _valid_packet(),
        lambda p: p["verdicts"]["cited_layers"].append("machine-checked-proof"),
    )
    issues = validate_competition_attempt_packet(bad)
    assert any("cited_layers" in issue.path for issue in issues)


def test_injection_unchecked_on_non_boxed_extraction_is_rejected():
    bad = _mutate(
        _valid_packet(),
        lambda p: p["answer_extraction"].update(
            {"method": "bare-last-line", "injection_checked": False}
        ),
    )
    assert any(
        "injection_checked" in issue.path
        for issue in validate_competition_attempt_packet(bad)
    )


def test_boxed_extraction_may_leave_injection_unchecked():
    ok = _mutate(
        _valid_packet(),
        lambda p: p["answer_extraction"].update({"injection_checked": False}),
    )
    assert validate_competition_attempt_packet(ok) == []


def test_unrendered_template_marker_is_rejected():
    for marker in ("answers/{{answer}}.txt", "prompt }} tail"):
        bad = _mutate(
            _valid_packet(),
            lambda p, m=marker: p["answer_extraction"].update({"extracted_ref": m}),
        )
        assert any(
            "extracted_ref" in issue.path
            for issue in validate_competition_attempt_packet(bad)
        ), marker


def test_hermetic_contradiction_is_rejected():
    # 0 hosted calls AND a provider receipt is a contradiction (0137 precedent).
    bad = _mutate(
        _valid_packet(),
        lambda p: p["attempt"].update({"provider_receipt_ref": "receipt:prov-1"}),
    )
    assert any(
        "external_model_calls" in issue.path
        for issue in validate_competition_attempt_packet(bad)
    )


def test_nonzero_calls_without_receipt_are_rejected():
    bad = _mutate(
        _valid_packet(),
        lambda p: p["attempt"].update({"external_model_calls": 3}),
    )
    assert any(
        "provider_receipt_ref" in issue.path
        for issue in validate_competition_attempt_packet(bad)
    )


def test_receipt_without_disclosed_count_is_rejected():
    bad = _mutate(
        _valid_packet(),
        lambda p: (
            p["attempt"].pop("external_model_calls", None),
            p["attempt"].update({"provider_receipt_ref": "receipt:prov-1"}),
        ),
    )
    assert any(
        "external_model_calls" in issue.path
        for issue in validate_competition_attempt_packet(bad)
    )


def test_undisclosed_attempt_stays_valid():
    ok = _mutate(
        _valid_packet(),
        lambda p: p["attempt"].pop("external_model_calls", None),
    )
    assert validate_competition_attempt_packet(ok) == []


def test_duplicate_certificate_layer_is_rejected():
    bad = _mutate(
        _valid_packet(),
        lambda p: p["certificate_layers"].append(dict(p["certificate_layers"][-1])),
    )
    assert any(
        "layer" in issue.path for issue in validate_competition_attempt_packet(bad)
    )


def test_unknown_layer_status_and_method_are_rejected():
    for fn, needle in (
        (lambda p: p["certificate_layers"][0].update({"layer": "vibes"}), "layer"),
        (lambda p: p["certificate_layers"][0].update({"status": "SKIPPED"}), "status"),
        (
            lambda p: p["answer_extraction"].update({"method": "regex-anywhere"}),
            "method",
        ),
    ):
        issues = validate_competition_attempt_packet(_mutate(_valid_packet(), fn))
        assert any(needle in issue.path for issue in issues), needle


def test_empty_certificate_ladder_is_rejected():
    bad = _mutate(
        _valid_packet(),
        lambda p: (
            p.update({"certificate_layers": []}),
            p["verdicts"].update({"overall": "UNVERIFIABLE", "cited_layers": []}),
        ),
    )
    assert any(
        "certificate_layers" in issue.path
        for issue in validate_competition_attempt_packet(bad)
    )


def test_forged_match_with_zero_executed_layers_is_rejected():
    # A passing judge verdict with zero EXECUTED layers must not validate.
    def fence_everything(p):
        for layer in p["certificate_layers"]:
            layer["status"] = "UNAVAILABLE_FENCED"
            layer["probe_evidence"] = "probe:stage-2-rung-fenced exit=127"
            layer.pop("passing", None)
        p["verdicts"]["cited_layers"] = []

    bad = _mutate(_valid_packet(), fence_everything)
    assert any(
        "overall" in issue.path for issue in validate_competition_attempt_packet(bad)
    )
