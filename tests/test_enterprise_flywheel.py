"""The flywheel is model-agnostic: it wraps ENTERPRISE models too.

The verified-inference loop does not care whose weights propose — a cheap local
14B or a frontier enterprise endpoint. This mocks an OpenAI-compatible endpoint
(fenced code, like a real enterprise model returns) and drives the SAME loop:
propose (enterprise) -> extract -> verify (pytest oracle) -> witness -> accept.
Proves 'ship what enterprise models have, and more' — the harness adds the
verification layer on top of any model.
"""
import io
import json
from pathlib import Path

import pytest

from harness.proposer import EnterpriseProposer
from harness.oracle import PytestOracle
from harness.loop import run_loop
from harness.witness import witness_envelope
from harness.task import load_task

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
# a real enterprise model wraps the answer in a markdown fence + prose:
ENTERPRISE_REPLY = ("Sure — here is the implementation:\n```python\n"
                    "def add(a, b):\n    return a + b\n```\nLet me know if you need tests.")


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


@pytest.fixture
def mock_openai(monkeypatch):
    captured = {}
    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["auth"] = req.headers.get("Authorization")
        payload = {"choices": [{"message": {"content": ENTERPRISE_REPLY}}]}
        return _Resp(json.dumps(payload).encode())
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    return captured


def test_enterprise_proposer_extracts_fenced_code(mock_openai):
    p = EnterpriseProposer(base_url="https://api.example.com/v1", model="gpt-frontier")
    out = p.generate("Implement add(a,b).", seed=0, temperature=0.0, max_new_tokens=64)
    assert out.text.strip() == "def add(a, b):\n    return a + b"   # fence + prose stripped
    assert out.model_ref == "enterprise:gpt-frontier"
    assert mock_openai["url"].endswith("/chat/completions")
    assert mock_openai["auth"] == "Bearer sk-test-not-real"


def test_flywheel_runs_end_to_end_on_an_enterprise_model(mock_openai, tmp_path):
    task = load_task(TASK_DIR, workdir=tmp_path / "w")
    p = EnterpriseProposer(base_url="https://api.example.com/v1", model="gpt-frontier")
    r = run_loop(task, p, PytestOracle(), envelopes_dir=tmp_path / "env")
    assert r.accepted and r.envelope.verdict == "PASS"
    assert r.envelope.model_ref == "enterprise:gpt-frontier"
    # the enterprise accept is re-witnessable exactly like a local one
    wv = witness_envelope(r.envelope, workdir=task.workdir, candidate_path=task.candidate_path)
    assert wv.verdict == "MATCH"
