"""Deterministic artifact oracles for cross-harness pilot tasks."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any


@dataclass(frozen=True)
class OracleContext:
    task_id: str
    oracle_spec: dict[str, Any]
    raw_output_path: Path
    artifact_paths: dict[str, Path]
    expected_input_sha256s: dict[str, str]
    scorecard_core: dict[str, Any]


@dataclass(frozen=True)
class OracleResult:
    state: str
    checker_id: str
    checker_version: str
    evidence: dict[str, Any]
    failure_codes: list[str]
    checked_artifacts: list[dict[str, str]]


class _DuplicateKey(ValueError):
    pass


def _pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in rows:
        if key in out:
            raise _DuplicateKey(key)
        out[key] = value
    return out


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _result(context: OracleContext, state: str, codes=(), *, evidence=None, checked=()) -> OracleResult:
    checker_id = str(context.oracle_spec.get("checker_id", ""))
    return OracleResult(
        state, checker_id, checker_id.rsplit("/", 1)[-1] if "/" in checker_id else "",
        evidence or {}, sorted(set(codes)), list(checked),
    )


def _inside(root: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        return None
    try:
        path = (root / value).resolve()
        return path if path.is_relative_to(root.resolve()) and path.is_file() else None
    except (OSError, RuntimeError):
        return None


def _load_fixture(context: OracleContext) -> dict[str, Any] | None:
    root = Path(str(context.scorecard_core.get("workspace_root", "")))
    path = _inside(root, context.oracle_spec.get("fixture"))
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs)
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeError, json.JSONDecodeError, _DuplicateKey):
        return None


def _common(context: OracleContext):
    expected = sorted(context.oracle_spec.get("expected_artifacts", []))
    actual = sorted(context.artifact_paths)
    if actual != expected:
        return None, None, _result(context, "fail", ["artifact_set_mismatch"])
    checked = []
    texts: dict[str, str] = {}
    for basename in actual:
        path = context.artifact_paths[basename]
        if not path.is_file():
            return None, None, _result(context, "malformed", ["artifact_not_regular"])
        checked.append({"basename": basename, "sha256": _sha(path)})
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError:
            return None, None, _result(context, "malformed", ["artifact_not_utf8"], checked=checked)
        if not text:
            return None, None, _result(context, "malformed", ["artifact_empty"], checked=checked)
        texts[basename] = text
    json_names = [name for name in actual if name.endswith(".json")]
    md_names = [name for name in actual if name.endswith(".md")]
    if len(json_names) != 1 or len(md_names) != 1:
        return None, None, _result(context, "malformed", ["artifact_set_mismatch"], checked=checked)
    try:
        report = json.loads(texts[json_names[0]], object_pairs_hook=_pairs)
    except _DuplicateKey:
        return None, None, _result(context, "malformed", ["json_duplicate_key"], checked=checked)
    except json.JSONDecodeError:
        return None, None, _result(context, "malformed", ["json_invalid"], checked=checked)
    if not isinstance(report, dict):
        return None, None, _result(context, "malformed", ["json_invalid"], checked=checked)
    codes = []
    if report.get("task_id") != context.task_id:
        codes.append("task_id_mismatch")
    if report.get("input_sha256s") != context.expected_input_sha256s:
        codes.append("input_hash_mismatch")
    if context.task_id not in texts[md_names[0]]:
        codes.append("markdown_task_id_missing")
    if codes:
        return None, None, _result(context, "fail", codes, checked=checked)
    return report, texts, checked


def _index(context: OracleContext, report: dict[str, Any], texts: dict[str, str], fixture: dict[str, Any]) -> list[str]:
    classes: set[str] = set()
    citations: set[str] = set()
    stale_mutated = False
    healthy = False
    for event in fixture.get("events", []):
        if not isinstance(event, dict):
            continue
        kind, outcome = event.get("type"), event.get("outcome")
        derived = None
        if kind == "mcp_call" and outcome == "failure": derived = "live_mcp_failure"
        elif kind == "artifact_read" and event.get("source") == "stale":
            derived = "stale_artifact_use"
            stale_mutated |= event.get("before_sha256") != event.get("after_sha256")
        elif kind == "json_parse" and outcome == "failure": derived = "invalid_json"
        elif kind == "match" and event.get("mode") == "degraded": derived = "degraded_match"
        healthy |= kind == "mcp_call" and outcome == "success"
        if derived:
            classes.add(derived)
            citations.add(str(event.get("event_id", "")))
    codes = []
    if report.get("failure_classes") != sorted(classes): codes.append("failure_classes_mismatch")
    if report.get("cited_event_ids") != sorted(citations): codes.append("event_citation_mismatch")
    if stale_mutated: codes.append("stale_artifact_mutated")
    health_claim = re.compile(r"\bmcp\s+(?:is\s+)?healthy\b|\bmcp health\s*[:=]\s*(?:healthy|pass)\b", re.I)
    if not healthy and any(health_claim.search(text) for text in texts.values()):
        codes.append("unsupported_mcp_health_claim")
    if report.get("receipt_input_sha256s") != context.expected_input_sha256s:
        codes.append("receipt_input_hash_mismatch")
    return codes


def _shared(context: OracleContext, report: dict[str, Any], texts: dict[str, str], _fixture: dict[str, Any]) -> list[str]:
    core = context.scorecard_core
    codes = []
    if report.get("raw_prompt_sha256") != core.get("raw_prompt_sha256"): codes.append("prompt_hash_mismatch")
    if report.get("tool_policy_sha256") != core.get("tool_policy_sha256"): codes.append("tool_policy_hash_mismatch")
    attempt = Path(str(core.get("attempt_dir", "")))
    raw = _inside(attempt, report.get("raw_artifact_path"))
    if raw is None: codes.append("raw_artifact_path_invalid")
    elif _sha(raw) != core.get("raw_artifact_sha256"): codes.append("raw_artifact_hash_mismatch")
    receipt = _inside(attempt, report.get("receipt_path"))
    if receipt is None or _sha(receipt) != core.get("receipt_sha256"): codes.append("receipt_path_invalid")
    states = core.get("orthogonal_states", {})
    failures = {"unavailable", "timeout", "internal_error", "malformed", "receipt_drift", "unverifiable", "oracle_fail"}
    derived = sorted({value for value in states.values() if value in failures}) if isinstance(states, dict) else []
    if report.get("failure_modes") != derived: codes.append("failure_modes_mismatch")
    normalized = " ".join(" ".join(texts.values()).lower().split())
    if any(phrase in normalized for phrase in ("same model behavior", "identical controls", "pure harness ablation")):
        codes.append("forbidden_claim")
    return codes


def _paired(context: OracleContext, report: dict[str, Any], _texts: dict[str, str], fixture: dict[str, Any]) -> list[str]:
    observations = [row for row in fixture.get("observations", []) if isinstance(row, dict)]
    exact_modes = sorted(context.oracle_spec.get("exact_modes", []))
    modes = sorted({str(row.get("mode", "")) for row in observations})
    keys = sorted({str(row.get("task_key", "")) for row in observations if row.get("task_key")})
    codes = []
    if modes != exact_modes: codes.append("fixture_mode_set_invalid")
    groups = {key: [row.get("mode") for row in observations if row.get("task_key") == key] for key in keys}
    complete = bool(keys) and all(sorted(values) == exact_modes for values in groups.values())
    if not complete: codes.append("fixture_pair_incomplete")
    pairs = [{"task_key": key, "modes": exact_modes} for key in keys]
    if report.get("modes") != exact_modes: codes.append("reported_pair_mismatch")
    if report.get("task_keys") != keys: codes.append("reported_task_keys_mismatch")
    if report.get("pairs") != pairs: codes.append("reported_pair_mismatch")
    if report.get("denominator") != len(keys): codes.append("denominator_mismatch")
    required = context.oracle_spec.get("required_safety_controls", [])
    if any(not row.get("safety_controls", {}).get(name) for row in observations for name in required):
        codes.append("fixture_safety_control_disabled")
    return codes


_CLAIMS = (
    r"\brectilinear crossing numbers?\b", r"\bcrossing numbers?\s+of\b",
    r"\bzarankiewicz numbers?\b", r"\boptimal (?:drawing|graph|scheme|construction|certificate)\b",
    r"\b(?:minimum|minimal|fewest possible|maximum possible)\s+(?:crossings?|edges?|rank)\b",
    r"\bproves?\s+optimality\b", r"\bwe\s+(?:solved|proved)\s+(?:the\s+)?(?:open\s+)?problem\b",
)
_DISCLAIMERS = ("not claimed", "not computed", "not bounded", "do not claim", "does not claim", "no claim",
                "not proven", "not proved", "cannot claim", "never claimed", "submitted drawing", "submitted graph",
                "submitted scheme", "submitted object", "not optimality", "without claiming", "makes no claim")


def _claim_violation(texts: dict[str, str]) -> bool:
    for text in texts.values():
        for sentence in re.split(r"(?<=[.!?])(?=\s)", text):
            low = " ".join(sentence.lower().split())
            if not any(word in low for word in _DISCLAIMERS) and any(re.search(pattern, low) for pattern in _CLAIMS):
                return True
    return False


def _docs(context: OracleContext, report: dict[str, Any], texts: dict[str, str], fixture: dict[str, Any]) -> list[str]:
    rows = [row for row in fixture.get("surfaces", []) if isinstance(row, dict)]
    expected_names = sorted(context.oracle_spec.get("expected_surfaces", []))
    fixture_names = sorted(str(row.get("surface", "")) for row in rows)
    reported = [row for row in report.get("surfaces", []) if isinstance(row, dict)]
    reported_names = sorted(str(row.get("surface", "")) for row in reported)
    codes = []
    if fixture_names != expected_names or len(fixture_names) != len(set(fixture_names)):
        codes.append("fixture_surface_set_invalid")
    if reported_names != fixture_names: codes.append("surface_set_mismatch")
    expected = {row.get("surface"): row for row in rows}
    root = Path(str(context.scorecard_core.get("workspace_root", "")))
    for row in reported:
        if _inside(root, row.get("path")) is None: codes.append("surface_path_invalid")
        reference = expected.get(row.get("surface"), {})
        if not reference:
            continue
        if row.get("code_refs") != reference.get("code_refs"): codes.append("code_refs_mismatch")
        if any(_inside(root, ref) is None for ref in row.get("code_refs", [])): codes.append("surface_path_invalid")
        if row.get("path") != reference.get("path"): codes.append("surface_path_invalid")
    if _claim_violation(texts): codes.append("claim_language_violation")
    return codes


_CHECKERS = {
    "index_fallback_integrity/v1": _index,
    "shared_task_artifact/v1": _shared,
    "paired_friction/v1": _paired,
    "documentation_maintenance/v1": _docs,
}


def evaluate_task_oracle(context: OracleContext) -> OracleResult:
    checker = _CHECKERS.get(context.oracle_spec.get("checker_id"))
    if checker is None:
        return _result(context, "unverifiable", evidence={"reason": "checker_not_configured"})
    common = _common(context)
    if len(common) == 3 and isinstance(common[2], OracleResult):
        return common[2]
    report, texts, checked = common
    fixture = _load_fixture(context)
    if fixture is None:
        return _result(context, "unverifiable", evidence={"reason": "fixture_unavailable"}, checked=checked)
    codes = checker(context, report, texts, fixture)
    return _result(context, "fail" if codes else "pass", codes, evidence={"predicate_count": len(codes)}, checked=checked)
