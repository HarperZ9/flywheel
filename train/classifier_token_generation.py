"""Optional generation comparators for classifier token baselines."""
from __future__ import annotations

import json
import time
from typing import Any

from harness.decision_contract import evaluate_proposal, validate_request
from train.classifier_token_baseline import (
    ABSTAIN_CHOICE_ID,
    VerbalizerMap,
    build_verbalizer_map,
)
from train.classifier_token_runtime import (
    DEFAULT_MAX_BATCH_SIZE,
    DEFAULT_MAX_INPUT_TOKENS,
    TransformersTokenComparator,
    _as_list,
    _batch_device,
    _inference_context,
    _positive_int,
    _sync_if_cuda,
    _torch_module,
    input_widths,
    render_chat_prompt,
)

SINGLE_TOKEN_GENERATION_SCHEMA = "flywheel.classifier-token-baseline.single-token-generation/v1"
SINGLE_TOKEN_GENERATION_CACHE_CAPABILITY = "single_token_generation_no_cache"
JSON_GENERATION_SCHEMA = "flywheel.classifier-token-baseline.json-generation/v1"
JSON_GENERATION_CACHE_CAPABILITY = "json_generation_no_cache"


class TransformersSingleTokenGenerationComparator(TransformersTokenComparator):
    def __init__(self, *args: Any, max_new_tokens: int = 1, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.max_new_tokens = _positive_int(max_new_tokens, "max_new_tokens")

    def generate_requests(self, requests: list[dict]) -> list[dict]:
        snapshots = [validate_request(req) for req in requests]
        maps = [build_verbalizer_map(self.tokenizer, req) for req in snapshots]
        batch = self._batch_prompts(self._render_prompts(snapshots, maps), left_padding=True)
        generated, latency_ms = _generate(self.model, batch, self.max_new_tokens)
        widths = input_widths(batch)
        return [
            _single_token_result(req, mapping, row, width, latency_ms=latency_ms,
                                 scorer_ref=self.scorer_ref, tokenizer=self.tokenizer)
            for req, mapping, row, width in zip(snapshots, maps, generated, widths, strict=True)
        ]


class TransformersJSONGenerationComparator(TransformersTokenComparator):
    def __init__(
        self,
        model: Any,
        tokenizer: Any,
        *,
        scorer_ref: str = "token_json_generation",
        max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS,
        max_batch_size: int = DEFAULT_MAX_BATCH_SIZE,
        max_new_tokens: int = 96,
    ):
        super().__init__(
            model, tokenizer, scorer_ref=scorer_ref,
            max_input_tokens=max_input_tokens, max_batch_size=max_batch_size)
        self.max_new_tokens = _positive_int(max_new_tokens, "max_new_tokens")

    def generate_requests(self, requests: list[dict]) -> list[dict]:
        snapshots = [validate_request(req) for req in requests]
        prompts = [render_chat_prompt(self.tokenizer, render_json_decision_prompt(req)) for req in snapshots]
        batch = self._batch_prompts(prompts, left_padding=True)
        generated, latency_ms = _generate(self.model, batch, self.max_new_tokens)
        widths = input_widths(batch)
        return [
            _json_result(req, row, width, latency_ms=latency_ms,
                         scorer_ref=self.scorer_ref, tokenizer=self.tokenizer)
            for req, row, width in zip(snapshots, generated, widths, strict=True)
        ]


def render_json_decision_prompt(request: dict) -> str:
    snapshot = validate_request(request)
    eligible = set(snapshot["eligible_choice_ids"])
    lines = [
        "Score one decision request.",
        "Return exactly one JSON object with keys \"choice_id\" and \"evidence_refs\".",
        "Use null choice_id to abstain. Do not include markdown or commentary.",
        f"Decision: {snapshot['decision_ref']}",
        "State:",
        snapshot["state"],
        "Choices:",
    ]
    for choice in snapshot["choices"]:
        status = "eligible" if choice["id"] in eligible else "not eligible"
        lines.append(f"- {choice['id']} [{status}]: {choice['description']}")
    lines.append("Available evidence_refs: " + json.dumps(snapshot["evidence_refs"], separators=(",", ":")))
    lines.append('JSON: {"choice_id": "<eligible choice id or null>", "evidence_refs": []}')
    return "\n".join(lines)


def _generate(model: Any, batch: Any, max_new_tokens: int) -> tuple[Any, float]:
    device = _batch_device(batch, getattr(model, "device", None))
    torch_mod = _torch_module()
    if hasattr(model, "eval"):
        model.eval()
    _sync_if_cuda(torch_mod, device)
    started = time.perf_counter()
    with _inference_context(torch_mod):
        generated = model.generate(
            **batch,
            max_new_tokens=max_new_tokens,
            do_sample=False,
        )
    _sync_if_cuda(torch_mod, device)
    return generated, round((time.perf_counter() - started) * 1000, 3)


def _single_token_result(
    request: dict,
    mapping: VerbalizerMap,
    generated_ids: Any,
    prompt_width: int,
    *,
    latency_ms: float,
    scorer_ref: str,
    tokenizer: Any,
) -> dict[str, Any]:
    new_ids = _continuation_ids(generated_ids, prompt_width)
    raw_text = tokenizer.decode(new_ids, skip_special_tokens=True)
    actual = None
    token_id = None
    for choice, expected in mapping.choice_to_verbalizer.items():
        if raw_text == expected:
            actual = choice
            token_id = mapping.choice_to_token[choice]
            break
    malformed = actual is None
    choice_id = None if malformed or actual == ABSTAIN_CHOICE_ID else actual
    proposal = None if malformed else json.dumps(
        {"choice_id": choice_id, "evidence_refs": []}, separators=(",", ":"))
    contract_input = raw_text if malformed else proposal
    return {
        "schema": SINGLE_TOKEN_GENERATION_SCHEMA,
        "decision_ref": request["decision_ref"],
        "choice_id": choice_id,
        "actual_verbalizer": raw_text if not malformed else None,
        "actual_token_id": token_id,
        "malformed": malformed,
        "malformed_reason": "" if not malformed else "generated_token_not_declared_verbalizer",
        "private_raw_text": raw_text,
        "generated_token_count": len(new_ids),
        "proposal_json": proposal,
        "contract_input": contract_input,
        "contract_result": evaluate_proposal(request, contract_input, scorer_ref=scorer_ref),
        "cache_capability": SINGLE_TOKEN_GENERATION_CACHE_CAPABILITY,
        "latency_ms": latency_ms,
        "uncalibrated": True,
    }


def _json_result(
    request: dict,
    generated_ids: Any,
    prompt_width: int,
    *,
    latency_ms: float,
    scorer_ref: str,
    tokenizer: Any,
) -> dict[str, Any]:
    new_ids = _continuation_ids(generated_ids, prompt_width)
    raw_text = tokenizer.decode(new_ids, skip_special_tokens=True)
    contract = evaluate_proposal(request, raw_text, scorer_ref=scorer_ref)
    malformed = contract["reason_code"] not in {"selected", "abstain"}
    return {
        "schema": JSON_GENERATION_SCHEMA,
        "decision_ref": request["decision_ref"],
        "choice_id": contract["choice_id"],
        "malformed": malformed,
        "malformed_reason": "" if not malformed else contract["reason_code"],
        "private_raw_text": raw_text,
        "generated_token_count": len(new_ids),
        "proposal_json": raw_text,
        "contract_result": contract,
        "cache_capability": JSON_GENERATION_CACHE_CAPABILITY,
        "latency_ms": latency_ms,
        "uncalibrated": True,
    }


def _continuation_ids(generated_ids: Any, prompt_width: int) -> list[int]:
    ids = _as_list(generated_ids)
    return ids[prompt_width:] if len(ids) > prompt_width else ids
