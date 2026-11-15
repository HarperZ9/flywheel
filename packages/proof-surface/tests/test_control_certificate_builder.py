"""Control-certificate wedge (#10): a stability claim must carry a certificate
that can fail.

Harvest of dogfood passes 0112 (Lyapunov stability certificate) + 0113
(constrained-MPC feasibility) + 0132 (executed residuals with a reachable
DRIFT path), converged with the operator's robotics/cybernetics lane. A
controller or iterative process claiming stability/termination/convergence
carries a declared certificate, witnessed conditions with real residuals, a
REQUIRED negative fixture that must violate the certificate, and an explicit
sim-to-real boundary: hardware validity is never claimable from
simulation-only evidence.
"""

from __future__ import annotations

from proof_surface.control_certificate import (
    build_control_certificate_packet,
    validate_control_certificate_packet,
)

_HEX = "a" * 64


def _packet(**overrides):
    spec = {
        "sources": [{"ref": "dogfood:pass-0112", "sha256": _HEX}],
        "system": {
            "description": "inverted pendulum under LQR",
            "domain": "robotics",
            "regime": "simulation",
        },
        "certificate": {
            "kind": "lyapunov",
            "name": "V(x) = x^T P x",
            "declared": "quadratic Lyapunov candidate from the Riccati solution",
        },
        "witnesses": [
            {
                "condition": "positive-definite",
                "residual": 0.0,
                "tolerance": 1e-9,
                "method": "min eigenvalue of P",
            },
            {
                "condition": "decrease",
                "residual": 3e-7,
                "tolerance": 1e-6,
                "method": "max dV/dt over sampled states",
            },
        ],
        "negative_fixture": {
            "description": "unstable double integrator with the same candidate",
            "condition": "decrease",
            "residual": 0.82,
            "tolerance": 1e-6,
            "violates_certificate": True,
        },
        "sim_to_real": {"hardware_validity_claim": False, "hardware_evidence": []},
        "trajectory": {"log_sha256": _HEX, "samples": 500},
        "claim": "the closed loop is stable on the sampled region",
        "scope": "one linearized plant, sampled states",
        "packet_id": "ctrl-1",
    }
    spec.update(overrides)
    return build_control_certificate_packet(**spec)


def test_witnessed_certificate_with_violating_fixture_is_a_match():
    packet = _packet()
    assert validate_control_certificate_packet(packet) == []
    assert packet["verdicts"]["overall"] == "MATCH"


def test_a_failing_condition_is_a_drift():
    packet = _packet(
        witnesses=[
            {
                "condition": "positive-definite",
                "residual": 0.0,
                "tolerance": 1e-9,
                "method": "eig",
            },
            {
                "condition": "decrease",
                "residual": 0.4,
                "tolerance": 1e-6,
                "method": "dV/dt",
            },
        ]
    )
    assert packet["verdicts"]["overall"] == "DRIFT"
    assert validate_control_certificate_packet(packet) == []


def test_no_witnesses_is_unverifiable_and_rejected():
    packet = _packet(witnesses=[])
    assert packet["verdicts"]["overall"] == "UNVERIFIABLE"
    assert any(
        "witnesses" in i.path for i in validate_control_certificate_packet(packet)
    )


def test_kind_missing_a_required_condition_is_rejected():
    # A lyapunov claim without a witnessed decrease condition is an assertion,
    # not a certificate.
    packet = _packet(
        witnesses=[
            {
                "condition": "positive-definite",
                "residual": 0.0,
                "tolerance": 1e-9,
                "method": "eig",
            }
        ]
    )
    assert any(
        "witnesses" in i.path for i in validate_control_certificate_packet(packet)
    )


def test_mpc_feasibility_requires_its_own_conditions():
    packet = _packet(
        certificate={"kind": "mpc-feasibility", "name": "N-step OCP"},
        witnesses=[
            {
                "condition": "recursive-feasibility",
                "residual": 0.0,
                "tolerance": 1e-9,
                "method": "terminal set containment",
            },
            {
                "condition": "constraint-satisfaction",
                "residual": 0.0,
                "tolerance": 1e-9,
                "method": "state/input bounds over horizon",
            },
        ],
        negative_fixture={
            "description": "shrunk terminal set loses containment",
            "condition": "recursive-feasibility",
            "residual": 0.3,
            "tolerance": 1e-9,
            "violates_certificate": True,
        },
    )
    assert validate_control_certificate_packet(packet) == []
    assert packet["verdicts"]["overall"] == "MATCH"


def test_non_violating_negative_fixture_is_rejected():
    packet = _packet(
        negative_fixture={
            "description": "supposedly unstable",
            "condition": "decrease",
            "residual": 0.0,
            "tolerance": 1e-6,
            "violates_certificate": False,
        }
    )
    assert any(
        "negative_fixture" in i.path
        for i in validate_control_certificate_packet(packet)
    )


def test_fixture_claiming_violation_within_tolerance_is_rejected():
    packet = _packet(
        negative_fixture={
            "description": "claims violation",
            "condition": "decrease",
            "residual": 1e-9,
            "tolerance": 1e-6,
            "violates_certificate": True,
        }
    )
    assert any(
        "negative_fixture" in i.path
        for i in validate_control_certificate_packet(packet)
    )


def test_hardware_validity_claim_from_simulation_is_rejected():
    # The sim-to-real overclaim: verified in sim presented as valid on hardware.
    packet = _packet(
        sim_to_real={"hardware_validity_claim": True, "hardware_evidence": []}
    )
    assert any(
        "sim_to_real" in i.path for i in validate_control_certificate_packet(packet)
    )


def test_hardware_validity_needs_hardware_evidence_even_on_hardware():
    packet = _packet(
        system={
            "description": "cartpole rig",
            "domain": "robotics",
            "regime": "hardware",
        },
        sim_to_real={"hardware_validity_claim": True, "hardware_evidence": []},
    )
    assert any(
        "sim_to_real" in i.path for i in validate_control_certificate_packet(packet)
    )


def test_hardware_validity_with_evidence_on_hardware_is_admissible():
    packet = _packet(
        system={
            "description": "cartpole rig",
            "domain": "robotics",
            "regime": "hardware",
        },
        sim_to_real={
            "hardware_validity_claim": True,
            "hardware_evidence": ["rig-log:2026-07-01", f"sha256:{_HEX}"],
        },
    )
    assert validate_control_certificate_packet(packet) == []


def test_certificate_provenance_defaults_to_author_asserted():
    # Fail-closed: an undeclared provenance is the weakest tier, never an
    # upgrade. Synthesized / verified / author-asserted are never conflated.
    packet = _packet()
    assert packet["certificate"]["provenance"] == "author-asserted"
    assert validate_control_certificate_packet(packet) == []


def test_unknown_certificate_provenance_is_rejected():
    packet = _packet(
        certificate={
            "kind": "lyapunov",
            "name": "V(x) = x^T P x",
            "provenance": "blessed",
        }
    )
    assert any(
        "certificate.provenance" in i.path
        for i in validate_control_certificate_packet(packet)
    )


def test_verified_provenance_with_ref_is_admissible():
    packet = _packet(
        certificate={
            "kind": "lyapunov",
            "name": "V(x) = x^T P x",
            "provenance": "verified",
            "provenance_ref": "sos-checker run 2026-07-01",
        }
    )
    assert validate_control_certificate_packet(packet) == []


def test_missing_trajectory_binding_is_rejected():
    # The receipt binds the certificate check to the executed trajectory log;
    # without the binding there is nothing the verdict is a verdict OF.
    packet = _packet()
    del packet["trajectory"]
    assert any(
        "trajectory" in i.path for i in validate_control_certificate_packet(packet)
    )


def test_bad_trajectory_digest_is_rejected():
    packet = _packet(trajectory={"log_sha256": "not-a-digest", "samples": 500})
    assert any(
        "trajectory.log_sha256" in i.path
        for i in validate_control_certificate_packet(packet)
    )


def test_non_positive_trajectory_samples_are_rejected():
    packet = _packet(trajectory={"log_sha256": _HEX, "samples": 0})
    assert any(
        "trajectory.samples" in i.path
        for i in validate_control_certificate_packet(packet)
    )


def test_unknown_certificate_kind_is_rejected():
    packet = _packet(certificate={"kind": "vibes", "name": "V"})
    assert any(
        "certificate" in i.path for i in validate_control_certificate_packet(packet)
    )


def test_unknown_witness_condition_is_rejected():
    packet = _packet(
        witnesses=[
            {
                "condition": "looks-stable",
                "residual": 0.0,
                "tolerance": 1e-9,
                "method": "m",
            },
            {
                "condition": "positive-definite",
                "residual": 0.0,
                "tolerance": 1e-9,
                "method": "eig",
            },
            {
                "condition": "decrease",
                "residual": 0.0,
                "tolerance": 1e-6,
                "method": "dV/dt",
            },
        ]
    )
    assert any(
        "witnesses[0].condition" in i.path
        for i in validate_control_certificate_packet(packet)
    )
