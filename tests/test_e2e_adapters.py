import json
from pathlib import Path

import pytest

from harness.cross_harness_process import ProcessOutcome
from harness.e2e_adapters import (
    CliProcessJourneyAdapter,
    MCPStdioJourneyAdapter,
    validate_gather_context_schema,
)
from harness.mcp_client import MCPError


def test_cli_adapter_uses_cross_harness_run_process_and_parses_json(monkeypatch, tmp_path):
    calls = []

    def fake_run_process(argv, *, cwd, stdin_text, timeout_seconds):
        calls.append((argv, cwd, stdin_text, timeout_seconds))
        return ProcessOutcome(0, '{"ok": true}', "", 7, False)

    monkeypatch.setattr("harness.e2e_adapters.run_process", fake_run_process)
    adapter = CliProcessJourneyAdapter(Path("C:/tool/gather.exe"), timeout_seconds=3)

    result = adapter.run_json(["docs", "sample.txt", "--json"], cwd=tmp_path, step_id="acquire")

    assert calls == [([str(Path("C:/tool/gather.exe")), "docs", "sample.txt", "--json"], tmp_path, "", 3)]
    assert result.status == "completed"
    assert result.parsed_json == {"ok": True}


def test_gather_context_schema_validation_requires_real_selection_contract():
    tools = [{
        "name": "gather.context",
        "inputSchema": {
            "type": "object",
            "required": ["corpus"],
            "properties": {
                "corpus": {"type": "string"},
                "select": {"type": "array"},
                "expected_corpus_digest": {"type": "string"},
            },
        },
    }]

    validate_gather_context_schema(tools)

    missing_digest = json.loads(json.dumps(tools))
    del missing_digest[0]["inputSchema"]["properties"]["expected_corpus_digest"]
    with pytest.raises(ValueError, match="expected_corpus_digest"):
        validate_gather_context_schema(missing_digest)


def test_mcp_adapter_closes_client_when_schema_validation_fails(monkeypatch, tmp_path):
    closed = []

    class FakeClient:
        def __init__(self, *_args, **_kwargs):
            pass
        def start(self):
            return self
        def list_tools(self):
            return [{"name": "other", "inputSchema": {"type": "object"}}]
        def close(self):
            closed.append(True)

    monkeypatch.setattr("harness.e2e_adapters.MCPClient", FakeClient)
    adapter = MCPStdioJourneyAdapter(Path("C:/tool/gather.exe"), cwd=tmp_path, timeout_seconds=3)

    with pytest.raises(ValueError, match="gather.context"):
        adapter.start()

    assert closed == [True]


def test_mcp_adapter_classifies_timeout_and_records_elapsed(monkeypatch, tmp_path):
    class FakeClient:
        def __init__(self, *_args, **_kwargs):
            pass
        def start(self):
            return self
        def list_tools(self):
            return [{
                "name": "gather.context",
                "inputSchema": {"type": "object", "required": ["corpus"], "properties": {
                    "corpus": {"type": "string"}, "select": {"type": "array"},
                    "expected_corpus_digest": {"type": "string"}}},
            }, {"name": "gather.run", "inputSchema": {"type": "object", "properties": {"config": {"type": "object"}}}}]
        def call_text(self, *_args, **_kwargs):
            raise MCPError("no response within 3s")
        def stderr_tail(self):
            return ""
        def close(self):
            pass

    monkeypatch.setattr("harness.e2e_adapters.MCPClient", FakeClient)
    adapter = MCPStdioJourneyAdapter(Path("C:/tool/gather.exe"), cwd=tmp_path, timeout_seconds=3)

    result = adapter.call_json("gather.context", {"corpus": "x"}, step_id="timeout")

    assert result.status == "failed"
    assert result.timed_out is True
    assert result.elapsed_ms >= 0


def test_mcp_adapter_caps_response_before_json_parse(monkeypatch, tmp_path):
    class FakeClient:
        def __init__(self, *_args, **_kwargs):
            pass
        def start(self):
            return self
        def list_tools(self):
            return [{
                "name": "gather.context",
                "inputSchema": {"type": "object", "required": ["corpus"], "properties": {
                    "corpus": {"type": "string"}, "select": {"type": "array"},
                    "expected_corpus_digest": {"type": "string"}}},
            }, {"name": "gather.run", "inputSchema": {"type": "object", "properties": {"config": {"type": "object"}}}}]
        def call_text(self, *_args, **_kwargs):
            return {"ok": True, "text": "{" + '"x":"' + ("a" * 1_100_000) + '"}', "raw": {}}
        def stderr_tail(self):
            return ""
        def close(self):
            pass

    monkeypatch.setattr("harness.e2e_adapters.MCPClient", FakeClient)
    adapter = MCPStdioJourneyAdapter(Path("C:/tool/gather.exe"), cwd=tmp_path, timeout_seconds=3)

    result = adapter.call_json("gather.context", {"corpus": "x"}, step_id="oversized")

    assert result.status == "failed"
    assert result.malformed_output is True
    assert result.evidence["reason"] == "mcp_response_too_large"
    assert len(result.stdout.encode("utf-8")) < 5000
