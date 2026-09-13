from pathlib import Path

import pytest

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


@pytest.mark.parametrize("host_name", ["plain", "evaluation-session-tmp"])
def test_inventory_labels_ignore_ancestors_outside_selected_root(tmp_path, monkeypatch, host_name):
    root = tmp_path / host_name / "corpus"
    root.mkdir(parents=True)
    token = root / "token.txt"
    token.write_text("private body", encoding="utf-8")

    def forbid_body_read(*args, **kwargs):
        raise AssertionError("inventory must not read file bodies")

    monkeypatch.setattr(Path, "read_text", forbid_body_read)
    monkeypatch.setattr(Path, "read_bytes", forbid_body_read)
    obj = build_inventory(Args(str(root)))

    assert obj["summary"]["label_counts"] == {"sensitive_name": 1}
    row, = obj["roots"][0]["entries"]
    assert row["path"] == str(token)
    assert row["labels"] == ["sensitive_name"]
    assert row["content_read"] is False


@pytest.mark.parametrize("root_name,label", [
    (".scratch", "scratch_temp"),
    ("benchmarks", "benchmark_artifact"),
    ("sessions", "session_context"),
])
@pytest.mark.parametrize("dot_root", [False, True])
def test_inventory_keeps_selected_root_labels(tmp_path, monkeypatch, root_name, label, dot_root):
    root = tmp_path / root_name
    root.mkdir()
    (root / "record.json").write_text("{}", encoding="utf-8")

    if dot_root:
        monkeypatch.chdir(root)
    obj = build_inventory(Args("." if dot_root else str(root)))

    row, = obj["roots"][0]["entries"]
    assert row["labels"] == [label]
    if dot_root:
        assert obj["roots"][0]["root"] == "."
        assert row["path"] == "record.json"


def test_inventory_keeps_descendant_path_labels(tmp_path):
    root = tmp_path / "corpus"
    nested = root / "benchmark-results"
    nested.mkdir(parents=True)
    (nested / "record.json").write_text("{}", encoding="utf-8")

    obj = build_inventory(Args(str(root)))

    assert obj["summary"]["entries"] == 2
    assert obj["summary"]["label_counts"] == {"benchmark_artifact": 2}
    assert all(row["labels"] == ["benchmark_artifact"] for row in obj["roots"][0]["entries"])


def test_inventory_parent_root_keeps_selected_root_name(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    child = root / "child"
    child.mkdir(parents=True)
    (root / "record.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(child)

    obj = build_inventory(Args(".."))

    assert obj["roots"][0]["root"] == ".."
    row = next(row for row in obj["roots"][0]["entries"] if row["name"] == "record.json")
    assert row["path"] == str(Path("..") / "record.json")
    assert row["labels"] == ["session_context"]
