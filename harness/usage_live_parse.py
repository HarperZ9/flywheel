"""Parsing and bounded HTTP helpers for private live usage telemetry."""
from __future__ import annotations

import ipaddress
import hashlib
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BYTE_LIMIT, HTTP_TIMEOUT = 262_144, 0.6
MAX_ENDPOINTS = 16
PROMPT_MISSING = "Prompt-processing counter not reported"


def display_model(raw: str) -> str:
    """Keep ordinary model/repository IDs; pseudonymize paths and unsafe labels."""
    raw = str(raw)
    if (len(raw) <= 120 and not raw.lower().startswith(("sk-", "hf_"))
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)?", raw)):
        return raw
    return "model-" + hashlib.sha256(raw.encode()).hexdigest()[:12]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_text(url: str, timeout: float, byte_limit: int) -> str:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    req = urllib.request.Request(url, headers={
        "Accept": "application/json,text/plain,*/*",
        "User-Agent": "flywheel-usage-live/1"})
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read(byte_limit + 1)
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            raise RuntimeError("redirect refused") from exc
        raise RuntimeError(f"http error {exc.code}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError("endpoint unavailable") from exc
    if len(raw) > byte_limit:
        raise RuntimeError("telemetry response too large")
    return raw.decode("utf-8", "replace")


def http_json(url: str, timeout: float, byte_limit: int) -> Any:
    try:
        return json.loads(http_text(url, timeout, byte_limit))
    except json.JSONDecodeError as exc:
        raise RuntimeError("telemetry response was not json") from exc


def literal_loopback_base(raw_url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(str(raw_url or "").strip())
        ip = ipaddress.ip_address(parsed.hostname or "")
    except ValueError:
        return ""
    if (parsed.scheme not in ("http", "https") or not ip.is_loopback
            or parsed.username or parsed.password or parsed.query
            or parsed.fragment):
        return ""
    path = parsed.path.rstrip("/")
    if path == "/v1" or path.endswith("/v1"):
        path = path[:-3].rstrip("/")
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not 0 <= value <= 2 ** 53 - 1:
        return None
    v = float(value)
    return v if math.isfinite(v) and v.is_integer() else None


def _prom_number(raw: str) -> float | None:
    try:
        v = float(raw.strip())
    except ValueError:
        return None
    return _number(v)


def _lookup(row: dict, path: str) -> tuple[bool, Any]:
    cur: Any = row
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


def _field_number(row: dict, names: tuple[str, ...]) -> tuple[bool, float | None]:
    for name in names:
        found, raw = _lookup(row, name)
        if found:
            return True, _number(raw)
    return False, None


def parse_llamacpp_slots(endpoint_model: str, get_json, base: str) -> dict | None:
    raw = get_json(f"{base}/slots", HTTP_TIMEOUT, BYTE_LIMIT)
    if not isinstance(raw, list) or not 0 < len(raw) <= MAX_ENDPOINTS:
        return None
    generated = prompt = 0.0
    prompt_missing = False
    reset_parts = []
    for idx, slot in enumerate(raw[:MAX_ENDPOINTS]):
        if not isinstance(slot, dict):
            return None
        dec_found, dec = _field_number(slot, ("next_token.n_decoded", "n_decoded"))
        if not dec_found or dec is None:
            return None
        prompt_found, pre = _field_number(slot, ("n_prompt_tokens_processed",))
        if prompt_found and pre is None:
            return None
        generated += dec
        if prompt_found:
            prompt += pre or 0.0
        else:
            prompt_missing = True
        slot_id = slot.get("id", idx)
        reset_parts.append(f"{slot_id}:{slot.get('id_task', slot.get('task_id', ''))}")
    if _number(generated) is None or _number(prompt) is None:
        return None
    return {"model": endpoint_model, "source": "llamacpp.slots",
            "generated": generated, "prompt": None if prompt_missing else prompt,
            "reset_key": "|".join(reset_parts), "scope": "current_request"}


def parse_vllm_metrics(endpoint_model: str, get_text, base: str) -> list[dict] | None:
    text = get_text(f"{base}/metrics", HTTP_TIMEOUT, BYTE_LIMIT)
    groups = {}
    lines = str(text).splitlines()
    if len(lines) > 5000:
        return None
    for line in lines:
        if not line or line.startswith("#") or " " not in line:
            continue
        head, raw_value = line.split(None, 1)
        name = head.split("{", 1)[0]
        if name not in ("vllm:generation_tokens_total",
                        "vllm_generation_tokens_total",
                        "vllm:prompt_tokens_total",
                        "vllm_prompt_tokens_total"):
            continue
        value = _prom_number(raw_value.split()[0])
        if value is None:
            return None
        labels = dict(re.findall(r'([A-Za-z_][A-Za-z0-9_]*)="([^"]*)"', head))
        model = labels.get("model_name") or labels.get("model") or endpoint_model
        group = groups.setdefault(model, {"generated": None, "prompt": None})
        if len(groups) > 32:
            return None
        field = "generated" if "generation_tokens_total" in name else "prompt"
        group[field] = (group[field] or 0) + value
        if _number(group[field]) is None:
            return None
    if not groups or any(g["generated"] is None for g in groups.values()):
        return None
    return [{"model": model, "source": "vllm.prometheus", **values,
             "reset_key": "vllm", "scope": "current_runtime"}
            for model, values in sorted(groups.items())]
