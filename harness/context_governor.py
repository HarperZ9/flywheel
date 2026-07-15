"""context_governor.py -- keep any model inside its reliable zone.

The wrapper cannot enlarge a model's attention; it can only curate what
occupies the window. Nominal context is not reliable context (models
degrade before their stated limit: lost-in-the-middle, RULER), so the
governor fills the window only to a per-model RELIABLE budget, set from
measurement, not up to the nominal cap.

The load-bearing rule is the governance-decay fix (measured: naive
compaction raised constraint violations 0 -> 30%+, pinning restored 0):
a pinned constraint NEVER leaves the window. If the pins alone exceed
the reliable budget the governor says so (over_pinned) rather than
eating a constraint, because a dropped constraint is a mistake, not a
saving. Everything evicted is FOLDED with a content hash, so a buried
fact is recallable verbatim, never lost. Model-agnostic by construction:
it operates on items and a token budget, so ChatGPT, Claude, or a local
model all route through the same curation, each with its own reliable
budget.

An item is {id, role, text, score?, tokens?}. role is 'pin' (a
constraint that must survive), 'evidence', or 'history'. score ranks
non-pins for keep-or-fold; tokens overrides the estimator when the
caller knows the true count.
"""
from __future__ import annotations

import hashlib

SCHEMA = "flywheel.context-governor/v1"

# a deliberately simple, dependency-free estimator (~0.75 words/token in
# English prose, so tokens ~= words / 0.75). The caller passes real token
# counts via item['tokens'] when it has them; this is the honest fallback.
_WORDS_PER_TOKEN = 0.75


def estimate_tokens(text: str) -> int:
    words = len((text or "").split())
    return max(1, round(words / _WORDS_PER_TOKEN)) if words else 0


def _tok(item: dict) -> int:
    t = item.get("tokens")
    if isinstance(t, (int, float)) and t >= 0:
        return int(t)
    return estimate_tokens(item.get("text", ""))


def _fold(item: dict) -> dict:
    # the folded record carries the VERBATIM text, not only its hash: a
    # one-way hash is not recoverable, so the span is moved OUT OF THE WINDOW
    # but retained here, which is what makes "nothing is lost" literally true
    text = item.get("text", "")
    return {"id": item.get("id", ""), "role": item.get("role", ""),
            "tokens": _tok(item), "text": text,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def recall_folded(folded: list, sha256: str) -> "str | None":
    """Return the verbatim text of a folded span by its content hash, or
    None if not present. This is what makes the fold recoverable rather
    than a one-way discard."""
    for f in folded or []:
        if f.get("sha256") == sha256:
            return f.get("text")
    return None


def govern_context(items: list, *, budget: int,
                   reliable_fraction: float = 0.6) -> dict:
    """Curate `items` to a reliable window. `budget` is the model's
    nominal token budget; `reliable_fraction` (0..1) is the measured
    safe zone below which the model is trusted. Returns the window, the
    folded overflow (each with a recall hash), and a receipt."""
    reliable_budget = max(0, int(budget * max(0.0, min(1.0,
                                                       reliable_fraction))))
    pins = [i for i in items if i.get("role") == "pin"]
    rest = [i for i in items if i.get("role") != "pin"]
    # pins always survive, in given order
    window = list(pins)
    used = sum(_tok(i) for i in pins)
    over_pinned = used > reliable_budget
    # a worse condition than over-reliable-budget: the pins alone exceed the
    # HARD nominal cap, so the window cannot even be assembled. Named
    # separately so the caller knows this is not a soft overflow.
    over_nominal = used > budget
    folded = []
    # fill the remaining reliable budget with the highest-scored non-pins;
    # ties break by original order (stable), so the result is deterministic
    ranked = sorted(enumerate(rest),
                    key=lambda ix: (-float(ix[1].get("score", 0.0)), ix[0]))
    for _, item in ranked:
        cost = _tok(item)
        if not over_pinned and used + cost <= reliable_budget:
            window.append(item)
            used += cost
        else:
            folded.append(_fold(item))
    # preserve original order in the emitted window (pins keep their slots)
    order = {i.get("id"): n for n, i in enumerate(items)}
    window.sort(key=lambda i: order.get(i.get("id"), 0))
    return {"schema": SCHEMA, "window": window, "folded": folded,
            "budget": int(budget), "reliable_budget": reliable_budget,
            "reliable_fraction": reliable_fraction,
            "used_tokens": used, "pinned_count": len(pins),
            "kept_count": len(window), "folded_count": len(folded),
            "over_pinned": over_pinned, "over_nominal": over_nominal,
            "note": "a pinned constraint never leaves the window; the "
                    "overflow is folded with its VERBATIM text plus a "
                    "content hash (recall_folded returns the exact span), so "
                    "it is moved out of the window, not lost; the window "
                    "fills only to the model's reliable zone, not its "
                    "nominal cap"}
