import json

import pytest

from harness.evidence_public import (
    TransportError, json_ref, public_metadata, public_result, relative_ref,
)


def test_extracted_metadata_keeps_public_https_and_nested_refs(tmp_path):
    """Dropping recursive admission would let secrets or path selectors cross routes."""
    value = {"source_url": "https://example.com/public?q=bounded",
             "receipt_refs": ["nested/receipt.json"]}
    assert public_metadata(value) is False
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "receipt.json").write_text(
        json.dumps(value), encoding="utf-8")
    assert json_ref(tmp_path, "nested/receipt.json") == value
    assert relative_ref("nested/receipt.json").as_posix() == "nested/receipt.json"


@pytest.mark.parametrize("value", [
    {"api_key": "never"}, {"source": "C:/private/record.json"},
    {"source": "file:private.json"}, {"receipt_ref": "../private.json"},
])
def test_extracted_metadata_keeps_fixed_non_echo_refusals(value):
    """Relaxing the extracted helper would weaken accepted V1 and new V2 together."""
    with pytest.raises(TransportError) as failure:
        public_metadata(value)
    assert failure.value.code == "UNSAFE_METADATA"
    assert "never" not in failure.value.message and "private" not in failure.value.message


def test_extracted_result_keeps_v1_candidate_reason_masking():
    """Returning a downstream reason would expose candidate-controlled text."""
    result = public_result("check", {
        "verdict": "UNVERIFIABLE", "unverifiable_reason": "ORACLE_UNAVAILABLE",
        "reason": "C:/private/provider detail", "oracle_id": "private-oracle",
    })
    assert result["reason"] == "registered oracle could not verify the submitted evidence"
    assert result["does_not_prove"] == ["the requested claim was not checked"]
    assert "oracle_id" not in result and "private" not in json.dumps(result)
