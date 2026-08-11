"""Deterministic artifact oracles for cross-harness pilot tasks."""
from __future__ import annotations
from collections import Counter
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
class _DuplicateKey(ValueError): pass
class _Malformed(ValueError): pass
_UNPARSED = object()
def _pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in rows:
        if key in out: raise _DuplicateKey(key)
        out[key] = value
    return out
def _sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def _read(checked, role: str, path: Path) -> bytes:
    for seen, data in checked.values():
        if seen == path: checked[role] = (path, data); return data
    data = path.read_bytes(); checked[role] = (path, data)
    return data
def _checked(items) -> list[dict[str, str]]:
    return [{"role": role, "basename": path.name, "sha256": _sha(data)}
            for role, (path, data) in sorted(items.items())]
def _result(context: OracleContext, state: str, codes=(), *, evidence=None, checked=None) -> OracleResult:
    checker_id = str(context.oracle_spec.get("checker_id", ""))
    return OracleResult(state, checker_id, checker_id.rsplit("/", 1)[-1] if "/" in checker_id else "",
                        evidence or {}, sorted(set(codes)), _checked(checked or {}))
def _inside(root: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value: return None
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts: return None
    try:
        path = (root / relative).resolve()
        return path if path.is_relative_to(root.resolve()) and path.is_file() else None
    except (OSError, RuntimeError): return None
def _admit(root: Path, value: Any) -> Path:
    if not isinstance(value, Path) or ".." in value.parts: raise _Malformed("attempt_path_invalid")
    try: path = (value if value.is_absolute() else root / value).resolve()
    except (OSError, RuntimeError) as exc: raise _Malformed("attempt_path_invalid") from exc
    if not path.is_relative_to(root): raise _Malformed("attempt_path_invalid")
    return path
def _rows(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise _Malformed(f"{field}_type_invalid")
    return value
def _strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise _Malformed(f"{field}_type_invalid")
    return value
def _root(context: OracleContext, field: str) -> Path:
    value = context.scorecard_core.get(field)
    if not isinstance(value, str) or not value: raise _Malformed(f"{field}_type_invalid")
    path = Path(value)
    if not path.is_dir(): raise _Malformed(f"{field}_directory_invalid")
    return path.resolve()
def _digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise _Malformed(f"{field}_type_invalid")
    return value
def _raw_boundary(context: OracleContext, checked, attempt: Path) -> tuple[dict[str, Any] | None, OracleResult | None]:
    try:
        path = _admit(attempt, context.raw_output_path)
        if not path.is_file(): raise _Malformed("attempt_path_invalid")
        text = _read(checked, "raw_output", path).decode("utf-8")
    except (OSError, UnicodeError, _Malformed):
        return None, _result(context, "malformed", ["json_invalid"], evidence={"reason": "raw_output_invalid"}, checked=checked)
    try:
        envelope = json.loads(text, object_pairs_hook=_pairs)
    except (json.JSONDecodeError, _DuplicateKey):
        return None, _result(context, "malformed", ["json_invalid"], evidence={"reason": "raw_output_invalid"}, checked=checked)
    expected = sorted(context.oracle_spec.get("expected_artifacts", []))
    artifacts = envelope.get("artifacts") if isinstance(envelope, dict) else None
    valid = isinstance(envelope, dict) and set(envelope) == {"artifacts"} and isinstance(artifacts, dict) and (sorted(artifacts) == expected if expected else bool(artifacts))
    if valid:
        valid = all(isinstance(value, str) if name.endswith(".md") else isinstance(value, dict)
                    for name, value in artifacts.items())
    if not valid:
        return None, _result(context, "malformed", ["json_invalid"], evidence={"reason": "response_envelope_invalid"}, checked=checked)
    return envelope, None
def _load_fixture(context: OracleContext, checked):
    root = _root(context, "workspace_root")
    ref = context.oracle_spec.get("fixture")
    path = _inside(root, ref)
    if path is None: return None, "fixture_unavailable"
    try: data = _read(checked, "input_fixture", path)
    except OSError: return None, "fixture_unavailable"
    if context.expected_input_sha256s.get(ref) != _sha(data): return None, "input_hash_mismatch"
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs)
        return (value, "") if isinstance(value, dict) else (None, "fixture_malformed")
    except (OSError, UnicodeError, json.JSONDecodeError, _DuplicateKey): return None, "fixture_malformed"
def _common(context: OracleContext, envelope: dict[str, Any], checked, attempt: Path):
    expected, actual = sorted(context.oracle_spec.get("expected_artifacts", [])), sorted(context.artifact_paths)
    mismatch = actual != expected or any(path.name != name for name, path in context.artifact_paths.items())
    codes, texts = (["artifact_set_mismatch"] if mismatch else []), {}
    for basename in actual:
        try: path = _admit(attempt, context.artifact_paths[basename])
        except _Malformed: raise
        if not path.is_file(): codes.append("artifact_not_regular"); continue
        try: text = _read(checked, f"provider:{basename}", path).decode("utf-8")
        except OSError: codes.append("artifact_not_regular"); continue
        except UnicodeError: codes.append("artifact_not_utf8"); continue
        if not text: codes.append("artifact_empty")
        texts[basename] = text
    json_names, md_names = [n for n in actual if n.endswith(".json")], [n for n in actual if n.endswith(".md")]
    if len(json_names) != 1 or len(md_names) != 1:
        codes.append("artifact_set_mismatch")
    report = _UNPARSED
    if len(json_names) == 1 and json_names[0] in texts:
        try: report = json.loads(texts[json_names[0]], object_pairs_hook=_pairs)
        except _DuplicateKey: codes.append("json_duplicate_key")
        except json.JSONDecodeError: codes.append("json_invalid")
    if report is not _UNPARSED:
        if not isinstance(report, dict) or not isinstance(report.get("task_id"), str) or not isinstance(report.get("input_sha256s"), dict): codes.append("json_invalid")
        else:
            if report["task_id"] != context.task_id: codes.append("task_id_mismatch")
            if report["input_sha256s"] != context.expected_input_sha256s: codes.append("input_hash_mismatch")
    structural = {"artifact_not_regular", "artifact_not_utf8", "artifact_empty", "json_invalid", "json_duplicate_key"}
    if len(md_names) == 1 and texts.get(md_names[0]) and context.task_id not in texts[md_names[0]]: codes.append("markdown_task_id_missing")
    if not mismatch and not structural & set(codes) and report is not _UNPARSED and all(name in texts for name in md_names):
        materialized = {json_names[0]: report, md_names[0]: texts[md_names[0]]}
        if envelope["artifacts"] != materialized: codes.append("json_invalid")
    if codes: return None, None, _result(context, "malformed" if structural & set(codes) else "fail", codes, checked=checked)
    return report, texts, None

def _index(context, report, texts, fixture, checked):
    classes, citations, stale_mutated, healthy = set(), set(), False, False
    for event in _rows(fixture.get("events"), "events"):
        kind, outcome, derived = event.get("type"), event.get("outcome"), None
        if kind == "mcp_call" and outcome == "failure": derived = "live_mcp_failure"
        elif kind == "artifact_read" and event.get("source") == "stale":
            derived, stale_mutated = "stale_artifact_use", stale_mutated or event.get("before_sha256") != event.get("after_sha256")
        elif kind == "json_parse" and outcome == "failure": derived = "invalid_json"
        elif kind == "match" and event.get("mode") == "degraded": derived = "degraded_match"
        healthy |= kind == "mcp_call" and outcome == "success"
        if derived: classes.add(derived); citations.add(str(event.get("event_id", "")))
    if not isinstance(report.get("receipt_input_sha256s"), dict): raise _Malformed("receipt_input_sha256s_type_invalid")
    _strings(report.get("failure_classes"), "failure_classes"); _strings(report.get("cited_event_ids"), "cited_event_ids")
    codes = []
    if report["failure_classes"] != sorted(classes): codes.append("failure_classes_mismatch")
    if report["cited_event_ids"] != sorted(citations): codes.append("event_citation_mismatch")
    if stale_mutated: codes.append("stale_artifact_mutated")
    status = re.compile(r"\bmcp(?:\s+(?:server|service|endpoint))?\s+(?:(?:is|was|remains|seems)\s+\w+|(?:health(?:\s+check)?|status)\s*(?:(?:is|was)\s+|[:=]\s*)?\w+|(?:passed|succeeded|responded)\b)", re.I)
    uncertain = re.compile(r"\b(?:not|no|never|unknown|unverified|unchecked|unavailable|unhealthy|failed|failure|disabled|down|indeterminate|cannot|unable)\b", re.I)
    if not healthy and any(status.search(clause) and not uncertain.search(clause) for text in texts.values() for clause in _clauses(text)): codes.append("unsupported_mcp_health_claim")
    if report["receipt_input_sha256s"] != context.expected_input_sha256s: codes.append("receipt_input_hash_mismatch")
    return codes

_STATE_VALUES = {"execution_state": {"not_started", "unavailable", "launched", "returned", "timeout", "malformed", "internal_error"},
                 "oracle_state": {"not_run", "pass", "fail", "unverifiable"},
                 "receipt_state": {"not_emitted", "verified", "drift"}}

def _shared(context, report, texts, fixture, checked):
    core, attempt, codes = context.scorecard_core, _root(context, "attempt_dir"), []
    axes = _rows(fixture.get("state_axes"), "state_axes")
    rules = {}
    for row in axes:
        axis, failures = row.get("axis"), set(_strings(row.get("failure_values"), "failure_values"))
        if axis not in _STATE_VALUES or not failures <= _STATE_VALUES[axis]: raise _Malformed("state_axes_invalid")
        rules[axis] = failures
    if set(rules) != set(_STATE_VALUES): raise _Malformed("state_axes_invalid")
    states = core.get("orthogonal_states")
    if not isinstance(states, dict) or set(states) != set(_STATE_VALUES) or any(value not in _STATE_VALUES[axis] for axis, value in states.items()):
        raise _Malformed("orthogonal_states_type_invalid")
    _strings(report.get("failure_modes"), "failure_modes")
    for field in ("raw_prompt_sha256", "tool_policy_sha256"):
        _digest(report.get(field), field); _digest(core.get(field), field)
    derived = sorted({value for axis, value in states.items() if value in rules.get(axis, set())})
    if report.get("raw_prompt_sha256") != core.get("raw_prompt_sha256"): codes.append("prompt_hash_mismatch")
    if report.get("tool_policy_sha256") != core.get("tool_policy_sha256"): codes.append("tool_policy_hash_mismatch")
    facts = _rows(fixture.get("artifact_facts"), "artifact_facts")
    expected_facts = {"raw_artifact_path": ("raw_artifact_sha256", "raw_artifact", "raw_artifact_path_invalid", "raw_artifact_hash_mismatch"),
                      "receipt_path": ("receipt_sha256", "receipt", "receipt_path_invalid", "receipt_path_invalid")}
    if {row.get("path_field") for row in facts} != set(expected_facts): raise _Malformed("artifact_facts_invalid")
    for fact in facts:
        field = fact["path_field"]; hash_fact, role, path_code, hash_code = expected_facts[field]
        if fact.get("hash_fact") != hash_fact: raise _Malformed("artifact_hash_fact_invalid")
        value = report.get(field)
        if not isinstance(value, str) or not value: raise _Malformed(f"{field}_type_invalid")
        path = _inside(attempt, value)
        if path is None: codes.append(path_code)
        else:
            try: data = _read(checked, role, path)
            except OSError: codes.append(path_code); continue
            if _sha(data) != core.get(hash_fact): codes.append(hash_code)
    if report.get("failure_modes") != derived: codes.append("failure_modes_mismatch")
    phrases = _strings(fixture.get("forbidden_claim_phrases"), "forbidden_claim_phrases")
    normalized = " ".join(" ".join(texts.values()).lower().split())
    if any(phrase in normalized for phrase in phrases): codes.append("forbidden_claim")
    return codes

def _paired(context, report, _texts, fixture, checked):
    observations = _rows(fixture.get("observations"), "observations")
    _strings(report.get("modes"), "modes"); _strings(report.get("task_keys"), "task_keys")
    _rows(report.get("pairs"), "pairs"); _rows(report.get("aggregates"), "aggregates")
    if not isinstance(report.get("denominator"), int) or isinstance(report.get("denominator"), bool): raise _Malformed("denominator_type_invalid")
    exact_modes = sorted(_strings(context.oracle_spec.get("exact_modes"), "exact_modes"))
    modes = sorted({str(row.get("mode", "")) for row in observations})
    keys = sorted({str(row.get("task_key", "")) for row in observations if row.get("task_key")})
    for row in observations:
        if not isinstance(row.get("completion"), str) or any(not isinstance(row.get(field), int) or isinstance(row.get(field), bool) for field in ("friction_events", "correction_steps")):
            raise _Malformed("observation_measure_type_invalid")
    groups = {key: [row.get("mode") for row in observations if row.get("task_key") == key] for key in keys}
    pairs = [{"task_key": key, "modes": exact_modes} for key in keys]
    aggregates = []
    for mode in exact_modes:
        rows = [row for row in observations if row.get("mode") == mode]
        aggregates.append({"mode": mode, "denominator": len(rows), "completion_counts": dict(sorted(Counter(row["completion"] for row in rows).items())),
                           "friction_events": sum(row["friction_events"] for row in rows), "correction_steps": sum(row["correction_steps"] for row in rows)})
    codes = []
    if modes != exact_modes: codes.append("fixture_mode_set_invalid")
    if not keys or not all(sorted(values) == exact_modes for values in groups.values()): codes.append("fixture_pair_incomplete")
    if report.get("task_keys") != keys: codes.append("reported_task_keys_mismatch")
    if report.get("pairs") != pairs or report.get("modes") != exact_modes or report.get("aggregates") != aggregates: codes.append("reported_pair_mismatch")
    if report.get("denominator") != len(keys): codes.append("denominator_mismatch")
    required = _strings(context.oracle_spec.get("required_safety_controls"), "required_safety_controls")
    if any(not isinstance(row.get("safety_controls"), dict) or row["safety_controls"].get(name) is not True for row in observations for name in required):
        codes.append("fixture_safety_control_disabled")
    return codes

_CLAIMS = (r"\brectilinear crossing numbers?\b", r"\bcrossing numbers?\s+of\b", r"\bzarankiewicz numbers?\b",
           r"\boptimal (?:drawing|graph|scheme|construction|certificate)\b", r"\b(?:minimum|minimal|fewest possible|maximum possible)\s+(?:crossings?|edges?|rank)\b",
           r"\bproves?\s+optimality\b", r"\bwe\s+(?:solved|proved)\s+(?:the\s+)?(?:open\s+)?problem\b")
_NEGATION = r"\b(?:not|never|no|without|cannot|do not|does not|did not|have not)\b"
_CATEGORIES = ((_CLAIMS[:3], r"\b(?:crossing numbers?|zarankiewicz numbers?)\b"),
               (_CLAIMS[3:-1], r"\b(?:optimal(?:ity)?|minimum|minimal|fewest possible|maximum possible)\b"),
               ((_CLAIMS[-1],), r"\b(?:solv\w*|prov\w*|open problem|solution)\b"))

def _clauses(text): return re.split(r"(?<=[.!?])(?=\s)|[,;\r\n]+|(?<!\w)[-*#]+\s+|\s+\b(?:and|but|however|yet|although)\b\s+", text, flags=re.I)
def _denied(low, category): return re.search(rf"(?:{category}).{{0,32}}{_NEGATION}|{_NEGATION}.{{0,32}}(?:{category})", low)
def _claim_violation(texts):
    return any(any(re.search(pattern, low) for pattern in patterns) and not _denied(low, category)
               for text in texts.values() for low in (" ".join(clause.lower().split()) for clause in _clauses(text)) for patterns, category in _CATEGORIES)

def _docs(context, report, texts, fixture, checked):
    rows, reported = _rows(fixture.get("surfaces"), "fixture_surfaces"), _rows(report.get("surfaces"), "surfaces")
    for row in rows + reported:
        if not isinstance(row.get("surface"), str) or not isinstance(row.get("path"), str): raise _Malformed("surface_entry_type_invalid")
        _strings(row.get("code_refs"), "code_refs")
    expected_names = sorted(_strings(context.oracle_spec.get("expected_surfaces"), "expected_surfaces"))
    fixture_names, reported_names = sorted(str(r.get("surface", "")) for r in rows), sorted(str(r.get("surface", "")) for r in reported)
    codes, expected, root = [], {row.get("surface"): row for row in rows}, _root(context, "workspace_root")
    if fixture_names != expected_names or len(fixture_names) != len(set(fixture_names)): codes.append("fixture_surface_set_invalid")
    if reported_names != fixture_names: codes.append("surface_set_mismatch")
    for row in reported:
        name, reference = row.get("surface"), expected.get(row.get("surface"), {})
        path = _inside(root, row.get("path"))
        if path is None: codes.append("surface_path_invalid")
        else: _read(checked, f"workspace:surface:{name}", path)
        if not reference: continue
        refs = _strings(row.get("code_refs"), "code_refs")
        if refs != reference.get("code_refs"): codes.append("code_refs_mismatch")
        for index, ref in enumerate(refs):
            ref_path = _inside(root, ref)
            if ref_path is None: codes.append("surface_path_invalid")
            else: _read(checked, f"workspace:code_ref:{name}:{index}", ref_path)
        if row.get("path") != reference.get("path"): codes.append("surface_path_invalid")
    if _claim_violation(texts): codes.append("claim_language_violation")
    return codes

_CHECKERS = {"index_fallback_integrity/v1": _index, "shared_task_artifact/v1": _shared,
             "paired_friction/v1": _paired, "documentation_maintenance/v1": _docs}

def evaluate_task_oracle(context: OracleContext) -> OracleResult:
    checked = {}
    try:
        _root(context, "workspace_root"); attempt = _root(context, "attempt_dir")
        envelope, boundary = _raw_boundary(context, checked, attempt)
        if boundary: return boundary
        checker = _CHECKERS.get(context.oracle_spec.get("checker_id"))
        if checker is None: return _result(context, "unverifiable", evidence={"reason": "checker_not_configured"}, checked=checked)
        report, texts, common = _common(context, envelope, checked, attempt)
        if common: return common
        fixture, fixture_error = _load_fixture(context, checked)
        if fixture_error == "input_hash_mismatch": return _result(context, "fail", [fixture_error], checked=checked)
        if fixture_error: return _result(context, "unverifiable", evidence={"reason": fixture_error}, checked=checked)
        codes = checker(context, report, texts, fixture, checked)
        return _result(context, "fail" if codes else "pass", codes, evidence={"failure_code_count": len(set(codes))}, checked=checked)
    except _Malformed as exc:
        return _result(context, "malformed", ["json_invalid"], evidence={"reason": str(exc)}, checked=checked)
