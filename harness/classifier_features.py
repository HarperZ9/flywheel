"""Deterministic features for the native classifier baseline."""
from __future__ import annotations

import hashlib
import math
import re

FEATURE_SCHEMA = "flywheel.classifier-features/v1"
TOKENIZER = "lowercase-ascii-alnum"
HASH_METHOD = "sha256-mod-buckets"
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_:-]*")
MAX_STATE_TOKENS = 96
MAX_DESCRIPTION_TOKENS = 48
MAX_PAIR_TOKENS = 24


class FeatureError(ValueError):
    """Feature extraction failed closed."""


class FeatureBatchCache:
    """Share request-state tokenization across a prediction batch."""

    def __init__(self) -> None:
        self._state_tokens: dict[str, tuple[str, ...]] = {}
        self.state_cache_hits = 0
        self.state_cache_misses = 0

    def state_tokens(self, state: str) -> tuple[str, ...]:
        if state in self._state_tokens:
            self.state_cache_hits += 1
            return self._state_tokens[state]
        self.state_cache_misses += 1
        tokens = tokenize(state, limit=MAX_STATE_TOKENS)
        self._state_tokens[state] = tokens
        return tokens

    def stats(self) -> dict:
        return {
            "state_cache_hits": self.state_cache_hits,
            "state_cache_misses": self.state_cache_misses,
        }


def feature_parameters(feature_buckets: int) -> dict:
    return {
        "schema": FEATURE_SCHEMA,
        "feature_buckets": feature_buckets,
        "hash": HASH_METHOD,
        "tokenizer": TOKENIZER,
        "max_state_tokens": MAX_STATE_TOKENS,
        "max_description_tokens": MAX_DESCRIPTION_TOKENS,
    }


def validate_feature_buckets(value: object) -> int:
    if type(value) is not int or not 8 <= value <= 16_384:
        raise FeatureError("invalid feature bucket count")
    return value


def tokenize(text: str, *, limit: int) -> tuple[str, ...]:
    if type(text) is not str:
        raise FeatureError("feature text must be a string")
    return tuple(TOKEN_RE.findall(text.lower())[:limit])


def _slot(name: str, buckets: int) -> int:
    digest = hashlib.sha256(name.encode("utf-8", "strict")).digest()
    return int.from_bytes(digest[:8], "big") % buckets


def _add(vector: dict[int, float], buckets: int, name: str, value: float) -> None:
    if not math.isfinite(value):
        raise FeatureError("non-finite feature value")
    key = _slot(name, buckets)
    vector[key] = vector.get(key, 0.0) + value


def candidate_feature_vector(
    request: dict,
    choice: dict,
    *,
    feature_buckets: int,
    cache: FeatureBatchCache | None = None,
) -> dict[int, float]:
    """Return hashed candidate/state features without using the candidate id."""
    buckets = validate_feature_buckets(feature_buckets)
    state_tokens = (
        cache.state_tokens(request["state"]) if cache is not None
        else tokenize(request["state"], limit=MAX_STATE_TOKENS)
    )
    desc_tokens = tokenize(
        choice["description"], limit=MAX_DESCRIPTION_TOKENS)
    state_set, desc_set = set(state_tokens), set(desc_tokens)
    overlap = sorted(state_set & desc_set)
    vector: dict[int, float] = {}
    _add(vector, buckets, "bias", 1.0)
    _add(vector, buckets, "state_token_count", min(len(state_tokens), 64) / 64)
    _add(vector, buckets, "description_token_count", min(len(desc_tokens), 64) / 64)
    _add(vector, buckets, "overlap_count", min(len(overlap), 16) / 16)
    desc_scale = 1 / math.sqrt(max(1, len(desc_tokens)))
    for token in desc_tokens:
        _add(vector, buckets, f"description:{token}", desc_scale)
    for token in overlap:
        _add(vector, buckets, f"overlap:{token}", 1.0)
    state_head = state_tokens[:MAX_PAIR_TOKENS]
    desc_head = desc_tokens[:MAX_PAIR_TOKENS]
    pair_scale = 1 / math.sqrt(max(1, len(state_head) * len(desc_head)))
    for state_token in state_head:
        for desc_token in desc_head:
            _add(vector, buckets, f"pair:{state_token}:{desc_token}", pair_scale)
    return {key: value for key, value in vector.items() if value}
