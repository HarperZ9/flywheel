import hashlib


def test_python_definition_spans_use_decoded_json_codepoint_offsets_with_unicode_and_crlf():
    from harness.inspect_python_units import enumerate_python_test_definitions
    source = 'BANNER = "😀\u2028"\r\n\r\ndef test_after_unicode():\r\n    marker = "β"\r\n    assert marker\r\n'

    result = enumerate_python_test_definitions(source)

    assert result["status"] == "ok"
    assert result["duplicate_definition_names"] == []
    assert result["nested_definitions_unsupported"] == []
    assert len(result["definitions"]) == 1
    item = result["definitions"][0]
    expected_start = source.index("def test_after_unicode")
    expected_end = source.rfind("\r\n")
    expected_value = source[expected_start:expected_end]
    assert item["unit_id"] == "after_unicode"
    assert item["span"] == {
        "encoding": "json-string-codepoints-v1",
        "start": expected_start,
        "end": expected_end,
    }
    assert item["source_value"] == expected_value
    assert item["source_value_sha256"] == hashlib.sha256(
        expected_value.encode("utf-8")).hexdigest()


def test_nested_test_definition_is_reported_unsupported_not_counted():
    from harness.inspect_python_units import enumerate_python_test_definitions
    source = 'def outer():\n    def test_inner():\n        assert True\n'

    result = enumerate_python_test_definitions(source)

    assert result["status"] == "unsupported"
    assert result["definitions"] == []
    assert result["nested_definitions_unsupported"] == ["test_inner"]
