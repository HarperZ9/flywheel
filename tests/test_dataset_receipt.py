"""Falsifiers for the dataset receipt — corpus -> shards -> checkpoint chain.

The two the increment lives or dies by:
  1. DRIFT fires: mutate ONE corpus file, re-verify, the receipt must flag the
     corpus layer drifted (localized — allowlist/manifest layers stay MATCH).
  2. Determinism: byte-identical inputs re-derive the IDENTICAL receipt.
Plus the privacy invariant (no source path ever appears in the artifact) and
fail-closed verification (gone inputs -> UNVERIFIABLE, never assumed MATCH).
"""
import json

import pytest

from dataset.receipt import (build_receipt, verify_receipt, write_receipt,
                             RECEIPT_NAME)


@pytest.fixture
def corpus(tmp_path):
    base = tmp_path / "dev"
    (base / "proj").mkdir(parents=True)
    files = {"proj/alpha_source.py": "def f():\n    return 1\n",
             "proj/beta_notes.md": "# notes\n",
             "proj/gamma_conf.toml": "[x]\ny = 2\n"}
    for rel, text in files.items():
        (base / rel).write_text(text, encoding="utf-8")
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("\n".join(
        json.dumps({"path": rel, "bytes": len(t), "ext": rel.split(".")[-1]})
        for rel, t in files.items()), encoding="utf-8")
    allowlist = tmp_path / "allowlist.yaml"
    allowlist.write_text("include:\n  - proj/**\n", encoding="utf-8")
    return {"base": base, "manifest": manifest, "allowlist": allowlist}


def _build(c, **kw):
    return build_receipt(allowlist=c["allowlist"], manifest=c["manifest"],
                         base=c["base"], tokenizer_ref="qwen2.5-coder-14b", **kw)


def _verify(r, c, **kw):
    return verify_receipt(r, allowlist=c["allowlist"], manifest=c["manifest"],
                          base=c["base"], **kw)


def test_determinism_identical_inputs_identical_receipt(corpus):
    assert _build(corpus) == _build(corpus)


def test_clean_chain_verifies_match(corpus):
    v = _verify(_build(corpus), corpus)
    assert v["verdict"] == "MATCH"
    assert set(v["layers"].values()) == {"MATCH"}


def test_falsifier_one_mutated_file_fires_corpus_drift(corpus):
    r = _build(corpus)
    f = corpus["base"] / "proj/alpha_source.py"
    f.write_text("def f():\n    return 999\n", encoding="utf-8")
    v = _verify(r, corpus)
    assert v["verdict"] == "DRIFT"
    assert v["drifted_layers"] == ["corpus"]          # localized
    assert v["layers"]["allowlist"] == "MATCH"
    assert v["layers"]["manifest"] == "MATCH"
    # restore byte-identical -> the chain re-verifies
    f.write_text("def f():\n    return 1\n", encoding="utf-8")
    assert _verify(r, corpus)["verdict"] == "MATCH"


def test_falsifier_tampered_manifest_fires_manifest_drift(corpus):
    r = _build(corpus)
    corpus["manifest"].write_text(
        corpus["manifest"].read_text(encoding="utf-8") + "\n" +
        json.dumps({"path": "proj/beta_notes.md", "bytes": 8, "ext": "md"}),
        encoding="utf-8")
    v = _verify(r, corpus)
    assert v["verdict"] == "DRIFT"
    assert "manifest" in v["drifted_layers"]


def test_privacy_no_source_path_in_the_artifact(corpus, tmp_path):
    ckpt = tmp_path / "checkpoint-2020"
    ckpt.mkdir()
    (ckpt / "adapter_config.json").write_text('{"r": 16}', encoding="utf-8")
    r = _build(corpus, checkpoint_dir=ckpt)
    serialized = json.dumps(r)
    for leak in ("alpha_source", "beta_notes", "gamma_conf", "proj/", "dev"):
        assert leak not in serialized, f"source identity leaked: {leak}"
    p = write_receipt(r, ckpt)
    assert p.name == RECEIPT_NAME
    on_disk = p.read_text(encoding="utf-8")
    assert "alpha_source" not in on_disk


def test_pack_and_checkpoint_layers_verify_and_drift(corpus, tmp_path):
    packed = tmp_path / "packed"
    packed.mkdir()
    (packed / "shard_00000.npy").write_bytes(b"\x01\x02\x03\x04")
    (packed / "PACK_COMPLETE.json").write_text('{"shards": 1}', encoding="utf-8")
    ckpt = tmp_path / "checkpoint-2020"
    ckpt.mkdir()
    (ckpt / "adapter_config.json").write_text('{"r": 16}', encoding="utf-8")
    (ckpt / "adapter_model.safetensors").write_bytes(b"\x00" * 64)
    r = _build(corpus, packed_dir=packed, checkpoint_dir=ckpt)
    v = _verify(r, corpus, packed_dir=packed, checkpoint_dir=ckpt)
    assert v["verdict"] == "MATCH"
    # a silently re-quantized/retouched shard must fire
    (packed / "shard_00000.npy").write_bytes(b"\x01\x02\x03\x05")
    v2 = _verify(r, corpus, packed_dir=packed, checkpoint_dir=ckpt)
    assert v2["verdict"] == "DRIFT" and v2["drifted_layers"] == ["pack"]


def test_failclosed_gone_inputs_are_unverifiable_not_match(corpus, tmp_path):
    packed = tmp_path / "packed"
    packed.mkdir()
    (packed / "PACK_COMPLETE.json").write_text('{"shards": 0}', encoding="utf-8")
    r = _build(corpus, packed_dir=packed)
    # verifier is not given the packed dir -> that layer cannot be confirmed
    v = _verify(r, corpus)
    assert v["layers"]["pack"] == "UNVERIFIABLE"
    assert v["verdict"] == "UNVERIFIABLE"
    # and a deleted allowlist is UNVERIFIABLE, not MATCH
    corpus["allowlist"].unlink()
    v2 = _verify(r, corpus, packed_dir=packed)
    assert v2["layers"]["allowlist"] == "UNVERIFIABLE"
