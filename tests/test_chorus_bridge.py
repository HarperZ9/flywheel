"""The chorus bridge must return chorus's own digest verbatim and fail honestly:
a scripted runner yields the digest under `result` with its verified flag, a
missing corpus is a named error, and a non-JSON or failed run never masquerades
as a digest."""

import json

from harness.chorus_bridge import discourse_digest


def _runner(rc, out, err=""):
    return lambda cmd: (rc, out, err)


def test_digest_is_returned_verbatim_with_the_verified_flag(tmp_path):
    corpus = tmp_path / "items.json"
    corpus.write_text("[]", encoding="utf-8")
    digest = {"responds_to": "v", "n_items": 3, "themes": [{"label": "x"}],
              "receipt": {"digest_sha256": "abc"}, "verified": True}
    out = discourse_digest(str(corpus), runner=_runner(0, json.dumps(digest)))
    assert out.get("error") is None, out
    assert out["schema"] == "flywheel.discourse-digest/v1"
    assert out["verified"] is True
    assert out["result"]["themes"][0]["label"] == "x"


def test_missing_corpus_is_a_named_error():
    out = discourse_digest("C:/nope/does/not/exist", runner=_runner(0, "{}"))
    assert "error" in out and "not found" in out["error"]


def test_failed_run_is_a_named_error(tmp_path):
    corpus = tmp_path / "items.json"
    corpus.write_text("[]", encoding="utf-8")
    out = discourse_digest(str(corpus), runner=_runner(1, "", "boom"))
    assert "error" in out and "boom" in out["error"]


def test_non_json_output_is_refused(tmp_path):
    corpus = tmp_path / "items.json"
    corpus.write_text("[]", encoding="utf-8")
    out = discourse_digest(str(corpus), runner=_runner(0, "not json"))
    assert "error" in out and "did not emit JSON" in out["error"]


from harness.chorus_bridge import list_corpora


def test_corpora_list_is_returned_with_schema(tmp_path):
    listing = {"root": str(tmp_path), "corpora": [
        {"name": "harari", "comments": 5, "subject": "AI", "responds_to": "vidH", "path": str(tmp_path)}]}
    out = list_corpora(str(tmp_path), runner=_runner(0, json.dumps(listing)))
    assert out.get("error") is None
    assert out["schema"] == "flywheel.discourse-corpora/v1"
    assert out["corpora"][0]["comments"] == 5


def test_corpora_bad_root_is_a_named_error_before_the_runner():
    out = list_corpora("C:/nope/not/here", runner=_runner(0, "{}"))
    assert "error" in out and "not an existing directory" in out["error"]


def test_corpora_passes_through_chorus_named_error(tmp_path):
    out = list_corpora(str(tmp_path), runner=_runner(1, json.dumps({"error": "bad root"})))
    assert out.get("error") == "bad root"


def test_corpora_non_json_is_refused(tmp_path):
    out = list_corpora(str(tmp_path), runner=_runner(0, "not json"))
    assert "error" in out and "did not emit JSON" in out["error"]
