"""Falsifiers for model reasoning capture and its publication gate.

Hermetic: literal response dicts only. Load-bearing: (1) reasoning that used to
be dropped on the floor is now read, on each dialect's own key; (2) the
redaction actually removes the text while keeping enough to prove what was
removed; (3) an encrypted redacted_thinking block is COUNTED and never read,
so "no reasoning" stays distinguishable from "reasoning nothing here can read";
(4) a Gemini thought part is reasoning and never the answer; (5) an absent
digest makes the match question unanswered rather than answered no.
"""
from harness import model_reasoning as mr
from harness.model_dialects import ANTHROPIC, GEMINI, OLLAMA, OPENAI

CHAIN = "step one, then step two"


# --- reading each dialect ---------------------------------------------------

def test_openai_compatible_reasoning_content_is_read():
    record = mr.capture(
        {"choices": [{"message": {"content": "hi", "reasoning_content": CHAIN}}]},
        dialect=OPENAI)
    assert record["present"] is True
    assert record["text"] == CHAIN
    assert record["source_key"] == "reasoning_content"


def test_the_openrouter_spelling_is_read_too():
    record = mr.capture(
        {"choices": [{"message": {"content": "hi", "reasoning": CHAIN}}]},
        dialect=OPENAI)
    assert record["text"] == CHAIN
    assert record["source_key"] == "reasoning"


def test_the_deepseek_spelling_wins_when_a_server_emits_both():
    record = mr.capture(
        {"choices": [{"message": {"reasoning_content": CHAIN,
                                  "reasoning": "other"}}]},
        dialect=OPENAI)
    assert record["text"] == CHAIN


def test_anthropic_thinking_blocks_are_joined_in_order():
    record = mr.capture(
        {"content": [{"type": "thinking", "thinking": "first", "signature": "s"},
                     {"type": "text", "text": "the answer"},
                     {"type": "thinking", "thinking": "second"}]},
        dialect=ANTHROPIC)
    assert record["blocks"] == 2
    assert record["text"] == "first\nsecond"
    assert "the answer" not in record["text"]


def test_gemini_thought_parts_are_reasoning_and_plain_parts_are_not():
    record = mr.capture(
        {"candidates": [{"content": {"parts": [
            {"text": CHAIN, "thought": True},
            {"text": "the answer"}]}}]},
        dialect=GEMINI)
    assert record["text"] == CHAIN
    assert "the answer" not in record["text"]


def test_a_gemini_thought_flag_of_another_type_is_not_read_as_a_thought():
    """A truthy non-boolean is a shape this reader does not understand, and
    reading it as a thought would file the answer under reasoning."""
    record = mr.capture(
        {"candidates": [{"content": {"parts": [{"text": "answer",
                                                "thought": "yes"}]}}]},
        dialect=GEMINI)
    assert record["present"] is False


def test_ollama_chat_thinking_is_read():
    record = mr.capture({"message": {"content": "hi", "thinking": CHAIN}},
                        dialect=OLLAMA)
    assert record["text"] == CHAIN
    assert record["source_key"] == "message.thinking"


def test_ollama_generate_puts_thinking_at_the_top_level():
    """/api/generate returns no message object. Reading only the chat shape
    would report no reasoning for every generate call."""
    record = mr.capture({"response": "hi", "thinking": CHAIN}, dialect=OLLAMA)
    assert record["text"] == CHAIN
    assert record["source_key"] == "thinking"


# --- absence versus unreadability -------------------------------------------

def test_a_response_with_no_reasoning_reports_absent_not_unmapped():
    record = mr.capture({"choices": [{"message": {"content": "hi"}}]},
                        dialect=OPENAI)
    assert record["present"] is False
    assert record["dialect_unmapped"] is False
    assert "text" not in record


def test_an_unmapped_dialect_says_so_rather_than_claiming_nothing_came_back():
    record = mr.capture({"anything": 1}, dialect="cohere")
    assert record["present"] is False
    assert record["dialect_unmapped"] is True


def test_redacted_thinking_is_counted_and_its_encrypted_payload_never_read():
    record = mr.capture(
        {"content": [{"type": "redacted_thinking", "data": "ENCRYPTEDBLOB"}]},
        dialect=ANTHROPIC)
    assert record["encrypted_blocks"] == 1
    assert record["present"] is False
    assert "ENCRYPTEDBLOB" not in repr(record)


def test_an_encrypted_block_beside_a_readable_one_is_reported_separately():
    record = mr.capture(
        {"content": [{"type": "thinking", "thinking": CHAIN},
                     {"type": "redacted_thinking", "data": "BLOB"}]},
        dialect=ANTHROPIC)
    assert record["present"] is True
    assert record["blocks"] == 1
    assert record["encrypted_blocks"] == 1


# --- the publication gate ---------------------------------------------------

def test_every_record_carries_the_not_approved_state():
    for dialect in (OPENAI, ANTHROPIC, GEMINI, OLLAMA, "cohere"):
        record = mr.capture({}, dialect=dialect)
        assert record["publication_state"] == "not_approved_for_publication"


def test_redaction_removes_the_text_and_keeps_the_proof():
    record = mr.capture(
        {"choices": [{"message": {"reasoning_content": CHAIN}}]}, dialect=OPENAI)
    safe = mr.redacted(record)
    assert "text" not in safe
    assert CHAIN not in repr(safe)
    assert safe["redacted"] is True
    assert safe["chars"] == len(CHAIN)
    assert safe["sha256"] == record["sha256"]


def test_redaction_does_not_mutate_the_record_it_was_given():
    record = mr.capture(
        {"choices": [{"message": {"reasoning_content": CHAIN}}]}, dialect=OPENAI)
    mr.redacted(record)
    assert record["text"] == CHAIN


def test_redacting_twice_is_the_same_as_redacting_once():
    record = mr.capture(
        {"choices": [{"message": {"reasoning_content": CHAIN}}]}, dialect=OPENAI)
    assert mr.redacted(mr.redacted(record)) == mr.redacted(record)


def test_redacting_a_non_record_still_yields_a_gated_record():
    safe = mr.redacted("not a record")
    assert safe["present"] is False
    assert safe["publication_state"] == "not_approved_for_publication"


# --- proving a held text is the captured one --------------------------------

def test_a_holder_of_the_text_can_prove_it_against_a_redacted_record():
    record = mr.capture(
        {"choices": [{"message": {"reasoning_content": CHAIN}}]}, dialect=OPENAI)
    safe = mr.redacted(record)
    assert mr.matches(safe, CHAIN) is True
    assert mr.matches(safe, CHAIN + " ") is False


def test_no_digest_makes_the_question_unanswered_rather_than_answered_no():
    record = mr.capture({"choices": []}, dialect=OPENAI)
    assert record["sha256"] is None
    assert mr.matches(record, "anything") is None


def test_matches_refuses_a_non_string_candidate():
    record = mr.capture(
        {"choices": [{"message": {"reasoning_content": CHAIN}}]}, dialect=OPENAI)
    assert mr.matches(record, None) is None


# --- hostile shapes ---------------------------------------------------------

def test_a_non_dict_response_is_absent_not_an_exception():
    for junk in (None, [], "text", 7):
        record = mr.capture(junk, dialect=OPENAI)
        assert record["present"] is False


def test_ragged_blocks_are_skipped_rather_than_crashing():
    record = mr.capture(
        {"content": ["not a dict", {"type": "thinking"},
                     {"type": "thinking", "thinking": ""},
                     {"type": "thinking", "thinking": CHAIN}]},
        dialect=ANTHROPIC)
    assert record["blocks"] == 1
    assert record["text"] == CHAIN
