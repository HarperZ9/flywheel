"""Falsifiers for the Azure OpenAI, Bedrock and Vertex backends (no network)."""
import datetime as dt
import json

from harness import endpoints_cloud as ec
from harness.code_session.backends import build_agent


def test_sigv4_matches_the_aws_documented_example():
    h = ec.sigv4_headers(
        "GET", "https://iam.amazonaws.com/?Action=ListUsers&Version=2010-05-08", b"",
        region="us-east-1", service="iam", access_key="AKIDEXAMPLE",
        secret_key="wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
        now=dt.datetime(2015, 8, 30, 12, 36, 0),
        extra={"content-type": "application/x-www-form-urlencoded; charset=utf-8"})
    assert h["authorization"].endswith(
        "Signature=5d672d79c15b13162d9279b0855cfba6789a8edb4c82c400e06b5924a6f2b5d7")
    assert h["x-amz-date"] == "20150830T123600Z"


def _capture(reply):
    seen = {}

    def transport(method, url, headers, body, timeout):
        seen.update(url=url, headers=headers, body=json.loads(body))
        return 200, reply
    return seen, transport


def test_azure_sends_the_key_header_and_reads_tokens(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://r.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "az-key")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-dep")
    seen, transport = _capture({"choices": [{"message": {"content": "hi"}}],
                                "usage": {"prompt_tokens": 5, "completion_tokens": 1}})
    b = ec.AzureOpenAIBackend(transport=transport)
    assert b.health()
    resp = build_agent([b]).send("hello")
    assert seen["url"].startswith("https://r.openai.azure.com/openai/deployments/gpt-dep/chat/completions?api-version=")
    assert seen["headers"]["api-key"] == "az-key"
    assert resp["x_token_usage"] == {"input_tokens": 5, "output_tokens": 1}


def test_bedrock_signs_and_parses_converse(monkeypatch):
    for k, v in {"AWS_ACCESS_KEY_ID": "AKID", "AWS_SECRET_ACCESS_KEY": "secret",
                 "AWS_REGION": "us-west-2", "BEDROCK_MODEL": "anthropic.claude-x"}.items():
        monkeypatch.setenv(k, v)
    seen, transport = _capture({"output": {"message": {"content": [{"text": "ok"}]}},
                                "usage": {"inputTokens": 7, "outputTokens": 2}})
    resp = build_agent([ec.BedrockBackend(transport=transport)]).send("hello")
    assert seen["url"] == ("https://bedrock-runtime.us-west-2.amazonaws.com/model/"
                           "anthropic.claude-x/converse")
    assert seen["headers"]["authorization"].startswith("AWS4-HMAC-SHA256 Credential=AKID/")
    assert seen["body"]["messages"][0]["content"] == [{"text": "hello"}]
    assert resp["x_token_usage"] == {"input_tokens": 7, "output_tokens": 2}


def test_vertex_uses_the_access_token_and_refuses_without_one(monkeypatch):
    for k, v in {"VERTEX_PROJECT": "p1", "VERTEX_LOCATION": "us-central1",
                 "VERTEX_MODEL": "gemini-x"}.items():
        monkeypatch.setenv(k, v)
    seen, transport = _capture({"candidates": [{"content": {"parts": [{"text": "yo"}]}}]})
    b = ec.VertexBackend(transport=transport, token_source=lambda: "tok-v")
    build_agent([b]).send("hello")
    assert seen["headers"]["Authorization"] == "Bearer tok-v"
    assert "/projects/p1/locations/us-central1/publishers/google/models/gemini-x:generateContent" in seen["url"]
    none = ec.VertexBackend(transport=transport, token_source=lambda: "")
    import pytest
    from harness.local_agent import BackendError
    with pytest.raises(BackendError):
        none.chat([{"role": "user", "content": "x"}], system="", max_tokens=5, temperature=0, seed=0)


def test_backends_stay_off_without_settings(monkeypatch):
    for k in ("AZURE_OPENAI_ENDPOINT", "AWS_ACCESS_KEY_ID", "VERTEX_PROJECT", "BEDROCK_MODEL",
              "AZURE_OPENAI_DEPLOYMENT", "VERTEX_MODEL"):
        monkeypatch.delenv(k, raising=False)
    assert ec.cloud_backends() == []
