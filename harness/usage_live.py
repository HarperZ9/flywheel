"""Private live local-runtime usage sampler."""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

from .usage_live_config import EndpointTelemetry
from .usage_live_parse import (
    PROMPT_MISSING,
    display_model,
    literal_loopback_base,
    parse_llamacpp_slots,
    parse_vllm_metrics,
)

SCHEMA = "flywheel.usage-live/v1"
MAX_ENDPOINTS, MAX_CACHE = 16, 32

def _model_row(endpoint: EndpointTelemetry, model: str, status: str, source: str,
               observed_utc: str, reason: str = "") -> dict:
    model = display_model(model or endpoint.model)
    return {
        "id": f"{endpoint.endpoint}:{model}",
        "model": model,
        "endpoint": endpoint.endpoint,
        "status": status,
        "source": source,
        "counter_scope": "current_runtime",
        "decode_tokens_per_second": None,
        "prefill_tokens_per_second": None,
        "generated_tokens": None,
        "prompt_tokens": None,
        "reason": reason,
        "report_denominator": {"kind": "live_poll_delta_seconds",
                               "seconds": None,
                               "last_observed_utc": observed_utc},
    }

def _source_label(counter_source: str, endpoint: EndpointTelemetry) -> str:
    if not endpoint.source or endpoint.source == counter_source:
        return counter_source
    return f"{counter_source} via {endpoint.source}"

class UsageLiveSampler:
    def __init__(self, *, get_json=None, get_text=None, now_seconds=None,
                 now_utc=None):
        from .usage_live_parse import http_json, http_text
        self._get_json = get_json or http_json
        self._get_text = get_text or http_text
        self._now_seconds = now_seconds or time.monotonic
        self._now_utc = now_utc or (lambda: datetime.now(timezone.utc))
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.Lock()

    def snapshot(self, endpoints: list[EndpointTelemetry] | None = None) -> dict:
        with self._lock:
            rows = list(endpoints or [])
            if not rows:
                self._cache.clear()
            models = []
            for ep in rows[:MAX_ENDPOINTS]:
                result = self._probe(ep)
                models.extend(result if isinstance(result, list) else [result])
            observed_utc = self._now_utc().isoformat()
        return {
            "schema": SCHEMA,
            "observed_utc": observed_utc,
            "clock": {"source": "process monotonic plus UTC wall clock"},
            "counter_scope": "per-model current_runtime or current_request",
            "source_semantics": {"llamacpp.slots": "slot counters scoped to current task ids",
                                 "vllm.prometheus": "process cumulative token counters"},
            "models": models,
        }

    def _stamp(self) -> tuple[float, str]:
        return float(self._now_seconds()), self._now_utc().isoformat()

    def _probe(self, endpoint: EndpointTelemetry) -> dict:
        now, observed_utc = self._stamp()
        if endpoint.endpoint not in ("llamacpp", "vllm"):
            return _model_row(endpoint, endpoint.model, "unavailable",
                              _source_label(endpoint.source, endpoint),
                              observed_utc,
                              "live telemetry unsupported for endpoint")
        telemetry_source = ("llamacpp.slots" if endpoint.endpoint == "llamacpp"
                            else "vllm.prometheus")
        counter_scope = ("current_request" if endpoint.endpoint == "llamacpp"
                         else "current_runtime")
        base = literal_loopback_base(endpoint.base_url)
        if not base:
            row = _model_row(endpoint, endpoint.model, "unavailable",
                             _source_label(telemetry_source, endpoint),
                             observed_utc,
                             "endpoint is not a literal loopback URL")
            row["counter_scope"] = counter_scope
            return row
        try:
            if endpoint.endpoint == "llamacpp":
                parsed = parse_llamacpp_slots(endpoint.model, self._get_json, base)
            else:
                parsed = parse_vllm_metrics(endpoint.model, self._get_text, base)
        except RuntimeError as exc:
            self._forget(endpoint)
            _now, observed_utc = self._stamp()
            row = _model_row(endpoint, endpoint.model, "unavailable",
                             _source_label(telemetry_source, endpoint),
                             observed_utc, str(exc))
            row["counter_scope"] = counter_scope
            return row
        now, observed_utc = self._stamp()
        if parsed is None:
            self._forget(endpoint)
            row = _model_row(endpoint, endpoint.model, "unavailable",
                             _source_label(telemetry_source, endpoint),
                             observed_utc,
                             "invalid runtime counters")
            row["counter_scope"] = counter_scope
            return row
        if isinstance(parsed, list):
            return [self._rate(endpoint, item, now, observed_utc) for item in parsed]
        return self._rate(endpoint, parsed, now, observed_utc)

    def _forget(self, endpoint: EndpointTelemetry) -> None:
        prefix = f"{endpoint.endpoint}|{endpoint.base_url}|"
        for key in list(self._cache):
            if key.startswith(prefix):
                del self._cache[key]

    def _rate(self, endpoint: EndpointTelemetry, parsed: dict, now: float,
              observed_utc: str) -> dict:
        model = str(parsed["model"])
        source = str(parsed["source"])
        row = _model_row(endpoint, model, "warming_up",
                         _source_label(source, endpoint), observed_utc,
                         "collecting baseline")
        row["counter_scope"] = str(parsed.get("scope", "current_runtime"))
        prompt = parsed.get("prompt")
        row["generated_tokens"] = int(parsed["generated"])
        row["prompt_tokens"] = int(prompt) if prompt is not None else None
        if prompt is None:
            row["reason"] = PROMPT_MISSING
        identity = (f"{endpoint.endpoint}|{endpoint.base_url}|{endpoint.model}|"
                    f"{source}|{model}")
        current = {"time": now, "model": model, "generated": parsed["generated"],
                   "prompt": prompt, "reset_key": parsed["reset_key"]}
        previous = self._cache.get(identity)
        self._cache[identity] = current
        self._cache.move_to_end(identity)
        while len(self._cache) > MAX_CACHE:
            self._cache.popitem(last=False)
        if previous is None:
            return row
        elapsed = now - float(previous["time"])
        reset = (previous["reset_key"] != current["reset_key"]
                 or previous["model"] != current["model"]
                 or current["generated"] < previous["generated"]
                 or (current["prompt"] is not None
                     and previous["prompt"] is not None
                     and current["prompt"] < previous["prompt"]))
        if reset:
            row["reason"] = "runtime counters reset or task changed"
            return row
        if elapsed <= 0:
            row["reason"] = "waiting for elapsed denominator"
            return row
        row["status"] = "observed"
        row["reason"] = row["reason"] if prompt is None else ""
        row["decode_tokens_per_second"] = round(
            (current["generated"] - previous["generated"]) / elapsed, 3)
        if current["prompt"] is not None and previous["prompt"] is not None:
            row["prefill_tokens_per_second"] = round(
                (current["prompt"] - previous["prompt"]) / elapsed, 3)
        elif current["prompt"] is not None:
            row["reason"] = "collecting prompt-processing baseline"
        row["report_denominator"]["seconds"] = round(elapsed, 3)
        return row

def handle_usage_live(req_or_qs: Any, _run_root: Any) -> tuple[dict, int]:
    from .usage_live_config import resolve_usage_live_endpoints
    return _LIVE_SAMPLER.snapshot(resolve_usage_live_endpoints(req_or_qs)), 200

_LIVE_SAMPLER = UsageLiveSampler()
