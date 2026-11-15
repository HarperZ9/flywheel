"""Tests for tools/token_optimizer.py — deterministic prompt compression.

Scope note: this file intentionally covers token_optimizer.py only. See the
task summary for why the sibling pipeline/vocab_backend/truth_profile test
files were not written in this pass.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest

from token_optimizer import (
    DEFAULT_MIN_CHARS,
    PromptDigest,
    TokenOptimizationResult,
    _dedupe,
    _extract_paths,
    _pick_goal,
    estimate_tokens,
    hook_payload_for_prompt,
    normalize_prompt,
    optimize_prompt,
)

# ---------------------------------------------------------------------------
# Shared fixture text for the "long repetitive text" scenarios
# ---------------------------------------------------------------------------

_GOAL_LINE = "Fix the intermittent session-token rejection before the next deploy."
_FILLER_LINE = "The authentication service intermittently rejects valid session tokens after a deploy."
_URL = "https://github.com/example-org/example/pull/42"
_WINPATH = "C:\\workspace\\behavior-transform.io\\tools\\pipeline.py"
_CMD = "pytest tests/test_thing.py -k something"
_CODE_FENCE = "```python\ndef add(a, b):\n    return a + b\n```"


def _build_long_fixture() -> str:
    """25x-repeated filler + goal/url/path/command/code -- forces beneficial=True."""
    return (
        _GOAL_LINE + "\n\n"
        + (_FILLER_LINE + "\n") * 25
        + "\n"
        + f"See {_WINPATH} for the gate implementation.\n"
        + f"Reference: {_URL}\n"
        + _CMD + "\n\n"
        + _CODE_FENCE + "\n"
    )


@pytest.fixture
def long_fixture_text() -> str:
    return _build_long_fixture()


@pytest.fixture
def long_fixture_result(long_fixture_text: str) -> TokenOptimizationResult:
    return optimize_prompt(long_fixture_text)


# ---------------------------------------------------------------------------
# estimate_tokens
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    def test_returns_zero_for_empty_string(self):
        assert estimate_tokens("") == 0

    def test_returns_positive_int_for_non_empty_text(self):
        result = estimate_tokens("test")
        assert isinstance(result, int)
        assert result == 2

    def test_scales_with_length(self):
        short_estimate = estimate_tokens("a" * 40)
        long_estimate = estimate_tokens("a" * 400)
        assert short_estimate == 10
        assert long_estimate == 100
        assert long_estimate > short_estimate

    def test_never_returns_less_than_one_for_non_empty_text(self):
        assert estimate_tokens("x") >= 1


# ---------------------------------------------------------------------------
# normalize_prompt
# ---------------------------------------------------------------------------


class TestNormalizePrompt:
    def test_collapses_multiple_blank_lines_to_one(self):
        assert normalize_prompt("a\n\n\n\nb") == "a\n\nb"

    def test_strips_trailing_whitespace_per_line(self):
        assert normalize_prompt("a   \nb\t\n") == "a\nb"

    def test_normalizes_crlf_and_cr_line_endings_to_lf(self):
        assert normalize_prompt("a\r\nb\rc") == "a\nb\nc"

    def test_strips_leading_and_trailing_whitespace_overall(self):
        assert normalize_prompt("\n\n  hello  \n\n") == "hello"

    def test_empty_string_stays_empty(self):
        assert normalize_prompt("") == ""


# ---------------------------------------------------------------------------
# optimize_prompt -- short text
# ---------------------------------------------------------------------------


class TestOptimizePromptShortText:
    def test_short_text_is_not_beneficial(self):
        text = "Fix the login bug please."
        result = optimize_prompt(text)
        assert result.beneficial is False

    def test_short_text_stays_below_min_chars_threshold(self):
        text = "Fix the login bug please."
        result = optimize_prompt(text)
        assert result.original_chars == len(text)
        assert result.original_chars < DEFAULT_MIN_CHARS

    def test_short_text_level_is_unchanged(self):
        result = optimize_prompt("Fix the login bug please.")
        assert result.level == "unchanged"

    def test_empty_text_returns_empty_optimized_and_not_beneficial(self):
        result = optimize_prompt("")
        assert result.optimized == ""
        assert result.beneficial is False

    def test_whitespace_only_text_normalizes_to_empty(self):
        result = optimize_prompt("   \n\n   \n  ")
        assert result.optimized == ""
        assert result.beneficial is False


# ---------------------------------------------------------------------------
# optimize_prompt -- long repetitive text
# ---------------------------------------------------------------------------


class TestOptimizePromptLongRepetitiveText:
    def test_beneficial_true_with_positive_savings(self, long_fixture_result):
        assert long_fixture_result.beneficial is True
        assert long_fixture_result.savings_ratio > 0
        assert long_fixture_result.saved_tokens > 0
        assert long_fixture_result.optimized_tokens < long_fixture_result.original_tokens

    def test_original_chars_matches_raw_input_length(self, long_fixture_text, long_fixture_result):
        assert long_fixture_result.original_chars == len(long_fixture_text)

    def test_duplicate_line_count_reflects_repeated_filler(self, long_fixture_result):
        # 25 repeats of the same filler line -> 24 counted as duplicates.
        assert long_fixture_result.duplicate_lines == 24

    def test_level_is_compact_or_aggressive_when_beneficial(self, long_fixture_result):
        assert long_fixture_result.level in {"compact", "aggressive"}


# ---------------------------------------------------------------------------
# optimize_prompt -- preservation of code fences / URLs / paths / commands
# ---------------------------------------------------------------------------


class TestOptimizePromptPreservesReferences:
    def test_preserves_url(self, long_fixture_result):
        assert _URL in long_fixture_result.optimized

    def test_preserves_windows_path(self, long_fixture_result):
        assert _WINPATH in long_fixture_result.optimized

    def test_preserves_command(self, long_fixture_result):
        assert _CMD in long_fixture_result.optimized

    def test_preserves_goal_line(self, long_fixture_result):
        assert f"Goal: {_GOAL_LINE}" in long_fixture_result.optimized

    def test_code_fence_is_summarized_not_dropped(self, long_fixture_result):
        assert long_fixture_result.preserved_code_blocks == 1
        assert "block 1:" in long_fixture_result.optimized

    def test_code_fence_raw_body_not_passed_through_verbatim(self, long_fixture_result):
        # The digest summarizes code blocks; it does not keep the fenced
        # source text itself in the compact output.
        assert "```" not in long_fixture_result.optimized
        assert "def add(a, b):" not in long_fixture_result.optimized


# ---------------------------------------------------------------------------
# TokenOptimizationResult.to_dict
# ---------------------------------------------------------------------------


class TestTokenOptimizationResultToDict:
    def test_to_dict_returns_expected_keys_and_values(self):
        result = TokenOptimizationResult(
            optimized="Goal: ship it",
            original_chars=1500,
            optimized_chars=13,
            original_tokens=375,
            optimized_tokens=4,
            saved_tokens=371,
            savings_ratio=0.9893,
            beneficial=True,
            level="aggressive",
            duplicate_lines=10,
            duplicate_sentences=2,
            preserved_code_blocks=1,
            warnings=("Large pasted code was summarized; prefer a file path for lossless review.",),
        )

        assert result.to_dict() == {
            "optimized": "Goal: ship it",
            "original_chars": 1500,
            "optimized_chars": 13,
            "original_tokens": 375,
            "optimized_tokens": 4,
            "saved_tokens": 371,
            "savings_ratio": 0.9893,
            "beneficial": True,
            "level": "aggressive",
            "duplicate_lines": 10,
            "duplicate_sentences": 2,
            "preserved_code_blocks": 1,
            "warnings": ["Large pasted code was summarized; prefer a file path for lossless review."],
        }

    def test_warnings_tuple_converted_to_list(self):
        result = TokenOptimizationResult(
            optimized="",
            original_chars=0,
            optimized_chars=0,
            original_tokens=0,
            optimized_tokens=0,
            saved_tokens=0,
            savings_ratio=0.0,
            beneficial=False,
            level="unchanged",
            duplicate_lines=0,
            duplicate_sentences=0,
            preserved_code_blocks=0,
        )
        d = result.to_dict()
        assert d["warnings"] == []
        assert isinstance(d["warnings"], list)


# ---------------------------------------------------------------------------
# hook_payload_for_prompt
# ---------------------------------------------------------------------------


class TestHookPayloadForPrompt:
    def test_returns_none_when_not_beneficial(self):
        assert hook_payload_for_prompt("Fix the login bug please.", mode="block-large") is None

    def test_block_large_mode_returns_block_payload_when_beneficial(self, long_fixture_text):
        payload = hook_payload_for_prompt(long_fixture_text, mode="block-large")
        assert payload is not None
        assert payload["decision"] == "block"
        assert payload["suppressOriginalPrompt"] is True
        assert "Token optimizer blocked a large prompt before model ingestion." in payload["reason"]
        assert "Saved ~" in payload["reason"]

    def test_default_mode_behaves_like_context(self, long_fixture_text):
        default_payload = hook_payload_for_prompt(long_fixture_text)
        explicit_payload = hook_payload_for_prompt(long_fixture_text, mode="context")
        assert default_payload == explicit_payload

    def test_context_mode_returns_context_payload_when_beneficial(self, long_fixture_text):
        payload = hook_payload_for_prompt(long_fixture_text, mode="context")
        assert payload is not None
        assert set(payload.keys()) == {"hookSpecificOutput"}
        inner = payload["hookSpecificOutput"]
        assert inner["hookEventName"] == "UserPromptSubmit"
        assert isinstance(inner["additionalContext"], str)
        assert len(inner["additionalContext"]) > 0

    def test_context_mode_returns_none_when_not_beneficial(self):
        assert hook_payload_for_prompt("Fix the login bug please.", mode="context") is None

    @pytest.mark.parametrize("mode", ["off", "OFF", "disabled", "none", "0", "false"])
    def test_off_variants_return_none_regardless_of_benefit(self, long_fixture_text, mode):
        assert hook_payload_for_prompt(long_fixture_text, mode=mode) is None


# ---------------------------------------------------------------------------
# _dedupe
# ---------------------------------------------------------------------------


class TestDedupe:
    def test_removes_duplicate_lines_case_insensitively(self):
        items = ["alpha", "beta", "alpha", "gamma", "Beta"]
        unique, duplicate_count = _dedupe(items)
        assert unique == ["alpha", "beta", "gamma"]
        assert duplicate_count == 2

    def test_normalizes_internal_whitespace_before_comparing(self):
        unique, duplicate_count = _dedupe(["a  b", "a b", "c"])
        assert unique == ["a  b", "c"]
        assert duplicate_count == 1

    def test_empty_input_returns_empty_output(self):
        assert _dedupe([]) == ([], 0)

    def test_no_duplicates_returns_all_items_unchanged(self):
        items = ["one", "two", "three"]
        unique, duplicate_count = _dedupe(items)
        assert unique == items
        assert duplicate_count == 0


# ---------------------------------------------------------------------------
# _pick_goal
# ---------------------------------------------------------------------------


class TestPickGoal:
    def test_finds_first_line_with_action_word(self):
        lines = [
            "Some unrelated context line here.",
            "We need to build the export pipeline next.",
            "Another line.",
        ]
        assert _pick_goal(lines, []) == "We need to build the export pipeline next."

    def test_falls_back_to_first_candidate_when_no_action_words(self):
        lines = ["Alpha line here.", "Beta line here."]
        assert _pick_goal(lines, []) == "Alpha line here."

    def test_checks_sentences_after_lines(self):
        lines = ["Alpha line here."]
        sentences = ["We should verify the deploy before merging the change today please."]
        assert _pick_goal(lines, sentences) == sentences[0]

    def test_returns_empty_string_when_no_candidates(self):
        assert _pick_goal([], []) == ""


# ---------------------------------------------------------------------------
# _extract_paths
# ---------------------------------------------------------------------------


class TestExtractPaths:
    def test_finds_windows_path(self):
        text = "Config lives at C:\\workspace\\behavior-transform.io\\tools\\pipeline.py and covers the gate."
        paths = _extract_paths(text, limit=12)
        assert "C:\\workspace\\behavior-transform.io\\tools\\pipeline.py" in paths

    def test_finds_url_like_relative_path(self):
        text = "See tools/token_optimizer.py, which implements the digest builder."
        paths = _extract_paths(text, limit=12)
        assert "tools/token_optimizer.py" in paths

    def test_respects_limit(self):
        text = " ".join(f"path/to/file{i}.py," for i in range(20))
        paths = _extract_paths(text, limit=3)
        assert len(paths) == 3

    def test_returns_empty_list_when_no_paths_present(self):
        text = "This sentence has no file paths or URLs in it at all whatsoever."
        assert _extract_paths(text, limit=12) == []


# ---------------------------------------------------------------------------
# PromptDigest
# ---------------------------------------------------------------------------


class TestPromptDigest:
    def test_instantiates_with_expected_fields(self):
        digest = PromptDigest(
            optimized="Goal: ship it",
            duplicate_lines=3,
            duplicate_sentences=1,
            code_blocks=2,
            warnings=("warn one",),
        )
        assert digest.optimized == "Goal: ship it"
        assert digest.duplicate_lines == 3
        assert digest.duplicate_sentences == 1
        assert digest.code_blocks == 2
        assert digest.warnings == ("warn one",)

    def test_is_frozen(self):
        digest = PromptDigest(
            optimized="x", duplicate_lines=0, duplicate_sentences=0, code_blocks=0, warnings=()
        )
        with pytest.raises(AttributeError):
            digest.optimized = "y"  # type: ignore[misc]
