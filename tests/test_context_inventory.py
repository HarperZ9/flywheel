from scripts.run_context_inventory import build_inventory, classify_path


class Args:
    def __init__(self, roots):
        self.roots = roots
        self.max_depth = 2
        self.max_entries_per_root = 50


def test_classify_path_labels_benchmark_session_and_sensitive_name():
    labels = classify_path(
        __import__("pathlib").Path("C:/tmp/codex_session_m7_scorecard_token.json")
    )

    assert "benchmark_artifact" in labels
    assert "session_context" in labels
    assert "scratch_temp" in labels
    assert "sensitive_name" in labels


def test_context_inventory_is_metadata_only_and_counts_labels(tmp_path):
    scratch = tmp_path / ".scratch"
    scratch.mkdir()
    scorecard = scratch / "m7_scorecard.json"
    scorecard.write_text('{"secret":"do-not-read"}', encoding="utf-8")
    token_file = scratch / "token.txt"
    token_file.write_text("do-not-read", encoding="utf-8")

    obj = build_inventory(Args(str(scratch)))

    assert obj["schema"] == "harness.context-inventory/v1"
    assert obj["summary"]["existing_roots"] == 1
    assert obj["summary"]["entries"] == 2
    assert obj["summary"]["label_counts"]["benchmark_artifact"] == 1
    assert obj["summary"]["sensitive_name_entries"] == 1
    for entry in obj["roots"][0]["entries"]:
        assert entry["content_read"] is False
        assert "do-not-read" not in str(entry)
