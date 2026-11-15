"""Prose renderer for parser-contract variants.

The prompt a rollout sees IS the contract: every normative rule the reference
implements, rendered from the same Variant object, plus two worked examples
(excluded from scoring) and the emission protocol. Hidden probes are unseen
INSTANCES of these rules, never unseen requirements.
"""

from __future__ import annotations

from .parser_contract import Variant, reference_parse

_RUNG_PROSE = {
    "tag": (
        'RUNG {n}: the tag <{arg}>. Candidate: the LAST occurrence of "<{arg}>" '
        'that has a "</{arg}>" somewhere after it; the candidate content is the '
        "text between that open tag and the FIRST close tag after it, stripped "
        "of surrounding whitespace. An open tag with no close tag after it is "
        "a MISS for that occurrence."
    ),
    "fence": (
        "RUNG {n}: the ```{arg} code fence. Candidate: the content of the LAST "
        "fence opened by a line starting ```{arg} and closed by ```, stripped. "
        "An unclosed fence is a MISS."
    ),
    "prefix": (
        'RUNG {n}: the line marker "{arg}". Candidate: take the LAST line '
        'whose content (ignoring leading whitespace) starts with "{arg}"; the '
        "candidate content is the remainder of that line after the marker, "
        "stripped."
    ),
    "lastline": (
        "RUNG {n}: the last non-empty line. Candidate: the LAST line containing "
        "any non-whitespace character, stripped."
    ),
}


def _rung_prose(n: int, rung: str) -> str:
    kind, _, arg = rung.partition(":")
    if rung == "lastline":
        return _RUNG_PROSE["lastline"].format(n=n)
    return _RUNG_PROSE[kind].format(n=n, arg=arg)


def _worked_examples(variant: Variant) -> list[tuple[str, str]]:
    """Two (input description, expected output) pairs, derived by running the
    reference so they can never contradict it. Payload tokens use the
    ``example`` prefix, which the grammar never emits, so these rows are
    disjoint from every scored probe by construction."""
    r1 = variant.ladder[0]
    kind, _, arg = r1.partition(":")
    if kind == "tag":
        hit = f"<{arg}>exampleAlpha</{arg}>"
    elif kind == "fence":
        hit = f"```{arg}\nexampleAlpha\n```"
    elif kind == "prefix":
        hit = f"{arg} exampleAlpha"
    else:
        hit = "exampleAlpha"
    text_one = f"intro words.\n{hit}\ntrailing words."
    text_two = "no recognizable structure at all."
    examples = []
    for text in (text_one, text_two):
        result = reference_parse(variant, text)
        rendered = "None" if result is None else f'"{result}"'
        examples.append((text, rendered))
    return examples


def render_prompt(variant: Variant) -> str:
    lines: list[str] = []
    a = lines.append
    a(
        "Write a Python module implementing EXACTLY the extraction contract "
        "below, using the verifiers library's parser interface."
    )
    a("")
    a("## Deliverable")
    a("")
    a(
        "Your module must define `build_parser()` returning an object whose "
        "`parse_answer(completion)` implements the contract. `completion` is "
        "either a plain string, a list of message dicts with `role` and "
        "`content` keys, or a list of message objects with `.role` and "
        "`.content` attributes. A message's `content` is either a string or a "
        'list of parts; each part is a dict, and only parts with `"type": '
        '"text"` contribute their `"text"` value.'
    )
    a("")
    a("## The contract, applied in this exact order")
    a("")
    if variant.scope == "last":
        a(
            "1. SCOPE: consider ONLY the last message's content. A plain-string "
            "completion is its own scope."
        )
    else:
        a(
            "1. SCOPE: join every message's content with a single newline, in "
            "order. A plain-string completion is its own scope."
        )
    a(
        "   List-typed content contributes its text-typed parts joined by ONE "
        "space, then stripped."
    )
    if variant.think_strip:
        a(
            "2. THINK-STRIP: remove every complete <think>...</think> section "
            "from the scope text, repeatedly. BOTH tags are required: a lone "
            "<think> or </think> strips nothing."
        )
    else:
        a("2. THINK-STRIP: none. <think> sections are ordinary text.")
    a(
        "3. THE LADDER: try each rung below in order on the scope text. The "
        "first rung that HITS decides the answer."
    )
    for n, rung in enumerate(variant.ladder, start=1):
        a("   " + _rung_prose(n, rung))
    if variant.empty_hit:
        a(
            "4. EMPTY RULE: a rung whose selected candidate strips to the "
            'empty string HITS, and the answer is "". Selection happens '
            "first: a rung never falls back to an earlier occurrence."
        )
    else:
        a(
            "4. EMPTY RULE: a rung whose selected candidate strips to the "
            "empty string MISSES, and the ladder falls through to the next "
            "rung. Selection happens first: a rung never falls back to an "
            "earlier occurrence."
        )
    a("5. If every rung misses, `parse_answer` returns None.")
    a("")
    a("## Worked examples (illustrative only; never scored)")
    a("")
    for text, rendered in _worked_examples(variant):
        a("Input scope text:")
        a("```text")
        a(text)
        a("```")
        a(f"parse_answer returns: {rendered}")
        a("")
    a("## Emission protocol")
    a("")
    a(
        "Reply with your complete module in a single ```python code fence. "
        "Extraction takes everything between the LAST ```python opener and "
        "the LAST ``` in your reply, so your code may itself contain "
        "triple-backtick literals; just do not write anything after your "
        "closing fence except plain prose without backticks. The module must "
        "import nothing beyond the Python standard library and (optionally) "
        "`verifiers`."
    )
    return "\n".join(lines)
