"""Negative-fixture conformance gate: verification is not theater.

For every domain, a valid packet plus a catalog of mutations that MUST each be
rejected. The load-bearing assertion is negative_pass_observed_count == 0: no
broken packet may validate clean.
"""

from __future__ import annotations

import copy

from proof_surface.agent_action import (
    attach_verdicts,
    build_agent_action_packet,
    validate_agent_action_packet,
)
from proof_surface.model_eval import build_model_eval_packet, validate_model_eval_packet
from proof_surface.research_claim import (
    build_research_claim_packet,
    validate_research_claim_packet,
)
from proof_surface.visual_measurement import (
    build_visual_measurement_packet,
    validate_visual_measurement_packet,
)

_HEX = "a" * 64
_HEX2 = "c" * 64


def _mut(fn):
    def wrapped(packet):
        clone = copy.deepcopy(packet)
        fn(clone)
        return clone

    return wrapped


# Mutations that must break any packet in the family.
_CROSS = {
    "drop-version": _mut(lambda p: p.pop("version", None)),
    "unknown-root-field": _mut(lambda p: p.update({"surprise": 1})),
    "forbidden-field": _mut(lambda p: p.update({"prefire": {}})),
    "authority-language": _mut(
        lambda p: p.update({"claim": "This result is CERTIFIED."})
    ),
    "drop-decision-summary": _mut(lambda p: p.pop("decision_summary", None)),
    "corrupt-decision-outcome": _mut(
        lambda p: p["decision_summary"].update({"decision": "yolo"})
    ),
}


def _agent_valid():
    trace = {
        "trace_id": "trace-1",
        "service": "demo",
        "spans": [
            {
                "span_id": "span-s2",
                "parent_span_id": None,
                "name": "write",
                "kind": "client",
                "start_unix_ns": 0,
                "end_unix_ns": 1,
                "status": {"code": "ok", "message": ""},
                "attributes": {
                    "actor.id": "user:zain",
                    "tool.name": "fs",
                    "action.kind": "fs.write",
                    "action.target": "/work/config.json",
                    "side_effect.class": "write",
                    "content.sha256": _HEX,
                    "after.sha256": _HEX2,
                },
                "events": [],
            }
        ],
    }
    auth = {
        "authorization_version": "0.1",
        "receipt_id": "auth-1",
        "kind": "authorization-grant",
        "principal": {"id": "user:zain"},
        "agent": {"id": "agent:claude"},
        "intent": "write",
        "scope": {
            "allowed_actions": ["fs.write"],
            "allowed_targets": ["/work/config.json"],
        },
        "granted_at": "2020-01-01T00:00:00+00:00",
        "expires_at": "2999-01-01T00:00:00+00:00",
        "revoked": False,
    }
    return attach_verdicts(
        build_agent_action_packet(trace, auth, claim="c", scope="s", packet_id="pkt-1")
    )


_AGENT_MUTATIONS = {
    "identity-substitution": _mut(
        lambda p: p.update({"packet_id": p["actions"][0]["action_id"]})
    ),
    "empty-admission": _mut(lambda p: p.update({"admission": []})),
    "corrupt-span-digest": _mut(
        lambda p: p["actions"][0].update({"span_digest": "nope"})
    ),
}


def _visual_valid():
    return build_visual_measurement_packet(
        artifact={"name": "s.png", "sha256": _HEX, "kind": "image"},
        color={"color_space": "sRGB", "transfer": "sRGB", "white_point": "D65"},
        metrics=[
            {
                "metric": "delta_e",
                "value": 1.0,
                "target": 0.0,
                "tolerance": 2.0,
                "unit": "dE",
                "method": "build-color",
                "evidence": [_HEX],
            }
        ],
        claim="c",
        scope="s",
        packet_id="vm",
    )


_VISUAL_MUTATIONS = {
    "not-read-only": _mut(lambda p: p.update({"read_only": False})),
    "zero-tolerance": _mut(lambda p: p["measurements"][0].update({"tolerance": 0})),
    "bad-artifact-digest": _mut(lambda p: p["artifact"].update({"sha256": "nope"})),
}


def _research_valid():
    return build_research_claim_packet(
        statement="an identity",
        sources=[{"ref": "src"}],
        attempts=[{"attempt_id": "a1", "method": "probe", "result": "bounded"}],
        checks=[{"checker": "probe", "status": "pass", "evidence": ["ok"]}],
        claim="c",
        scope="s",
        packet_id="rc",
    )


_RESEARCH_MUTATIONS = {
    "promoted-law": _mut(lambda p: p.update({"promotion": "PROMOTED_LAW"})),
    "source-without-ref": _mut(lambda p: p.update({"sources": [{"url": "https://x"}]})),
    "bad-check-status": _mut(lambda p: p["checks"][0].update({"status": "definitely"})),
    "fenced-branch-claims-verdict": _mut(
        lambda p: p.update(
            {
                "declared_branches": [
                    {
                        "branch_id": "lean-kernel",
                        "status": "UNAVAILABLE_FENCED",
                        "verdict": "MATCH",
                        "probe_evidence": "lake build failed: toolchain missing",
                    }
                ]
            }
        )
    ),
    "promotion-cites-fenced-branch": _mut(
        lambda p: p.update(
            {
                "declared_branches": [
                    {
                        "branch_id": "lean-kernel",
                        "status": "UNAVAILABLE_FENCED",
                        "probe_evidence": "lake build failed: toolchain missing",
                    }
                ],
                "claim": "the lean-kernel branch confirmed the identity",
            }
        )
    ),
    "tier-inflated-promotion": _mut(
        # Base packet derives CRUCIBLE_MATCH; only a numeric probe ran.
        lambda p: p.update(
            {
                "witness_tier": {
                    "declared_target_verifier": "kernel-proof",
                    "strongest_executed_tier": "numeric-probe",
                    "target_slot_status": "NOT_EXECUTED_FENCED",
                }
            }
        )
    ),
    "single-modality-fact-promotion": _mut(
        lambda p: p.update({"evidence_classes": ["single-modality-derived"]})
    ),
}


def _model_valid():
    return build_model_eval_packet(
        model={"id": "m", "provider": "hosted"},
        eval_set={"name": "b", "ref": "r"},
        objective={"name": "o", "summary": "s"},
        metrics=[
            {
                "metric": "accuracy",
                "value": 0.95,
                "target": 0.9,
                "direction": "maximize",
                "tolerance": 0.01,
                "method": "exact-match",
                "evidence": [_HEX],
            }
        ],
        claim="c",
        scope="s",
        packet_id="me",
    )


_MODEL_MUTATIONS = {
    "promote-without-match": _mut(
        lambda p: (p["verdicts"].update({"overall": "DRIFT"}), None)[1]
    ),
    "bad-provider": _mut(lambda p: p["model"].update({"provider": "magic"})),
    "bad-direction": _mut(lambda p: p["metrics"][0].update({"direction": "sideways"})),
}


_DOMAINS = [
    (
        "agent-action",
        validate_agent_action_packet,
        _agent_valid(),
        {**_CROSS, **_AGENT_MUTATIONS},
    ),
    (
        "visual",
        validate_visual_measurement_packet,
        _visual_valid(),
        {**_CROSS, **_VISUAL_MUTATIONS},
    ),
    (
        "research",
        validate_research_claim_packet,
        _research_valid(),
        {**_CROSS, **_RESEARCH_MUTATIONS},
    ),
    (
        "model-eval",
        validate_model_eval_packet,
        _model_valid(),
        {**_CROSS, **_MODEL_MUTATIONS},
    ),
]


def test_every_valid_packet_validates_clean():
    for name, validate, valid, _muts in _DOMAINS:
        assert validate(valid) == [], name


def test_no_negative_fixture_validates_clean():
    negative_pass_observed: list[str] = []
    total = 0
    for name, validate, valid, muts in _DOMAINS:
        for mname, mutate in muts.items():
            total += 1
            if validate(mutate(valid)) == []:
                negative_pass_observed.append(f"{name}:{mname}")
    assert total >= 24  # the corpus is not empty
    assert negative_pass_observed == [], (
        f"negative_pass_observed_count={len(negative_pass_observed)}: {negative_pass_observed}"
    )
