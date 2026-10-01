"""Capture adapters: documented signals only, opaque fields by digest, gaps typed."""
import ast
import json
from pathlib import Path

import pytest

from harness.trace_observation import adapters
from harness.trace_observation.channel import A1R, A1S, A3, GapRecord, ReasoningRecord

FIX = Path(__file__).parent / "fixtures" / "trace_observation"
ADAPTER_DIR = Path(adapters.__file__).parent


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def cap(provider, name):
    f = load(name)
    return adapters.capture(provider, f["request"], f["response"], run_id="r1")


def test_anthropic_summarized_is_separate_model_summary_with_opaque_digests():
    c = cap("anthropic", "anthropic_summarized.json")
    d = c.record.to_dict()
    assert d["channel"] == "summary_separate_model" and d["access_class"] == A1S
    assert d["summarizer"] == "separate_model"
    assert d["reasoning_tokens_reported"] == "88"
    assert {o["name"] for o in d["opaque_fields"]} == {"signature", "redacted_thinking.data"}
    assert "PROVIDER_ENCRYPTED" in c.gap_codes()
    text = json.dumps(d)
    assert "SENTINEL" not in text and "The user asks" not in text  # digests only
    assert len(d["tool_calls"]) == 1


def test_anthropic_without_display_records_omitted_gap_not_silent_blank():
    c = cap("anthropic", "anthropic_omitted.json")
    assert c.record.access_class == "A0"
    assert c.record.to_dict()["channel"] == "none"
    assert "REASONING_OMITTED_BY_DEFAULT" in c.gap_codes()
    gap = next(g for g in c.gaps if g.gap_code == "REASONING_OMITTED_BY_DEFAULT")
    assert gap.scope == "local_setup"


@pytest.mark.parametrize("provider,name,channel,tokens", [
    ("openai", "openai_responses_summary.json", "summary_unknown_origin", "256"),
    ("xai", "xai_responses.json", "summary_unknown_origin", "140"),
    ("google", "gemini_thought_summary.json", "summary_unknown_origin", "77"),
    ("deepseek", "deepseek_reasoning_content.json", "raw", "30"),
    ("mistral", "mistral_thinkchunk.json", "unspecified_trace", "unknown"),
])
def test_each_provider_types_its_channel(provider, name, channel, tokens):
    c = cap(provider, name)
    d = c.record.to_dict()
    assert d["channel"] == channel
    assert d["reasoning_tokens_reported"] == tokens
    assert d["answer"]["sha256"]
    assert c.field_map, "every adapter names the paths it reads"
    for path, (source, conf) in c.field_map.items():
        assert conf in ("high", "moderate", "low"), path


def test_deepseek_raw_answer_logprobs_do_not_grant_a3_over_reasoning():
    c = cap("deepseek", "deepseek_reasoning_content.json")
    assert c.record.access_class == A1R
    assert A3 not in c.record.classes()
    assert c.record.to_dict()["logprobs_ref"] != "absent"


def test_recorded_qwen3_capture_is_raw_and_complete():
    c = cap("ollama", "ollama_qwen3_recorded.json")
    d = c.record.to_dict()
    assert d["channel"] == "raw" and d["truncated"] == "false"
    assert int(d["reasoning_text"]["bytes"]) > 5000
    assert c.gaps == []


def test_ollama_inline_think_span_is_split_and_truncation_flagged():
    c = adapters.capture("ollama", {}, {"response": "<think>half a thought", "done_reason": "length"},
                         run_id="r")
    assert c.record.truncated and "REASONING_TRUNCATED" in c.gap_codes()
    with_lp = adapters.capture("ollama", {}, {"thinking": "t", "response": "a", "done_reason": "stop",
                                              "logprobs": [{"token": "a", "logprob": -0.1}]}, run_id="r")
    assert A3 in with_lp.record.classes()


def test_unknown_provider_and_non_dict_response_refused():
    with pytest.raises(ValueError):
        adapters.capture("acme", {}, {}, run_id="r")
    with pytest.raises(ValueError):
        adapters.capture("openai", {}, "raw text", run_id="r")


def test_records_carry_no_floats_and_unknown_gap_codes_refused():
    rec = ReasoningRecord(run_id="r", turn_index=0, provider="x", sampling={"temperature": 0.6})
    def walk(v):
        assert not isinstance(v, float)
        if isinstance(v, dict):
            [walk(x) for x in v.values()]
        if isinstance(v, list):
            [walk(x) for x in v]
    walk(rec.to_dict())
    with pytest.raises(ValueError):
        GapRecord("MADE_UP", "c")


_FORBIDDEN_CALLS = {"b64decode", "urlsafe_b64decode", "decodebytes", "decrypt", "loads", "unhexlify"}


def test_no_adapter_decodes_or_parses_any_value():
    """Static boundary check: adapters never call a decoder or parser on anything."""
    for path in ADAPTER_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                assert name not in _FORBIDDEN_CALLS, f"{path.name} calls {name}"
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mods = [a.name for a in node.names] + [getattr(node, "module", "") or ""]
                assert not any(m in ("base64", "binascii", "cryptography", "zlib") for m in mods), path.name
