"""The README's diagrams are rendered from a spec, so they rot like any other
derived file: a rule changes, nobody re-renders, and the picture describes a
validator that stopped existing. The art gate re-renders and compares bytes; this
runs it under pytest, then drives the code each drawing describes."""

import json
import subprocess
import sys
from pathlib import Path

from model_provenance_validator.cli import main
from model_provenance_validator.packet import validate_proof_surface_packet
from model_provenance_validator.validator import (
    MAX_MESSAGE_LENGTH,
    load_schema,
    scrub_text,
    validate_envelope,
)

_REPO = Path(__file__).resolve().parents[1]
_GATE = _REPO / "tools" / "check_repo_art.py"
_SPEC = _REPO / "docs" / "art" / "model-provenance-validator.art.json"

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

DRAWINGS = ("docs/art/model-provenance-validator-header.svg",
            "docs/art/envelope-lane.svg", "docs/art/packet-lane.svg",
            "docs/art/redaction-rules.svg")


def _receipt() -> dict:
    out = subprocess.run([sys.executable, str(_GATE), "--json"],
                         cwd=_REPO, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    return json.loads(out.stdout)


def test_every_gate_passes_and_the_receipt_names_what_it_ran():
    receipt = _receipt()
    assert receipt["schema"] == "model-provenance-validator.repo-art/v1"
    assert [c["name"] for c in receipt["checks"]] == list(GATES)
    assert all(c["passed"] for c in receipt["checks"]), \
        [c for c in receipt["checks"] if not c["passed"]]


def test_both_diagrams_and_the_card_are_accounted_for():
    receipt = _receipt()
    assert receipt["specs"] == ["docs/art/model-provenance-validator.art.json"]
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
    (tmp_path / "model-provenance-validator.art.json").write_text(
        json.dumps(spec), encoding="utf-8")
    monkeypatch.setattr(gate, "ART", tmp_path)
    assert len(gate.check_outcome_fits_its_box([])) == 1


# envelope-lane.svg says what the validator reads and in what order.
# packet-lane.svg says how a batch becomes a packet another tool can read.
# redaction-rules.svg says what the scrubber removes and why order matters.
# Everything below drives the real code, so a claim that stops holding fails.


SCHEMA = load_schema()


def _envelope(**over) -> dict:
    base = {
        "envelope_version": "1",
        "subject": "A claim about a released model.",
        "source": {"name": "vendor release note", "kind": "release-note"},
        "references": [{
            "name": "release note",
            "locator": "https://example.invalid/notes",
            "retrieved_at": "2026-01-15",
        }],
        "validation": {"status": "verified"},
    }
    base.update(over)
    return base


def _paths(envelope: dict) -> list[str]:
    return [error.path for error in validate_envelope(envelope, SCHEMA)]


def test_five_fields_are_required_at_the_root_and_a_sixth_is_named():
    assert _paths(_envelope()) == []
    assert sorted(SCHEMA["required"]) == [
        "envelope_version", "references", "source", "subject", "validation",
    ]
    assert _paths(_envelope(vibe="good")) == ["$.vibe"]
    missing = _paths({"envelope_version": "1"})
    assert sorted(missing) == ["$.references", "$.source", "$.subject",
                               "$.validation"]


def test_an_unexpected_field_is_refused_inside_a_nested_object_too():
    """The drawing says every nested object is checked the same way. A guard that
    only reads the root is defeated by one more level of nesting."""
    nested = _envelope()
    nested["source"] = dict(nested["source"], confidence="high")
    assert _paths(nested) == ["$.source.confidence"]
    deeper = _envelope()
    deeper["references"] = [dict(deeper["references"][0], mirror="elsewhere")]
    assert _paths(deeper) == ["$.references[0].mirror"]


def test_the_source_kind_and_the_validation_status_are_closed_sets():
    kinds = SCHEMA["properties"]["source"]["properties"]["kind"]["enum"]
    statuses = (SCHEMA["properties"]["validation"]["properties"]["status"]["enum"])
    assert kinds == ["official-doc", "paper", "release-note", "local-fixture",
                     "other"]
    assert statuses == ["verified", "partial", "unknown"]
    off_list = _envelope(source={"name": "a blog", "kind": "blog-post"})
    assert _paths(off_list) == ["$.source.kind"]
    assert _paths(_envelope(validation={"status": "true"})) == \
        ["$.validation.status"]


def test_the_version_is_a_constant_and_a_reference_list_may_not_be_empty():
    assert _paths(_envelope(envelope_version="2")) == ["$.envelope_version"]
    assert _paths(_envelope(references=[])) == ["$.references"]
    assert _paths(_envelope(subject="")) == ["$.subject"]


def test_a_date_is_checked_against_the_pattern_and_then_the_calendar():
    """Both halves, because a well-shaped date that never existed is the case a
    pattern alone waves through."""
    shape = _envelope()
    shape["references"] = [dict(shape["references"][0], retrieved_at="15/01/26")]
    assert _paths(shape) == ["$.references[0].retrieved_at"]

    calendar = _envelope()
    calendar["references"] = [dict(calendar["references"][0],
                                   retrieved_at="2026-02-30")]
    assert _paths(calendar) == ["$.references[0].retrieved_at"]


def test_a_status_records_what_was_checked_and_settles_nothing_about_the_claim():
    """The return edge on the first drawing. A verified status is a statement
    about the envelope, so an envelope whose reference points nowhere real is
    still structurally valid."""
    unreachable = _envelope()
    unreachable["references"] = [dict(unreachable["references"][0],
                                      locator="not a locator at all")]
    unreachable["validation"] = {"status": "verified"}
    assert _paths(unreachable) == []


def _scrubbed(text: str) -> str:
    return scrub_text(text)


def test_each_row_of_the_card_removes_the_shape_it_names():
    assert "\x00" not in _scrubbed("before\x00after")
    key = ("-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIB\n"
           "-----END RSA PRIVATE KEY-----")
    assert "MIIBOgIB" not in _scrubbed(f"failed on {key}")
    assert "AKIAIOSFODNN7EXAMPLE" not in _scrubbed("id AKIAIOSFODNN7EXAMPLE here")
    assert "ASIAIOSFODNN7EXAMPLE" not in _scrubbed("id ASIAIOSFODNN7EXAMPLE here")
    for prefix in ("ghp_", "github_pat_", "sk-"):
        token = prefix + "a" * 24
        assert token not in _scrubbed(f"sent {token} upstream")
        short = prefix + "a" * 4
        assert short in _scrubbed(f"sent {short} upstream"), prefix


def test_the_named_secret_rule_catches_a_shape_nobody_catalogued():
    """The accented row. Every other rule needs a prefix it has seen before;
    this one reads the label instead, so an unfamiliar vendor is still covered."""
    invented = "zz9-plural-z-alpha-not-a-known-prefix"
    assert invented in _scrubbed(f"value {invented}")
    for label in ("Bearer", "token", "API_KEY", "password", "secret"):
        for sep in (":", "="):
            leaked = _scrubbed(f"{label}{sep} {invented}")
            assert invented not in leaked, f"{label}{sep}"


def test_both_path_rules_run_and_the_second_leaves_a_url_alone():
    windows = _scrubbed("opened " + "D:" + chr(92) + "keys" + chr(92) + "id.pem")
    assert "keys" not in windows
    assert "/home/someone/.ssh" not in _scrubbed("read /home/someone/.ssh/id")
    assert "/Users/someone" not in _scrubbed("read /Users/someone/notes")
    kept = _scrubbed("see https://example.invalid/home/page")
    assert "example.invalid" in kept


def test_order_is_load_bearing_from_the_first_rule_to_the_last():
    """Truncation runs last, so a long message is redacted before any of it is
    discarded. Collapsing whitespace after redaction is the cost side, and
    the card says so: a prefix rule never sees across a line break."""
    split = "ghp_" + "a" * 12 + "\n" + "b" * 12
    assert "ghp_" in _scrubbed(split), "the gap the card admits has closed"
    assert "ghp_" not in _scrubbed("ghp_" + "a" * 24)

    long_prefix = "e" * (MAX_MESSAGE_LENGTH + 40)
    trailing = "AKIAIOSFODNN7EXAMPLE"
    scrubbed = _scrubbed(f"{long_prefix} {trailing}")
    assert trailing not in scrubbed
    assert len(scrubbed) <= MAX_MESSAGE_LENGTH
    assert scrubbed.endswith("...")

    assert "  " not in _scrubbed("a     b\t\tc")


def _run(capsys, argv: list[str]) -> tuple[int, str]:
    code = main(argv)
    return code, capsys.readouterr().out


def test_a_file_that_will_not_read_becomes_an_error_and_still_counts(capsys,
                                                                     tmp_path):
    """The return edge on the second drawing. An unreadable file has to land in
    the tally rather than end the run."""
    good = _REPO / "tests" / "fixtures" / "valid.json"
    missing = tmp_path / "absent.json"
    code, out = _run(capsys, [str(good), str(missing), "--summary", "--json"])
    summary = json.loads(out)
    assert code == 1
    assert summary["total"] == 2
    assert summary["valid"] == 1 and summary["invalid"] == 1
    assert summary["error_count"] >= 1


def test_the_action_item_list_stops_at_eight_however_large_the_batch(capsys,
                                                                     tmp_path):
    bad = []
    for index in range(11):
        path = tmp_path / f"bad{index}.json"
        path.write_text("{}", encoding="utf-8")
        bad.append(str(path))
    code, out = _run(capsys, bad + ["--summary", "--json"])
    summary = json.loads(out)
    assert code == 1
    assert summary["total"] == 11 and summary["invalid"] == 11
    assert len(summary["action_items"]) == 8


def test_the_packet_carries_three_claims_and_one_check_either_way(capsys,
                                                                 tmp_path):
    good = _REPO / "tests" / "fixtures" / "valid.json"
    _, out = _run(capsys, [str(good), "--proof-packet"])
    ready = json.loads(out)
    assert ready["status"] == "ready"
    assert ready["checks"][0]["status"] == "pass"
    assert len(ready["claims"]) == 3 and len(ready["checks"]) == 1
    assert validate_proof_surface_packet(ready) == []

    broken = tmp_path / "broken.json"
    broken.write_text("{}", encoding="utf-8")
    code, out = _run(capsys, [str(broken), "--proof-packet"])
    blocked = json.loads(out)
    assert code == 1
    assert blocked["status"] == "blocked"
    assert blocked["checks"][0]["status"] == "fail"
    assert len(blocked["claims"]) == 3
    assert validate_proof_surface_packet(blocked) == []


def test_the_packet_is_checked_against_the_shared_contract_before_printing():
    """The self-check stage. The contract is owned elsewhere, so this asserts the
    adapter still reports a real violation rather than an empty list."""
    assert validate_proof_surface_packet({}) != []
    issues = validate_proof_surface_packet({
        "proof_surface_version": "0.1", "packet_id": "p", "surface": "s",
        "status": "ready", "claims": [], "checks": [], "action_items": [],
    })
    assert any(issue.startswith("$.claims") for issue in issues), issues


def test_a_schema_that_will_not_load_stops_the_run_before_any_envelope(capsys,
                                                                      tmp_path):
    good = _REPO / "tests" / "fixtures" / "valid.json"
    absent = tmp_path / "no-schema.json"
    code, out = _run(capsys, [str(good), "--schema", str(absent), "--json"])
    assert code == 1
    assert "error" in json.loads(out)
