"""usage_route.py -- the usage-metering surface behind the gateway's thin stubs.

Three entry points, plus the emit-on-route hook the /api/route path calls:

  handle_usage_verify   -- re-check a usage receipt with the offline verifier.
  handle_usage_summary  -- roll the emitted usage receipts under a run root into
                           one session summary (token totals, per-endpoint splits,
                           a priced total that sums ONLY the priced receipts, and
                           an unpriced count) plus the receipts themselves so a
                           client can render and re-verify them.
  emit_route_usage      -- after a routed answer, build + emit a usage receipt
                           chained onto the route receipt, from the provider's
                           reported token usage when it returned one, else a
                           clearly-labeled stdlib estimate. Never raises.

Two provenances are kept distinct, because conflating them would overstate:
  - the TOKEN counts are provider-reported when the provider returned a usage
    object, and an explicit len//4 estimate otherwise;
  - the DOLLAR amount is ALWAYS a table lookup against the small price table
    below, never a provider-billed figure -- so the receipt's cost.note says so,
    and a local endpoint with no per-token charge records no dollar figure at all.

This module reads a clock (datetime.timezone.utc, py3.10-safe) and does decimal
money math; it is NOT on the verifier closure (the verify path is usage_receipt,
which stays import-clean stdlib). Standard library only.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from .tool_call_receipt import _sha256_hex
from .usage_receipt import (
    build_usage_receipt,
    emit_usage_receipt,
    verify_usage_receipt,
)

# Per-MILLION-token list prices, matched by substring of the model_ref. This is a
# SMALL, deliberately labeled table: the dollar figure in any usage receipt is
# always this lookup, never a provider-billed number. List prices drift; a
# receipt records which per-million rates it used so a reader can re-price. More
# specific keys come first so "gpt-4o" does not shadow "gpt-4o-mini".
PRICES_AS_OF = "2026-08"  # illustrative list prices; verify against the provider
PRICES: dict[str, dict[str, str]] = {
    "gpt-4o-mini": {"input": "0.15", "output": "0.60", "currency": "USD"},
    "gpt-5.3-codex": {"input": "1.25", "output": "10.00", "currency": "USD"},
    "gpt-4o": {"input": "2.50", "output": "10.00", "currency": "USD"},
    "deepseek-chat": {"input": "0.27", "output": "1.10", "currency": "USD"},
    "claude-haiku": {"input": "0.80", "output": "4.00", "currency": "USD"},
    "claude-sonnet": {"input": "3.00", "output": "15.00", "currency": "USD"},
    "claude-opus": {"input": "15.00", "output": "75.00", "currency": "USD"},
}


def _now_iso() -> str:
    """UTC timestamp, timezone-aware. datetime.timezone.utc (never the 3.11
    alias) so the module runs on the declared Python floor."""
    return datetime.now(timezone.utc).isoformat()


def _as_int(v: Any) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 0
    return n if n >= 0 else 0


def _estimate_tokens(text: Any) -> int:
    """A stdlib token estimate (~4 chars/token). It is CLEARLY an estimate: any
    receipt built from it carries source='estimated', never provider_reported."""
    return max(0, len(str(text or "")) // 4)


def _usage_ok(raw: Any) -> bool:
    return isinstance(raw, dict) and all(
        isinstance(raw.get(k), int) and not isinstance(raw.get(k), bool)
        for k in ("prompt", "completion", "total"))


def _price_for(model_ref: str) -> dict[str, str] | None:
    lower = str(model_ref or "").lower()
    for key, price in PRICES.items():
        if key in lower:
            return price
    return None


def _looks_local(endpoint: str) -> bool:
    """A local endpoint has no per-token charge. serve/stub are built-in local;
    every other name is resolved against the provider registry's local flag."""
    name = str(endpoint or "").split(":", 1)[0]
    if name in ("serve", "stub", ""):
        return True
    try:
        from . import providers
        spec = providers.REGISTRY.get(name)
        if spec is not None:
            return bool(spec.local)
    except Exception:
        pass
    return False


def _money(prompt: int, completion: int, per_m_in: str, per_m_out: str) -> str:
    """Dollar amount as a decimal STRING (no float ever enters the body):
    (prompt * in + completion * out) / 1e6, at the listed per-million rates."""
    try:
        amt = (Decimal(int(prompt)) * Decimal(str(per_m_in))
               + Decimal(int(completion)) * Decimal(str(per_m_out))) / Decimal(1_000_000)
        return str(amt.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))
    except Exception:
        return ""


def _cost_and_source(tokens: dict, price: dict | None, local: bool,
                     usage_present: bool) -> tuple[dict, str]:
    """The cost block and the one source label. The dollar is a table lookup when
    a price exists; otherwise no dollar figure is recorded and the note says why.
    The label never claims provider_reported when the tokens were estimated."""
    if price is not None:
        amount = _money(tokens["prompt"], tokens["completion"],
                        price.get("input", ""), price.get("output", ""))
        cost = {"amount": amount, "currency": price.get("currency", "USD"),
                "per_million_input": str(price.get("input", "")),
                "per_million_output": str(price.get("output", "")),
                "note": "dollar amount is a table lookup at listed per-million "
                        "prices, not a provider-billed figure"}
        return cost, ("provider_reported" if usage_present else "estimated")
    if local:
        return ({"amount": "", "currency": "", "per_million_input": "",
                 "per_million_output": "",
                 "note": "no per-token price for a local endpoint"}, "unpriced_local")
    return ({"amount": "", "currency": "", "per_million_input": "",
             "per_million_output": "",
             "note": "no price entry for this model"}, "estimated")


def _route_receipt_sha(receipt: Any) -> str:
    """A 64-char content hash of the route receipt, so the usage receipt chains
    onto the exact answer whose spend it meters. Empty when no receipt is given."""
    if not isinstance(receipt, dict):
        return ""
    return _sha256_hex(
        json.dumps(receipt, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def emit_route_usage(route_body: Any, run_root: Any, prompt: str = "") -> str:
    """Build + emit a usage receipt for one routed answer. Returns the bare
    receipt filename, or "" if nothing was written. Never raises: metering must
    not turn a good answer into a 500.

    Provider-reported tokens are used when ``route_body['usage']`` carries them;
    otherwise the tokens are a len//4 estimate and the receipt says so. The
    receipt chains onto the route receipt via prev_receipt_sha256.
    """
    try:
        if run_root is None or not isinstance(route_body, dict):
            return ""
        endpoint = str(route_body.get("endpoint", ""))
        model_ref = str(route_body.get("model_ref", "") or endpoint)
        text = str(route_body.get("text", ""))
        raw_usage = route_body.get("usage")
        usage_present = _usage_ok(raw_usage)
        if usage_present:
            tokens = {"prompt": _as_int(raw_usage.get("prompt")),
                      "completion": _as_int(raw_usage.get("completion")),
                      "total": _as_int(raw_usage.get("total"))}
        else:
            p, c = _estimate_tokens(prompt), _estimate_tokens(text)
            tokens = {"prompt": p, "completion": c, "total": p + c}
        cost, source = _cost_and_source(
            tokens, _price_for(model_ref), _looks_local(endpoint), usage_present)
        now = _now_iso()
        run_id = f"usage-{endpoint or 'route'}-{os.urandom(4).hex()}"
        receipt = build_usage_receipt(
            run_id=run_id, endpoint=endpoint, model_ref=model_ref, tokens=tokens,
            cost=cost, source=source, started_utc=now, finished_utc=now,
            prev_receipt_sha256=_route_receipt_sha(route_body.get("receipt")))
        written = emit_usage_receipt(receipt, Path(run_root) / "usage")
        return written.name if written is not None else ""
    except Exception:  # noqa: BLE001 -- metering must never break the answer path
        return ""


def handle_usage_verify(req: dict) -> tuple[dict, int]:
    """Re-check a usage receipt offline. Always 200: the verdict (MATCH /
    TAMPERED / UNVERIFIABLE) is the answer, so a corrupted receipt is a first-
    class result, never an HTTP error."""
    receipt = req.get("receipt") if isinstance(req, dict) else None
    return verify_usage_receipt(receipt if isinstance(receipt, dict) else None), 200


def _load_usage_receipts(usage_dir: Path, limit: int = 200) -> list[dict]:
    """Every emitted usage receipt under ``usage_dir``, newest first, capped. A
    file that will not parse is skipped, never fatal."""
    out: list[dict] = []
    try:
        files = sorted(usage_dir.glob("usage-receipt-*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return out
    for p in files[:limit]:
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                out.append(obj)
        except Exception:
            continue
    return out


def handle_usage_summary(req_or_qs: Any, run_root: Any) -> tuple[dict, int]:
    """Roll the emitted usage receipts into one session summary. The priced total
    sums ONLY the receipts that carry a dollar amount; the rest are counted as
    unpriced, kept separate so a local session never reads as costing zero when it
    simply has no per-token price. Token totals are digit strings (no floats)."""
    receipts = _load_usage_receipts(Path(run_root) / "usage")
    tp = tc = tt = 0
    by_endpoint: dict[str, dict[str, int]] = {}
    priced_amt = Decimal(0)
    priced_n = 0
    unpriced = 0
    currency = ""
    for r in receipts:
        tk = r.get("tokens", {}) if isinstance(r.get("tokens"), dict) else {}
        p, c, t = _as_int(tk.get("prompt")), _as_int(tk.get("completion")), _as_int(tk.get("total"))
        tp += p
        tc += c
        tt += t
        ep = str(r.get("endpoint", "")) or "(unknown)"
        be = by_endpoint.setdefault(ep, {"n": 0, "prompt": 0, "completion": 0, "total": 0})
        be["n"] += 1
        be["prompt"] += p
        be["completion"] += c
        be["total"] += t
        cost = r.get("cost", {}) if isinstance(r.get("cost"), dict) else {}
        amount = str(cost.get("amount", ""))
        if amount:
            try:
                priced_amt += Decimal(amount)
                priced_n += 1
                currency = currency or str(cost.get("currency", ""))
            except Exception:
                unpriced += 1
        else:
            unpriced += 1
    by_endpoint_str = {
        ep: {"n": str(v["n"]), "prompt": str(v["prompt"]),
             "completion": str(v["completion"]), "total": str(v["total"])}
        for ep, v in sorted(by_endpoint.items())}
    body = {
        "schema": "flywheel.usage-summary/v1",
        "n": str(len(receipts)),
        "total_tokens": {"prompt": str(tp), "completion": str(tc), "total": str(tt)},
        "by_endpoint": by_endpoint_str,
        "priced_total": {"amount": str(priced_amt) if priced_n else "",
                         "currency": currency or "USD", "n": str(priced_n)},
        "unpriced_count": str(unpriced),
        "prices_as_of": PRICES_AS_OF,
        "note": "tokens are provider-reported when the provider returned a usage "
                "object, else an explicit estimate; the dollar total is a table "
                "lookup, never a provider-billed figure",
        "receipts": receipts,
    }
    return body, 200
