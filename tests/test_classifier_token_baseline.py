import json

import pytest

from train.classifier_token_baseline import (
    ABSTAIN_CHOICE_ID,
    VerbalizerError,
    build_verbalizer_map,
    final_nonpadding_indices,
    render_decision_prompt,
    score_final_logits,
)


class FakeTokenizer:
    def __init__(self, vocab):
        self.vocab = dict(vocab)

    def encode(self, text, add_special_tokens=False):
        if text in self.vocab:
            value = self.vocab[text]
            return list(value) if isinstance(value, tuple) else [value]
        return [900, 901]


def request(**overrides):
    payload = {
        "schema": "flywheel.decision-request/v1",
        "decision_ref": "route_1",
        "state": "Need a local routing choice for a context-heavy task.",
        "choices": [
            {"id": "local", "description": "Use the local 14B model."},
            {"id": "hosted", "description": "Escalate to a hosted model."},
            {"id": "defer", "description": "Ask the operator for missing state."},
        ],
        "eligible_choice_ids": ["local", "hosted"],
        "evidence_refs": ["ev_roster"],
    }
    payload.update(overrides)
    return payload


def test_final_nonpadding_indices_handle_left_and_right_padding():
    assert final_nonpadding_indices([[1, 1, 0, 0], [0, 0, 1, 1]]) == [1, 3]
    assert final_nonpadding_indices(None, batch_size=2, sequence_length=4) == [3, 3]


def test_verbalizer_map_uses_only_single_token_unique_verbalizers():
    tok = FakeTokenizer({" A": 11, " B": (12, 13), " C": 14, " D": 11, " E": 15})
    mapping = build_verbalizer_map(tok, request(), candidates=[" A", " B", " C", " D", " E"])
    assert mapping.choice_to_token == {"local": 11, "hosted": 14, ABSTAIN_CHOICE_ID: 15}
    assert mapping.choice_to_verbalizer["hosted"] == " C"


def test_verbalizer_map_fails_when_coverage_is_insufficient():
    tok = FakeTokenizer({" A": (1, 2), " B": 3})
    with pytest.raises(VerbalizerError, match="single-token verbalizers"):
        build_verbalizer_map(tok, request(), candidates=[" A", " B"])


def test_prompt_names_choice_descriptions_and_visible_verbalizers():
    tok = FakeTokenizer({" A": 1, " B": 2, " C": 3})
    mapping = build_verbalizer_map(tok, request(), candidates=[" A", " B", " C"])
    prompt = render_decision_prompt(request(), mapping)
    assert "Use the local 14B model." in prompt
    assert "Escalate to a hosted model." in prompt
    assert "Ask the operator for missing state." in prompt
    assert " A" in prompt and " B" in prompt and " C" in prompt
    assert "hidden" not in prompt.lower()


def test_score_final_logits_masks_ineligible_and_normalizes_with_abstain():
    tok = FakeTokenizer({" A": 0, " B": 1, " C": 2})
    req = request()
    mapping = build_verbalizer_map(tok, req, candidates=[" A", " B", " C"])
    result = score_final_logits([1.0, 3.0, 2.0], req, mapping, scorer_ref="unit")

    assert set(result["scores"]) == {"local", "hosted", "defer", ABSTAIN_CHOICE_ID}
    assert result["scores"]["defer"]["probability"] == 0.0
    assert result["scores"]["defer"]["eligible"] is False
    total = sum(result["scores"][key]["probability"] for key in ("local", "hosted", ABSTAIN_CHOICE_ID))
    assert total == pytest.approx(1.0)
    assert result["choice_id"] == "hosted"
    assert json.loads(result["proposal_json"])["choice_id"] == "hosted"
    assert result["contract_result"]["reason_code"] == "selected"
    assert result["uncalibrated"] is True


def test_score_final_logits_can_choose_abstain_and_keeps_contract_honest():
    tok = FakeTokenizer({" A": 0, " B": 1, " C": 2})
    mapping = build_verbalizer_map(tok, request(), candidates=[" A", " B", " C"])
    result = score_final_logits([0.0, 0.5, 4.0], request(), mapping, scorer_ref="unit")

    assert result["choice_id"] is None
    assert json.loads(result["proposal_json"])["choice_id"] is None
    assert result["scores"][ABSTAIN_CHOICE_ID]["probability"] > 0.9
    assert result["contract_result"]["reason_code"] == "abstain"


def test_score_final_logits_rejects_missing_vocab_coverage_and_bad_eligibility():
    tok = FakeTokenizer({" A": 0, " B": 1, " C": 5})
    mapping = build_verbalizer_map(tok, request(), candidates=[" A", " B", " C"])
    with pytest.raises(ValueError, match="outside logits vocabulary"):
        score_final_logits([0.0, 1.0], request(), mapping, scorer_ref="unit")

    bad = request(eligible_choice_ids=["local", "ghost"])
    with pytest.raises(Exception):
        build_verbalizer_map(FakeTokenizer({" A": 0, " B": 1}), bad, candidates=[" A", " B"])
