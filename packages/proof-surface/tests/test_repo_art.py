"""The README's diagrams are rendered from a spec, so they rot like any other derived
file: a rule moves, nobody re-renders, and the picture describes a gate that stopped
existing. The art gate re-renders and compares bytes; this runs it under pytest, and
then drives the code each drawing describes, so a drifted claim fails the suite."""

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from proof_surface import evaluate_gate, validate_gate_request, validate_packet
from proof_surface import pre_execution_gate as peg
from proof_surface._bundle import verify_receipts, write_receipts
from proof_surface._decision import (
    CONFIDENCE,
    DECISION_OUTCOMES,
    derive_decision_summary,
)
from proof_surface._verdict import combine_overall, verdict_for_measurement
from proof_surface._validate import Issue
from proof_surface.cli import _DOMAINS, main
from proof_surface.competition_attempt._gates import executed_layer_names
from proof_surface.conservation._gates import validate_negative_fixture
from proof_surface.eval_attempt._integrity import validate_integrity
from proof_surface.optimization_workflow._boundary_gate import validate_boundary
from proof_surface.visual_measurement._calibration import validate_calibration_boundary

_REPO = Path(__file__).resolve().parents[1]
_GATE = _REPO / "tools" / "check_repo_art.py"
_SPEC = _REPO / "docs" / "art" / "proof-surface.art.json"

GATES = (
    "spec.present", "art.matches_spec", "art.render_is_deterministic",
    "art.identity_per_repository", "art.seed_is_recorded",
    "art.no_local_paths_or_em_dashes", "art.spec_words_reach_the_drawing",
    "art.note_survives_the_wrapper", "art.return_edge_stays_on_its_row",
    "art.every_illustration_is_shown", "art.tagline_stays_inside_its_rule",
    "art.outcome_fits_its_box", "art.card_draws_shapes_not_digits",
    "art.card_text_fits_its_column", "art.card_widths_bound_every_face",
    "art.card_draws_measured_characters", "art.card_carries_one_mark",
    "art.card_alt_reaches_the_readme", "art.the_gate_can_fail",
)

DRAWINGS = ("docs/art/proof-surface-header.svg", "docs/art/gate-lane.svg",
            "docs/art/packet-lane.svg", "docs/art/wedge-refusals.svg")


def _receipt() -> dict:
    out = subprocess.run([sys.executable, str(_GATE), "--json"],
                         cwd=_REPO, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    return json.loads(out.stdout)


def test_every_gate_passes_and_the_receipt_names_what_it_ran():
    receipt = _receipt()
    assert receipt["schema"] == "proof-surface.repo-art/v1"
    assert [c["name"] for c in receipt["checks"]] == list(GATES)
    assert all(c["passed"] for c in receipt["checks"]), \
        [c for c in receipt["checks"] if not c["passed"]]


def test_both_diagrams_and_the_card_are_accounted_for():
    receipt = _receipt()
    assert receipt["specs"] == ["docs/art/proof-surface.art.json"]
    drawn = {out["file"]: out for out in receipt["outputs"]}
    assert set(drawn) == set(DRAWINGS)
    for path, out in drawn.items():
        assert len(out["sha256"]) == 64, path
        assert out["bytes"] > 0, path


def test_a_gate_that_cannot_fail_is_not_a_gate(tmp_path, monkeypatch):
    """Point the outcome-box check at a note too wide for its box and it has to
    complain. Without this, a green suite proves only that the gate ran."""
    sys.path.insert(0, str(_REPO / "tools"))
    import check_repo_art as gate
    spec = json.loads(_SPEC.read_text("utf-8"))
    spec["flows"][0]["outcomes"][0]["note"] = "x" * 80
    (tmp_path / "proof-surface.art.json").write_text(json.dumps(spec), encoding="utf-8")
    monkeypatch.setattr(gate, "ART", tmp_path)
    assert len(gate.check_outcome_fits_its_box([])) == 1


# gate-lane.svg says what the pre-execution gate reads and how four checks collapse
# into one decision. packet-lane.svg says how evidence becomes a re-derivable packet.
# wedge-refusals.svg says what each of the eleven domains refuses. Everything below
# drives the real code, so a drawing that stops being true stops the suite.


def _stamp(offset: int) -> str:
    moment = datetime.now(tz=timezone.utc) + timedelta(seconds=offset)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _request(**over) -> dict:
    request = {
        "planned_action": {"action_kind": "read_file", "target": "notes/a.txt"},
        "authorization": {
            "authorization_version": "0.1",
            "receipt_id": "ar-art-fixture",
            "kind": "authorization-grant",
            "principal": {"id": "user:alice@example.com"},
            "agent": {"id": "agent:art"},
            "intent": "Fixture for the repository artwork.",
            "scope": {"allowed_actions": ["read_file"], "allowed_targets": []},
            "granted_at": _stamp(-3600),
            "expires_at": _stamp(3600),
            "revoked": False,
        },
        "budget": {},
    }
    request.update(over)
    return request


def test_the_gate_reads_five_root_fields_and_refuses_a_sixth():
    assert peg.ROOT_FIELDS == {
        "planned_action", "authorization", "budget", "state", "human_gap"
    }
    assert validate_gate_request(_request()) == []
    stray = _request()
    stray["retry_policy"] = "aggressive"
    assert [issue.path for issue in validate_gate_request(stray)] == ["$.retry_policy"]


def test_a_reserved_name_is_refused_at_any_depth_not_only_the_top():
    """The drawing says the guard runs at every level. A guard that only reads the
    root is defeated by one extra layer of nesting, so both cases are checked."""
    forbidden = sorted(peg.FORBIDDEN_FIELDS)[0]
    top = _request()
    top[forbidden] = True
    buried = _request()
    buried["planned_action"] = dict(top["planned_action"], estimated_cost={
        "tokens": 10, "wall_ms": 10, forbidden: True,
    })
    for request in (top, buried):
        messages = [i.message for i in validate_gate_request(request)]
        assert any("forbidden" in m for m in messages), messages


def test_four_checks_answer_on_a_four_value_lattice():
    decision = evaluate_gate(_request())
    assert set(decision.checks) == {"authorization", "budget", "state", "human_gap"}
    assert peg.CHECK_VALUES == {"pass", "fail", "unknown", "not-applicable"}
    assert peg.DECISION_VALUES == {"allow", "deny", "needs-human"}
    assert set(decision.checks.values()) <= peg.CHECK_VALUES


def test_three_of_the_seven_witness_verdicts_confirm_anything():
    assert len(peg.WITNESS_VERDICTS) == 7
    assert peg.WITNESS_CONFIRMING == {"MATCH", "COHERENT", "CORROBORATED"}
    assert peg.WITNESS_CONFIRMING < set(peg.WITNESS_VERDICTS)


def test_allow_needs_authorization_to_pass_and_the_rest_to_stand_aside():
    decision = evaluate_gate(_request())
    assert decision.decision == "allow"
    assert decision.checks["authorization"] == "pass"
    assert set(decision.checks.values()) - {"pass"} <= {"not-applicable"}


def test_one_failure_denies_and_an_unknown_only_sends_it_to_a_person():
    revoked = _request()
    revoked["authorization"] = dict(revoked["authorization"], revoked=True)
    denied = evaluate_gate(revoked)
    assert denied.decision == "deny"
    assert denied.checks["authorization"] == "fail"

    costed = _request()
    costed["planned_action"]["estimated_cost"] = {"tokens": 500, "wall_ms": 500}
    asked = evaluate_gate(costed)
    assert asked.decision == "needs-human"
    assert asked.checks["budget"] == "unknown"
    assert "fail" not in asked.checks.values()


def test_a_request_the_gate_cannot_parse_is_denied_rather_than_passed_along():
    broken = evaluate_gate({"planned_action": "a string, not an object"})
    assert broken.decision == "deny"
    assert broken.checks == {
        "authorization": "fail", "budget": "not-applicable",
        "state": "not-applicable", "human_gap": "not-applicable",
    }


def test_the_decision_carries_no_authority_because_it_cannot_be_edited():
    decision = evaluate_gate(_request())
    try:
        decision.decision = "allow"
    except Exception as exc:
        assert type(exc).__name__ == "FrozenInstanceError"
    else:
        raise AssertionError("a gate decision that can be rewritten is not a receipt")


def test_eleven_domains_share_one_seam_and_an_unknown_one_is_refused():
    assert len(_DOMAINS) == 11
    spec = json.loads(_SPEC.read_text("utf-8"))
    rows = [row["key"] for row in spec["cards"][0]["fields"]]
    assert sorted(rows) == sorted(_DOMAINS)
    assert main(["not-a-domain"]) == 2
    assert main([]) == 2


def test_an_unknown_field_is_refused_rather_than_ignored():
    packet = {
        "proof_surface_version": "0.1", "packet_id": "art-1", "surface": "demo",
        "status": "ready",
        "claims": [{"claim": "it holds", "evidence": "the run"}],
        "checks": [{"tool": "pytest", "status": "pass", "summary": "green"}],
        "action_items": [],
    }
    assert validate_packet(packet) == []
    assert [i.path for i in validate_packet(dict(packet, mood="upbeat"))] == ["$.mood"]


def test_a_measurement_is_a_margin_and_a_missing_one_never_passes():
    assert verdict_for_measurement(0.5, 1.0) == "MATCH"
    assert verdict_for_measurement(1.0, 1.0) == "MATCH"
    assert verdict_for_measurement(1.5, 1.0) == "DRIFT"
    for bad in (None, float("nan"), float("inf"), -0.1):
        assert verdict_for_measurement(bad, 1.0) == "UNVERIFIABLE"
    assert verdict_for_measurement(0.5, 0) == "UNVERIFIABLE"


def test_verdicts_combine_by_worst_case_and_an_empty_set_reads_as_a_match():
    assert combine_overall(["MATCH", "DRIFT", "UNVERIFIABLE"]) == "UNVERIFIABLE"
    assert combine_overall(["MATCH", "DRIFT"]) == "DRIFT"
    assert combine_overall(["MATCH", "MATCH"]) == "MATCH"
    assert combine_overall([]) == "MATCH"


def test_the_decision_follows_the_verdict_and_defaults_to_escalation():
    assert len(DECISION_OUTCOMES) == 7 and len(CONFIDENCE) == 3
    assert derive_decision_summary("MATCH")["decision"] == "approve"
    assert derive_decision_summary("DRIFT")["decision"] == "block"
    unknown = derive_decision_summary("SOMETHING NEW")
    assert unknown == derive_decision_summary("UNVERIFIABLE")
    assert unknown["decision"] == "escalate" and unknown["confidence"] == "low"


def test_a_reader_recomputes_the_manifest_from_the_bytes_on_disk(tmp_path):
    """Both halves of the promise: an edited artifact and an edited manifest each
    have to be caught, and a manifest that is simply absent is not a pass."""
    (tmp_path / "packet.json").write_text('{"a": 1}', encoding="utf-8")
    (tmp_path / "report.md").write_text("# report\n", encoding="utf-8")
    digest = write_receipts(tmp_path, domain="art", packet_id="art-1")
    assert len(digest) == 64
    assert verify_receipts(tmp_path) == []

    (tmp_path / "packet.json").write_text('{"a": 2}', encoding="utf-8")
    assert [i.path for i in verify_receipts(tmp_path)] == ["$.files[0].sha256"]

    bundle = json.loads((tmp_path / "bundle.json").read_text(encoding="utf-8"))
    bundle["bundle_hash"] = "0" * 64
    (tmp_path / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
    assert "$.bundle_hash" in [i.path for i in verify_receipts(tmp_path)]
    (tmp_path / "bundle.json").unlink()
    assert [i.path for i in verify_receipts(tmp_path)] == ["$.bundle.json"]


def _issues(fn, *args) -> list[Issue]:
    found: list[Issue] = []
    fn(*args, found)
    return found


def test_each_row_of_the_card_refuses_what_it_says_it_refuses():
    """One assertion per accented claim on the card. A row whose rule stopped
    refusing would leave the drawing asserting something the code no longer does."""
    clean = {"outcome": "correct"}
    assert _issues(validate_integrity, clean, {"had_ground_truth": False}) == []
    leaked = _issues(validate_integrity, clean, {"had_ground_truth": True})
    assert [i.path for i in leaked] == ["$.boundaries"]

    honest = {"description": "breaks it", "drift": 5.0, "tolerance": 1.0,
              "breaks_invariant": True}
    assert _issues(validate_negative_fixture, honest) == []
    assert _issues(validate_negative_fixture, dict(honest, breaks_invariant=False))
    toothless = _issues(validate_negative_fixture, dict(honest, drift=0.5))
    assert [i.path for i in toothless] == ["$.negative_fixture"]

    solved = {"method": "exact", "status": "COMPLETED"}
    modest = {"hardware_execution_claim": False, "quantum_advantage_claim": False}
    assert _issues(validate_boundary, modest, solved) == []
    assert _issues(validate_boundary, dict(modest, hardware_execution_claim=True),
                   solved)
    assert _issues(validate_boundary, dict(modest, quantum_advantage_claim=True),
                   {"method": "hardware", "status": "COMPLETED"})

    read_only = {"hardware_measurement_used": False,
                 "physical_calibration_claim": True, "instrument": None,
                 "mutation_evidence": None}
    assert _issues(validate_calibration_boundary, read_only, True)

    ladder = [{"layer": "judge-verdict", "status": "EXECUTED"},
              {"layer": "replication", "status": "UNAVAILABLE_FENCED"}]
    assert executed_layer_names(ladder) == {"judge-verdict"}
