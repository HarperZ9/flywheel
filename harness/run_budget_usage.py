"""run_budget_usage.py -- read the tokens and cost a provider reports.

Providers name their counters differently. These helpers read the provider's
own numbers and never estimate one: a report with no usable counter is None,
and the run budget names that call as one that reported nothing.
"""
from __future__ import annotations

import math

#: Anthropic reports cached input apart from input_tokens, so both are added
#: when no total is given. Codex `cached_input_tokens` and OpenAI
#: `prompt_tokens_details.cached_tokens` are subsets of input and are not.
TOKEN_KEYS = ("prompt_tokens", "input_tokens", "promptTokenCount",
              "completion_tokens", "output_tokens", "candidatesTokenCount",
              "cache_creation_input_tokens", "cache_read_input_tokens")


def reported_tokens(usage) -> int | None:
    """The tokens one provider report covers, or None when it names none."""
    if type(usage) is not dict:
        return None
    total = usage.get("total_tokens", usage.get("totalTokenCount"))
    if type(total) is int and total >= 0:
        return total
    parts = [usage.get(k) for k in TOKEN_KEYS]
    counted = [p for p in parts if type(p) is int and p >= 0]
    return sum(counted) if counted else None


def reported_cost_micros(usage, cost_usd) -> int | None:
    """The spend one report states, in micro-dollars, or None when it states none."""
    value = cost_usd if cost_usd is not None else (
        usage.get("cost") if type(usage) is dict else None)
    if type(value) in (int, float) and math.isfinite(value) and value >= 0:
        return int(round(value * 1_000_000))
    return None


def proposer_usage(usage) -> dict | None:
    """A proposer's usage as a provider report the budget reads.

    Direct API proposers normalize usage to {"prompt", "completion", "total"}
    (proposer.normalize_usage). Other adapters keep the provider's own block,
    which is read as it is."""
    if type(usage) is not dict:
        return None
    total = usage.get("total")
    if reported_tokens(usage) is None and type(total) is int and total >= 0:
        return {"total_tokens": total}
    return usage
