from harness.writing_reader_flow import build_diagnostic, scope_replacement_plan
from harness.writing_types import sha256_bytes, validate_artifact


def test_reader_diagnostic_keeps_semantic_quality_unmeasured():
    diagnostic = build_diagnostic(
        project_ref="wpr_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        section_ref="sec_recommendation",
        revision_ref="rev_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        body_sha256="a" * 64,
        body="Recommendation: hold because receipts are pending. [src_receipt]\n",
        source_ids=["src_receipt"],
    )

    assert diagnostic["schema"] == "flywheel.writing-reader-flow-diagnostic/v1"
    assert diagnostic["reader_state_summary"]["measurement_status"] == "unmeasured"
    assert diagnostic["reader_state_summary"]["basis"] == "none"
    assert diagnostic["reader_state_summary"]["entry_state"] == ""
    assert diagnostic["units"] == []
    assert diagnostic["revision_cards"] == []
    assert diagnostic["source_grounding"][0]["status"] == "known_source"
    assert diagnostic["source_grounding"][0]["span_refs"][0]["excerpt"] == "[src_receipt]"
    assert "does_not_prove" in diagnostic


def test_reader_diagnostic_marker_records_validate_as_public_metadata():
    diagnostic = build_diagnostic(
        project_ref="wpr_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        section_ref="sec_recommendation",
        revision_ref="rev_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        body_sha256="a" * 64,
        body="Recommendation: release. [src_receipt]\n",
        source_ids=["src_receipt"],
    )

    validated = validate_artifact(diagnostic, "diagnostic")
    assert validated["source_grounding"][0]["status"] == "known_source"
    assert validated["source_grounding"][0]["span_refs"][0]["excerpt"] == "[src_receipt]"


def test_reader_diagnostic_unknown_marker_reports_citation_gap():
    diagnostic = build_diagnostic(
        project_ref="wpr_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        section_ref="sec_recommendation",
        revision_ref="rev_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        body_sha256="a" * 64,
        body="Recommendation: release. [src_missing]\n",
        source_ids=["src_receipt"],
    )

    assert diagnostic["source_grounding"][0]["status"] == "unknown_source"
    assert diagnostic["source_grounding"][0]["span_refs"][0]["excerpt"] == "[src_missing]"
    assert diagnostic["problems"][0]["kind"] == "citation_gap"
    assert diagnostic["problems"][0]["source_id"] == "src_missing"


def test_reader_diagnostic_handles_empty_revision_without_zero_width_unit():
    diagnostic = build_diagnostic(
        project_ref="wpr_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        section_ref="sec_recommendation",
        revision_ref="rev_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        body_sha256="a" * 64,
        body="",
        source_ids=[],
    )

    assert diagnostic["units"] == []
    assert diagnostic["revision_cards"] == []
    assert diagnostic["reader_state_summary"]["new_information"] == []
    assert diagnostic["source_grounding"][0]["measurement_status"] == "unsupported"


def test_scope_replacement_accepts_exact_span_only():
    base = "Evidence stays.\nRecommendation: wait for release.\n"
    selected = "Recommendation: wait for release."
    target = {
        "section_ref": "sec_recommendation",
        "base_revision_ref": "rev_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "base_body_sha256": sha256_bytes(base.encode()),
        "coordinate_type": "unicode_codepoint",
        "start": base.index(selected),
        "end": base.index(selected) + len(selected),
        "selected_span_sha256": sha256_bytes(selected.encode()),
    }
    candidate = base.replace(selected, "Recommendation: publish after download-back.")

    result = scope_replacement_plan(base, candidate, target)

    assert result["verdict"] == "PASS"
    assert result["replacement_text"] == "Recommendation: publish after download-back."
    assert result["does_not_prove"]


def test_scope_replacement_blocks_out_of_scope_or_imprecise_targets():
    base = "Evidence stays.\nRecommendation: wait.\n"
    selected = "Recommendation: wait."
    target = {
        "section_ref": "sec_recommendation",
        "base_revision_ref": "rev_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "base_body_sha256": sha256_bytes(base.encode()),
        "coordinate_type": "unicode_codepoint",
        "start": base.index(selected),
        "end": base.index(selected) + len(selected),
        "selected_span_sha256": sha256_bytes(selected.encode()),
    }
    out_of_scope = "Evidence changed.\nRecommendation: publish.\n"

    result = scope_replacement_plan(base, out_of_scope, target)

    assert result["verdict"] == "HOLD"
    assert "prefix" in result["failure_reasons"]
    bool_target = {**target, "start": True}
    bool_result = scope_replacement_plan(base, base, bool_target)
    assert bool_result["verdict"] == "HOLD"
    assert "target_type" in bool_result["failure_reasons"]


def test_scope_replacement_blocks_overlapping_preserved_edges():
    base = "abcXabc"
    target = {
        "section_ref": "sec_one",
        "base_revision_ref": "rev_one",
        "base_body_sha256": sha256_bytes(base.encode()),
        "coordinate_type": "unicode_codepoint",
        "start": 3,
        "end": 4,
        "selected_span_sha256": sha256_bytes(b"X"),
    }
    result = scope_replacement_plan(base, "abc", target)
    assert result["verdict"] == "HOLD"
    assert "candidate_length" in result["failure_reasons"]
