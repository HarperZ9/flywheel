import json

from chorus.corpora import list_corpora


def _write_corpus(d, ref, title, n_comments):
    d.mkdir(parents=True, exist_ok=True)
    (d / "objects").mkdir(exist_ok=True)
    rows = [{"kind": "metadata", "id": ref, "ref": ref, "title": title, "meta": {}}]
    for i in range(n_comments):
        rows.append({"kind": "comment", "id": f"c{i}", "ref": ref, "title": f"comment on {title}",
                     "meta": {"author": "a", "like_count": i}})
    (d / "catalog.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def test_lists_corpora_under_a_root_with_counts_and_subject(tmp_path):
    _write_corpus(tmp_path / "harari", "vidH", "AI has hacked civilization", 5)
    _write_corpus(tmp_path / "kaneb", "vidK", "Joyful Pessimism", 3)
    (tmp_path / "not_a_corpus").mkdir()   # no catalog.jsonl -> skipped

    out = list_corpora(str(tmp_path))
    assert "error" not in out
    by_name = {c["name"]: c for c in out["corpora"]}
    assert set(by_name) == {"harari", "kaneb"}
    assert by_name["harari"]["comments"] == 5
    assert by_name["harari"]["responds_to"] == "vidH"
    assert by_name["kaneb"]["subject"] == "Joyful Pessimism"


def test_root_itself_counts_as_a_corpus_when_it_holds_a_catalog(tmp_path):
    _write_corpus(tmp_path, "vidR", "root corpus", 2)
    out = list_corpora(str(tmp_path))
    paths = {c["path"] for c in out["corpora"]}
    assert str(tmp_path).replace("\\", "/") in paths


def test_missing_root_is_a_named_error():
    out = list_corpora("C:/nope/not/here")
    assert "error" in out and "not an existing directory" in out["error"]


def test_cli_corpora_prints_json(tmp_path, capsys):
    from chorus.cli import main
    _write_corpus(tmp_path / "c1", "v1", "One", 1)
    assert main(["corpora", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["corpora"][0]["name"] == "c1"
