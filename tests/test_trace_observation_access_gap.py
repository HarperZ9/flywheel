"""Measured-gap record: documentation against what the run saw, with source hygiene."""
import json
from pathlib import Path

import pytest

from harness.trace_observation import access_gap_data as data
from harness.trace_observation.access_gap import documented, measured_gap
from harness.trace_observation.adapters import capture

FIX = Path(__file__).parent / "fixtures" / "trace_observation"
CORE = ("openai", "anthropic", "google", "xai", "deepseek", "mistral")


def cap(provider, name):
    f = json.loads((FIX / name).read_text(encoding="utf-8"))
    return capture(provider, f["request"], f["response"], run_id="r1")


def field(rec, name):
    return next(f for f in rec["fields"] if f["field"] == name)


def test_snapshot_rules_every_provider_every_field_and_sources_registered():
    ids = {s["id"] for s in data.SOURCES}
    for p in CORE:
        assert {c["field"] for c in data.CELLS if c["provider"] == p} == set(data.FIELDS)
    for c in data.CELLS:
        if c["value"] != "unknown":
            assert c["source_ids"] and set(c["source_ids"]) <= ids, c
        else:
            assert c["confidence"] == "unknown"
    assert len(data.SOURCE_SHA256) == 64


def test_reseller_only_cells_are_marked_for_openai():
    doc = documented("openai")
    assert doc["raw_extraction_policy"]["reseller_only"] is True      # Azure page only
    assert doc["reasoning_text"]["reseller_only"] is False
    assert documented("anthropic")["reasoning_text"]["undated_only"] is True


def test_anthropic_summary_run_matches_documentation_and_lists_outside_gaps():
    rec = measured_gap("anthropic", [cap("anthropic", "anthropic_summarized.json")],
                       run_id="r1", observed_on="2026-10-01")
    assert field(rec, "reasoning_text")["agreement"] == "MATCH"
    assert field(rec, "opaque_reasoning_field")["agreement"] == "MATCH"
    assert field(rec, "reasoning_token_count")["agreement"] == "MATCH"
    assert field(rec, "model_snapshot_pinning")["agreement"] == "DOCUMENTED_ONLY"
    codes = {g["gap_code"] for g in rec["not_observable_from_outside"]}
    assert {"NOT_OBSERVABLE_FROM_OUTSIDE", "SUMMARY_ONLY_CHANNEL", "PROVIDER_ENCRYPTED",
            "INTERNALS_UNAVAILABLE", "REASONING_WRITE_UNAVAILABLE"} <= codes
    assert rec["documentation_drift"] == []
    assert all(g["scope"] == "outside_observability" for g in rec["not_observable_from_outside"])


def test_omitted_run_is_unverifiable_not_a_finding_about_reasoning():
    rec = measured_gap("anthropic", [cap("anthropic", "anthropic_omitted.json")],
                       run_id="r1", observed_on="2026-10-01")
    assert field(rec, "reasoning_text")["agreement"] == "UNVERIFIABLE"
    assert "REASONING_OMITTED_BY_DEFAULT" in {g["gap_code"] for g in rec["not_yet_observed_local"]}


def test_drift_when_run_contradicts_documentation():
    c = cap("openai", "openai_responses_summary.json")
    c.record.channel = "raw"          # a run that saw raw text where docs say summary
    rec = measured_gap("openai", [c], run_id="r1", observed_on="2026-10-01")
    assert "reasoning_text" in rec["documentation_drift"]


def test_unknown_cells_become_local_documentation_gaps_and_staleness_is_computed():
    rec = measured_gap("google", [cap("google", "gemini_thought_summary.json")],
                       run_id="r1", observed_on="2027-03-01")
    local = {(g["gap_code"], g["component"]) for g in rec["not_yet_observed_local"]}
    assert ("DOCUMENTATION_UNREAD", "reasoning_token_count") in local
    assert ("DOCUMENTATION_STALE", "reasoning_text") in local
    assert field(rec, "reasoning_text")["stale"] == "true"


def test_deepseek_raw_has_no_raw_reasoning_gap_but_internals_gap():
    rec = measured_gap("deepseek", [cap("deepseek", "deepseek_reasoning_content.json")],
                       run_id="r1", observed_on="2026-10-01")
    codes = {g["gap_code"] for g in rec["not_observable_from_outside"]}
    assert "NOT_OBSERVABLE_FROM_OUTSIDE" not in codes and "INTERNALS_UNAVAILABLE" in codes


def test_local_open_weight_run_has_no_outside_gaps():
    rec = measured_gap("ollama", [cap("ollama", "ollama_qwen3_recorded.json")],
                       run_id="r1", observed_on="2026-10-01")
    assert rec["not_observable_from_outside"] == []
    assert "ACCESS_CLASS_UNAVAILABLE_LOCALLY" in {g["gap_code"] for g in rec["not_yet_observed_local"]}


def test_unknown_provider_refused():
    with pytest.raises(ValueError):
        measured_gap("acme", [], run_id="r", observed_on="2026-10-01")
