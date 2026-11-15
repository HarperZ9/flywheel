"""Every domain report carries the non-promotion / uniqueness boundary."""

from __future__ import annotations

from proof_surface import agent_action, model_eval, research_claim, visual_measurement
from proof_surface.agent_action import attach_verdicts, build_agent_action_packet

_HEX = "a" * 64
_HEX2 = "c" * 64


def _agent_report():
    trace = {
        "trace_id": "t1",
        "service": "d",
        "spans": [
            {
                "span_id": "s2",
                "parent_span_id": None,
                "name": "w",
                "kind": "client",
                "start_unix_ns": 0,
                "end_unix_ns": 1,
                "status": {"code": "ok", "message": ""},
                "attributes": {
                    "actor.id": "u",
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
        "principal": {"id": "u"},
        "agent": {"id": "a"},
        "intent": "w",
        "scope": {
            "allowed_actions": ["fs.write"],
            "allowed_targets": ["/work/config.json"],
        },
        "granted_at": "2020-01-01T00:00:00+00:00",
        "expires_at": "2999-01-01T00:00:00+00:00",
        "revoked": False,
    }
    packet = attach_verdicts(
        build_agent_action_packet(trace, auth, claim="c", scope="s", packet_id="pkt-1")
    )
    return agent_action.render_report(packet)


def _visual_report():
    p = visual_measurement.build_visual_measurement_packet(
        artifact={"name": "s.png", "sha256": _HEX, "kind": "image"},
        color={"color_space": "sRGB", "transfer": "sRGB", "white_point": "D65"},
        metrics=[
            {
                "metric": "d",
                "value": 1.0,
                "target": 0.0,
                "tolerance": 2.0,
                "unit": "dE",
                "method": "m",
                "evidence": [_HEX],
            }
        ],
        claim="c",
        scope="s",
        packet_id="vm",
    )
    return visual_measurement.render_report(p)


def _research_report():
    p = research_claim.build_research_claim_packet(
        statement="x",
        sources=[{"ref": "s"}],
        attempts=[{"attempt_id": "a1", "method": "m", "result": "bounded"}],
        checks=[{"checker": "c", "status": "pass", "evidence": ["ok"]}],
        claim="c",
        scope="s",
        packet_id="rc",
    )
    return research_claim.render_report(p)


def _model_report():
    p = model_eval.build_model_eval_packet(
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
    )
    return model_eval.render_report(p)


def test_every_report_carries_the_non_promotion_boundary():
    for report in (
        _agent_report(),
        _visual_report(),
        _research_report(),
        _model_report(),
    ):
        assert "## Boundary" in report
        assert "Promoted natural laws: none." in report
        assert "HYPOTHESIS_ONLY" in report
