"""The art gate settles whether a drawing fits its columns and matches its spec. It
cannot settle whether the drawing is true of the code, because both sides are derived
from the same JSON. So this file drives the indexer instead: every claim the three
drawings make is asserted here against running code, and a claim that stops holding
fails the suite rather than staying on the page."""

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from repo_proof_index.cli import main
from repo_proof_index.indexer import (
    format_summary,
    format_table,
    load_rows,
    summarize_contract,
    summarize_rows,
)

_SPEC = Path(__file__).resolve().parents[1] / "docs" / "art" / "repo-proof-index.art.json"

SHAPES = (
    ({"manifest_id": "m", "product": "telos"}, "product-use-case"),
    ({"descriptor_id": "d", "backends": []}, "backend-capability"),
    ({"receipt_id": "r", "verdict": "pass"}, "witness-receipt"),
    ({"proof_surface_version": "0.1", "packet_id": "p"}, "proof-surface-packet"),
    (
        {
            "version": "research-claim-proof-packet/v0",
            "packet_id": "rc",
            "verdicts": {"overall": "UNVERIFIABLE", "per_check": []},
        },
        "research-claim-packet",
    ),
    ({"module_id": "orca.module.organ_exchange.bundle", "summary": {}}, "organ-exchange"),
    ({"organ_bundle_version": "1", "bundle_id": "b", "entries": []}, "organ-receipt-bundle"),
)


def _row(tmp_path, name, data):
    path = tmp_path / (name + ".json")
    path.write_text(json.dumps(data), encoding="utf-8")
    return summarize_contract(path, tmp_path)


def test_known_shapes_are_recognized_and_each_reports_its_own_kind(tmp_path) -> None:
    for index, (data, kind) in enumerate(SHAPES):
        assert _row(tmp_path, "shape%d" % index, data).kind == kind, kind


def test_the_first_match_wins_and_the_later_fields_are_never_read(tmp_path) -> None:
    row = _row(
        tmp_path,
        "both",
        {
            "manifest_id": "m",
            "product": "telos",
            "maturity": "shipped",
            "receipt_id": "r",
            "verdict": "fail",
        },
    )
    assert row.kind == "product-use-case"
    assert row.status == "shipped"


def test_an_unrecognized_shape_still_gets_a_row(tmp_path) -> None:
    row = _row(tmp_path, "odd", {"whatever": 1})
    assert row.kind == "contract"
    assert row.status == "unknown"


def test_a_file_with_no_identifier_borrows_the_stem_of_its_own_path(tmp_path) -> None:
    row = _row(tmp_path, "nameless", {"whatever": 1})
    assert row.contract == "nameless"
    assert row.surface == "nameless"


def test_a_root_that_is_not_an_object_is_refused_before_any_shape_is_tried(tmp_path) -> None:
    path = tmp_path / "list.json"
    path.write_text("[{}]", encoding="utf-8")
    with pytest.raises(ValueError):
        summarize_contract(path)


def test_every_row_carries_the_same_eight_fields(tmp_path) -> None:
    row = _row(tmp_path, "any", {"id": "x"})
    assert list(asdict(row)) == [
        "contract",
        "kind",
        "surface",
        "status",
        "evidence",
        "path",
        "producer_status",
        "verification_state",
    ]


def test_a_field_that_is_not_a_scalar_reads_as_unknown(tmp_path) -> None:
    assert _row(tmp_path, "nested", {"id": "x", "status": {"deep": True}}).status == "unknown"


def test_the_evidence_line_prefers_checks_that_passed(tmp_path) -> None:
    data = {
        "id": "x",
        "verification": [
            {"status": "fail", "evidence": "the failing one"},
            {"status": "PASS", "evidence": "the passing one"},
        ],
    }
    evidence = _row(tmp_path, "verified", data).evidence
    assert evidence == "PASS: the passing one"
    assert "failing" not in evidence


def test_the_evidence_line_falls_back_through_claims_then_notes_then_a_null(tmp_path) -> None:
    claims = {"id": "a", "claims": [{"evidence": "claimed"}]}
    assert _row(tmp_path, "a", claims).evidence == "claimed"
    assert _row(tmp_path, "b", {"id": "b", "notes": "a free note"}).evidence == "a free note"
    assert _row(tmp_path, "c", {"id": "c"}).evidence == "no evidence summary"


def test_a_path_is_shown_against_the_base_and_stays_whole_outside_it(tmp_path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    path = nested / "one.json"
    path.write_text(json.dumps({"id": "one"}), encoding="utf-8")
    assert summarize_contract(path, tmp_path).path == "nested/one.json"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert summarize_contract(path, elsewhere).path == path.as_posix()


def test_the_table_prints_four_fields_and_the_other_four_reach_only_json(tmp_path) -> None:
    data = {"id": "row-contract-id", "name": "surf", "status": "pass", "notes": "seen"}
    row = _row(tmp_path, "row-file", data)
    table = format_table([row])
    assert "surf" in table and "pass" in table and "seen" in table
    assert "row-contract-id" not in table
    assert row.path not in table


def test_a_long_field_is_clipped_with_a_trailing_ellipsis(tmp_path) -> None:
    row = _row(tmp_path, "long", {"id": "long", "notes": "e" * 200})
    line = format_table([row]).splitlines()[2]
    assert "e" * 69 + "..." in line
    assert "e" * 70 not in line


def test_the_gap_test_is_a_string_test_so_a_note_saying_no_counts_as_a_gap(tmp_path) -> None:
    row = _row(tmp_path, "clean", {"id": "clean", "status": "pass", "notes": "no regressions found"})
    summary = summarize_rows([row])
    assert summary.evidence_gaps == 1
    assert summary.action_items == ["clean: add evidence (clean.json)"]


def test_nine_status_values_put_a_row_on_the_action_list(tmp_path) -> None:
    nine = [
        "blocked",
        "draft",
        "drift",
        "fail",
        "needs-polish",
        "planned",
        "unknown",
        "unverifiable",
        "unverified",
    ]
    for index, status in enumerate(nine):
        data = {"id": "n%d" % index, "status": status, "notes": "evidence here"}
        rows = [_row(tmp_path, "n%d" % index, data)]
        assert summarize_rows(rows).action_items, status
    passing = [_row(tmp_path, "ok", {"id": "ok", "status": "pass", "notes": "evidence here"})]
    assert summarize_rows(passing).action_items == []


def test_a_backend_matrix_never_lands_on_the_list_by_its_status(tmp_path) -> None:
    row = _row(tmp_path, "d", {"descriptor_id": "d", "backends": [{"status": "ready"}]})
    assert row.status == "backend-matrix"
    assert row.evidence == "ready=1"
    assert summarize_rows([row]).action_items == []


def test_the_action_list_stops_at_eight_and_says_nothing_about_the_rest(tmp_path) -> None:
    rows = [
        _row(tmp_path, "f%d" % index, {"id": "f%d" % index, "status": "fail", "notes": "seen"})
        for index in range(12)
    ]
    summary = summarize_rows(rows)
    assert summary.total == 12
    assert len(summary.action_items) == 8
    printed = format_summary(summary)
    assert len([line for line in printed.splitlines() if line.startswith("- ")]) == 8
    assert "12" not in "\n".join(summary.action_items)


def test_the_bundle_status_is_the_worst_entry_status_in_a_fixed_order(tmp_path) -> None:
    cases = (
        (["deny", "warn", "needs-human", "unverified", "pass"], "block"),
        (["warn", "needs-human", "unverified", "pass"], "warn"),
        (["needs-human", "unverified", "pass"], "needs-human"),
        (["unknown", "pass"], "unverified"),
        (["pass", "pass"], "pass"),
        ([], "unverified"),
    )
    for index, (statuses, expected) in enumerate(cases):
        data = {
            "organ_bundle_version": "1",
            "bundle_id": "b%d" % index,
            "entries": [{"status": status} for status in statuses],
        }
        assert _row(tmp_path, "b%d" % index, data).status == expected, statuses


def test_the_summary_carries_six_fields_counted_and_sorted(tmp_path) -> None:
    rows = [
        _row(tmp_path, "z", {"receipt_id": "z", "verdict": "pass", "notes": "seen"}),
        _row(tmp_path, "a", {"manifest_id": "a", "product": "p", "maturity": "shipped", "notes": "seen"}),
        _row(tmp_path, "m", {"manifest_id": "m", "product": "p", "maturity": "draft", "notes": "seen"}),
    ]
    summary = summarize_rows(rows)
    assert list(asdict(summary)) == [
        "total",
        "kinds",
        "statuses",
        "verification_states",
        "evidence_gaps",
        "action_items",
    ]
    assert list(summary.kinds) == ["product-use-case", "witness-receipt"]
    assert list(summary.statuses) == ["draft", "pass", "shipped"]
    assert summary.verification_states == {"not_assessed": 3}


def test_named_files_are_sorted_and_a_missing_directory_is_named(tmp_path) -> None:
    for name in ("b", "a", "c"):
        (tmp_path / (name + ".json")).write_text(json.dumps({"id": name}), encoding="utf-8")
    named = [tmp_path / "c.json", tmp_path / "a.json", tmp_path / "b.json"]
    assert [row.contract for row in load_rows(named, root=tmp_path)] == ["a", "b", "c"]
    with pytest.raises(FileNotFoundError):
        load_rows(root=tmp_path / "empty")


def test_the_command_exits_zero_on_a_clean_run_and_one_on_a_refusal(tmp_path, capsys) -> None:
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"id": "good"}), encoding="utf-8")
    assert main([str(good)]) == 0
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    assert main([str(bad)]) == 1
    assert capsys.readouterr().out.splitlines()[-1].startswith("error: ")


def test_the_card_names_every_kind_the_indexer_can_report(tmp_path) -> None:
    spec = json.loads(_SPEC.read_text(encoding="utf-8"))
    named = {field["value"] for field in spec["cards"][0]["fields"]}
    produced = {_row(tmp_path, "k%d" % index, data).kind for index, (data, _) in enumerate(SHAPES)}
    produced.add(_row(tmp_path, "fallback", {"whatever": 1}).kind)
    assert produced <= named, produced - named
