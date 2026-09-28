"""Optional first-token decision classifier baseline for local HF models.

This module is not on Flywheel's accept path. It scores a validated
``flywheel.decision-request/v1`` by asking a causal LM for the next-token logit of
visible, tokenizer-verified one-token labels. The probabilities are uncalibrated
and normalized only over eligible choices plus an explicit abstain label.
"""
from __future__ import annotations

import json
import math
import string
from dataclasses import dataclass
from typing import Any, Iterable

from harness.decision_contract import evaluate_proposal, validate_request

ABSTAIN_CHOICE_ID = "__abstain__"
RESULT_SCHEMA = "flywheel.classifier-token-baseline.result/v1"
CACHE_CAPABILITY = "batched_prompt_forward_no_shared_prefix_kv_cache"


class VerbalizerError(ValueError):
    """The tokenizer cannot provide enough unique one-token verbalizers."""


@dataclass(frozen=True)
class VerbalizerMap:
    choice_to_verbalizer: dict[str, str]
    choice_to_token: dict[str, int]
    token_to_choice: dict[int, str]


def default_verbalizer_candidates() -> list[str]:
    values = list(string.ascii_uppercase)
    values.extend(f" {ch}" for ch in string.ascii_uppercase)
    values.extend(str(i) for i in range(100))
    values.extend(f" {i}" for i in range(100))
    values.extend(f" {a}{b}" for a in string.ascii_uppercase for b in string.ascii_uppercase)
    return values


def _encode(tokenizer: Any, text: str) -> list[int]:
    if hasattr(tokenizer, "encode"):
        return list(tokenizer.encode(text, add_special_tokens=False))
    encoded = tokenizer(text, add_special_tokens=False)
    ids = encoded["input_ids"] if isinstance(encoded, dict) else encoded.input_ids
    return list(ids)


def build_verbalizer_map(
    tokenizer: Any,
    request: dict,
    *,
    candidates: Iterable[str] | None = None,
) -> VerbalizerMap:
    snapshot = validate_request(request)
    needed = list(snapshot["eligible_choice_ids"]) + [ABSTAIN_CHOICE_ID]
    selected: dict[str, str] = {}
    selected_ids: dict[str, int] = {}
    used_tokens: set[int] = set()
    pool = list(candidates) if candidates is not None else default_verbalizer_candidates()
    for text in pool:
        if len(selected) >= len(needed):
            break
        if not isinstance(text, str) or not text:
            continue
        ids = _encode(tokenizer, text)
        if len(ids) != 1 or ids[0] in used_tokens:
            continue
        choice = needed[len(selected)]
        selected[choice] = text
        selected_ids[choice] = int(ids[0])
        used_tokens.add(int(ids[0]))
    if len(selected) != len(needed):
        raise VerbalizerError("not enough unique single-token verbalizers")
    return VerbalizerMap(
        choice_to_verbalizer=selected,
        choice_to_token=selected_ids,
        token_to_choice={token: choice for choice, token in selected_ids.items()},
    )


def render_decision_prompt(request: dict, verbalizers: VerbalizerMap) -> str:
    snapshot = validate_request(request)
    lines = [
        "Score one decision request. Reply with exactly one visible label token.",
        f"Decision: {snapshot['decision_ref']}",
        "State:",
        snapshot["state"],
        "Choices:",
    ]
    eligible = set(snapshot["eligible_choice_ids"])
    for choice in snapshot["choices"]:
        cid = choice["id"]
        label = verbalizers.choice_to_verbalizer.get(cid, "(not eligible)")
        status = "eligible" if cid in eligible else "not eligible"
        lines.append(f"- {label} => {cid} [{status}]: {choice['description']}")
    lines.append(f"- {verbalizers.choice_to_verbalizer[ABSTAIN_CHOICE_ID]} => abstain: choose no eligible option")
    lines.append("Return only the label token.")
    lines.append("Label:")
    return "\n".join(lines)


def final_nonpadding_indices(
    attention_mask: Any | None,
    *,
    batch_size: int | None = None,
    sequence_length: int | None = None,
) -> list[int]:
    if attention_mask is None:
        if batch_size is None or sequence_length is None:
            raise ValueError("batch_size and sequence_length are required without attention_mask")
        return [sequence_length - 1 for _ in range(batch_size)]
    rows = attention_mask.tolist() if hasattr(attention_mask, "tolist") else attention_mask
    indices: list[int] = []
    for row in rows:
        last = None
        for idx, value in enumerate(row):
            if int(value) != 0:
                last = idx
        if last is None:
            raise ValueError("attention_mask row has no nonpadding token")
        indices.append(last)
    return indices


def gather_final_logits(logits: Any, attention_mask: Any | None = None) -> list[list[float]]:
    shape = getattr(logits, "shape", None)
    if shape is not None:
        batch, seq_len = int(shape[0]), int(shape[1])
    else:
        batch, seq_len = len(logits), len(logits[0])
    indices = final_nonpadding_indices(attention_mask, batch_size=batch, sequence_length=seq_len)
    rows = []
    for row, idx in enumerate(indices):
        values = logits[row, idx, :] if shape is not None else logits[row][idx]
        if hasattr(values, "detach"):
            values = values.detach().float().cpu().tolist()
        rows.append([float(item) for item in values])
    return rows


def _softmax(logits: list[float]) -> list[float]:
    peak = max(logits)
    exps = [math.exp(value - peak) for value in logits]
    total = sum(exps)
    return [value / total for value in exps]


def score_final_logits(
    final_logits: list[float],
    request: dict,
    verbalizers: VerbalizerMap,
    *,
    scorer_ref: str,
    latency_ms: float | None = None,
    cache_capability: str = "logits_supplied_no_model_call",
) -> dict:
    snapshot = validate_request(request)
    declared = [choice["id"] for choice in snapshot["choices"]]
    eligible = list(snapshot["eligible_choice_ids"])
    scored_keys = eligible + [ABSTAIN_CHOICE_ID]
    raw_logits: list[float] = []
    for key in scored_keys:
        token_id = verbalizers.choice_to_token[key]
        if token_id >= len(final_logits):
            raise ValueError(f"verbalizer token {token_id} outside logits vocabulary")
        raw_logits.append(float(final_logits[token_id]))
    probs = _softmax(raw_logits)
    prob_by_key = dict(zip(scored_keys, probs, strict=True))
    selected_key = max(scored_keys, key=lambda key: prob_by_key[key])
    choice_id = None if selected_key == ABSTAIN_CHOICE_ID else selected_key
    proposal = json.dumps({"choice_id": choice_id, "evidence_refs": []}, separators=(",", ":"))
    scores: dict[str, dict[str, Any]] = {}
    for choice in declared:
        is_eligible = choice in eligible
        scores[choice] = {
            "eligible": is_eligible,
            "probability": prob_by_key.get(choice, 0.0) if is_eligible else 0.0,
            "logit": float(final_logits[verbalizers.choice_to_token[choice]]) if is_eligible else None,
            "verbalizer": verbalizers.choice_to_verbalizer.get(choice),
            "token_id": verbalizers.choice_to_token.get(choice),
        }
    scores[ABSTAIN_CHOICE_ID] = {
        "eligible": True,
        "probability": prob_by_key[ABSTAIN_CHOICE_ID],
        "logit": float(final_logits[verbalizers.choice_to_token[ABSTAIN_CHOICE_ID]]),
        "verbalizer": verbalizers.choice_to_verbalizer[ABSTAIN_CHOICE_ID],
        "token_id": verbalizers.choice_to_token[ABSTAIN_CHOICE_ID],
    }
    return {
        "schema": RESULT_SCHEMA,
        "decision_ref": snapshot["decision_ref"],
        "choice_id": choice_id,
        "scores": scores,
        "proposal_json": proposal,
        "contract_result": evaluate_proposal(snapshot, proposal, scorer_ref=scorer_ref),
        "normalization": "softmax_over_eligible_verbalizers_plus_abstain",
        "cache_capability": cache_capability,
        "latency_ms": latency_ms,
        "uncalibrated": True,
    }
