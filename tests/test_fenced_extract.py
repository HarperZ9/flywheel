"""fenced_extract.py: extract_fenced_body, Extraction, and ExtractingProposer.

No network. Every case in the task's own TDD list gets one test, plus a
proof that a malformed body extracted from a fence is still refused by the
real, unmodified `harness.certificates.base.parse_certificate` -- the
extractor must never repair content, only slice out the envelope around it.

Loaded the same importlib way as tests/test_demo_proposer.py, since scripts/
is not a package.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "fenced_extract", ROOT / "scripts" / "fenced_extract.py")
FE = importlib.util.module_from_spec(_spec)
sys.modules["fenced_extract"] = FE   # dataclass field resolution needs this
_spec.loader.exec_module(FE)

from harness.certificates.base import parse_certificate  # noqa: E402


# --- extract_fenced_body: the six required cases -----------------------------

def test_a_json_tagged_fence_yields_the_inner_json_exactly():
    text = '```json\n{"a": 1, "b": 2}\n```'
    result = FE.extract_fenced_body(text)
    assert result.body == '{"a": 1, "b": 2}'
    assert result.fence_found is True
    assert result.fence_count == 1
    assert json.loads(result.body) == {"a": 1, "b": 2}


def test_a_fence_with_no_language_tag_works():
    text = '```\n{"a": 1}\n```'
    result = FE.extract_fenced_body(text)
    assert result.body == '{"a": 1}'
    assert result.fence_found is True
    assert result.fence_count == 1


def test_a_bare_unfenced_response_is_unchanged():
    text = '{"a": 1}'
    result = FE.extract_fenced_body(text)
    assert result.body == text
    assert result.fence_found is False
    assert result.fence_count == 0


def test_prose_before_and_after_a_fence_yields_only_the_fenced_content():
    text = 'Here is the certificate:\n```json\n{"a": 1}\n```\nThanks!'
    result = FE.extract_fenced_body(text)
    assert result.body == '{"a": 1}'
    assert "Here is the certificate" not in result.body
    assert "Thanks" not in result.body


def test_two_fences_takes_the_first_and_reports_the_count():
    """Documented choice: a response is read top to bottom, so the first
    fenced span wins over any later one. fence_count still says two were
    present, so a caller can see the choice mattered."""
    text = ('```json\n{"first": 1}\n```\nsome commentary in between\n'
           '```json\n{"second": 2}\n```')
    result = FE.extract_fenced_body(text)
    assert result.body == '{"first": 1}'
    assert result.fence_count == 2
    assert "second" not in result.body


def test_malformed_json_inside_a_fence_passes_through_unchanged():
    """The extractor never repairs content. What comes out of the fence is
    exactly as malformed as what went in, and the REAL, unmodified checker
    still refuses it downstream -- extraction only decodes the envelope."""
    text = '```json\n{"a": }\n```'
    result = FE.extract_fenced_body(text)
    assert result.body == '{"a": }'          # sliced verbatim, not repaired

    ok, cert, why = parse_certificate(result.body)
    assert ok is False
    assert cert == {}
    assert "not valid json" in why


def test_the_raw_field_always_holds_the_original_untouched_text():
    text = 'noise\n```json\n{"a": 1}\n```\nmore noise'
    result = FE.extract_fenced_body(text)
    assert result.raw == text


def test_a_non_string_input_is_returned_unchanged_in_body_and_raw():
    result = FE.extract_fenced_body(None)
    assert result.body is None
    assert result.raw is None
    assert result.fence_found is False


# --- a fenced body that itself parses and passes the real accept path -------

def test_extracted_body_from_a_realistic_fence_is_well_formed_json():
    """Mirrors the shape actually observed from the live pilot: a fenced
    zarankiewicz certificate. Confirms extraction, not just this test's own
    fixture, produces something parse_certificate accepts as valid JSON."""
    text = (
        '```json\n'
        '{\n'
        '  "m": 3, "n": 3, "s": 2, "t": 2,\n'
        '  "edges": [[0, 0], [0, 1], [1, 0]],\n'
        '  "edge_count": 3\n'
        '}\n'
        '```'
    )
    result = FE.extract_fenced_body(text)
    ok, cert, why = parse_certificate(result.body)
    assert ok is True, why
    assert cert["m"] == 3 and cert["edge_count"] == 3


# --- ExtractingProposer: the wiring point -------------------------------------

class _FakeInner:
    def __init__(self, texts):
        self._texts = list(texts)
        self.calls = []

    def generate(self, prompt, *, seed, temperature, max_new_tokens):
        self.calls.append((prompt, seed, temperature, max_new_tokens))

        class R:
            text = self._texts[len(self.calls) - 1]
        return R()


def test_extracting_proposer_returns_the_extracted_text_not_the_raw_one():
    inner = _FakeInner(['```json\n{"a": 1}\n```'])
    wrapped = FE.ExtractingProposer(inner)
    result = wrapped.generate("p", seed=0, temperature=0.0, max_new_tokens=10)
    assert result.text == '{"a": 1}'


def test_extracting_proposer_passes_through_an_unfenced_response_unchanged():
    inner = _FakeInner(['{"a": 1}'])
    wrapped = FE.ExtractingProposer(inner)
    result = wrapped.generate("p", seed=0, temperature=0.0, max_new_tokens=10)
    assert result.text == '{"a": 1}'


def test_extracting_proposer_logs_one_extraction_per_call_in_call_order():
    inner = _FakeInner(['{"a": 1}', '```\n{"b": 2}\n```'])
    wrapped = FE.ExtractingProposer(inner)
    wrapped.generate("p1", seed=0, temperature=0.0, max_new_tokens=10)
    wrapped.generate("p2", seed=1, temperature=0.1, max_new_tokens=10)
    assert len(wrapped.log) == 2
    assert wrapped.log[0].raw == '{"a": 1}'
    assert wrapped.log[0].fence_found is False
    assert wrapped.log[1].raw == '```\n{"b": 2}\n```'
    assert wrapped.log[1].fence_found is True
    assert wrapped.log[1].body == '{"b": 2}'


def test_extracting_proposer_forwards_a_raised_exception_and_logs_nothing():
    class _Raising:
        def generate(self, prompt, *, seed, temperature, max_new_tokens):
            raise RuntimeError("boom")

    wrapped = FE.ExtractingProposer(_Raising())
    try:
        wrapped.generate("p", seed=0, temperature=0.0, max_new_tokens=10)
        assert False, "expected RuntimeError to propagate"
    except RuntimeError as e:
        assert "boom" in str(e)
    assert wrapped.log == []


def test_extraction_policy_name_is_declared_and_versioned():
    assert FE.EXTRACTION == "fenced-json-v1"
