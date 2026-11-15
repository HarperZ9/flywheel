"""Input grammar for the parser-contract family.

Each variant gets a deterministic battery of probe inputs, one per behavioral
CELL. Cells aim inputs at the contract's load-bearing seams (rung precedence,
last-occurrence-wins, empty-vs-missing, the both-tags think rule, message
scope, content-part joining); the expectation for every probe is derived by
running the committed reference, so a cell whose construction drifts from its
intent can never corrupt the oracle -- it just probes something else.

Everything is a pure function of (variant, probe values); no randomness.
Probe values are ASCII tokens derived from the variant id so no two variants
share payload strings.
"""

from __future__ import annotations

from .parser_contract import Variant

# The edge cells named by the design carry EDGE_CREDIT of each instance's
# probe weight between them; every other cell shares the remainder.
EDGE_CELLS = frozenset(
    {
        "contradict",
        "contradict-within",
        "empty-rung",
        "empty-then-hit",
        "missing-close",
        "think-inside",
        "think-lone-tag",
        "multipart",
        "multipart-split-tag",
    }
)
EDGE_CREDIT = 0.45


def _hit(rung: str, value: str) -> str:
    kind, _, arg = rung.partition(":")
    if kind == "tag":
        return f"<{arg}>{value}</{arg}>"
    if kind == "fence":
        return f"```{arg}\n{value}\n```"
    if kind == "prefix":
        return f"{arg} {value}"
    if rung == "lastline":
        return value
    raise ValueError(rung)


def _empty_form(rung: str) -> str | None:
    kind, _, arg = rung.partition(":")
    if kind == "tag":
        return f"<{arg}></{arg}>"
    if kind == "fence":
        return f"```{arg}\n```"
    if kind == "prefix":
        return arg
    return None  # lastline has no empty form


def _unclosed_form(rung: str, value: str) -> str | None:
    kind, _, arg = rung.partition(":")
    if kind == "tag":
        return f"<{arg}>{value}"
    if kind == "fence":
        return f"```{arg}\n{value}"
    return None  # prefix / lastline cannot be "unclosed"


def _text(recipe_value: str) -> dict:
    return {"kind": "text", "value": recipe_value}


def _chat(*message_texts: str) -> dict:
    return {
        "kind": "chat",
        "messages": [{"role": "assistant", "content": t} for t in message_texts],
    }


def _attr(*message_texts: str) -> dict:
    recipe = _chat(*message_texts)
    recipe["kind"] = "attr"
    return recipe


def probes_for(variant: Variant) -> list[dict]:
    """The probe battery for one variant: ``[{"cell", "recipe"}, ...]``."""
    vid = variant.variant_id.replace("-", "")
    val = lambda tag: f"v{tag}{vid[-8:]}"
    r1 = variant.ladder[0]
    filler = "plain filler sentence."
    probes: list[dict] = []

    def add(cell: str, recipe: dict) -> None:
        probes.append({"cell": cell, "recipe": recipe})

    # Straightforward hits, in all three completion shapes.
    body = f"{filler}\n{_hit(r1, val('a'))}\nafter text."
    add("basic-text", _text(body))
    add("basic-chat", _chat(filler, body))
    add("basic-attr", _attr(filler, body))

    # Every deeper rung: an input where only that rung's pattern appears.
    for k, rung in enumerate(variant.ladder[1:], start=2):
        add(f"rung-{k}", _text(f"{filler}\n{_hit(rung, val(f'r{k}'))}"))

    # Precedence: rung 1 and rung 2 both present, different payloads.
    if len(variant.ladder) > 1:
        add(
            "contradict",
            _text(
                f"{_hit(variant.ladder[1], val('lo'))}\n{_hit(r1, val('hi'))}\n{filler}"
            ),
        )
        # Same, with rung 2 appearing AFTER rung 1 in the text.
        add(
            "contradict-after",
            _text(f"{_hit(r1, val('hi2'))}\n{_hit(variant.ladder[1], val('lo2'))}"),
        )

    # Last-occurrence-wins within a single rung.
    add(
        "contradict-within",
        _text(f"{_hit(r1, val('old'))}\n{filler}\n{_hit(r1, val('new'))}"),
    )

    # Empty vs missing.
    empty = _empty_form(r1)
    if empty is not None:
        add("empty-rung", _text(f"{filler}\n{empty}"))
        if len(variant.ladder) > 1:
            add(
                "empty-then-hit",
                _text(f"{empty}\n{_hit(variant.ladder[1], val('fb'))}"),
            )
    unclosed = _unclosed_form(r1, val("uc"))
    if unclosed is not None:
        add("missing-close", _text(f"{filler}\n{unclosed}"))

    # Think-strip semantics.
    add(
        "think-inside",
        _text(f"<think>\n{_hit(r1, val('th'))}\n</think>\n{filler}"),
    )
    add(
        "think-lone-tag",
        _text(f"<think>\n{filler}\n{_hit(r1, val('lone'))}"),
    )
    add(
        "think-then-hit",
        _text(f"<think>{_hit(r1, val('inner'))}</think>\n{_hit(r1, val('outer'))}"),
    )

    # Message scope: the hit lives in the EARLIER message only.
    add("scope-cross", _chat(f"{filler}\n{_hit(r1, val('sc'))}", filler))
    # And the regression twin: the hit in the LAST message.
    add("scope-last", _chat(filler, _hit(r1, val("sl"))))

    # Content parts.
    add(
        "multipart",
        {
            "kind": "chat",
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": f"{filler}"},
                        {"type": "image", "url": "ignored"},
                        {"type": "text", "text": _hit(r1, val("mp"))},
                    ],
                }
            ],
        },
    )
    if r1.startswith("tag:"):
        name = r1.partition(":")[2]
        add(
            "multipart-split-tag",
            {
                "kind": "chat",
                "messages": [
                    {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": f"<{name}"},
                            {"type": "text", "text": f">{val('sp')}</{name}>"},
                        ],
                    }
                ],
            },
        )

    # Nothing anywhere; and a scope with no non-empty line at all.
    add("all-miss", _text(f"{filler}\nnothing to extract here."))
    add("whitespace-only", _text("   \n\t\n  "))
    return probes


def probe_weights(probes: list[dict]) -> list[float]:
    """Per-probe weights: edge cells share EDGE_CREDIT, the rest share the
    remainder, uniformly within each group."""
    edge_ix = [i for i, p in enumerate(probes) if p["cell"] in EDGE_CELLS]
    base_ix = [i for i, p in enumerate(probes) if p["cell"] not in EDGE_CELLS]
    weights = [0.0] * len(probes)
    if edge_ix:
        for i in edge_ix:
            weights[i] = EDGE_CREDIT / len(edge_ix)
        for i in base_ix:
            weights[i] = (1.0 - EDGE_CREDIT) / len(base_ix)
    else:  # a ladder with no edge-capable rungs: uniform
        for i in base_ix:
            weights[i] = 1.0 / len(base_ix)
    return weights
