import json
import hashlib

from chorus.decision import build_decision, decision_from_paths


def _reference_rows():
    return [
        {
            "kind": "comment",
            "id": "kept",
            "ref": "workflow",
            "text": "fast install works well",
            "meta": {"like_count": 12, "source_url": "https://example.test/comments/kept"},
        },
        {
            "kind": "comment",
            "id": "changed",
            "ref": "workflow",
            "text": "login barrier is bad and slow",
            "meta": {"like_count": 4, "source_url": "https://example.test/comments/changed"},
        },
        {
            "kind": "comment",
            "id": "removed",
            "ref": "workflow",
            "text": "private payload should not leak",
            "meta": {"like_count": 2, "source_url": "https://example.test/comments/removed"},
        },
    ]


def _current_rows():
    return [
        {
            "kind": "comment",
            "id": "kept",
            "ref": "workflow",
            "text": "fast install works well",
            "meta": {"like_count": 12, "source_url": "https://example.test/comments/kept"},
        },
        {
            "kind": "comment",
            "id": "changed",
            "ref": "workflow",
            "text": "login barrier is bad and expensive",
            "meta": {"like_count": 4, "source_url": "https://example.test/comments/changed"},
        },
        {
            "kind": "comment",
            "id": "added",
            "ref": "workflow",
            "text": "sync workflows need durable memory migration",
            "meta": {"like_count": 8, "source_url": "https://example.test/comments/added"},
        },
    ]


def test_source_decision_reports_added_removed_and_changed_items_without_public_raw_text():
    result = build_decision(
        _current_rows(),
        _reference_rows(),
        task="Decide whether the gathered workflow evidence changed before release.",
    )

    assert result["ok"] is True
    assert result["status"] == "DRIFT"
    assert result["decision"] == "review_current_sources"
    assert result["changes"]["counts"] == {
        "added": 1,
        "removed": 1,
        "changed": 1,
        "unchanged": 1,
    }
    assert [row["id"] for row in result["changes"]["added"]] == ["added"]
    assert [row["id"] for row in result["changes"]["removed"]] == ["removed"]
    assert [row["id"] for row in result["changes"]["changed"]] == ["changed"]
    assert result["checks"]["current_digest_verified"] is True
    assert result["checks"]["reference_digest_verified"] is True

    public_text = json.dumps(result["public_projection"], ensure_ascii=False)
    assert "private payload should not leak" not in public_text
    assert "sync workflows need durable memory migration" not in public_text
    assert "https://example.test/comments/added" not in public_text
    assert result["public_projection"]["changes"]["counts"]["changed"] == 1


def test_operator_public_projection_policy_can_publish_safe_values():
    result = build_decision(
        [
            {
                "kind": "comment",
                "id": "added-id",
                "ref": "workflow",
                "text": "new official source observation",
                "meta": {"like_count": 1, "source_url": "https://example.test/comments/added-id"},
            }
        ],
        [
            {
                "kind": "comment",
                "id": "kept-id",
                "ref": "workflow",
                "text": "reference source",
                "meta": {"like_count": 1, "source_url": "https://example.test/comments/kept-id"},
            }
        ],
        task="Project only explicitly allowlisted source URLs.",
        public_projection_policy={
            "items": {
                "added-id": {
                    "id": "added-public",
                    "source": "official-doc",
                    "responds_to": "source-review-gate",
                    "source_url": "https://example.test/comments/added-id",
                }
            }
        },
    )

    public = result["public_projection"]["changes"]["added"][0]
    assert public["public"] == {
        "id": "added-public",
        "source": "official-doc",
        "responds_to": "source-review-gate",
        "source_url": "https://example.test/comments/added-id",
    }


def test_public_projection_omits_unallowlisted_task_ids_sources_and_refs():
    result = build_decision(
        [
            {
                "kind": "comment",
                "id": "C:/private/current-id",
                "ref": "C:/private/video-ref",
                "text": "changed source row",
                "meta": {"like_count": 2, "source_url": "https://example.test/private-current"},
            }
        ],
        [
            {
                "kind": "comment",
                "id": "C:/private/reference-id",
                "ref": "C:/private/video-ref",
                "text": "reference source row",
                "meta": {
                    "like_count": 1,
                    "public_projection_id": "safe-reference-id",
                    "public_projection_source": "official-doc",
                    "public_projection_responds_to": "source-reuse-gate",
                    "source_url": "https://example.test/reference",
                    "public_projection_url_allowed": True,
                },
            }
        ],
        task="Compare C:/private/task path",
    )

    public = result["public_projection"]
    rendered = json.dumps(public, ensure_ascii=False)
    assert "C:/private" not in rendered
    assert "private-current" not in rendered
    assert public["task_sha256"]
    assert "task" not in public
    assert public["changes"]["removed"][0]["public"] == {}
    assert public["changes"]["added"][0]["public"] == {}


def test_source_row_public_metadata_does_not_authorize_public_projection():
    result = build_decision(
        [
            {
                "kind": "comment",
                "id": "source-controlled-id",
                "ref": "workflow",
                "text": "new source-controlled row",
                "meta": {
                    "like_count": 1,
                    "public_projection_id": "source-controlled-public-id",
                    "public_projection_source": "source-controlled-public-source",
                    "public_projection_responds_to": "source-controlled-public-ref",
                    "source_url": "https://example.test/source-controlled",
                    "public_projection_url_allowed": True,
                },
            }
        ],
        [
            {
                "kind": "comment",
                "id": "reference-id",
                "ref": "workflow",
                "text": "reference source row",
                "meta": {"like_count": 1},
            }
        ],
        task="Source row metadata is untrusted for public projection.",
    )

    public = result["public_projection"]
    rendered = json.dumps(public, ensure_ascii=False)
    assert "source-controlled-public-id" not in rendered
    assert "source-controlled-public-source" not in rendered
    assert "source-controlled-public-ref" not in rendered
    assert "https://example.test/source-controlled" not in rendered
    assert public["changes"]["added"][0]["public"] == {}


def test_inline_comment_rows_without_text_are_typed_unverifiable():
    result = build_decision(
        [{"kind": "comment", "id": "current-row", "ref": "claim", "meta": {"like_count": 1}}],
        [{"kind": "comment", "id": "reference-row", "ref": "claim", "meta": {"like_count": 1}}],
        task="Detect missing inline text.",
    )

    assert result["status"] == "UNVERIFIABLE"
    assert result["decision"] == "hold_for_source_repair"
    assert [failure["code"] for failure in result["source_failures"]] == [
        "missing_current_text",
        "missing_reference_text",
    ]
    assert result["source_counts"]["current_rows"] == 1
    assert result["source_counts"]["current_items"] == 1


def test_gather_corpus_invalid_sha_without_text_is_typed_unverifiable(tmp_path):
    current = tmp_path / "current"
    reference = tmp_path / "reference"
    current.mkdir()
    reference.mkdir()
    row = {
        "kind": "comment",
        "id": "source-row",
        "ref": "claim",
        "sha256": "not-a-sha",
        "meta": {"like_count": 1},
    }
    for corpus in (current, reference):
        (corpus / "catalog.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    result = decision_from_paths(str(current), str(reference), task="Detect malformed gather catalog rows.")

    assert result["status"] == "UNVERIFIABLE"
    assert result["decision"] == "hold_for_source_repair"
    assert [failure["code"] for failure in result["source_failures"]] == [
        "invalid_current_object_hash",
        "invalid_reference_object_hash",
    ]
    assert result["source_counts"]["current_rows"] == 1
    assert result["source_counts"]["reference_rows"] == 1


def test_inline_null_item_id_is_typed_unverifiable_before_normalize():
    result = build_decision(
        [{"kind": "comment", "id": None, "ref": "claim", "text": "same source text", "meta": {"like_count": 1}}],
        [{"kind": "comment", "id": "None", "ref": "claim", "text": "same source text", "meta": {"like_count": 1}}],
        task="Detect null source identity before normalize can stringify it.",
    )

    assert result["status"] == "UNVERIFIABLE"
    assert result["decision"] == "hold_for_source_repair"
    assert [failure["code"] for failure in result["source_failures"]] == ["missing_current_item_id"]
    assert result["source_counts"]["current_rows"] == 1
    assert result["source_counts"]["reference_items"] == 1


def test_inline_blank_item_id_is_typed_unverifiable_before_normalize():
    result = build_decision(
        [{"kind": "comment", "id": "  ", "ref": "claim", "text": "current source text", "meta": {"like_count": 1}}],
        [{"kind": "comment", "id": "valid", "ref": "claim", "text": "reference source text", "meta": {"like_count": 1}}],
        task="Detect blank source identity before normalize.",
    )

    assert result["status"] == "UNVERIFIABLE"
    assert [failure["code"] for failure in result["source_failures"]] == ["missing_current_item_id"]


def test_inline_non_string_item_ids_are_typed_unverifiable_before_normalize():
    rows = [
        (True, "invalid_current_item_id"),
        (7, "invalid_current_item_id"),
        (["row"], "invalid_current_item_id"),
        ({"row": "id"}, "invalid_current_item_id"),
    ]
    for bad_id, expected_code in rows:
        result = build_decision(
            [{"kind": "comment", "id": bad_id, "ref": "claim", "text": "current source text", "meta": {"like_count": 1}}],
            [{"kind": "comment", "id": "valid", "ref": "claim", "text": "reference source text", "meta": {"like_count": 1}}],
            task="Detect non-string source identity before normalize.",
        )

        assert result["status"] == "UNVERIFIABLE"
        assert [failure["code"] for failure in result["source_failures"]] == [expected_code]


def test_gather_corpus_null_item_id_is_typed_unverifiable_before_normalize(tmp_path):
    current = tmp_path / "current"
    reference = tmp_path / "reference"
    current.mkdir()
    reference.mkdir()
    text = "same source text"
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    for corpus in (current, reference):
        obj = corpus / "objects" / sha[:2] / sha[2:]
        obj.parent.mkdir(parents=True)
        obj.write_text(text, encoding="utf-8")
        (corpus / "catalog.jsonl").write_text(json.dumps({
            "kind": "comment",
            "id": None,
            "ref": "claim",
            "sha256": sha,
            "meta": {"like_count": 1},
        }) + "\n", encoding="utf-8")

    result = decision_from_paths(str(current), str(reference), task="Detect null gather identity.")

    assert result["status"] == "UNVERIFIABLE"
    assert result["decision"] == "hold_for_source_repair"
    assert [failure["code"] for failure in result["source_failures"]] == [
        "missing_current_item_id",
        "missing_reference_item_id",
    ]
    assert result["source_counts"]["current_rows"] == 1
    assert result["source_counts"]["current_items"] == 1


def test_gather_corpus_missing_content_object_is_typed_unverifiable(tmp_path):
    current = tmp_path / "current"
    reference = tmp_path / "reference"
    current.mkdir()
    reference.mkdir()
    missing_sha = "a" * 64
    reference_text = "valid reference object"
    reference_sha = hashlib.sha256(reference_text.encode("utf-8")).hexdigest()
    row = {
        "kind": "comment",
        "id": "source-row",
        "ref": "claim",
        "sha256": missing_sha,
        "meta": {"like_count": 1},
    }
    reference_row = {**row, "sha256": reference_sha}
    reference_obj = reference / "objects" / reference_sha[:2] / reference_sha[2:]
    reference_obj.parent.mkdir(parents=True)
    reference_obj.write_text(reference_text, encoding="utf-8")
    (current / "catalog.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    (reference / "catalog.jsonl").write_text(json.dumps(reference_row) + "\n", encoding="utf-8")

    result = decision_from_paths(str(current), str(reference), task="Detect missing gather objects.")

    assert result["status"] == "UNVERIFIABLE"
    assert result["source_failures"][0]["code"] == "missing_current_object"
    assert result["source_counts"]["current_rows"] == 1
    assert result["source_counts"]["reference_rows"] == 1
    assert result["source_counts"]["reference_items"] == 1


def test_gather_corpus_mismatched_content_object_hash_is_typed_unverifiable(tmp_path):
    current = tmp_path / "current"
    reference = tmp_path / "reference"
    current.mkdir()
    reference.mkdir()
    actual_text = "object bytes do not match the catalog sha"
    advertised_sha = "b" * 64
    actual_sha = hashlib.sha256(actual_text.encode("utf-8")).hexdigest()
    for corpus in (current, reference):
        obj = corpus / "objects" / advertised_sha[:2] / advertised_sha[2:]
        obj.parent.mkdir(parents=True)
        obj.write_text(actual_text, encoding="utf-8")
        row = {
            "kind": "comment",
            "id": "source-row",
            "ref": "claim",
            "sha256": advertised_sha,
            "meta": {"like_count": 1},
        }
        (corpus / "catalog.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    result = decision_from_paths(str(current), str(reference), task="Detect object hash mismatch.")

    assert actual_sha != advertised_sha
    assert result["status"] == "UNVERIFIABLE"
    assert result["source_failures"][0]["code"] == "mismatched_current_object_hash"
    assert result["source_counts"]["current_rows"] == 1


def test_changed_text_is_drift_even_when_each_digest_receipt_verifies():
    result = build_decision(
        [
            {
                "kind": "comment",
                "id": "same-id",
                "ref": "workflow",
                "text": "the source now says the connector fails closed",
                "meta": {"like_count": 3},
            }
        ],
        [
            {
                "kind": "comment",
                "id": "same-id",
                "ref": "workflow",
                "text": "the source says the connector works",
                "meta": {"like_count": 3},
            }
        ],
        task="Detect altered source content.",
    )

    assert result["status"] == "DRIFT"
    assert result["changes"]["counts"] == {"added": 0, "removed": 0, "changed": 1, "unchanged": 0}
    assert result["checks"]["current_digest_verified"] is True
    assert result["checks"]["reference_digest_verified"] is True


def test_missing_current_path_is_a_typed_unverifiable_result(tmp_path):
    reference = tmp_path / "reference.json"
    reference.write_text(json.dumps(_reference_rows()), encoding="utf-8")

    result = decision_from_paths(
        str(tmp_path / "missing.json"),
        str(reference),
        task="Detect missing source failures.",
    )

    assert result["ok"] is False
    assert result["status"] == "UNVERIFIABLE"
    assert result["decision"] == "hold_for_source_repair"
    assert result["source_failures"][0]["code"] == "missing_current"
    assert result["source_counts"]["reference_rows"] == 3
    assert result["source_counts"]["reference_items"] == 3
