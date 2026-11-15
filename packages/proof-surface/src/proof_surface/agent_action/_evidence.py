"""Evidence references: preserve the incumbent trace/eval/model/runtime pointers.

Harvest of dogfood pass 0064 ("Required Telos Receipt Fields"). An accountable
action receipt must carry back-references to the incumbent systems it wraps --
the exact native refs the ``trace_adapters`` evidence importers emit -- so "keep
your stack, attach receipts" is structural, not just narrative. Every ref is a
``{ref, optional sha256}`` object, the same shape as ``$.sources``.
"""

from __future__ import annotations

import re
from typing import Any

from .._validate import Issue, reject_unknown, require_text

EVIDENCE_REFS_FIELDS = {"trace_refs", "eval_refs", "model_refs", "runtime_refs"}
REF_FIELDS = {"ref", "sha256"}
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def validate_evidence_refs(value: Any, issues: list[Issue]) -> None:
    """Validate the optional evidence_refs block. Absent or None is valid."""
    if value is None:
        return
    if not isinstance(value, dict):
        issues.append(Issue("$.evidence_refs", "expected object"))
        return
    reject_unknown(value, "$.evidence_refs", EVIDENCE_REFS_FIELDS, issues)
    for key in EVIDENCE_REFS_FIELDS:
        if key not in value:
            continue
        path = f"$.evidence_refs.{key}"
        entries = value.get(key)
        if not isinstance(entries, list):
            issues.append(Issue(path, "expected array"))
            continue
        for index, item in enumerate(entries):
            _validate_ref(item, f"{path}[{index}]", issues)


def _validate_ref(item: Any, path: str, issues: list[Issue]) -> None:
    if not isinstance(item, dict):
        issues.append(Issue(path, "expected object"))
        return
    reject_unknown(item, path, REF_FIELDS, issues)
    require_text(item, "ref", issues, f"{path}.ref")
    sha = item.get("sha256")
    if sha is not None and (not isinstance(sha, str) or not _HEX64.fullmatch(sha)):
        issues.append(
            Issue(f"{path}.sha256", "expected 64-char lowercase hex digest or null")
        )


def adapter_refs(adapter_output: Any) -> list[dict[str, Any]]:
    """Extract the native ref objects a trace_adapters evidence import surfaced.

    Ready to drop straight into an evidence_refs bucket, e.g.
    ``{"eval_refs": adapter_refs(import_braintrust_experiment(exp))}``.
    """
    sources = (
        adapter_output.get("sources") if isinstance(adapter_output, dict) else None
    )
    out: list[dict[str, Any]] = []
    if isinstance(sources, list):
        for source in sources:
            if isinstance(source, dict) and isinstance(source.get("ref"), str):
                entry = {"ref": source["ref"]}
                if isinstance(source.get("sha256"), str):
                    entry["sha256"] = source["sha256"]
                out.append(entry)
    return out
