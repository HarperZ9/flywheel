"""Typed failure_labels across the whole family: the spine demand, completed.

The rl-scaling note demands typed failure codes for the whole receipt spine and
the audit confirmed only agent_action carried them. Every wedge now accepts an
optional failure_labels list validated against the shared _failure.FAILURE_CODES
vocabulary; an unknown code is rejected everywhere.
"""

from __future__ import annotations

from proof_surface.ai4science import build_ai4science_packet, validate_ai4science_packet
from proof_surface.conservation import (
    build_conservation_packet,
    validate_conservation_packet,
)
from proof_surface.eval_attempt import (
    build_eval_attempt_packet,
    validate_eval_attempt_packet,
)
from proof_surface.model_eval import build_model_eval_packet, validate_model_eval_packet
from proof_surface.optimization_workflow import (
    build_optimization_workflow_packet,
    validate_optimization_workflow_packet,
)
from proof_surface.research_claim import (
    build_research_claim_packet,
    validate_research_claim_packet,
)
from proof_surface.rollout_receipt import (
    build_rollout_receipt_packet,
    validate_rollout_receipt_packet,
)
from proof_surface.visual_measurement import (
    build_visual_measurement_packet,
    validate_visual_measurement_packet,
)

_HEX = "a" * 64
_LABELS = ["evidence_gap", "stale_criterion"]


def _wedges():
    return [
        (
            "visual",
            validate_visual_measurement_packet,
            lambda **kw: build_visual_measurement_packet(
                artifact={"name": "s.png", "sha256": _HEX, "kind": "image"},
                color={"color_space": "sRGB", "transfer": "sRGB"},
                metrics=[
                    {
                        "metric": "dE",
                        "value": 1.0,
                        "target": 0.0,
                        "tolerance": 2.0,
                        "unit": "dE",
                        "method": "m",
                    }
                ],
                claim="c",
                scope="s",
                packet_id="vm",
                **kw,
            ),
        ),
        (
            "research",
            validate_research_claim_packet,
            lambda **kw: build_research_claim_packet(
                statement="st",
                sources=[{"ref": "src"}],
                attempts=[{"attempt_id": "a1", "method": "m", "result": "bounded"}],
                checks=[{"checker": "c1", "status": "pass", "evidence": ["ok"]}],
                claim="c",
                scope="s",
                packet_id="rc",
                **kw,
            ),
        ),
        (
            "model-eval",
            validate_model_eval_packet,
            lambda **kw: build_model_eval_packet(
                model={"id": "m", "provider": "hosted"},
                eval_set={"name": "b", "ref": "r"},
                objective={"name": "o", "summary": "s"},
                metrics=[
                    {
                        "metric": "acc",
                        "value": 0.95,
                        "target": 0.9,
                        "direction": "maximize",
                        "tolerance": 0.01,
                        "method": "m",
                        "evidence": [_HEX],
                    }
                ],
                claim="c",
                scope="s",
                packet_id="me",
                **kw,
            ),
        ),
        (
            "optimization",
            validate_optimization_workflow_packet,
            lambda **kw: build_optimization_workflow_packet(
                sources=[{"ref": "r", "sha256": _HEX}],
                problem={"sense": "maximize", "objective": "v", "constraints": []},
                baseline={
                    "method": "exact",
                    "objective_value": 1,
                    "feasible": True,
                    "candidate_digest": _HEX,
                },
                candidate_space={
                    "variables": 1,
                    "evaluated": 2,
                    "feasible": 1,
                    "infeasible": 1,
                },
                solver={
                    "branch_id": "b",
                    "method": "exact",
                    "status": "COMPLETED",
                    "objective_value": 1,
                    "constraint_status": "satisfied",
                    "tolerance": 0.5,
                },
                claim="c",
                scope="s",
                packet_id="opt",
                **kw,
            ),
        ),
        (
            "rollout",
            validate_rollout_receipt_packet,
            lambda **kw: build_rollout_receipt_packet(
                sources=[{"ref": "r", "sha256": _HEX}],
                rollout={
                    "rollout_id": "r1",
                    "policy_ref": "p",
                    "checkpoint_ref": "ck",
                    "verifier_ref": "v",
                    "reward_digest": _HEX,
                },
                reward={"score": 0.5},
                verifier={"verdict": "MATCH", "evidence": ["e"]},
                admission={"decision": "allow", "reasons": []},
                claim="c",
                scope="s",
                packet_id="ro",
                **kw,
            ),
        ),
        (
            "eval-attempt",
            validate_eval_attempt_packet,
            lambda **kw: build_eval_attempt_packet(
                sources=[{"ref": "r", "sha256": _HEX}],
                benchmark={
                    "benchmark_ref": "b",
                    "task_id": "t",
                    "authority_receipt": "auth",
                },
                attempt={"attempt_id": "a", "prompt_ref": "p", "model_ref": "m"},
                result={"outcome": "correct", "score": 1.0},
                boundaries={
                    "had_ground_truth": False,
                    "had_internet": False,
                    "had_tools": False,
                },
                claim="c",
                scope="s",
                packet_id="ea",
                **kw,
            ),
        ),
        (
            "ai4science",
            validate_ai4science_packet,
            lambda **kw: build_ai4science_packet(
                sources=[{"ref": "r", "sha256": _HEX}],
                domain="biology",
                scientific_claim="sc",
                agent_actions=[{"action": "a"}],
                protocol={"protocol_ref": "p", "reproducible": True},
                measurement={"measured": True, "measurement_ref": "m1"},
                reproduction={"status": "INDEPENDENTLY_REPRODUCED"},
                reviewer_objections=[],
                negative_result=False,
                claim="c",
                scope="s",
                packet_id="a4s",
                **kw,
            ),
        ),
        (
            "conservation",
            validate_conservation_packet,
            lambda **kw: build_conservation_packet(
                sources=[{"ref": "r", "sha256": _HEX}],
                transformation={"description": "d", "domain": "chem"},
                invariant={"name": "mass", "declared": "sum"},
                witnesses=[
                    {"kind": "numeric", "drift": 0.0, "tolerance": 1e-9, "method": "m"}
                ],
                negative_fixture={
                    "description": "leak",
                    "drift": 0.5,
                    "tolerance": 0.01,
                    "breaks_invariant": True,
                },
                claim="c",
                scope="s",
                packet_id="cons",
                **kw,
            ),
        ),
    ]


def test_every_wedge_accepts_typed_failure_labels():
    for name, validate, build in _wedges():
        packet = build(failure_labels=_LABELS)
        assert packet["failure_labels"] == _LABELS, name
        assert validate(packet) == [], name


def test_every_wedge_omits_failure_labels_by_default():
    for name, validate, build in _wedges():
        packet = build()
        assert "failure_labels" not in packet, name
        assert validate(packet) == [], name


def test_every_wedge_rejects_an_unknown_failure_code():
    for name, validate, build in _wedges():
        packet = build(failure_labels=["kinda_broke"])
        assert any("failure_labels" in i.path for i in validate(packet)), name
