"""Optional Transformers runtime comparator for classifier token baselines."""
from __future__ import annotations

import argparse
import json
import time
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from harness.decision_contract import validate_request
from train.classifier_token_baseline import (
    CACHE_CAPABILITY,
    build_verbalizer_map,
    gather_final_logits,
    render_decision_prompt,
    score_final_logits,
)

DEFAULT_MAX_INPUT_TOKENS = 4096
DEFAULT_MAX_BATCH_SIZE = 4
CACHE_CAPABILITY_REASON = (
    "No shared-prefix KV cache is implemented. The comparator batches full prompt "
    "forwards and labels that path honestly instead of claiming cached scoring."
)


class InputTooLongError(ValueError):
    """A prompt exceeds the caller's explicit max_input_tokens bound."""


def build_model_load_kwargs(
    *,
    load_in_4bit: bool = False,
    dtype: Any = None,
    device_map: str | None = None,
    bitsandbytes_config_cls: Any | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "local_files_only": True,
        "trust_remote_code": False,
        "use_safetensors": True,
    }
    if dtype is not None:
        kwargs["torch_dtype"] = dtype
    if device_map is not None:
        kwargs["device_map"] = device_map
    if load_in_4bit:
        if bitsandbytes_config_cls is None:
            from transformers import BitsAndBytesConfig
            bitsandbytes_config_cls = BitsAndBytesConfig
        kwargs["quantization_config"] = bitsandbytes_config_cls(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=dtype,
        )
    return kwargs


def load_local_comparator(
    model_path: str,
    *,
    load_in_4bit: bool = False,
    dtype: Any = None,
    device_map: str | None = None,
    max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS,
    max_batch_size: int = DEFAULT_MAX_BATCH_SIZE,
    scorer_ref: str = "token_baseline",
    tokenizer_factory: Any | None = None,
    model_factory: Any | None = None,
    bitsandbytes_config_cls: Any | None = None,
) -> "TransformersTokenComparator":
    if tokenizer_factory is None or model_factory is None:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        tokenizer_factory = tokenizer_factory or AutoTokenizer
        model_factory = model_factory or AutoModelForCausalLM
    tokenizer = tokenizer_factory.from_pretrained(
        model_path, local_files_only=True, trust_remote_code=False, use_fast=True)
    kwargs = build_model_load_kwargs(
        load_in_4bit=load_in_4bit, dtype=dtype, device_map=device_map,
        bitsandbytes_config_cls=bitsandbytes_config_cls)
    model = model_factory.from_pretrained(model_path, **kwargs)
    return TransformersTokenComparator(
        model, tokenizer, scorer_ref=scorer_ref,
        max_input_tokens=max_input_tokens, max_batch_size=max_batch_size)


class TransformersTokenComparator:
    cache_capability = CACHE_CAPABILITY
    cache_capability_reason = CACHE_CAPABILITY_REASON

    def __init__(
        self,
        model: Any,
        tokenizer: Any,
        *,
        scorer_ref: str = "token_baseline",
        max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS,
        max_batch_size: int = DEFAULT_MAX_BATCH_SIZE,
    ):
        self.model = model
        self.tokenizer = tokenizer
        self.scorer_ref = scorer_ref
        self.max_input_tokens = _positive_int(max_input_tokens, "max_input_tokens")
        self.max_batch_size = _positive_int(max_batch_size, "max_batch_size")

    @classmethod
    def from_local_model(cls, model_path: str, **kwargs: Any) -> "TransformersTokenComparator":
        return load_local_comparator(model_path, **kwargs)

    def _render_prompts(self, requests: list[dict], maps: list[Any]) -> list[str]:
        prompts = [
            render_decision_prompt(req, mapping)
            for req, mapping in zip(requests, maps, strict=True)
        ]
        return [render_chat_prompt(self.tokenizer, prompt) for prompt in prompts]

    def _batch_prompts(self, prompts: list[str], *, left_padding: bool = False) -> Any:
        if len(prompts) > self.max_batch_size:
            raise ValueError(
                f"batch size {len(prompts)} exceeds max_batch_size={self.max_batch_size}")
        if getattr(self.tokenizer, "pad_token", None) is None and getattr(self.tokenizer, "eos_token", None) is not None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        old_padding_side = getattr(self.tokenizer, "padding_side", None)
        if left_padding and old_padding_side is not None:
            self.tokenizer.padding_side = "left"
        try:
            try:
                batch = self.tokenizer(
                    prompts, return_tensors="pt", padding=True, truncation=False)
            except TypeError as exc:
                if "truncation" not in str(exc):
                    raise
                batch = self.tokenizer(prompts, return_tensors="pt", padding=True)
        finally:
            if left_padding and old_padding_side is not None:
                self.tokenizer.padding_side = old_padding_side
        self._reject_overlong(batch)
        device = getattr(self.model, "device", None)
        if device is not None and hasattr(batch, "to"):
            batch = batch.to(device)
        return batch

    def _reject_overlong(self, batch: Any) -> None:
        mask = batch.get("attention_mask") if hasattr(batch, "get") else None
        ids = batch.get("input_ids") if hasattr(batch, "get") else None
        rows = mask if mask is not None else ids
        values = rows.tolist() if hasattr(rows, "tolist") else rows
        for row in values:
            count = sum(int(v) for v in row) if mask is not None else len(row)
            if count > self.max_input_tokens:
                raise InputTooLongError(
                    f"prompt length {count} exceeds max_input_tokens={self.max_input_tokens}; "
                    "refusing to truncate")

    def score_requests(self, requests: list[dict]) -> list[dict]:
        snapshots = [validate_request(req) for req in requests]
        maps = [build_verbalizer_map(self.tokenizer, req) for req in snapshots]
        batch = self._batch_prompts(self._render_prompts(snapshots, maps))
        device = _batch_device(batch, getattr(self.model, "device", None))
        torch_mod = _torch_module()
        if hasattr(self.model, "eval"):
            self.model.eval()
        _sync_if_cuda(torch_mod, device)
        started = time.perf_counter()
        with _inference_context(torch_mod):
            outputs = self.model(**batch, use_cache=False)
        _sync_if_cuda(torch_mod, device)
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        rows = gather_final_logits(outputs.logits, batch.get("attention_mask"))
        return [
            score_final_logits(
                row, req, mapping, scorer_ref=self.scorer_ref, latency_ms=latency_ms,
                cache_capability=CACHE_CAPABILITY)
            for row, req, mapping in zip(rows, snapshots, maps, strict=True)
        ]


def _positive_int(value: Any, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def render_chat_prompt(tokenizer: Any, prompt: str) -> str:
    apply_chat_template = getattr(tokenizer, "apply_chat_template", None)
    if callable(apply_chat_template):
        return apply_chat_template(
            [{"role": "user", "content": prompt}],
            tokenize=False,
            add_generation_prompt=True,
        )
    return prompt


def input_widths(batch: Any) -> list[int]:
    ids = batch.get("input_ids") if hasattr(batch, "get") else None
    values = ids.tolist() if hasattr(ids, "tolist") else ids
    return [len(row) for row in values]


def _input_lengths(batch: Any) -> list[int]:
    mask = batch.get("attention_mask") if hasattr(batch, "get") else None
    ids = batch.get("input_ids") if hasattr(batch, "get") else None
    rows = mask if mask is not None else ids
    values = rows.tolist() if hasattr(rows, "tolist") else rows
    return [sum(int(v) for v in row) if mask is not None else len(row) for row in values]


def _as_list(value: Any) -> list[int]:
    if isinstance(value, int):
        return [value]
    if hasattr(value, "detach"):
        value = value.detach().cpu().tolist()
    elif hasattr(value, "tolist"):
        value = value.tolist()
    return [int(item) for item in value]


def _batch_device(batch: Any, default: Any) -> Any:
    ids = batch.get("input_ids") if hasattr(batch, "get") else None
    return getattr(ids, "device", default)


def _torch_module() -> Any:
    try:
        import torch
    except ImportError:
        return None
    return torch


def _inference_context(torch_mod: Any) -> Any:
    if torch_mod is None:
        return nullcontext()
    if hasattr(torch_mod, "inference_mode"):
        return torch_mod.inference_mode()
    if hasattr(torch_mod, "no_grad"):
        return torch_mod.no_grad()
    return nullcontext()


def _sync_if_cuda(torch_mod: Any, device: Any) -> None:
    if torch_mod is None or device is None:
        return
    if "cuda" in str(device).lower() and hasattr(torch_mod, "cuda"):
        torch_mod.cuda.synchronize()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run optional classifier comparators.")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--request-json", required=True)
    parser.add_argument("--mode", choices=["logits", "single-token-generate", "json-generate"], default="logits")
    parser.add_argument("--load-in-4bit", action="store_true")
    parser.add_argument("--dtype", default="bfloat16")
    parser.add_argument("--device-map", default="auto")
    parser.add_argument("--max-input-tokens", type=int, default=DEFAULT_MAX_INPUT_TOKENS)
    parser.add_argument("--max-batch-size", type=int, default=DEFAULT_MAX_BATCH_SIZE)
    parser.add_argument("--max-new-tokens", type=int, default=96)
    args = parser.parse_args(argv)
    request = json.loads(Path(args.request_json).read_text(encoding="utf-8"))
    loader = load_local_comparator(
        args.model_path, load_in_4bit=args.load_in_4bit, dtype=args.dtype,
        device_map=args.device_map, max_input_tokens=args.max_input_tokens,
        max_batch_size=args.max_batch_size)
    if args.mode == "single-token-generate":
        from train.classifier_token_generation import TransformersSingleTokenGenerationComparator
        comparator = TransformersSingleTokenGenerationComparator(
            loader.model, loader.tokenizer, max_input_tokens=args.max_input_tokens,
            max_batch_size=args.max_batch_size)
        result = comparator.generate_requests([request])[0]
    elif args.mode == "json-generate":
        from train.classifier_token_generation import TransformersJSONGenerationComparator
        comparator = TransformersJSONGenerationComparator(
            loader.model, loader.tokenizer, max_input_tokens=args.max_input_tokens,
            max_batch_size=args.max_batch_size, max_new_tokens=args.max_new_tokens)
        result = comparator.generate_requests([request])[0]
    else:
        result = loader.score_requests([request])[0]
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
