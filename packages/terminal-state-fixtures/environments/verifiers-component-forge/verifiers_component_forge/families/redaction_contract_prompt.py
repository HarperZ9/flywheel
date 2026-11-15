"""Prompt renderer for the redaction-contract family."""

from __future__ import annotations

import json

from .redaction_contract import RedactionVariant, worked_for


def render_prompt(variant: RedactionVariant) -> str:
    examples = worked_for(variant)
    lines: list[str] = []
    a = lines.append
    a(
        "Write a Python module implementing EXACTLY the redaction contract "
        "below. The input values are synthetic; do not add network calls, file "
        "reads, credentials, provider SDKs, or environment access."
    )
    a("")
    a("## Deliverable")
    a("")
    a(
        "Your module must define `redact_record(record)`. It receives one "
        "JSON-like dict and returns one JSON-serializable dict."
    )
    a("")
    a("## Scenario")
    a("")
    a(f"{variant.title}: {variant.purpose}.")
    a("")
    a("## Contract")
    a("")
    a(
        "1. Secret declarations live in `record['secrets']`, a list of dicts "
        "with `name`, `value`, and optional `source`."
    )
    a(
        "2. Replace every non-empty raw secret `value` everywhere it appears "
        "inside any string with `<redacted:NAME>`, where NAME is that secret's "
        "`name`."
    )
    a(
        "3. When secret values overlap, replace longer raw values first so a "
        "short secret never partially redacts a longer one."
    )
    a(
        "4. Preserve non-secret metadata exactly: endpoints, trace IDs, path "
        "labels, sha256 digests, bytes, booleans, numbers, nulls, and "
        "`{'secret_ref': NAME}` objects."
    )
    a("5. Return a dict with `redaction_policy` set to `redaction-contract/1`.")
    a("6. Do not remove rows, reorder lists, hash secret values, or invent new keys.")
    a("")
    a("## Worked examples (illustrative only; never scored)")
    a("")
    for row in examples:
        a("Input:")
        a("```json")
        a(json.dumps(row["record"], indent=2, sort_keys=True))
        a("```")
        a("Expected output:")
        a("```json")
        a(json.dumps(row["expect"], indent=2, sort_keys=True))
        a("```")
        a("")
    a("## Emission protocol")
    a("")
    a(
        "Reply with your complete module in one ```python code fence. "
        "Extraction takes everything between the LAST ```python opener and "
        "the LAST ``` in your reply. Use only the Python standard library."
    )
    return "\n".join(lines)
