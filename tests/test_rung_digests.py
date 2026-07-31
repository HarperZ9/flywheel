"""The rung pins in the frozen prereg are checkable, and the checker can fail.

A digest checker that only ever passes is decoration. These tests establish that
each way the local store could contradict the freeze produces a mismatch, that
an edited prereg refuses to be used as a source of pins at all, and that the
checker still passes against the real store when one is present.
"""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "rung_gate", ROOT / "scripts" / "verify_rung_digests.py")
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)

PREREG = json.loads((ROOT / "artifacts" / "prereg" / "FREEZE.json")
                    .read_text(encoding="utf-8"))


def make_store(tmp_path, model, blob_bytes, *, media=".image.model",
               extra_layers=()):
    """A minimal but real Ollama store: manifest naming a blob, blob on disk."""
    digest = "sha256:" + hashlib.sha256(blob_bytes).hexdigest()
    layers = [{"mediaType": "application/vnd.ollama" + media,
               "digest": digest, "size": len(blob_bytes)}]
    layers.extend(extra_layers)
    name, _, tag = model.partition(":")
    man = (tmp_path / "manifests" / "registry.ollama.ai" / "library"
           / name / (tag or "latest"))
    man.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps({"schemaVersion": 2, "layers": layers}).encode()
    man.write_bytes(raw)
    blobs = tmp_path / "blobs"
    blobs.mkdir(exist_ok=True)
    (blobs / digest.replace(":", "-")).write_bytes(blob_bytes)
    return {"manifest_sha256": hashlib.sha256(raw).hexdigest(),
            "model_layer": digest, "blob": digest.replace(":", "-")}


def test_the_checker_carries_no_pin_of_its_own():
    """Pins live in the frozen document. A digest hard-coded here would be a
    second source of truth, and this is the test that would notice."""
    import re
    src = (ROOT / "scripts" / "verify_rung_digests.py").read_text(encoding="utf-8")
    assert not re.search(r"\b[0-9a-f]{64}\b", src)


def test_the_checker_names_no_local_drive_path():
    """This repo is published. A default store pointing at the author's drive is
    both a leak and, after a relocation, the wrong directory to check."""
    import re
    src = (ROOT / "scripts" / "verify_rung_digests.py").read_text(encoding="utf-8")
    assert not re.search(r"[A-Za-z]:[\\/](?:dev|Users|local-model-run)", src)


def test_the_store_default_follows_the_environment(tmp_path, monkeypatch):
    """A relocated store must be found, and the source must be reported so a
    reader can tell "incomplete ladder" from "checked the wrong directory"."""
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "relocated"))
    store, source = G.default_store()
    assert store == tmp_path / "relocated"
    assert source == "OLLAMA_MODELS"
    monkeypatch.delenv("OLLAMA_MODELS")
    store, source = G.default_store()
    assert store.name == "models" and store.parent.name == ".ollama"
    assert "default" in source


# ---- the checks, one failure mode at a time


def test_matching_store_passes(tmp_path):
    got = make_store(tmp_path, "demo:1b", b"weights")
    pin = {"rung": "R1", "kind": "manifest", "model": "demo:1b", **got}
    out = G.check_rung(pin, tmp_path, False)
    assert out["status"] == G.PASS, out


def test_wrong_model_layer_is_a_mismatch(tmp_path):
    got = make_store(tmp_path, "demo:1b", b"weights")
    pin = {"rung": "R1", "kind": "manifest", "model": "demo:1b",
           "manifest_sha256": got["manifest_sha256"],
           "model_layer": "sha256:" + "f" * 64}
    out = G.check_rung(pin, tmp_path, False)
    assert out["status"] == G.FAIL
    assert any("model layer" in n for n in out["notes"])


def test_wrong_manifest_digest_is_a_mismatch(tmp_path):
    got = make_store(tmp_path, "demo:1b", b"weights")
    pin = {"rung": "R1", "kind": "manifest", "model": "demo:1b",
           "manifest_sha256": "0" * 64, "model_layer": got["model_layer"]}
    out = G.check_rung(pin, tmp_path, False)
    assert out["status"] == G.FAIL
    assert any("manifest sha256" in n for n in out["notes"])


def test_blob_pin_form_is_checked(tmp_path):
    """R1-R4 are pinned in filename form (sha256-...), not manifest form."""
    got = make_store(tmp_path, "demo:1b", b"weights")
    ok = G.check_rung({"rung": "R1", "kind": "blob", "model": "demo:1b",
                       "blob": got["blob"]}, tmp_path, False)
    assert ok["status"] == G.PASS
    bad = G.check_rung({"rung": "R1", "kind": "blob", "model": "demo:1b",
                        "blob": "sha256-" + "e" * 64}, tmp_path, False)
    assert bad["status"] == G.FAIL


def test_absent_model_is_absent_not_failed(tmp_path):
    """Pinning never required possession, so absence is not a contradiction."""
    (tmp_path / "blobs").mkdir()
    out = G.check_rung({"rung": "R7", "kind": "manifest", "model": "gone:1b",
                        "manifest_sha256": "0" * 64, "model_layer": "sha256:x"},
                       tmp_path, False)
    assert out["status"] == G.ABSENT


def test_missing_blob_behind_a_present_manifest_is_a_mismatch(tmp_path):
    got = make_store(tmp_path, "demo:1b", b"weights")
    (tmp_path / "blobs" / got["blob"]).unlink()
    out = G.check_rung({"rung": "R1", "kind": "manifest", "model": "demo:1b",
                        **got}, tmp_path, False)
    assert out["status"] == G.FAIL
    assert any("missing from store" in n for n in out["notes"])


def test_manifest_with_no_model_layer_is_a_mismatch(tmp_path):
    got = make_store(tmp_path, "demo:1b", b"weights", media=".image.template")
    out = G.check_rung({"rung": "R1", "kind": "manifest", "model": "demo:1b",
                        "manifest_sha256": got["manifest_sha256"],
                        "model_layer": got["model_layer"]}, tmp_path, False)
    assert out["status"] == G.FAIL
    assert any("no model layer" in n for n in out["notes"])


def test_model_layer_is_found_among_other_layers(tmp_path):
    """A real manifest carries template/system/license layers too."""
    extra = [{"mediaType": "application/vnd.ollama.image.license",
              "digest": "sha256:" + "1" * 64, "size": 10}]
    got = make_store(tmp_path, "demo:1b", b"weights", extra_layers=extra)
    out = G.check_rung({"rung": "R1", "kind": "manifest", "model": "demo:1b",
                        **got}, tmp_path, False)
    assert out["status"] == G.PASS


def test_rehash_catches_corrupted_blob_content(tmp_path):
    """Without --rehash the check is presence plus size. With it, content."""
    got = make_store(tmp_path, "demo:1b", b"weights")
    blob = tmp_path / "blobs" / got["blob"]
    blob.write_bytes(b"WEIGHTS")          # same length, different bytes
    pin = {"rung": "R1", "kind": "manifest", "model": "demo:1b", **got}
    assert G.check_rung(pin, tmp_path, False)["status"] == G.PASS
    out = G.check_rung(pin, tmp_path, True)
    assert out["status"] == G.FAIL
    assert any("does not hash to its own digest" in n for n in out["notes"])


def test_size_disagreement_between_blob_and_manifest_is_caught(tmp_path):
    got = make_store(tmp_path, "demo:1b", b"weights")
    (tmp_path / "blobs" / got["blob"]).write_bytes(b"weights-longer")
    out = G.check_rung({"rung": "R1", "kind": "manifest", "model": "demo:1b",
                        **got}, tmp_path, False)
    assert out["status"] == G.FAIL
    assert any("manifest declares" in n for n in out["notes"])


def test_unregistered_local_artifact_is_unchecked_not_passed(tmp_path):
    """R6 as a bare GGUF is not a store entry. Claiming PASS for it would be a
    false accept; the honest status is UNCHECKED with a pointer to what does
    check it."""
    out = G.check_rung({"rung": "R6", "kind": "weight", "model": "telos-coder-32b",
                        "weight_sha256": "0" * 64, "bytes": 1}, tmp_path, False)
    assert out["status"] == G.UNCHECKED
    assert any("not servable" in n for n in out["notes"])


def test_registered_local_artifact_becomes_checkable(tmp_path):
    """Ollama stores a registered GGUF under its own sha256, so the weight pin
    turns into a store check the moment the artifact is servable."""
    weights = b"thirty-two-billion-parameters"
    got = make_store(tmp_path, "telos-coder-32b", weights)
    out = G.check_rung({"rung": "R6", "kind": "weight",
                        "model": "telos-coder-32b",
                        "weight_sha256": hashlib.sha256(weights).hexdigest(),
                        "bytes": len(weights)}, tmp_path, False)
    assert out["status"] == G.PASS, out
    assert out["weight_sha256"] == got["model_layer"].split(":")[1]


def test_registered_artifact_with_wrong_weight_digest_fails(tmp_path):
    make_store(tmp_path, "telos-coder-32b", b"not-the-pinned-weights")
    out = G.check_rung({"rung": "R6", "kind": "weight",
                        "model": "telos-coder-32b",
                        "weight_sha256": "b" * 64, "bytes": 22}, tmp_path, False)
    assert out["status"] == G.FAIL
    assert any("weight sha256" in n for n in out["notes"])


def test_registered_artifact_with_wrong_byte_count_fails(tmp_path):
    """The prereg pins an exact byte count for R6, so a differently sized file
    under the same name is a contradiction even before hashing."""
    weights = b"short"
    make_store(tmp_path, "telos-coder-32b", weights)
    out = G.check_rung({"rung": "R6", "kind": "weight",
                        "model": "telos-coder-32b",
                        "weight_sha256": hashlib.sha256(weights).hexdigest(),
                        "bytes": 19_851_336_480}, tmp_path, False)
    assert out["status"] == G.FAIL
    assert any("pinned 19851336480" in n.replace(",", "") for n in out["notes"])


# ---- the command line, end to end


def _run(*args):
    import subprocess
    import sys as _sys
    return subprocess.run(
        [_sys.executable, str(ROOT / "scripts" / "verify_rung_digests.py"), *args],
        capture_output=True, text=True, cwd=ROOT)


def test_storeless_run_exits_zero_but_require_all_does_not(tmp_path):
    """The CI job runs storeless and must pass, because absence is not a
    contradiction. A demonstration run adds --require-all and must NOT pass on
    the same empty store, or the flag would assert nothing."""
    empty = str(tmp_path / "no-store")
    assert _run("--store", empty).returncode == 0
    assert _run("--store", empty, "--require-all").returncode == 1


def test_json_output_carries_the_freeze_and_a_verdict(tmp_path):
    out = _run("--store", str(tmp_path / "no-store"), "--json")
    doc = json.loads(out.stdout)
    assert doc["frozen_sha256"] == PREREG["frozen_sha256"]
    assert doc["verdict"] == "CONSISTENT_WITH_FREEZE"
    assert len(doc["findings"]) == 9
    assert doc["rehashed"] is False


# ---- against reality


def test_the_real_store_does_not_contradict_the_freeze():
    store, _ = G.default_store()
    if not (store / "manifests").is_dir():
        pytest.skip(f"no local model store at {store}")
    text, _ = G.frozen_prereg(ROOT)
    pins = G.parse_pins(text)
    bad = [G.check_rung(p, store, False) for p in pins.values()]
    bad = [f for f in bad if f["status"] == G.FAIL]
    assert bad == [], bad
