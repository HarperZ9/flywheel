"""Competition-attempt builder: the verdict is derived, never asserted.

MATCH only from an EXECUTED, passing judge-verdict layer; a passing verdict
with zero EXECUTED layers is impossible by construction.
"""

from __future__ import annotations

from proof_surface.competition_attempt import (
    build_competition_attempt_packet,
    to_crucible_inputs,
    validate_competition_attempt_packet,
)

_HEX64 = "a" * 64
_HEX40 = "b" * 40

_CHALLENGE = {
    "challenge_ref": "challenge:sair-2026",
    "stage": "stage-1",
    "judge_repo": {
        "repo_ref": "github:example/judge",
        "head_sha": _HEX40,
        "observed_files": 12,
        "files_digest": _HEX64,
    },
}
_ATTEMPT = {"attempt_id": "att-1", "model_ref": "model:m-1"}
_EXTRACTION = {
    "method": "boxed",
    "extracted_ref": "answers/final.txt",
    "injection_checked": True,
}


def _build(layers):
    return build_competition_attempt_packet(
        sources=[{"ref": "run:comp-1", "sha256": _HEX64}],
        challenge=_CHALLENGE,
        attempt=_ATTEMPT,
        answer_extraction=_EXTRACTION,
        certificate_layers=layers,
        claim="c",
        scope="s",
        packet_id="comp-1",
    )


def _judge(status="EXECUTED", **extra):
    layer = {"layer": "judge-verdict", "status": status, "evidence_ref": "judge:r"}
    layer.update(extra)
    return layer


def _informal():
    return {
        "layer": "informal-model-output",
        "status": "EXECUTED",
        "evidence_ref": "transcript:att-1",
    }


def test_executed_passing_judge_is_match():
    packet = _build([_informal(), _judge(passing=True)])
    assert packet["verdicts"]["overall"] == "MATCH"
    assert packet["verdicts"]["cited_layers"] == [
        "informal-model-output",
        "judge-verdict",
    ]
    assert packet["decision_summary"]["decision"] == "approve"
    assert validate_competition_attempt_packet(packet) == []


def test_executed_failing_judge_is_drift():
    packet = _build([_informal(), _judge(passing=False)])
    assert packet["verdicts"]["overall"] == "DRIFT"
    assert packet["decision_summary"]["decision"] == "block"
    assert validate_competition_attempt_packet(packet) == []


def test_fenced_judge_is_unverifiable():
    packet = _build(
        [
            _informal(),
            {
                "layer": "judge-verdict",
                "status": "UNAVAILABLE_FENCED",
                "probe_evidence": "probe:judge-endpoint-unreachable exit=7",
            },
        ]
    )
    assert packet["verdicts"]["overall"] == "UNVERIFIABLE"
    assert packet["verdicts"]["cited_layers"] == ["informal-model-output"]
    assert validate_competition_attempt_packet(packet) == []


def test_missing_judge_layer_is_unverifiable():
    packet = _build([_informal()])
    assert packet["verdicts"]["overall"] == "UNVERIFIABLE"


def test_zero_executed_layers_never_match():
    # 0139: every layer fenced (the Stage-2 rung) -- MATCH is impossible by
    # construction because the judge-verdict layer did not execute.
    packet = _build(
        [
            {
                "layer": "judge-verdict",
                "status": "UNAVAILABLE_FENCED",
                "probe_evidence": "probe:stage-2-rung-fenced exit=127",
            },
            {
                "layer": "machine-checked-proof",
                "status": "UNAVAILABLE_FENCED",
                "probe_evidence": "probe:lean-toolchain-missing exit=127",
            },
        ]
    )
    assert packet["verdicts"]["overall"] == "UNVERIFIABLE"
    assert packet["verdicts"]["cited_layers"] == []
    assert validate_competition_attempt_packet(packet) == []


def test_cited_layers_only_ever_name_executed_layers():
    packet = _build([_informal(), _judge(passing=True)])
    executed = {
        layer["layer"]
        for layer in packet["certificate_layers"]
        if layer["status"] == "EXECUTED"
    }
    assert set(packet["verdicts"]["cited_layers"]) <= executed


def test_to_crucible_inputs_round_trip_shape():
    packet = _build([_informal(), _judge(passing=True)])
    thesis, measurements = to_crucible_inputs(packet)
    assert thesis["claims"], "expected at least one crucible claim"
    rows = measurements["measurements"]
    assert rows and rows[0]["claim"] == thesis["claims"][0]["text"]
    assert rows[0]["deviation"] == 0.0
