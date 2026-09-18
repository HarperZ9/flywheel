import json

from train.classifier_token_generation import (
    JSON_GENERATION_CACHE_CAPABILITY,
    JSON_GENERATION_SCHEMA,
    SINGLE_TOKEN_GENERATION_CACHE_CAPABILITY,
    SINGLE_TOKEN_GENERATION_SCHEMA,
    TransformersJSONGenerationComparator,
    TransformersSingleTokenGenerationComparator,
)
from tests.test_classifier_token_baseline import FakeTokenizer, request
from tests.test_classifier_token_runtime import Batch, FakeTorch


class GenerationTokenizer(FakeTokenizer):
    eos_token = "<eos>"
    pad_token = None
    padding_side = "right"

    def __init__(self, vocab):
        super().__init__(vocab)
        self.prompts = []
        self.chat_calls = []
        self.padding_sides = []

    def apply_chat_template(self, messages, *, tokenize=False, add_generation_prompt=False):
        self.chat_calls.append({
            "messages": messages,
            "tokenize": tokenize,
            "add_generation_prompt": add_generation_prompt,
        })
        return f"CHAT:{messages[0]['content']}:ASSISTANT"

    def __call__(self, prompts, return_tensors=None, padding=False,
                 add_special_tokens=True, truncation=False):
        if isinstance(prompts, str):
            return {"input_ids": self.encode(prompts, add_special_tokens=add_special_tokens)}
        self.prompts.extend(prompts)
        self.padding_sides.append(self.padding_side)
        length = 5
        width = 7
        if self.padding_side == "left":
            row = [0] * (width - length) + [1] * length
            mask = [0] * (width - length) + [1] * length
        else:
            row = [1] * length + [0] * (width - length)
            mask = [1] * length + [0] * (width - length)
        return Batch({"input_ids": [row], "attention_mask": [mask]})

    def decode(self, ids, skip_special_tokens=True):
        table = {
            1: "prompt",
            10: "A",
            11: "B",
            12: "C",
            99: "not-a-label",
            200: '{"choice_id":"local","evidence_refs":[]}',
            201: "not json",
        }
        if isinstance(ids, int):
            return table.get(ids, "")
        return "".join(table.get(int(item), "") for item in ids)


class GenerateModel:
    device = "cpu"

    def __init__(self, continuation_token):
        self.continuation_token = continuation_token
        self.eval_called = False
        self.generate_kwargs = None

    def eval(self):
        self.eval_called = True
        return self

    def generate(self, **kwargs):
        self.generate_kwargs = kwargs
        assert kwargs["do_sample"] is False
        return [[0, 0, 1, 1, 1, 1, 1, self.continuation_token]]


def test_single_token_generation_uses_left_padding_width_and_plain_labels(monkeypatch):
    fake_torch = FakeTorch()
    monkeypatch.setattr("train.classifier_token_generation._torch_module", lambda: fake_torch)
    tokenizer = GenerationTokenizer({"A": 10, "B": 11, "C": 12})
    model = GenerateModel(10)

    result = TransformersSingleTokenGenerationComparator(
        model, tokenizer, max_input_tokens=20).generate_requests([request()])[0]

    assert result["schema"] == SINGLE_TOKEN_GENERATION_SCHEMA
    assert tokenizer.padding_sides == ["left"]
    assert tokenizer.chat_calls[0]["add_generation_prompt"] is True
    assert model.eval_called is True
    assert fake_torch.entered == 1
    assert result["choice_id"] == "local"
    assert result["actual_verbalizer"] == "A"
    assert result["private_raw_text"] == "A"
    assert result["generated_token_count"] == 1
    assert json.loads(result["proposal_json"])["choice_id"] == "local"
    assert result["contract_result"]["reason_code"] == "selected"
    assert result["cache_capability"] == SINGLE_TOKEN_GENERATION_CACHE_CAPABILITY


def test_single_token_generation_malformed_label_is_not_masked_as_abstain(monkeypatch):
    monkeypatch.setattr("train.classifier_token_generation._torch_module", lambda: FakeTorch())
    tokenizer = GenerationTokenizer({"A": 10, "B": 11, "C": 12})
    result = TransformersSingleTokenGenerationComparator(
        GenerateModel(99), tokenizer, max_input_tokens=20).generate_requests([request()])[0]

    assert result["choice_id"] is None
    assert result["malformed"] is True
    assert result["malformed_reason"] == "generated_token_not_declared_verbalizer"
    assert result["proposal_json"] is None
    assert result["contract_input"] == "not-a-label"
    assert result["contract_result"]["reason_code"] == "malformed_json"
    assert result["private_raw_text"] == "not-a-label"
    assert result["generated_token_count"] == 1


def test_json_generation_uses_same_contract_prompt_and_greedy_bounded_decode(monkeypatch):
    monkeypatch.setattr("train.classifier_token_generation._torch_module", lambda: FakeTorch())
    tokenizer = GenerationTokenizer({"A": 10, "B": 11, "C": 12})
    model = GenerateModel(200)

    result = TransformersJSONGenerationComparator(
        model, tokenizer, max_input_tokens=20, max_new_tokens=32).generate_requests([request()])[0]

    prompt = tokenizer.chat_calls[0]["messages"][0]["content"]
    assert result["schema"] == JSON_GENERATION_SCHEMA
    assert tokenizer.padding_sides == ["left"]
    assert model.generate_kwargs["max_new_tokens"] == 32
    assert model.generate_kwargs["do_sample"] is False
    assert '"choice_id"' in prompt
    assert "evidence_refs" in prompt
    assert "Use the local 14B model." in prompt
    assert result["choice_id"] == "local"
    assert result["malformed"] is False
    assert result["proposal_json"] == '{"choice_id":"local","evidence_refs":[]}'
    assert result["private_raw_text"] == '{"choice_id":"local","evidence_refs":[]}'
    assert result["contract_result"]["reason_code"] == "selected"
    assert result["cache_capability"] == JSON_GENERATION_CACHE_CAPABILITY


def test_json_generation_bad_json_is_evaluated_raw_not_sanitized(monkeypatch):
    monkeypatch.setattr("train.classifier_token_generation._torch_module", lambda: FakeTorch())
    tokenizer = GenerationTokenizer({"A": 10, "B": 11, "C": 12})
    result = TransformersJSONGenerationComparator(
        GenerateModel(201), tokenizer, max_input_tokens=20).generate_requests([request()])[0]

    assert result["choice_id"] is None
    assert result["malformed"] is True
    assert result["proposal_json"] == "not json"
    assert result["private_raw_text"] == "not json"
    assert result["contract_result"]["reason_code"] == "malformed_json"
