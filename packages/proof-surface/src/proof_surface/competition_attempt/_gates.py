"""Competition-attempt gates: the certificate ladder cannot be inflated.

Harvest of the SAIR competition dogfood cluster (0136 pattern, 0137 hermetic
fixture, 0138 source-pinned judge-repo adapter, 0139 fenced Stage-2 rung).
Three load-bearing honesty rules: (1) prompt instructions must never be parsed
as answers -- a non-boxed extraction must record an injection check, and an
unrendered template marker in the extracted answer is rejected; (2) an
UNAVAILABLE_FENCED certificate layer must cite the probe that proved the fence
and may not smuggle a pass/fail result; (3) no tier inflation -- the overall
verdict may only cite layers that EXECUTED, and MATCH is only derivable from
an executed, passing judge verdict.
"""

from __future__ import annotations

from typing import Any

from .._validate import Issue, reject_unknown, require_enum, require_text

EXTRACTION_METHODS = {"boxed", "last-labeled", "bare-last-line"}
ANSWER_EXTRACTION_FIELDS = {"method", "extracted_ref", "injection_checked"}

CERTIFICATE_LAYERS = {
    "informal-model-output",
    "machine-checked-proof",
    "finite-counterexample",
    "judge-verdict",
}
LAYER_STATUSES = {"EXECUTED", "UNAVAILABLE_FENCED"}
LAYER_FIELDS = {"layer", "status", "evidence_ref", "probe_evidence", "passing"}
JUDGE_LAYER = "judge-verdict"


def _opt_text(value: Any, path: str, issues: list[Issue]) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        issues.append(Issue(path, "expected non-empty string or null"))


def validate_answer_extraction(value: Any, issues: list[Issue]) -> None:
    """0137: prompt instructions must never be parsed as answers."""
    path = "$.answer_extraction"
    if not isinstance(value, dict):
        issues.append(Issue(path, "expected object"))
        return
    reject_unknown(value, path, ANSWER_EXTRACTION_FIELDS, issues)
    require_enum(value, "method", EXTRACTION_METHODS, issues, f"{path}.method")
    require_text(value, "extracted_ref", issues, f"{path}.extracted_ref")
    extracted = value.get("extracted_ref")
    if isinstance(extracted, str) and ("{{" in extracted or "}}" in extracted):
        issues.append(
            Issue(
                f"{path}.extracted_ref",
                "unrendered template marker -- an unrendered prompt placeholder "
                "is not an extracted answer",
            )
        )
    checked = value.get("injection_checked")
    if not isinstance(checked, bool):
        issues.append(Issue(f"{path}.injection_checked", "expected boolean"))
        return
    if value.get("method") in EXTRACTION_METHODS - {"boxed"} and not checked:
        issues.append(
            Issue(
                f"{path}.injection_checked",
                "a non-boxed extraction must record an injection check -- "
                "prompt instructions must never be parsed as answers",
            )
        )


def _validate_layer(item: Any, path: str, seen: set[str], issues: list[Issue]) -> None:
    if not isinstance(item, dict):
        issues.append(Issue(path, "expected object"))
        return
    reject_unknown(item, path, LAYER_FIELDS, issues)
    require_enum(item, "layer", CERTIFICATE_LAYERS, issues, f"{path}.layer")
    require_enum(item, "status", LAYER_STATUSES, issues, f"{path}.status")
    layer = item.get("layer")
    if layer in CERTIFICATE_LAYERS:
        if layer in seen:
            issues.append(Issue(f"{path}.layer", "duplicate certificate layer"))
        seen.add(layer)
    _opt_text(item.get("evidence_ref"), f"{path}.evidence_ref", issues)
    _opt_text(item.get("probe_evidence"), f"{path}.probe_evidence", issues)
    passing = item.get("passing")
    if passing is not None and not isinstance(passing, bool):
        issues.append(Issue(f"{path}.passing", "expected boolean or null"))
    if item.get("status") != "UNAVAILABLE_FENCED":
        return
    probe = item.get("probe_evidence")
    if not isinstance(probe, str) or not probe.strip():
        issues.append(
            Issue(
                f"{path}.probe_evidence",
                "an UNAVAILABLE_FENCED layer must cite the probe that proved "
                "the fence -- a fence without its probe is an unwitnessed excuse",
            )
        )
    if isinstance(passing, bool):
        issues.append(
            Issue(
                f"{path}.passing",
                "a fenced layer cannot carry a pass/fail result -- "
                "unexecuted is not a verdict",
            )
        )


def validate_certificate_layers(value: Any, issues: list[Issue]) -> None:
    """0139: a fence must cite its probe; the ladder is closed and duplicate-free."""
    path = "$.certificate_layers"
    if not isinstance(value, list):
        issues.append(Issue(path, "expected array"))
        return
    if not value:
        issues.append(Issue(path, "expected at least one certificate layer"))
    seen: set[str] = set()
    for index, item in enumerate(value):
        _validate_layer(item, f"{path}[{index}]", seen, issues)


def executed_layer_names(layers: Any) -> set[str]:
    """The layer names that actually EXECUTED (the only citable evidence)."""
    if not isinstance(layers, list):
        return set()
    return {
        item.get("layer")
        for item in layers
        if isinstance(item, dict)
        and item.get("status") == "EXECUTED"
        and item.get("layer") in CERTIFICATE_LAYERS
    }


def validate_verdict_citation(layers: Any, verdicts: Any, issues: list[Issue]) -> None:
    """No tier inflation: the verdict may only cite EXECUTED layers, and MATCH
    requires an executed, passing judge verdict."""
    if not isinstance(verdicts, dict):
        return
    executed = executed_layer_names(layers)
    cited = verdicts.get("cited_layers")
    if not isinstance(cited, list):
        issues.append(
            Issue(
                "$.verdicts.cited_layers",
                "expected array of executed certificate layer names",
            )
        )
    else:
        for index, name in enumerate(cited):
            if name not in CERTIFICATE_LAYERS:
                issues.append(
                    Issue(
                        f"$.verdicts.cited_layers[{index}]",
                        "expected a known certificate layer",
                    )
                )
            elif name not in executed:
                issues.append(
                    Issue(
                        f"$.verdicts.cited_layers[{index}]",
                        f"tier inflation: the verdict cites layer {name!r} which "
                        "did not EXECUTE -- a verdict may only cite executed layers",
                    )
                )
    if verdicts.get("overall") != "MATCH":
        return
    judge_passed = isinstance(layers, list) and any(
        isinstance(item, dict)
        and item.get("layer") == JUDGE_LAYER
        and item.get("status") == "EXECUTED"
        and item.get("passing") is True
        for item in layers
    )
    if not judge_passed:
        issues.append(
            Issue(
                "$.verdicts.overall",
                "MATCH requires an EXECUTED, passing judge-verdict layer -- "
                "a passing verdict with no executed judge is not derivable",
            )
        )
