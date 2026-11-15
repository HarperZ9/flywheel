from __future__ import annotations

import base64
import binascii
import html
import json
import re

from .canonical_json import canonical_json_text, is_sha256_ref
from .capsule import Capsule, capsule_bytes, validate_capsule
from .readiness import CRITICAL_SET_KEYS

CANON_MD_SECTIONS = (
    "Capsule identity",
    "Target and integration tier",
    "Freshness, trust, and unknowns",
    "Active goals",
    "Authority, permissions, prohibitions, and constraints",
    "Current frontier and working state",
    "Decisions and rationale",
    "Conflicts requiring resolution",
    "Canonical instructions",
    "Evidence references",
    "Omissions",
    "Lossy transforms",
    "Bootstrap readiness probe",
    "Does-not-prove",
)
_CARRIER_RE = re.compile(r"<!--\s*canon:capsule/v1\b(?P<attrs>.*?)-->", re.DOTALL)
_ATTR_RE = re.compile(r"(?P<name>[A-Za-z_][A-Za-z0-9_-]*)=(?P<value>[^\s>]+)")
_CRITICAL_SET_BY_TYPE = {
    "active-goal": "active_goal_ids",
    "permission": "permission_ids",
    "prohibition": "prohibition_ids",
    "constraint": "constraint_ids",
    "frontier-state": "frontier_state_ids",
    "conflict": "unresolved_conflict_ids",
    "unknown": "unknown_ids",
}


class CanonMdError(ValueError):
    pass


def render_canon_md(capsule: Capsule, *, include_machine_carrier: bool = True) -> str:
    _require_valid_capsule(capsule)
    lines = ["# CANON"]
    if include_machine_carrier:
        lines.append(_carrier_line(capsule))
    lines.append("")
    for section in CANON_MD_SECTIONS:
        lines.append("## " + section)
        lines.extend(_section_lines(section, capsule))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_canon_md_carrier(text: str) -> dict:
    if not isinstance(text, str):
        raise CanonMdError("CANON.md text must be a string")
    matches = list(_CARRIER_RE.finditer(text))
    if len(matches) != 1:
        raise CanonMdError(f"expected exactly one carrier, found {len(matches)}")
    _check_carrier_placement(text, matches[0])
    attrs = _carrier_attrs(matches[0].group("attrs"))
    payload = _decode_payload(attrs["payload"])
    if not isinstance(payload, dict):
        raise CanonMdError("carrier payload must decode to a capsule object")
    _check_carrier_digest(attrs["digest"], payload)
    return payload


def verify_canon_md(text: str, capsule: Capsule | None = None) -> list[str]:
    problems: list[str] = []
    try:
        carrier = parse_canon_md_carrier(text)
        carrier_capsule = Capsule.from_dict(carrier)
    except Exception as exc:
        return [f"carrier: {exc}"]
    problems.extend(f"carrier capsule: {p}" for p in validate_capsule(carrier_capsule))
    if capsule is not None:
        problems.extend(_capsule_mismatch(carrier, capsule))
    try:
        if text != render_canon_md(carrier_capsule):
            problems.append("body drift: rendered Markdown differs from carrier capsule")
    except Exception as exc:
        problems.append(f"body drift: could not re-render carrier capsule: {exc}")
    return problems


def _carrier_line(capsule: Capsule) -> str:
    payload = base64.urlsafe_b64encode(capsule_bytes(capsule)).decode("ascii").rstrip("=")
    return f"<!-- canon:capsule/v1 digest={capsule.capsule_id} payload={payload} -->"


def _carrier_attrs(attrs_text: str) -> dict:
    attrs = {m.group("name"): m.group("value") for m in _ATTR_RE.finditer(attrs_text)}
    missing = [name for name in ("digest", "payload") if name not in attrs]
    if missing:
        raise CanonMdError("carrier missing " + ", ".join(missing))
    if not is_sha256_ref(attrs["digest"]):
        raise CanonMdError("carrier digest must be a sha256: reference")
    return attrs


def _check_carrier_placement(text: str, match: re.Match[str]) -> None:
    lines = text.splitlines()
    if len(lines) < 2 or lines[0] != "# CANON" or lines[1] != match.group(0):
        raise CanonMdError("carrier must appear immediately after # CANON")


def _decode_payload(payload: str) -> object:
    try:
        padded = payload + ("=" * (-len(payload) % 4))
        raw = base64.b64decode(padded.encode("ascii"), altchars=b"-_", validate=True)
        return json.loads(raw.decode("utf-8"))
    except (binascii.Error, json.JSONDecodeError, UnicodeError, ValueError) as exc:
        raise CanonMdError(f"carrier payload is invalid: {exc}") from exc


def _check_carrier_digest(digest: str, payload: dict) -> None:
    capsule_id = payload.get("capsule_id")
    if capsule_id != digest:
        raise CanonMdError("carrier digest must match payload capsule_id")


def _capsule_mismatch(carrier: dict, capsule: Capsule) -> list[str]:
    try:
        return [] if capsule.to_dict() == carrier else ["capsule mismatch: provided capsule differs from carrier"]
    except Exception as exc:
        return [f"capsule mismatch: could not read provided capsule: {exc}"]


def _require_valid_capsule(capsule: Capsule) -> None:
    problems = validate_capsule(capsule)
    if problems:
        raise CanonMdError("invalid capsule: " + "; ".join(problems))


def _section_lines(section: str, capsule: Capsule) -> list[str]:
    if section == "Capsule identity":
        return _identity_lines(capsule)
    if section == "Target and integration tier":
        return _target_lines(capsule)
    if section == "Freshness, trust, and unknowns":
        return _freshness_lines(capsule)
    if section == "Authority, permissions, prohibitions, and constraints":
        return _atom_group_lines(capsule, ("permission", "prohibition", "constraint"))
    if section == "Current frontier and working state":
        return _frontier_lines(capsule)
    mapping = {
        "Active goals": ("active-goal",),
        "Decisions and rationale": ("decision",),
        "Conflicts requiring resolution": ("conflict",),
        "Canonical instructions": ("instruction",),
        "Evidence references": ("evidence-ref",),
    }
    if section in mapping:
        return _atom_group_lines(capsule, mapping[section])
    return _receipt_section_lines(section, capsule)


def _identity_lines(capsule: Capsule) -> list[str]:
    return [
        f"- Capsule id: {_code(capsule.capsule_id)}",
        f"- Manifest SHA-256: {_code(capsule.integrity.manifest_sha256)}",
        f"- Profile: {_code(capsule.profile)}",
        f"- Canonicalization: {_code(capsule.integrity.canonicalization)}",
        f"- Compatibility: record {_code(capsule.compatibility.record_schema_min)}, capsule {_code(capsule.compatibility.capsule_schema)}",
    ]


def _target_lines(capsule: Capsule) -> list[str]:
    target = capsule.target
    return [
        f"- Adapter: {_code(target.adapter)}",
        f"- Surface: {_code(target.surface)}",
        f"- Integration tier: {_code(target.integration_tier)}",
        f"- Host enforcement observed: {_code(str(target.host_enforcement_observed).lower())}",
    ]


def _freshness_lines(capsule: Capsule) -> list[str]:
    lines = [f"- Layers: {_csv(capsule.layers)}"]
    lines.extend(f"- Freshness {_code(row.get('id'))}: status {_code(row.get('status'))}, state {_code(_state(row))}" for row in capsule.freshness)
    lines.extend(f"- Unknown {_code(atom.id)}: {_summary(atom.value)}" for atom in capsule.unknowns)
    return lines or ["- None."]


def _frontier_lines(capsule: Capsule) -> list[str]:
    lines = _atom_group_lines(capsule, ("frontier-state",))
    source = capsule.source_state.to_dict()
    for key in sorted(source):
        if source[key] is not None:
            lines.append(f"- Source state {_code(key)}: {_code(source[key])}")
    return lines


def _atom_group_lines(capsule: Capsule, atom_types: tuple[str, ...]) -> list[str]:
    lines = [_atom_line(atom) for atom in capsule.atoms if atom.type in atom_types]
    return lines or ["- None."]


def _receipt_section_lines(section: str, capsule: Capsule) -> list[str]:
    if section == "Omissions":
        return [_omission_line(item) for item in capsule.omissions] or ["- None."]
    if section == "Lossy transforms":
        return [_transform_line(item) for item in capsule.lossy_transforms] or ["- None."]
    if section == "Bootstrap readiness probe":
        return _readiness_lines(capsule)
    if section == "Does-not-prove":
        return [f"- {_safe_text(item)}" for item in capsule.does_not_prove] or ["- None."]
    return ["- None."]


def _atom_line(atom: object) -> str:
    refs = _csv(ref.get("ref", "") for ref in getattr(atom, "source_refs", ()) if isinstance(ref, dict))
    suffix = f"; refs: {refs}" if refs != "none" else ""
    meta = f"{_safe_text(atom.type)}, {_safe_text(atom.layer)}, {_safe_text(atom.status)}"
    return f"- {_code(atom.id)} ({meta}, critical={_safe_text(str(atom.critical).lower())}): {_summary(atom.value)}{suffix}"


def _omission_line(item: object) -> str:
    proof = "; does-not-prove: " + _join_safe(item.does_not_prove, " | ") if item.does_not_prove else ""
    return f"- {_code(item.reason)} {_safe_text(item.decision)}; critical={_safe_text(str(item.critical).lower())}; affected: {_csv(item.affected_ids)}{proof}"


def _transform_line(item: object) -> str:
    proof = "; does-not-prove: " + _join_safe(item.does_not_prove, " | ") if item.does_not_prove else ""
    return f"- {_code(item.transform)} via {_code(item.method_id)} -> {_code(item.output_ref)}; retained: {_csv(item.retained_critical_atom_ids)}{proof}"


def _readiness_lines(capsule: Capsule) -> list[str]:
    sets = {key: [] for key in CRITICAL_SET_KEYS}
    for atom in capsule.atoms:
        key = _CRITICAL_SET_BY_TYPE.get(atom.type)
        if key is not None and atom.critical is True:
            sets[key].append(atom.id)
    lines = ["- Challenge format: `json`", "- Checker: `exact-id-set-and-status-match`"]
    lines.extend(f"- {_code(key)}: {_csv(sets[key])}" for key in CRITICAL_SET_KEYS)
    return lines


def _summary(value: object) -> str:
    if isinstance(value, dict):
        for key in ("summary", "question", "current_state", "allows", "forbids", "requires", "resolution"):
            if key in value:
                return _safe_text(value[key])
    return _safe_text(value)


def _state(row: dict) -> str:
    freshness = row.get("freshness")
    return freshness.get("state", "unknown") if isinstance(freshness, dict) else "unknown"


def _compact(value: object) -> str:
    return canonical_json_text(value).strip() if isinstance(value, (dict, list)) else str(value)


def _safe_text(value: object) -> str:
    text = _compact(value).replace("\r\n", "\n").replace("\r", "\n")
    safe = html.escape(" / ".join(text.split("\n")), quote=False).replace("#", r"\#")
    return safe.replace("`", "&#96;")


def _code(value: object) -> str:
    return f"`{_safe_text(value)}`"


def _join_safe(values: object, separator: str) -> str:
    return separator.join(_safe_text(value) for value in _iter_values(values))


def _csv(values: object) -> str:
    items = [_safe_text(value) for value in _iter_values(values)]
    return ", ".join(items) if items else "none"


def _iter_values(values: object) -> tuple[object, ...]:
    if isinstance(values, str):
        return (values,)
    try:
        return tuple(values)
    except TypeError:
        return (values,)
