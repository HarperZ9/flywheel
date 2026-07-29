"""demo_proposer.py: OllamaProposer.generate() against a faked /api/generate.

No test touches the network or a GPU -- every HTTP call goes through an
injected `fetch(request, timeout=...)`, mirroring the fake-fetch seam
tests/test_determinism_pins.py already uses for determinism_pins.py.

The load-bearing tests are the two at the bottom: they run
scripts/demo_proposer.OllamaProposer through harness/pool.py's real `fill`,
with a fetch that fails on one seed, and assert the failure lands in the
slot's `error` field rather than being cached as a literal "None" candidate.
That is the actual contract pool.fill implements (see the module docstring),
not the one a cursory reading of `fill` might suggest.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "demo_proposer", ROOT / "scripts" / "demo_proposer.py")
DP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(DP)

sys.path.insert(0, str(ROOT))
from harness.pool import fill  # noqa: E402


class FakeResponse:
    """A urlopen()-shaped stand-in: context manager, .read(), .status."""

    def __init__(self, payload: dict, status: int = 200):
        self._data = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fetch_returning(payload, status=200):
    def fetch(request, timeout=None):
        return FakeResponse(payload, status=status)
    return fetch


def fetch_raising(exc):
    def fetch(request, timeout=None):
        raise exc
    return fetch


# --- request shape -----------------------------------------------------------

def test_generate_posts_model_prompt_stream_false_and_sampler_options():
    seen = {}

    def fetch(request, timeout=None):
        seen["request"] = request
        seen["timeout"] = timeout
        body = json.loads(request.data.decode("utf-8"))
        seen["body"] = body
        return FakeResponse({"response": "ok"})

    proposer = DP.OllamaProposer("qwen2.5:0.5b", host="example.invalid:11434",
                                 fetch=fetch)
    result = proposer.generate("hello", seed=7, temperature=0.3,
                               max_new_tokens=128)

    assert result.text == "ok"
    assert seen["body"] == {
        "model": "qwen2.5:0.5b", "prompt": "hello", "stream": False,
        "options": {"seed": 7, "temperature": 0.3, "num_predict": 128},
    }
    assert seen["request"].get_method() == "POST"
    assert seen["request"].full_url == "http://example.invalid:11434/api/generate"


def test_timeout_is_600_seconds_a_cold_load_outruns_30():
    seen = {}

    def fetch(request, timeout=None):
        seen["timeout"] = timeout
        return FakeResponse({"response": "ok"})

    DP.OllamaProposer("m", host="h:1", fetch=fetch).generate(
        "p", seed=0, temperature=0.0, max_new_tokens=1)
    assert seen["timeout"] == 600


# --- host resolution -----------------------------------------------------------

def test_default_host_reads_ollama_host_env_var(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "10.0.0.5:9999")
    assert DP.default_base_url() == "http://10.0.0.5:9999"


def test_default_host_falls_back_to_localhost_11434(monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    assert DP.default_base_url() == "http://127.0.0.1:11434"


def test_explicit_host_wins_over_env_var(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "should-not-be-used:1")
    assert DP.default_base_url("192.168.1.1:11434") == "http://192.168.1.1:11434"


def test_a_host_already_carrying_a_scheme_is_left_alone():
    assert DP.default_base_url("https://remote.example:443") == "https://remote.example:443"


# --- failure paths: every one must RAISE, matching pool.fill's contract ------

def test_http_error_raises_ollama_generation_error():
    exc = urllib.error.HTTPError(
        "http://h/api/generate", 500, "boom", {}, io.BytesIO(b"server exploded"))
    proposer = DP.OllamaProposer("m", host="h:1", fetch=fetch_raising(exc))
    with pytest.raises(DP.OllamaGenerationError, match="HTTP 500"):
        proposer.generate("p", seed=0, temperature=0.0, max_new_tokens=1)


def test_url_error_raises_ollama_generation_error():
    exc = urllib.error.URLError("connection refused")
    proposer = DP.OllamaProposer("m", host="h:1", fetch=fetch_raising(exc))
    with pytest.raises(DP.OllamaGenerationError, match="could not reach ollama"):
        proposer.generate("p", seed=0, temperature=0.0, max_new_tokens=1)


def test_non_200_status_raises_even_without_an_httperror():
    proposer = DP.OllamaProposer(
        "m", host="h:1", fetch=fetch_returning({"response": "x"}, status=503))
    with pytest.raises(DP.OllamaGenerationError, match="503"):
        proposer.generate("p", seed=0, temperature=0.0, max_new_tokens=1)


def test_non_json_body_raises():
    def fetch(request, timeout=None):
        class R:
            status = 200
            def read(self):
                return b"not json at all"
            def __enter__(self):
                return self
            def __exit__(self, *exc):
                return False
        return R()

    proposer = DP.OllamaProposer("m", host="h:1", fetch=fetch)
    with pytest.raises(DP.OllamaGenerationError, match="non-JSON"):
        proposer.generate("p", seed=0, temperature=0.0, max_new_tokens=1)


def test_an_ollama_reported_error_field_raises():
    proposer = DP.OllamaProposer(
        "m", host="h:1", fetch=fetch_returning({"error": "model not found"}))
    with pytest.raises(DP.OllamaGenerationError, match="model not found"):
        proposer.generate("p", seed=0, temperature=0.0, max_new_tokens=1)


def test_a_missing_response_field_raises_rather_than_yielding_text_none():
    """The critical case: if this returned .text=None instead of raising,
    pool.fill's `str(res.text)` would silently cache the four-character
    string "None" as if it were a real candidate."""
    proposer = DP.OllamaProposer("m", host="h:1", fetch=fetch_returning({}))
    with pytest.raises(DP.OllamaGenerationError, match="no string 'response'"):
        proposer.generate("p", seed=0, temperature=0.0, max_new_tokens=1)


def test_a_null_response_field_raises_rather_than_yielding_text_none():
    proposer = DP.OllamaProposer(
        "m", host="h:1", fetch=fetch_returning({"response": None}))
    with pytest.raises(DP.OllamaGenerationError, match="no string 'response'"):
        proposer.generate("p", seed=0, temperature=0.0, max_new_tokens=1)


# --- the actual contract: run it through pool.fill ---------------------------

TASKS = [{"task_id": "t1", "prompt": "p1"}, {"task_id": "t2", "prompt": "p2"}]


def _fp(k=2):
    return dict(model_ref="qwen2.5:0.5b", model_digest="sha256:" + "aa" * 32,
               engine="ollama", engine_version="0.32.3", quantization="Q4_K_M",
               k=k, seeds=list(range(k)), temperatures=[0.0] + [0.2] * (k - 1),
               max_new_tokens=64, prompt_template_sha256="sha256:" + "bb" * 32)


def test_a_raising_generate_is_recorded_in_its_slot_not_swallowed(tmp_path):
    calls = {"n": 0}

    def fetch(request, timeout=None):
        calls["n"] += 1
        body = json.loads(request.data.decode("utf-8"))
        if body["options"]["seed"] == 1:
            raise urllib.error.URLError("connection reset")
        return FakeResponse({"response": f"cand-seed-{body['options']['seed']}"})

    proposer = DP.OllamaProposer("qwen2.5:0.5b", host="h:1", fetch=fetch)
    from harness.pool import Pool
    fill(TASKS, proposer, _fp(k=2), tmp_path)

    pool = Pool(tmp_path)
    slots = pool.slots("t1")
    assert slots[0]["candidate_sha256"] is not None
    assert slots[0]["error"] is None
    assert slots[1]["candidate_sha256"] is None
    assert "connection reset" in slots[1]["error"]
    # the surviving slot is a real candidate, never the string "None"
    assert pool.text(slots[0]["candidate_sha256"]) == "cand-seed-0"


def test_every_slot_still_generates_even_when_one_model_response_is_malformed(tmp_path):
    """No early stopping survives a mid-run failure: pool.fill's k=4 (here
    k=2) guarantee holds even when a slot in the middle raises."""

    def fetch(request, timeout=None):
        body = json.loads(request.data.decode("utf-8"))
        seed = body["options"]["seed"]
        if seed == 0:
            return FakeResponse({"response": "ok0"})
        return FakeResponse({"not_response": "oops"})  # triggers the raise path

    proposer = DP.OllamaProposer("qwen2.5:0.5b", host="h:1", fetch=fetch)
    from harness.pool import Pool
    doc = fill(TASKS, proposer, _fp(k=2), tmp_path)

    assert doc["n_tasks"] == 2
    pool = Pool(tmp_path)
    for t in ("t1", "t2"):
        slots = pool.slots(t)
        assert len(slots) == 2, "both slots attempted despite the failure"
        assert slots[0]["candidate_sha256"] is not None
        assert slots[1]["candidate_sha256"] is None
        assert "no string 'response'" in slots[1]["error"]
