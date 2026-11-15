import dataclasses

from chorus.item import DiscourseItem
from chorus.sentiment import score, model_pass
from chorus.synthesize import synthesize
from chorus.receipt import verify, digest_body_sha


def _items():
    # "amazing" is clearly positive; the two neutral lines are lexicon-uncertain (~0).
    rows = [("a", "amazing sound design", 20), ("b", "the meeting is at three", 5),
            ("c", "it is what it is", 8), ("d", "amazing wonderful audio", 3)]
    return [DiscourseItem(i, "video", "v", None, "au", t, e, None, {}) for i, t, e in rows]


def _stub_model(texts):
    # a deterministic stand-in: the model reads the neutral lines as mildly negative sarcasm.
    return [{"compound": -0.4, "label": "dry/sarcastic"} for _ in texts]


def test_model_pass_overlays_only_the_lexicon_uncertain_items_with_provenance():
    scored = score(_items())
    overlays = model_pass(scored, _stub_model, model_ref="stub/1", ambiguous_cut=0.1)
    ids = {o["item_id"] for o in overlays}
    assert ids == {"b", "c"}                       # a and d are clearly positive -> not sent
    o = overlays[0]
    assert o["provenance"] == "model:stub/1"
    assert o["model_compound"] == -0.4 and o["label"] == "dry/sarcastic"
    assert "lexicon_compound" in o and o["prompt_sha"]


def test_a_raising_model_marks_items_failed_never_crashes():
    scored = score(_items())

    def boom(texts):
        raise RuntimeError("model down")

    overlays = model_pass(scored, boom, model_ref="stub/1", ambiguous_cut=0.1)
    assert overlays and all(o["model_compound"] is None for o in overlays)
    assert all("model-failed" in o["label"] for o in overlays)


def test_model_layer_attaches_without_changing_the_verifiable_core():
    scored = score(_items())
    plain = synthesize(scored)
    overlays = model_pass(scored, _stub_model, model_ref="stub/1", ambiguous_cut=0.1)
    withmodel = synthesize(scored, model_scores=overlays, model_ref="stub/1")

    # the model layer is attached and the receipt names the model...
    assert withmodel.model_layer and withmodel.receipt.model_ref == "stub/1"
    assert plain.receipt.model_ref is None
    # ...but the re-checkable core (themes, weights, distribution) is byte-identical,
    # so the model never silently changes what a stranger can verify.
    assert digest_body_sha(withmodel) == digest_body_sha(plain)
    assert withmodel.receipt.digest_sha256 == plain.receipt.digest_sha256
    # and verify still passes: it re-derives the lexicon core, ignoring the overlay.
    assert verify(withmodel, scored) is True


def test_subprocess_model_roundtrips(tmp_path):
    import sys
    from chorus.model import SubprocessModel
    script = tmp_path / "m.py"
    script.write_text(
        "import sys, json\n"
        "texts = json.loads(sys.stdin.read())\n"
        "print(json.dumps([{'compound': 0.5, 'label': 'pos'} for _ in texts]))\n",
        encoding="utf-8")
    model = SubprocessModel([sys.executable, str(script)], ref="fake/1")
    out = model(["hello", "world"])
    assert out == [{"compound": 0.5, "label": "pos"}, {"compound": 0.5, "label": "pos"}]
    assert model.ref == "fake/1"


def test_cli_run_with_a_model_command_attaches_the_overlay(tmp_path, capsys):
    import sys, json as _j
    from chorus.cli import main
    rows = [{"kind": "comment", "id": "a", "ref": "v", "text": "amazing sound", "meta": {"like_count": 5}},
            {"kind": "comment", "id": "b", "ref": "v", "text": "it is what it is", "meta": {"like_count": 2}}]
    corpus = tmp_path / "items.json"
    corpus.write_text(_j.dumps(rows), encoding="utf-8")
    script = tmp_path / "m.py"
    script.write_text(
        "import sys, json\n"
        "texts = json.loads(sys.stdin.read())\n"
        "print(json.dumps([{'compound': -0.5, 'label': 'sarcastic'} for _ in texts]))\n",
        encoding="utf-8")
    cmd = f'"{sys.executable}" "{script}"'
    assert main(["run", str(corpus), "--model", cmd, "--model-ref", "test/1", "--verify"]) == 0
    out = _j.loads(capsys.readouterr().out)
    assert out["verified"] is True                     # model overlay never breaks verification
    assert out["receipt"]["model_ref"] == "test/1"
    assert any(m["label"] == "sarcastic" for m in out["model_layer"])
