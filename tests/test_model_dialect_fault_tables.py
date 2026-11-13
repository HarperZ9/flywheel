"""Focused dialect-table regressions for provider fault/deadline recovery."""
from harness import model_dialects as md


def test_provider_kinds_map_to_the_wire_dialect_their_error_bodies_use():
    assert md.dialect_for("openrouter") == md.OPENAI
    assert md.dialect_for("anthropic") == md.ANTHROPIC
    assert md.dialect_for("gemini") == md.GEMINI
    assert md.dialect_for("ollama") == md.OLLAMA
    assert md.dialect_for("unknown-provider") is None


def test_openai_responses_is_a_distinct_dialect_with_its_own_usage_paths():
    assert md.OPENAI_RESPONSES in md.DIALECTS
    assert md.MEANINGS[md.OPENAI_RESPONSES]["input"] == (("input_tokens",),)
    assert md.MEANINGS[md.OPENAI]["input"] == (("prompt_tokens",),)
    assert md.BLOCK[md.OPENAI_RESPONSES] == ("usage",)


def test_openrouter_route_model_prefers_generator_attestation_path():
    assert md.SERVED[md.OPENAI][0] == ("choices", 0, "message", "model")
    assert md.SERVED[md.OPENAI][1] == ("model",)


def test_dialect_tables_keep_unknowns_as_unknowns_not_false_claims():
    assert md.OUTPUT_INCLUDES_REASONING[md.OLLAMA] is None
    assert md.ABSENT_MEANS_UNREPORTED[md.OLLAMA] is False
    assert md.INPUT_INCLUDES_CACHE_READ[md.ANTHROPIC] is False
