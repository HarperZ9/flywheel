"""model_usage.py -- what a provider actually reported about one model call.

Every hosted backend in endpoints.py used to return {text, model_ref, seed} and
throw the rest of the response away. The provider's usage block went with it, so
no downstream layer could ever price a call, count a cached token, or say which
model the server really served. This module is the capture that survives that
boundary. The field names it reads live in model_dialects, with the source each
one was verified against.

Three rules, the same ones cross_harness_usage.py already holds the inner-call
path to:

- VERBATIM. The provider's own field names are copied as-is into ``reported``.
  Nothing here renames a field, computes a count, or fills a missing one.
- NEVER FILL. A quantity the provider did not report is ABSENT from ``counts``.
  It is never zero. Zero is a measurement and absent is a silence, and a cost
  layer that cannot tell them apart will bill the silence.
- NAMED REFUSAL. A usage block carrying a value that is not a nonnegative
  integer keeps its verbatim form and refuses the normalized reading with a
  reason, rather than coercing the value or dropping the block.

The normalized reading exists because several dialects spell the same quantity
several ways. It is a reading OF the verbatim block, never a replacement for it,
and ``read_from`` names the exact path each count came out of, so a stranger
holding both can re-derive one from the other and catch a misread map.

Standard library only. This module never reads a clock and never makes a call.
"""
from __future__ import annotations

from typing import Any

from .model_dialects import (ABSENT_MEANS_UNREPORTED, ANTHROPIC, BLOCK, BYOK,
                             DIALECTS, GEMINI, INPUT_INCLUDES_CACHE_READ,
                             MEANINGS, OLLAMA, OPENAI,
                             OUTPUT_INCLUDES_REASONING, REPORTED_COST, SERVED)

NOT_AN_OBJECT = "USAGE_NOT_AN_OBJECT: the response carried no usage object"
NOT_COUNTS = ("USAGE_NOT_WHOLE_COUNTS: a reported usage field is not a "
              "nonnegative integer")
UNMAPPED = "USAGE_DIALECT_UNMAPPED: no normalized reading exists for this dialect"


def _dig(obj: Any, path: tuple) -> Any:
    """Walk a path of dict keys and list indices, or None if the walk fails.

    An int step indexes a list. A routing proxy puts the model that actually
    generated an answer at choices[0].message.model, so reaching it means
    stepping through a list, and a dict-only walk cannot express that path at
    all. A negative index is refused rather than wrapped, because wrapping
    would read the last element for a path that asked for one before the first.
    """
    cursor = obj
    for key in path:
        if type(key) is int and isinstance(cursor, list):
            if key < 0 or key >= len(cursor):
                return None
            cursor = cursor[key]
            continue
        if not isinstance(cursor, dict) or key not in cursor:
            return None
        cursor = cursor[key]
    return cursor


def _is_count(value: Any) -> bool:
    """A token count is a nonnegative int. bool is an int in Python and is not
    a count, so it is excluded by type identity rather than by isinstance."""
    return type(value) is int and value >= 0


def reported_block(response: Any, *, dialect: str) -> "dict | None":
    """The provider's own usage block, verbatim, or None if it sent none.

    For ollama the counts sit on the response rather than in a sub-object, so
    the verbatim block is assembled from the fields local_usage already names.
    Reusing that keeps one definition of what an ollama usage field is.
    """
    if not isinstance(response, dict):
        return None
    if dialect == OLLAMA:
        from .local_usage import ollama_native_usage
        return ollama_native_usage(response)
    block = _dig(response, BLOCK.get(dialect, ("usage",)))
    return dict(block) if isinstance(block, dict) else None


def normalized(block: Any, *, dialect: str) -> dict:
    """Read a verbatim block as named quantities, or refuse with a reason.

    The return always carries either ``counts`` or ``refused``, never both and
    never neither. A dialect with no map refuses rather than guessing that its
    keys happen to match another dialect's. Where a meaning has several known
    spellings the first one present answers, and ``read_from`` records which,
    so a wrong map shows up as a wrong path rather than as a plausible number.
    """
    meanings = MEANINGS.get(dialect)
    if meanings is None:
        return {"refused": UNMAPPED}
    if not isinstance(block, dict):
        return {"refused": NOT_AN_OBJECT}
    counts: "dict[str, int]" = {}
    read_from: "dict[str, str]" = {}
    for meaning in sorted(meanings):
        for path in meanings[meaning]:
            value = _dig(block, path)
            if value is None:
                continue               # this spelling absent, try the next
            if not _is_count(value):
                return {"refused": NOT_COUNTS}
            counts[meaning] = value
            read_from[meaning] = ".".join(path)
            break
    return {"counts": counts, "read_from": read_from}


def _is_amount(value: Any) -> bool:
    """A money amount is a nonnegative real. bool is excluded the same way a
    count excludes it, by type identity rather than by isinstance."""
    return type(value) in (int, float) and value >= 0


def served_model(response: Any, *, dialect: str) -> "str | None":
    """The model name the server put on its own response, or None.

    Read through the dialect's preference order, first present wins. ollama
    carries two names on a proxied call: ``model`` is the local alias the
    request used and ``remote_model`` is what actually ran on the cloud host.
    Reading only the first would name the alias and claim it was the model.
    """
    if not isinstance(response, dict):
        return None
    for path in SERVED.get(dialect, (("model",),)):
        value = _dig(response, path)
        if isinstance(value, str) and value:
            return value
    return None


def reported_cost(response: Any, *, dialect: str) -> dict:
    """What the provider says the call cost, in the provider's own unit.

    Measured by the party doing the billing, so it beats the same call priced
    from a local rate card, and a disagreement between the two is a signal
    rather than noise. Values are amounts and not token counts, so they are
    read here and never through the whole-count check. Nothing converts units
    and nothing adds a figure from one provider to a figure from another.

    ``byok`` says the upstream charge landed on the caller's own provider
    account, which changes what the number means and is therefore reported
    beside it rather than folded into it.
    """
    record: dict = {"present": False, "values": {}, "read_from": {},
                    "byok": None, "unit": "provider_native"}
    if not isinstance(response, dict):
        return record
    for name, path in REPORTED_COST.get(dialect, ()):
        value = _dig(response, path)
        if value is None or not _is_amount(value):
            continue
        record["values"][name] = value
        record["read_from"][name] = ".".join(path)
    record["present"] = bool(record["values"])
    flag = _dig(response, BYOK.get(dialect, ()))
    if isinstance(flag, bool):
        record["byok"] = flag
    return record


def capture(response: Any, *, dialect: str, requested_model: str = "") -> dict:
    """One call's usage reading: verbatim, normalized, and who served it.

    ``served_matches_requested`` is None when either name is missing, because a
    comparison with an absent operand is not a disagreement. When both names are
    present and differ, the call was answered by something other than what was
    asked for. That is a fact for a receipt to carry, not a fault to raise on,
    and a pinned revision answering an alias reads as a difference here.

    ``absent_means_unreported`` is False on exactly one dialect. ollama tags
    every metrics field omitempty, so a real zero is dropped from the JSON and
    arrives looking identical to a field the server never filled in. On that
    dialect a missing count is ambiguous, and the record says so rather than
    letting a reader assume the usual meaning.
    """
    block = reported_block(response, dialect=dialect)
    reading = normalized(block, dialect=dialect) if block is not None else None
    served = served_model(response, dialect=dialect)
    matches: "bool | None" = None
    if served and requested_model:
        matches = served == requested_model
    record = {
        "dialect": dialect,
        "reported": block,
        "provenance": "provider_reported" if block else "absent",
        "served_model": served,
        "requested_model": requested_model or None,
        "served_matches_requested": matches,
        "input_includes_cache_read": INPUT_INCLUDES_CACHE_READ.get(dialect),
        "output_includes_reasoning": OUTPUT_INCLUDES_REASONING.get(dialect),
        "absent_means_unreported": ABSENT_MEANS_UNREPORTED.get(dialect),
        "cost": reported_cost(response, dialect=dialect),
    }
    if reading is not None:
        record.update(reading)
    return record


def billable_input(record: Any) -> "int | None":
    """Input tokens that were not served from cache, or None if unknowable.

    A caller pricing a call needs the uncached figure, and the two dialect
    conventions give it either by subtraction or by reading it straight. Where
    an operand for that arithmetic is absent, so is the answer.
    """
    counts = record.get("counts") if isinstance(record, dict) else None
    if not isinstance(counts, dict) or "input" not in counts:
        return None
    if not record.get("input_includes_cache_read"):
        return counts["input"]
    cached = counts.get("cache_read")
    if cached is None:
        return None
    return max(0, counts["input"] - cached)


def billable_output(record: Any) -> "int | None":
    """Output tokens excluding reasoning, or None if unknowable.

    Reasoning tokens bill at the output rate on every provider here, so this is
    not the figure to price a call with. It is the figure that answers how much
    of the spend went to text the caller actually received. A dialect whose
    convention is unknown returns None rather than guessing which side of the
    total its reasoning tokens sit on.
    """
    counts = record.get("counts") if isinstance(record, dict) else None
    if not isinstance(counts, dict) or "output" not in counts:
        return None
    includes = record.get("output_includes_reasoning")
    if includes is False:
        return counts["output"]        # reasoning is already outside output
    if includes is not True:
        return None                    # unknown convention, so no answer
    thinking = counts.get("reasoning")
    if thinking is None:
        return None
    return max(0, counts["output"] - thinking)


def priceable(record: Any) -> dict:
    """The four quantities a price table multiplies, or a reason there are none.

    Kept here rather than in a pricing module so the arithmetic that depends on
    a dialect convention lives beside the convention. Every value is either an
    int the provider reported or None, and None never becomes zero on the way
    to a total.

    ``cache_write_ttl`` is a DECOMPOSITION of ``cache_write`` and never an
    addition to it. Anthropic reports a five-minute and a one-hour bucket whose
    sum is the cache_write figure above, and the buckets are here because they
    price at different rates. A layer that multiplies both levels bills the same
    tokens twice, so this key is nested and named for what it is.
    """
    counts = record.get("counts") if isinstance(record, dict) else None
    if not isinstance(counts, dict):
        reason = record.get("refused") if isinstance(record, dict) else None
        return {"priceable": False, "reason": reason or NOT_AN_OBJECT}
    priced = {
        "priceable": True,
        "uncached_input": billable_input(record),
        "cache_read": counts.get("cache_read"),
        "cache_write": counts.get("cache_write"),
        "output": counts.get("output"),
        "cache_write_ttl": {"5m": counts.get("cache_write_5m"),
                            "1h": counts.get("cache_write_1h")},
    }
    cost = record.get("cost")
    if isinstance(cost, dict) and cost.get("present"):
        # The provider already did this arithmetic against its own rate card.
        priced["provider_reported"] = cost
    return priced


__all__ = ["ANTHROPIC", "DIALECTS", "GEMINI", "NOT_AN_OBJECT", "NOT_COUNTS",
           "OLLAMA", "OPENAI", "UNMAPPED", "billable_input", "billable_output",
           "capture", "normalized", "priceable", "reported_block",
           "reported_cost", "served_model"]
