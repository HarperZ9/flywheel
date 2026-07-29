"""The determinism surface: captured as data, witnessed against a live server.

`determinism_pins.py` is the "what did the server say" half of the story;
Task 2's baseline is the "did it say the same thing twice" half. Covers
capture and witness only: nine rungs with no field silently omitted, a
witness that names the exact field when something drifts, the prereg
citation, a digest stable under key order. The fake `/api/show` fixture
mirrors Ollama 0.32.3's real shape (details + model_info, no digest, no
kv_cache_type). No test touches a network; every HTTP call is injected.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "determinism_pins", ROOT / "scripts" / "determinism_pins.py")
D = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(D)

# D's exec above put scripts/ on sys.path, so this plain import resolves too.
import determinism_baseline as DB  # noqa: E402

FREEZE = json.loads((ROOT / "artifacts" / "prereg" / "FREEZE.json")
                    .read_text(encoding="utf-8"))

BASE_URL = "http://example.invalid:11434"

class FakeResponse:
    """A urlopen()-shaped stand-in, shared by every urllib-level fake below."""
    def __init__(self, payload):
        self._data = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

def make_fake_fetch(version="0.3.14", quantization="Q4_K_M", fmt="gguf",
                    parameter_size="0.5B", context_length=4096, family="qwen2",
                    details=None, model_info=None):
    """A fetch(path, payload=None) that never touches the network, shaped
    like the real 0.32.3 /api/show: details + model_info, no digest field."""
    def fetch(path, payload=None):
        if path == "/api/version":
            return {"version": version}
        if path == "/api/show":
            assert isinstance(payload, dict) and "model" in payload, (
                "/api/show must be called with {'model': name}")
            shown_details = {"quantization_level": quantization, "format": fmt,
                             "parameter_size": parameter_size}
            shown_model_info = {f"{family}.context_length": context_length}
            return {"details": details if details is not None else shown_details,
                    "model_info": model_info if model_info is not None else shown_model_info}
        raise AssertionError(f"unexpected path {path!r}")
    return fetch

# ---- capture shape

def test_capture_builds_nine_rungs_from_the_frozen_prereg():
    models = D.default_models()
    assert len(models) == 9
    assert "telos-coder-32b" in models       # R6, weight-kind pin
    assert "telos-coder-14b" in models       # R4, blob-kind pin
    doc = D.capture(BASE_URL, models, fetch=make_fake_fetch())
    assert doc["schema"] == "flywheel.determinism-pins/v1"
    assert len(doc["rungs"]) == 9
    assert {r["model"] for r in doc["rungs"]} == set(models)

def test_absent_values_are_null_not_omitted():
    """A field the server never exposed is still a key, with value null --
    never silently missing, which would look like a typo in the reader."""
    doc = D.capture(BASE_URL, ["qwen2.5:0.5b"],
                    fetch=make_fake_fetch(details={}, model_info={}))
    rung = doc["rungs"][0]
    for field in ("quantization", "format", "parameter_size",
                  "context_length", "kv_cache_type"):
        assert field in rung and rung[field] is None, field
    assert rung["sampler"] == D.SAMPLER_TUPLE

def test_context_length_found_under_any_family_prefix():
    """The prefix varies by family; find the one key ending in the suffix."""
    rec = D.rung_record(BASE_URL, "m", fetch=make_fake_fetch(
        model_info={"llama.context_length": 8192}))
    assert rec["context_length"] == 8192

def test_runtime_record_shape():
    rt = D.runtime_record(BASE_URL, fetch=make_fake_fetch(version="0.9.1"))
    assert rt == {"engine": "ollama", "version": "0.9.1",
                  "host_os": rt["host_os"]}
    import platform
    assert rt["host_os"] == platform.system()

def test_does_not_prove_is_present_and_nonempty():
    doc = D.capture(BASE_URL, ["qwen2.5:0.5b"], fetch=make_fake_fetch())
    assert isinstance(doc["does_not_prove"], list)
    assert len(doc["does_not_prove"]) > 0
    assert all(isinstance(item, str) for item in doc["does_not_prove"])

def test_cites_prereg_sha256_matches_freeze():
    doc = D.capture(BASE_URL, ["qwen2.5:0.5b"], fetch=make_fake_fetch())
    assert doc["cites_prereg_sha256"] == FREEZE["frozen_sha256"]

# ---- sha256_of

def test_sha256_of_is_stable_under_key_order():
    a = {"z": 1, "a": {"y": 2, "x": 3}, "m": [3, 2, 1]}
    b = {"a": {"x": 3, "y": 2}, "m": [3, 2, 1], "z": 1}
    assert D.sha256_of(a) == D.sha256_of(b)

def test_sha256_of_changes_when_content_changes():
    a = {"x": 1}
    b = {"x": 2}
    assert D.sha256_of(a) != D.sha256_of(b)

def test_saved_file_bytes_hash_to_sha256_of(tmp_path):
    import hashlib
    doc = {"b": 1, "a": {"z": None, "y": [1, 2]}}
    p = tmp_path / "pins.json"
    D.save(doc, p)
    assert hashlib.sha256(p.read_bytes()).hexdigest() == D.sha256_of(doc)

# ---- witness: clean and each field named on drift

def _capture_and_save(tmp_path, fetch, models=("qwen2.5:0.5b", "telos-coder-32b")):
    doc = D.capture(BASE_URL, list(models), fetch=fetch)
    path = tmp_path / "determinism-pins.json"
    D.save(doc, path)
    return path, doc

def test_witness_is_clean_against_its_own_unchanged_capture(tmp_path):
    fetch = make_fake_fetch()
    path, _ = _capture_and_save(tmp_path, fetch)
    drift = D.witness(BASE_URL, path, fetch=fetch)
    assert drift == []

def test_witness_names_a_mutated_version(tmp_path):
    fetch = make_fake_fetch(version="0.3.14")
    path, _ = _capture_and_save(tmp_path, fetch)
    pinned = D.load(path)
    pinned["runtime"]["version"] = "9.9.9"
    D.save(pinned, path)

    drift = D.witness(BASE_URL, path, fetch=fetch)
    assert drift, "a mutated runtime version must be reported as drift"
    assert any("version" in d for d in drift), drift

def test_witness_names_a_mutated_sampler(tmp_path):
    fetch = make_fake_fetch()
    path, _ = _capture_and_save(tmp_path, fetch)
    pinned = D.load(path)
    pinned["rungs"][0]["sampler"] = dict(pinned["rungs"][0]["sampler"], temperature=1)
    D.save(pinned, path)

    drift = D.witness(BASE_URL, path, fetch=fetch)
    assert drift, "a mutated sampler tuple must be reported as drift"
    assert any("sampler" in d for d in drift), drift

def test_witness_names_a_mutated_context_length(tmp_path):
    fetch = make_fake_fetch(context_length=4096)
    path, _ = _capture_and_save(tmp_path, fetch)
    pinned = D.load(path)
    pinned["rungs"][0]["context_length"] = 99999
    D.save(pinned, path)

    drift = D.witness(BASE_URL, path, fetch=fetch)
    assert drift, "a mutated context_length must be reported as drift"
    assert any("context_length" in d for d in drift), drift

def test_witness_names_a_mutated_quantization(tmp_path):
    fetch = make_fake_fetch(quantization="Q4_K_M")
    path, _ = _capture_and_save(tmp_path, fetch)
    pinned = D.load(path)
    pinned["rungs"][0]["quantization"] = "Q8_0"
    D.save(pinned, path)

    drift = D.witness(BASE_URL, path, fetch=fetch)
    assert drift, "a mutated quantization must be reported as drift"
    assert any("quantization" in d for d in drift), drift

def test_witness_ignores_a_baselines_key(tmp_path):
    """Baselines are Task 2's own mode; present or not, never reported as drift."""
    fetch = make_fake_fetch()
    path, _ = _capture_and_save(tmp_path, fetch)
    pinned = D.load(path)
    pinned["baselines"] = {"qwen2.5:0.5b": {"n": 3, "digests": ["x", "x", "x"],
                                            "witnessed": True}}
    D.save(pinned, path)

    drift = D.witness(BASE_URL, path, fetch=fetch)
    assert drift == []

# ---- the default (real) fetch: GET for /api/version, POST for /api/show

def test_default_fetch_gets_version_and_posts_show(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(req)
        if req.full_url.endswith("/api/version"):
            assert req.data is None
            return FakeResponse({"version": "0.1.0"})
        if req.full_url.endswith("/api/show"):
            assert req.get_method() == "POST"
            body = json.loads(req.data.decode("utf-8"))
            assert body == {"model": "qwen2.5:0.5b"}
            return FakeResponse({"details": {"quantization_level": "Q4_K_M"},
                                 "model_info": {"qwen2.context_length": 2048}})
        raise AssertionError(f"unexpected url {req.full_url}")

    monkeypatch.setattr(D.urllib.request, "urlopen", fake_urlopen)
    fetch = D._default_fetch(BASE_URL)

    v = fetch("/api/version")
    assert v == {"version": "0.1.0"}

    s = fetch("/api/show", {"model": "qwen2.5:0.5b"})
    assert s["details"]["quantization_level"] == "Q4_K_M"
    assert s["model_info"]["qwen2.context_length"] == 2048
    assert len(calls) == 2
    assert calls[0].get_method() == "GET"

# ---- Task 2: repeat-run digest baseline (determinism_baseline.py)

def make_fake_generate_fetch(responses):
    """responses: {model: [text, ...]}, consumed in call order at /api/generate."""
    cursors = {model: iter(texts) for model, texts in responses.items()}

    def fetch(path, payload=None):
        assert path == "/api/generate"
        assert payload["stream"] is False
        assert payload["options"] == DB.SAMPLER_TUPLE
        return {"response": next(cursors[payload["model"]])}
    return fetch

def test_baseline_identical_texts_are_witnessed_true():
    import hashlib
    fetch = make_fake_generate_fetch({"qwen2.5:0.5b": ["12", "12", "12"]})
    rung = DB.baseline(BASE_URL, ["qwen2.5:0.5b"], n=3, fetch=fetch)["qwen2.5:0.5b"]
    assert rung["model"] == "qwen2.5:0.5b" and rung["n"] == 3
    assert len(rung["digests"]) == 3 and len(set(rung["digests"])) == 1
    assert rung["digests"][0] == hashlib.sha256(b"12").hexdigest()
    assert rung["witnessed"] is True

def test_baseline_differing_texts_are_witnessed_false_and_all_recorded():
    fetch = make_fake_generate_fetch({"qwen2.5:0.5b": ["12", "13", "12"]})
    rung = DB.baseline(BASE_URL, ["qwen2.5:0.5b"], n=3, fetch=fetch)["qwen2.5:0.5b"]
    assert rung["witnessed"] is False
    assert len(rung["digests"]) == 3, "every digest is recorded, none hidden"
    assert len(set(rung["digests"])) == 2

def test_baseline_respects_n():
    fetch = make_fake_generate_fetch({"qwen2.5:0.5b": ["12"] * 5})
    rung = DB.baseline(BASE_URL, ["qwen2.5:0.5b"], n=2, fetch=fetch)["qwen2.5:0.5b"]
    assert rung["n"] == 2 and len(rung["digests"]) == 2

def test_baseline_prompt_is_a_short_fixed_string():
    assert isinstance(DB.BASELINE_PROMPT, str) and 0 < len(DB.BASELINE_PROMPT) < 200

def test_cli_baseline_without_a_pins_file_exits_2(tmp_path, capsys):
    rc = D.main(["--baseline", "--pins-path", str(tmp_path / "missing.json")])
    assert rc == 2
    assert "--capture" in capsys.readouterr().err

def test_cli_baseline_merges_and_preserves_the_rest_of_the_doc(tmp_path, monkeypatch):
    fetch = make_fake_fetch()
    path, original = _capture_and_save(tmp_path, fetch, models=("qwen2.5:0.5b",))

    def fake_urlopen(req, timeout=None):
        body = json.loads(req.data.decode("utf-8"))
        assert body["model"] == "qwen2.5:0.5b" and body["options"] == D.SAMPLER_TUPLE
        return FakeResponse({"response": "391"})
    monkeypatch.setattr(D.urllib.request, "urlopen", fake_urlopen)

    rc = D.main(["--baseline", "--n", "2", "--pins-path", str(path), "--base-url", BASE_URL])
    assert rc == 0

    saved = D.load(path)
    for key in ("schema", "runtime", "rungs", "cites_prereg_sha256", "does_not_prove"):
        assert saved[key] == original[key], f"{key} must survive a --baseline merge"
    assert saved["baselines"]["qwen2.5:0.5b"]["n"] == 2
    assert saved["baselines"]["qwen2.5:0.5b"]["witnessed"] is True
    import hashlib; assert hashlib.sha256(path.read_bytes()).hexdigest() == D.sha256_of(saved)

def test_empty_rungs_pins_file_refuses_rather_than_witnessing_nothing(tmp_path):
    p = tmp_path / "pins.json"
    D.save({"schema": D.SCHEMA, "rungs": []}, p)
    assert D.main(["--baseline", "--pins-path", str(p)]) == 2

def test_zero_n_is_refused():
    with pytest.raises(ValueError):
        DB.baseline(BASE_URL, ["qwen2.5:0.5b"], n=0, fetch=lambda p, payload=None: {})
