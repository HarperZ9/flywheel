import pytest

from harness.scope import LEGACY_SCOPE_KEY
from harness.writing_types import (
    SCHEMAS, SCHEMAS_V1, WritingTypeError, sha256_bytes, validate_artifact,
    validate_target,
)


PROJECT = "wpr_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def test_project_brief_rejects_fiction_scope():
    with pytest.raises(WritingTypeError, match="UNSUPPORTED_WRITING_MODE"):
        validate_artifact({"schema": "flywheel.writing-project-brief/v2",
            "project_ref": PROJECT, "mode": "fiction", "form": "essay",
            "working_title": "Scene", "audience": "readers",
            "reader_job": "read", "author_intent": "write a scene",
            "voice_contract": {"style_ref": "voice_rules"},
            "source_packet_ref": "packet_main", "writing_profile": "nonfiction",
            "scope": ["quality"]},
            "brief")


def test_project_brief_accepts_v2_nonfiction_fields():
    brief = validate_artifact({"schema": "flywheel.writing-project-brief/v2",
        "project_ref": PROJECT, "mode": "nonfiction", "form": "essay",
        "working_title": "Release evidence", "audience": "operators",
        "reader_job": "decide whether to publish",
        "author_intent": "bind claims to receipts",
        "voice_contract": {"voice_rules": "ref_abc"},
        "source_packet_ref": "writing/v1/owners/owner_x/projects/wpr_y/source/source.json",
        "writing_profile": "nonfiction", "scope": ["truth"]},
        "brief")
    assert brief["form"] == "essay"


def test_v1_artifacts_still_validate_under_the_older_key_and_only_there():
    v1 = {"schema": SCHEMAS_V1["source_packet"], "project_ref": PROJECT,
        "source_packet_ref": "packet_main", "sources": [{"source_id": "src_1",
        "title": "Receipt", "origin": "local", "allowed_use": "cite"}],
        LEGACY_SCOPE_KEY: ["source truth"]}
    assert validate_artifact(v1, "source_packet")["schema"] == SCHEMAS_V1["source_packet"]
    v1_new_name = {**{k: v for k, v in v1.items() if k != LEGACY_SCOPE_KEY},
                   "scope": ["source truth"]}
    v2_old_name = {**v1, "schema": SCHEMAS["source_packet"]}
    for bad in (v1_new_name, v2_old_name):
        with pytest.raises(WritingTypeError, match="ARTIFACT_FIELDS_INVALID"):
            validate_artifact(bad, "source_packet")
    assert SCHEMAS["section"] == SCHEMAS_V1["section"]


def test_source_packet_accepts_v2_sources_and_caps_count():
    source = {"schema": "flywheel.writing-source-packet/v2",
        "project_ref": PROJECT, "source_packet_ref": "packet_main",
        "sources": [{"source_id": "src_1", "title": "Receipt",
        "origin": "local", "allowed_use": "cite"}],
        "scope": ["source truth"]}
    assert validate_artifact(source, "source_packet")["sources"][0]["source_id"] == "src_1"
    too_many = {**source, "sources": source["sources"] * 33}
    with pytest.raises(WritingTypeError, match="SOURCES_INVALID"):
        validate_artifact(too_many, "source_packet")


def test_target_requires_exact_unicode_codepoint_shape():
    body = "AβC\n"
    target = {"section_ref": "sec_one",
        "base_revision_ref": "rev_" + "a" * 32,
        "base_body_sha256": sha256_bytes(body.encode()), "coordinate_type": "unicode_codepoint",
        "start": 1, "end": 2,
        "selected_span_sha256": sha256_bytes("β".encode())}
    assert validate_target(target, body=body)["coordinate_type"] == "unicode_codepoint"
    with pytest.raises(WritingTypeError, match="TARGET_INVALID"):
        validate_target({k: v for k, v in target.items() if k != "coordinate_type"}, body=body)
    with pytest.raises(WritingTypeError, match="TARGET_COORDINATE_INVALID"):
        validate_target({**target, "coordinate_type": "byte_offset"}, body=body)
    with pytest.raises(WritingTypeError, match="TARGET_INVALID"):
        validate_target({**target, "unexpected": "field"}, body=body)
