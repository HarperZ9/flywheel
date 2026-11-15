"""The known-provenance corpus: every document is hashed and says where it came
from, committed texts match their hashes, local-only texts stay out of the
repository, and every detector score names its text, models and date."""
import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROV = ROOT / "corpus" / "provenance"


def _script(name):
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C = _script("provenance_common")
DOCS = C.load_manifest()["documents"]


def test_every_document_has_class_genre_hash_and_origin():
    assert len(DOCS) >= 100 and len({d["id"] for d in DOCS}) == len(DOCS)
    for d in DOCS:
        assert d["class"] in ("human", "ai", "mixed"), d["id"]
        assert d["genre"] and len(d["sha256"]) == 64 and d["location"] in ("repo", "local")
        if d["class"] == "human":
            assert d["source"]["licence"] and d["written"], d["id"]
        else:
            g = d["generation"]
            assert g["model"] and g["digest"] and g["date"] and "seed" in g, d["id"]
            assert g.get("prompt") or g.get("prompt_sha256") or g.get("edit"), d["id"]


def test_mixed_documents_name_their_base_and_the_edit():
    for d in (d for d in DOCS if d["class"] == "mixed"):
        edit = d["generation"]["edit"]
        base = next(b for b in DOCS if b["id"] == edit["base_id"])
        assert base["class"] == "human" and base["sha256"] == edit["base_sha256"]
        assert edit["instruction"] and edit["by"] == d["generation"]["model"]


def test_committed_texts_match_their_hashes():
    repo = [d for d in DOCS if d["location"] == "repo"]
    assert repo
    for d in repo:
        assert C.read_checked(d) is not None, d["id"]


def test_local_only_texts_are_not_in_the_repository():
    local = [d for d in DOCS if d["location"] == "local"]
    assert local
    for d in local:
        assert not (PROV / d["path"]).exists(), d["id"]
        assert "persuade" in json.dumps(d).lower(), d["id"]


def test_every_detector_score_names_text_models_and_date():
    by_id = {d["id"]: d for d in DOCS}
    lines = (PROV / "detector-records.jsonl").read_text(encoding="utf-8").splitlines()
    assert lines
    for line in lines:
        r = json.loads(line)
        assert by_id[r["text_id"]]["sha256"] == r["text_sha256"]
        assert r["detector"] in ("binoculars", "fast-detectgpt") and r["version"]
        assert all("@" in m for m in r["models"].values()) and r["observed"]
        assert r["environment"]["script_sha256"]


def test_results_carry_their_limits():
    res = json.loads((PROV / "results.json").read_text(encoding="utf-8"))
    assert "scope" in res
    overall = res["articulate"]["overall"]
    assert {"precision", "recall", "fpr"} <= set(overall)
    assert all(v["ci95"] for v in overall.values())


def test_confusion_counts_on_a_fixture():
    ev = _script("provenance_eval")
    rows = [{"class": "ai", "flag": True}, {"class": "ai", "flag": False},
            {"class": "human", "flag": True}, {"class": "human", "flag": False},
            {"class": "human", "flag": False}]
    c = ev.confusion(rows)
    assert (c["recall"]["k"], c["recall"]["n"]) == (1, 2)
    assert (c["fpr"]["k"], c["fpr"]["n"]) == (1, 3)
    assert (c["precision"]["k"], c["precision"]["n"]) == (1, 2)


def test_manifest_refuses_to_change_a_hash():
    import pytest
    man = {"documents": [{"id": "x", "sha256": "a"}]}
    assert C.upsert(man, {"id": "x", "sha256": "a"}) is False
    with pytest.raises(ValueError):
        C.upsert(man, {"id": "x", "sha256": "b"})
