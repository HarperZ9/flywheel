import json
from chorus.cli import main


def test_run_on_json_rows_prints_digest(tmp_path, capsys):
    rows = [
        {"kind": "comment", "id": "a", "ref": "v", "text": "great sound design",
         "meta": {"author": "x", "like_count": 20}},
        {"kind": "comment", "id": "b", "ref": "v", "text": "loved the sound design",
         "meta": {"author": "y", "like_count": 3}},
        {"kind": "comment", "id": "c", "ref": "v", "text": "the plot was bad",
         "meta": {"author": "z", "like_count": 9}},
    ]
    p = tmp_path / "items.json"
    p.write_text(json.dumps(rows), encoding="utf-8")

    assert main(["run", str(p), "--verify"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["responds_to"] == "v" and out["n_items"] == 3
    assert out["themes"] and "receipt" in out
    assert out["verified"] is True


def test_run_missing_path_is_error(capsys):
    assert main(["run", "does_not_exist.json"]) == 1
    assert "not found" in capsys.readouterr().err


def test_run_non_list_json_is_a_clean_error_not_a_traceback(tmp_path, capsys):
    p = tmp_path / "obj.json"
    p.write_text('{"kind": "comment"}', encoding="utf-8")   # a dict, not a list of rows
    assert main(["run", str(p)]) == 1
    assert "must be a list" in capsys.readouterr().err


def test_run_malformed_json_is_a_clean_error(tmp_path, capsys):
    p = tmp_path / "broken.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert main(["run", str(p)]) == 1
    assert "could not read" in capsys.readouterr().err


def test_decision_command_emits_source_change_result(tmp_path, capsys):
    reference = tmp_path / "reference.json"
    current = tmp_path / "current.json"
    reference.write_text(json.dumps([
        {"kind": "comment", "id": "same", "ref": "workflow", "text": "install works well",
         "meta": {"like_count": 7, "source_url": "https://example.test/same"}},
        {"kind": "comment", "id": "old", "ref": "workflow", "text": "older source row",
         "meta": {"like_count": 1}},
    ]), encoding="utf-8")
    current.write_text(json.dumps([
        {"kind": "comment", "id": "same", "ref": "workflow", "text": "install works well",
         "meta": {"like_count": 7, "source_url": "https://example.test/same"}},
        {"kind": "comment", "id": "new", "ref": "workflow", "text": "new evidence row",
         "meta": {"like_count": 2}},
    ]), encoding="utf-8")

    assert main([
        "decision",
        str(current),
        "--reference",
        str(reference),
        "--task",
        "Decide whether source evidence changed.",
    ]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["schema"] == "chorus.source-decision/v1"
    assert out["status"] == "DRIFT"
    assert out["changes"]["counts"] == {"added": 1, "removed": 1, "changed": 0, "unchanged": 1}


def test_decision_command_can_emit_public_projection_without_raw_text(tmp_path, capsys):
    reference = tmp_path / "reference.json"
    current = tmp_path / "current.json"
    reference.write_text(json.dumps([
        {"kind": "comment", "id": "same", "ref": "workflow", "text": "private baseline sentence",
         "meta": {"like_count": 3}},
    ]), encoding="utf-8")
    current.write_text(json.dumps([
        {"kind": "comment", "id": "same", "ref": "workflow", "text": "private changed sentence",
         "meta": {"like_count": 3}},
    ]), encoding="utf-8")

    assert main([
        "decision",
        str(current),
        "--reference",
        str(reference),
        "--task",
        "Publish only an allowlisted source-change projection.",
        "--public",
    ]) == 0
    out = json.loads(capsys.readouterr().out)
    rendered = json.dumps(out, ensure_ascii=False)
    assert out["schema"] == "chorus.public-source-decision/v1"
    assert out["status"] == "DRIFT"
    assert "private baseline sentence" not in rendered
    assert "private changed sentence" not in rendered


def test_decision_command_uses_operator_public_policy_not_row_metadata(tmp_path, capsys):
    reference = tmp_path / "reference.json"
    current = tmp_path / "current.json"
    policy = tmp_path / "public-policy.json"
    reference.write_text(json.dumps([
        {"kind": "comment", "id": "old", "ref": "workflow", "text": "older source row",
         "meta": {"like_count": 1}},
    ]), encoding="utf-8")
    current.write_text(json.dumps([
        {"kind": "comment", "id": "new", "ref": "workflow", "text": "new source row",
         "meta": {
             "like_count": 2,
             "public_projection_id": "source-controlled-public-id",
             "source_url": "https://example.test/source-controlled",
             "public_projection_url_allowed": True,
         }},
    ]), encoding="utf-8")
    policy.write_text(json.dumps({
        "items": {
            "new": {
                "id": "operator-public-id",
                "source": "official-doc",
                "responds_to": "source-review-gate",
                "source_url": "https://example.test/operator-public",
            }
        }
    }), encoding="utf-8")

    assert main([
        "decision",
        str(current),
        "--reference",
        str(reference),
        "--task",
        "Publish policy-selected source refs.",
        "--public",
        "--public-policy",
        str(policy),
    ]) == 0
    out = json.loads(capsys.readouterr().out)
    rendered = json.dumps(out, ensure_ascii=False)
    assert out["changes"]["added"][0]["public"] == {
        "id": "operator-public-id",
        "source": "official-doc",
        "responds_to": "source-review-gate",
        "source_url": "https://example.test/operator-public",
    }
    assert "source-controlled-public-id" not in rendered
    assert "https://example.test/source-controlled" not in rendered
