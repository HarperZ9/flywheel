from types import SimpleNamespace

import pytest

from train.classifier_token_runtime import (
    CACHE_CAPABILITY,
    CACHE_CAPABILITY_REASON,
    DEFAULT_MAX_BATCH_SIZE,
    DEFAULT_MAX_INPUT_TOKENS,
    InputTooLongError,
    TransformersTokenComparator,
    build_model_load_kwargs,
    load_local_comparator,
)
from tests.test_classifier_token_baseline import FakeTokenizer, request


class Batch(dict):
    def to(self, device):
        self["moved_to"] = device
        return self


class RuntimeTokenizer(FakeTokenizer):
    eos_token = "<eos>"
    pad_token = None
    padding_side = "right"

    def __init__(self, vocab):
        super().__init__(vocab)
        self.prompts = []
        self.chat_calls = []
        self.padding_sides = []
        self.truncation_values = []

    def apply_chat_template(self, messages, *, tokenize=False, add_generation_prompt=False):
        self.chat_calls.append({
            "messages": messages,
            "tokenize": tokenize,
            "add_generation_prompt": add_generation_prompt,
        })
        return f"CHAT:{messages[0]['content']}:ASSISTANT"

    def __call__(self, prompts, return_tensors=None, padding=False,
                 add_special_tokens=True, truncation=False):
        self.truncation_values.append(truncation)
        if isinstance(prompts, str):
            return {"input_ids": self.encode(prompts, add_special_tokens=add_special_tokens)}
        self.prompts.extend(prompts)
        self.padding_sides.append(self.padding_side)
        lengths = [5, 7, 6, 4][: len(prompts)]
        max_len = max(lengths)
        rows, masks = [], []
        for length in lengths:
            if self.padding_side == "left":
                rows.append([0] * (max_len - length) + [1] * length)
                masks.append([0] * (max_len - length) + [1] * length)
            else:
                rows.append([1] * length + [0] * (max_len - length))
                masks.append([1] * length + [0] * (max_len - length))
        return Batch({"input_ids": rows, "attention_mask": masks})

    def decode(self, ids, skip_special_tokens=True):
        table = {10: "A", 11: "B", 12: "C", 99: "not-a-label"}
        if isinstance(ids, int):
            return table.get(ids, "")
        return "".join(table.get(int(item), "") for item in ids)


class FakeTorch:
    def __init__(self):
        self.active = False
        self.entered = 0

    def inference_mode(self):
        outer = self

        class Context:
            def __enter__(self):
                outer.active = True
                outer.entered += 1

            def __exit__(self, exc_type, exc, tb):
                outer.active = False

        return Context()


def test_loader_kwargs_can_request_nf4_without_importing_real_dependencies():
    class FakeBitsAndBytesConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    kwargs = build_model_load_kwargs(
        load_in_4bit=True,
        dtype="bfloat16",
        device_map="auto",
        bitsandbytes_config_cls=FakeBitsAndBytesConfig,
    )

    assert kwargs["local_files_only"] is True
    assert kwargs["trust_remote_code"] is False
    assert kwargs["use_safetensors"] is True
    assert kwargs["device_map"] == "auto"
    assert kwargs["torch_dtype"] == "bfloat16"
    assert kwargs["quantization_config"].kwargs == {
        "load_in_4bit": True,
        "bnb_4bit_quant_type": "nf4",
        "bnb_4bit_use_double_quant": True,
        "bnb_4bit_compute_dtype": "bfloat16",
    }


def test_load_local_comparator_uses_factories_and_4bit_kwargs():
    calls = {}

    class TokenizerFactory:
        @staticmethod
        def from_pretrained(path, **kwargs):
            calls["tokenizer"] = (path, kwargs)
            return RuntimeTokenizer({"A": 10, "B": 11, "C": 12})

    class ModelFactory:
        @staticmethod
        def from_pretrained(path, **kwargs):
            calls["model"] = (path, kwargs)
            return SimpleNamespace(device="cpu")

    class FakeBitsAndBytesConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    comparator = load_local_comparator(
        "models/test-local-comparator",
        load_in_4bit=True,
        dtype="bfloat16",
        device_map="auto",
        tokenizer_factory=TokenizerFactory,
        model_factory=ModelFactory,
        bitsandbytes_config_cls=FakeBitsAndBytesConfig,
    )

    assert isinstance(comparator, TransformersTokenComparator)
    assert comparator.max_input_tokens == DEFAULT_MAX_INPUT_TOKENS
    assert comparator.max_batch_size == DEFAULT_MAX_BATCH_SIZE
    assert calls["tokenizer"][1]["local_files_only"] is True
    assert calls["model"][1]["quantization_config"].kwargs["bnb_4bit_quant_type"] == "nf4"
    assert calls["model"][1]["device_map"] == "auto"


def test_runtime_validates_token_and_batch_bounds():
    tokenizer = RuntimeTokenizer({"A": 10, "B": 11, "C": 12})
    model = SimpleNamespace(device="cpu")

    comparator = TransformersTokenComparator(model, tokenizer)
    assert comparator.max_input_tokens == 4096
    assert comparator.max_batch_size == 4

    with pytest.raises(ValueError, match="max_input_tokens"):
        TransformersTokenComparator(model, tokenizer, max_input_tokens=0)
    with pytest.raises(ValueError, match="max_batch_size"):
        TransformersTokenComparator(model, tokenizer, max_batch_size="4")
    with pytest.raises(ValueError, match="max_batch_size"):
        TransformersTokenComparator(model, tokenizer, max_batch_size=0)


def test_runtime_rejects_overlong_inputs_without_truncation():
    tokenizer = RuntimeTokenizer({"A": 10, "B": 11, "C": 12})
    model = SimpleNamespace(device="cpu")
    comparator = TransformersTokenComparator(model, tokenizer, max_input_tokens=3)

    with pytest.raises(InputTooLongError, match="exceeds max_input_tokens"):
        comparator.score_requests([request()])
    assert tokenizer.truncation_values == [False]


def test_runtime_rejects_batches_above_explicit_bound_before_model_call():
    class Model:
        device = "cpu"
        called = False

        def __call__(self, **kwargs):
            self.called = True

    tokenizer = RuntimeTokenizer({"A": 10, "B": 11, "C": 12})
    model = Model()
    comparator = TransformersTokenComparator(model, tokenizer, max_batch_size=1)

    with pytest.raises(ValueError, match="max_batch_size"):
        comparator.score_requests([request(), request(decision_ref="route_2")])
    assert model.called is False


def test_runtime_applies_chat_template_and_uses_eval_inference_context(monkeypatch):
    fake_torch = FakeTorch()

    class Model:
        device = "cpu"
        eval_called = False

        def eval(self):
            self.eval_called = True
            return self

        def __call__(self, **kwargs):
            assert fake_torch.active is True
            assert kwargs["use_cache"] is False
            seq_len = len(kwargs["input_ids"][0])
            row = [[0.0] * 13 for _ in range(seq_len)]
            row[4][10] = 5.0
            row[4][11] = 1.0
            row[4][12] = 0.0
            return SimpleNamespace(logits=[row])

    monkeypatch.setattr("train.classifier_token_runtime._torch_module", lambda: fake_torch)
    tokenizer = RuntimeTokenizer({"A": 10, "B": 11, "C": 12})
    model = Model()
    result = TransformersTokenComparator(model, tokenizer, max_input_tokens=20).score_requests([request()])[0]

    assert model.eval_called is True
    assert fake_torch.entered == 1
    assert tokenizer.chat_calls[0]["tokenize"] is False
    assert tokenizer.chat_calls[0]["add_generation_prompt"] is True
    assert tokenizer.prompts[0].startswith("CHAT:")
    assert "Use the local 14B model." in tokenizer.prompts[0]
    assert result["choice_id"] == "local"
    assert result["contract_result"]["reason_code"] == "selected"


def test_runtime_cache_label_is_honest_about_deferred_shared_kv():
    tokenizer = RuntimeTokenizer({"A": 10, "B": 11, "C": 12})
    model = SimpleNamespace(device="cpu")
    comparator = TransformersTokenComparator(model, tokenizer)

    assert comparator.cache_capability == CACHE_CAPABILITY
    assert "No shared-prefix KV cache" in CACHE_CAPABILITY_REASON
