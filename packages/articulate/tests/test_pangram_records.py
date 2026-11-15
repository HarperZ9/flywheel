"""Versioned Pangram reference records: each result names its text by hash, its
model version and its date, old results are kept, and the rescore script sends
nothing it should not and never rewrites a record."""
import importlib.util
import json
import pathlib
import shutil

import pytest

from articulate import bench, pangram_records as PR

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"


def _script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_record_names_its_text_model_and_date():
    records = PR.load(str(CORPUS))
    assert records
    for rec in records:
        path = CORPUS / rec["text"]
        assert path.is_file(), rec["text"]
        assert PR.text_sha256(path) == rec["text_sha256"], rec["text"]
        assert rec["model"] and rec["observed"] and rec["source"]


def test_the_unversioned_results_are_kept_and_labelled():
    legacy = [r for r in PR.load(str(CORPUS)) if r["model"] == PR.UNRECORDED]
    assert {r["text"] for r in legacy} == {"ai/flagship-clean.txt", "human/ptacek-tweets.txt"}
    for rec in legacy:
        side = (CORPUS / rec["text"]).with_suffix(".pangram")
        assert side.read_text(encoding="utf-8").strip() == rec["reported"]
        assert "model unrecorded" in PR.describe(rec)


def test_bench_prints_the_model_and_date(capsys):
    bench.main([str(CORPUS)])
    out = capsys.readouterr().out
    assert "[pangram: AI 100% (model unrecorded, date unrecorded)]" in out


def test_a_corpus_without_records_falls_back_to_the_sidecar(tmp_path):
    (tmp_path / "ai").mkdir()
    text = tmp_path / "ai" / "a.txt"
    text.write_text("Some words here.\n", encoding="utf-8")
    (tmp_path / "ai" / "a.pangram").write_text("AI 90%\n", encoding="utf-8")
    assert PR.reference(str(tmp_path), str(text)) == "AI 90% (model unrecorded, date unrecorded)"


def test_a_versioned_record_is_described_with_its_version():
    rec = {"model": "4.1", "observed": "2026-10-21", "prediction_short": "Human",
           "fraction_ai": 0.0}
    assert PR.describe(rec) == "Human fraction_ai 0.00 (Pangram 4.1, 2026-10-21)"


def test_estimate_rounds_up_per_text_and_never_sends_the_unlicensed_file():
    rs = _script("pangram_rescore")
    texts = rs.corpus_texts()
    assert "human/ptacek-tweets.txt" not in {t for t, _ in texts}
    rows, usd = rs.estimate(texts)
    assert all(units == max(1, -(-n // 100)) for _, n, units in rows)
    assert usd == round(sum(u for *_, u in rows) * 0.05, 2)


class FakeClient:
    def __init__(self):
        self.sent = []

    def predict(self, text, model):
        self.sent.append((text, model))
        return {"version": "4.1", "prediction_short": "Human", "fraction_ai": 0.0,
                "windows": [{"text": text, "label": "Human Written",
                             "class_probabilities": [0.97, 0.02, 0.01]}]}


def _work_corpus(tmp_path):
    work = tmp_path / "corpus"
    shutil.copytree(CORPUS, work)
    return work


def test_score_appends_and_never_rewrites(tmp_path):
    rs = _script("pangram_rescore")
    work = _work_corpus(tmp_path)
    before = (work / PR.RECORDS_NAME).read_text(encoding="utf-8")
    texts = rs.corpus_texts(work)[:2]
    client = FakeClient()
    assert rs.score(texts, "pangram-4.1", 5.0, False, corpus=work, client=client) == 0
    after = (work / PR.RECORDS_NAME).read_text(encoding="utf-8")
    assert after.startswith(before)
    new = [json.loads(l) for l in after[len(before):].splitlines()]
    assert [r["model"] for r in new] == ["4.1", "4.1"]
    assert all("text" not in w for r in new for w in r["windows"])
    assert [m for _, m in client.sent] == ["pangram-4.1", "pangram-4.1"]
    rs.score(texts, "pangram-4.1", 5.0, False, corpus=work, client=client)
    assert len(client.sent) == 2


def test_score_refuses_above_the_budget_before_any_call(tmp_path):
    rs = _script("pangram_rescore")
    work = _work_corpus(tmp_path)
    client = FakeClient()
    assert rs.score(rs.corpus_texts(work), "pangram-4.1", 0.10, False,
                    corpus=work, client=client) == 2
    assert client.sent == []


def test_agreement_reports_disagreement_in_both_directions():
    ag = _script("pangram_agreement")
    rows = [("a", True, 80, True), ("b", True, 70, False),
            ("c", False, 0, True), ("d", False, 0, False)]
    s = ag.summarize(rows)
    assert s["agreement"][:2] == [2, 4]
    assert s["precision"][:2] == [1, 2] and s["recall"][:2] == [1, 2]
    assert s["flagged_pangram_human"] == ["b"] and s["clean_pangram_positive"] == ["c"]
    assert s["auroc_texture"][0] == pytest.approx(0.625)
    assert "not applicable" in s["calibration"]
