"""access_gap.py -- one measured-gap record per run, built on the provider access-gap record.

The access-gap record says what each provider documents an outside caller can
see. A run says what this caller saw. measured_gap() sets the two side by side,
field by field: MATCH when the run agrees with the documentation, DRIFT when it
contradicts it, UNVERIFIABLE when one run cannot settle the field (an absence
in one response does not contradict a documented field), and DOCUMENTED_ONLY
for fields no single call can test (snapshot policy, access routes). It then
lists every quantity the run could not observe, split into outside gaps (a
limit of the provider's interface) and local gaps (work Flywheel could do).

Source hygiene the critic required is computed, not asserted: a cell whose
only sources come from a publisher other than the provider is marked
reseller_only; a cell whose sources carry no page date is marked undated_only;
a cell read longer ago than max_age_days is stale.
"""
from __future__ import annotations

from datetime import date

from . import access_gap_data as data
from .channel import (DRIFT, MATCH, RAW, SUMMARY_SEPARATE, SUMMARY_UNKNOWN, UNSPECIFIED,
                      UNVERIFIABLE, GapRecord)

SCHEMA = "flywheel.measured-gap/v1"
DOCUMENTED_ONLY = "DOCUMENTED_ONLY"
PUBLISHER = {"openai": "OpenAI", "anthropic": "Anthropic", "google": "Google", "xai": "xAI",
             "deepseek": "DeepSeek", "mistral": "Mistral"}
LOCAL_OPEN_WEIGHT = ("ollama",)
DOES_NOT_PROVE = (
    "A measured gap shows what this run could and could not read through documented "
    "interfaces on the recorded date. It says nothing about provider intent, about "
    "whether exposed reasoning is faithful, or about terms of private agreements. "
    "Provider interfaces change; every documentation cell carries its read date.")
_SOURCES = {s["id"]: s for s in data.SOURCES}


def documented(provider: str) -> dict:
    """field -> cell, with source hygiene flags computed from the source register."""
    out = {}
    for cell in data.CELLS:
        if cell["provider"] != provider:
            continue
        srcs = [_SOURCES[s] for s in cell["source_ids"] if s in _SOURCES]
        own = [s for s in srcs if PUBLISHER.get(provider, "") in (s.get("publisher") or "")]
        out[cell["field"]] = dict(cell, reseller_only=bool(srcs) and not own,
                                  undated_only=bool(srcs) and all(not s.get("page_date") for s in srcs),
                                  read_dates=sorted({s["read_date"] for s in srcs}))
    return out


def _observed(captures) -> dict:
    recs = [c.record for c in captures]
    channels = {r.channel for r in recs if r.reasoning_text}
    if RAW in channels:
        text = "raw"
    elif channels & {SUMMARY_SEPARATE, SUMMARY_UNKNOWN}:
        text = "summary"
    elif UNSPECIFIED in channels:
        text = "unspecified_trace"
    else:
        text = "none_seen"
    return {
        "reasoning_text": text,
        "opaque_reasoning_field": "present" if any(r.opaque_fields for r in recs) else "none_seen",
        "reasoning_token_count": "exposed" if any(r.reasoning_tokens_reported != "unknown"
                                                  for r in recs) else "none_seen",
        "output_logprobs_reasoning_models": "exposed" if any(r.logprobs for r in recs) else "none_seen",
        "tool_call_trace": "exposed" if any(r.tool_calls for r in recs) else "none_seen",
    }


def _agree(field: str, doc: str, seen: str) -> str:
    if seen == "none_seen":
        if doc in ("not_exposed", "none", "not_documented", "absent"):
            return MATCH
        return UNVERIFIABLE
    if doc == "unknown":
        return UNVERIFIABLE
    if field == "reasoning_text":
        return MATCH if seen == doc else DRIFT
    if seen == "present":
        return MATCH if doc == "present" else DRIFT
    # seen == "exposed"
    return MATCH if doc in ("exposed", "partial") else DRIFT


def _stale(read_dates: list, observed_on: str, max_age_days: int) -> bool:
    if not read_dates:
        return False
    oldest = date.fromisoformat(min(read_dates))
    return (date.fromisoformat(observed_on) - oldest).days > max_age_days


def _outside_gaps(provider: str, doc: dict, seen: dict) -> list:
    def ev(field):
        cell = doc.get(field, {})
        srcs = ",".join(cell.get("source_ids", [])) or "none"
        return f"access-gap {data.SCHEMA_VERSION} {provider}.{field}={cell.get('value', 'unknown')} " \
               f"(sources {srcs}; read {','.join(cell.get('read_dates', [])) or 'n/a'})"
    gaps = []
    text_doc = doc.get("reasoning_text", {}).get("value", "unknown")
    if text_doc != "raw" and seen["reasoning_text"] != "raw":
        gaps.append(GapRecord("NOT_OBSERVABLE_FROM_OUTSIDE", "raw reasoning", "A1r", "A1s",
                              ev("reasoning_text")))
    if text_doc in ("summary", "unspecified_trace") or seen["reasoning_text"] == "summary":
        gaps.append(GapRecord("SUMMARY_ONLY_CHANNEL", "reasoning text", "A1r", "A1s",
                              ev("reasoning_text")))
    if doc.get("opaque_reasoning_field", {}).get("value") == "present" \
            or seen["opaque_reasoning_field"] == "present":
        gaps.append(GapRecord("PROVIDER_ENCRYPTED", "opaque reasoning field", "A1r", "A0",
                              ev("opaque_reasoning_field")))
    lp = doc.get("output_logprobs_reasoning_models", {}).get("value", "unknown")
    if lp in ("not_exposed", "partial") and seen["output_logprobs_reasoning_models"] != "exposed":
        gaps.append(GapRecord("LOGPROBS_UNAVAILABLE", "reasoning-token logprobs", "A3", "A0",
                              ev("output_logprobs_reasoning_models")))
    for code, comp, need in (("INTERNALS_UNAVAILABLE", "hidden states and interventions", "A3"),
                             ("REASONING_WRITE_UNAVAILABLE", "edit or prefill reasoning", "A2"),
                             ("TRAINING_ACCESS_UNAVAILABLE", "fine-tuning or RL control", "A5")):
        gaps.append(GapRecord(code, comp, need, "A0",
                              f"{provider}: closed weights; no documented caller path in the "
                              f"access-gap field catalog {data.SCHEMA_VERSION}"))
    return gaps


def measured_gap(provider: str, captures: list, *, run_id: str, observed_on: str,
                 max_age_days: int = 90) -> dict:
    """The per-run measured-gap record. String values only, ready for a receipt."""
    seen = _observed(captures)
    capture_gaps = [g for c in captures for g in c.gaps]
    fields, local = [], list(capture_gaps)
    if provider in LOCAL_OPEN_WEIGHT:
        doc = {}
        outside = []
        local.append(GapRecord("ACCESS_CLASS_UNAVAILABLE_LOCALLY", "hidden states on a thinking model",
                               "A3", "A1r", "Ollama returns reasoning and logprobs, not hidden states"))
    else:
        doc = documented(provider)
        if not doc:
            raise ValueError(f"no access-gap cells for provider {provider!r}")
        outside = [g for g in _outside_gaps(provider, doc, seen)
                   if g.gap_code not in {c.gap_code for c in capture_gaps}]
    for field in data.FIELDS:
        cell = doc.get(field, {"value": "unknown", "confidence": "unknown", "source_ids": [],
                               "reseller_only": False, "undated_only": False, "read_dates": []})
        agreement = _agree(field, cell["value"], seen[field]) if field in seen else DOCUMENTED_ONLY
        stale = _stale(cell["read_dates"], observed_on, max_age_days)
        fields.append({"field": field, "documented": cell["value"],
                       "observed": seen.get(field, "not_testable_in_one_call"),
                       "agreement": agreement, "confidence": cell["confidence"],
                       "source_ids": list(cell["source_ids"]),
                       "reseller_only": "true" if cell["reseller_only"] else "false",
                       "undated_only": "true" if cell["undated_only"] else "false",
                       "stale": "true" if stale else "false"})
        if doc and cell["value"] == "unknown":
            local.append(GapRecord("DOCUMENTATION_UNREAD", field, evidence=f"{provider}.{field} unknown "
                                   f"in access-gap {data.SCHEMA_VERSION}"))
        if stale:
            local.append(GapRecord("DOCUMENTATION_STALE", field, evidence=f"read {cell['read_dates']}"))
    drift = [f["field"] for f in fields if f["agreement"] == DRIFT]
    return {
        "schema": SCHEMA, "run_id": run_id, "provider": provider, "observed_on": observed_on,
        "built_on": {"schema": data.SCHEMA, "schema_version": data.SCHEMA_VERSION,
                     "compiled": data.COMPILED, "source_sha256": data.SOURCE_SHA256},
        "turns": str(len(captures)),
        "access_classes": sorted({k for c in captures for k in c.record.classes()}),
        "fields": fields,
        "documentation_drift": drift,
        "not_observable_from_outside": [g.to_dict() for g in outside + [
            g for g in capture_gaps if g.scope == "outside_observability"]],
        "not_yet_observed_local": [g.to_dict() for g in local if g.scope == "local_setup"],
        "does_not_prove": DOES_NOT_PROVE,
    }
