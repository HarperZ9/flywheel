from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .bootstrap_validation import require_serializable_data, safe_text, snapshot_data, thaw_mapping_or_none
from .canonical_json import is_sha256_ref
from .cli_artifacts import MAX_SOURCE_BYTES, SourceBytes
from .exit_codes import exit_code_for
from .secret_quarantine import scan_text

_BOMS = (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff", b"\x00\x00\xfe\xff", b"\xff\xfe\x00\x00")
_ADAPTER_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DOCTOR_FAILURE_PRIORITY = {
    "secret_quarantine": 0,
    "source_changed": 1,
    "invalid_args": 2,
    "source_unreachable": 3,
    "unsafe_path": 4,
    "unsupported_lifecycle": 5,
}
DOCTOR_FAILURE_CODES = frozenset({"ok", *DOCTOR_FAILURE_PRIORITY})


class SourceParseError(ValueError):
    def __init__(self, code: str = "invalid_args", *, line: int | None = None) -> None:
        self.code = code
        self.line = line
        super().__init__(code)


class DoctorConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class JsonLine:
    line: int
    value: dict


@dataclass(frozen=True, slots=True, repr=False)
class DoctorConfig:
    workspace: str = field(default=".", repr=False)
    target: str = field(default="", repr=False)
    records: str | None = field(default=None, repr=False)
    atoms: str | None = field(default=None, repr=False)
    offline: bool = False
    expected_source_state: str | None = field(default=None, repr=False)
    stdin_source: SourceBytes | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        for name, value in snapshot_doctor_config(self).items():
            object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True, repr=False)
class DoctorFinding:
    code: str
    severity: str
    failure_code: str
    message: str = field(repr=False)
    evidence: object = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        _check_finding_fields(self)
        object.__setattr__(self, "evidence", _snapshot_public_data(self.evidence, "invalid doctor finding"))

    def to_dict(self) -> dict[str, object]:
        check_doctor_finding(self)
        return {"code": self.code, "evidence": thaw_mapping_or_none(self.evidence),
                "failure_code": self.failure_code, "message": self.message,
                "severity": self.severity}


@dataclass(frozen=True, slots=True, repr=False)
class DoctorReport:
    ok: bool
    failure_code: str
    message: str = field(repr=False)
    findings: tuple[DoctorFinding, ...]
    data: object = field(default_factory=dict, repr=False)
    exit_code: int = field(init=False)

    def __post_init__(self) -> None:
        _check_report_fields(self)
        object.__setattr__(self, "data", _snapshot_public_data(self.data, "invalid doctor report"))
        object.__setattr__(self, "exit_code", exit_code_for(self.failure_code))

    def to_dict(self) -> dict[str, object]:
        check_doctor_report(self)
        return {"data": thaw_mapping_or_none(self.data), "exit_code": self.exit_code,
                "failure_code": self.failure_code,
                "findings": [finding.to_dict() for finding in self.findings],
                "message": self.message, "ok": self.ok}

    def to_result_data(self) -> dict[str, object]:
        check_doctor_report(self)
        data = thaw_mapping_or_none(self.data) or {}
        data["findings"] = [finding.to_dict() for finding in self.findings]
        return data


def snapshot_doctor_config(config: DoctorConfig) -> dict[str, object]:
    if type(config) is not DoctorConfig:
        raise DoctorConfigError("invalid doctor config")
    return {"workspace": _path_text(config.workspace), "target": _adapter_id(config.target),
            "records": None if config.records is None else _path_text(config.records),
            "atoms": None if config.atoms is None else _path_text(config.atoms),
            "offline": _bool(config.offline),
            "expected_source_state": _sha_or_none(config.expected_source_state),
            "stdin_source": _stdin_snapshot(config.stdin_source)}


def check_doctor_finding(finding: DoctorFinding) -> None:
    try:
        _check_finding_fields(finding)
        _check_public_data(finding.evidence, "invalid doctor finding")
    except TypeError:
        raise TypeError("invalid doctor finding") from None


def check_doctor_report(report: DoctorReport) -> None:
    try:
        _check_report_fields(report)
        for finding in report.findings:
            check_doctor_finding(finding)
        if type(report.exit_code) is not int or report.exit_code != exit_code_for(report.failure_code):
            raise TypeError("invalid doctor report")
        _check_public_data(report.data, "invalid doctor report")
    except TypeError:
        raise TypeError("invalid doctor report") from None


def utf8_text(data: bytes) -> str:
    if type(data) is not bytes or data.startswith(_BOMS) or b"\0" in data:
        raise SourceParseError("invalid_args")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceParseError("invalid_args") from exc


def strict_jsonl_objects(data: bytes) -> tuple[JsonLine, ...]:
    objects: list[JsonLine] = []
    for lineno, line in enumerate(utf8_text(data).splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line, object_pairs_hook=_object_no_duplicates)
        except (json.JSONDecodeError, ValueError) as exc:
            raise SourceParseError("invalid_args", line=lineno) from exc
        if type(value) is not dict:
            raise SourceParseError("invalid_args", line=lineno)
        objects.append(JsonLine(lineno, value))
    return tuple(objects)


def _object_no_duplicates(pairs: list[tuple[str, object]]) -> dict:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key")
        result[key] = value
    return result


def _stdin_snapshot(value: object) -> SourceBytes | None:
    if value is None:
        return None
    if type(value) is not SourceBytes or type(value.path) is not str or type(value.data) is not bytes:
        raise DoctorConfigError("invalid doctor config")
    _scan_config_text(value.path)
    if len(value.data) > MAX_SOURCE_BYTES:
        raise DoctorConfigError("invalid doctor config")
    return SourceBytes(value.path, bytes(value.data))


def _path_text(value: object) -> str:
    if type(value) is not str or value == "" or _has_control(value):
        raise DoctorConfigError("invalid doctor config")
    _scan_config_text(value)
    return value


def _adapter_id(value: object) -> str:
    if type(value) is not str or _has_control(value):
        raise DoctorConfigError("invalid doctor config")
    _scan_config_text(value)
    if _ADAPTER_ID_RE.fullmatch(value) is None:
        raise DoctorConfigError("invalid doctor config")
    return value


def _sha_or_none(value: object) -> str | None:
    if value is None:
        return None
    if type(value) is not str or _has_control(value):
        raise DoctorConfigError("invalid doctor config")
    _scan_config_text(value)
    if not is_sha256_ref(value):
        raise DoctorConfigError("invalid doctor config")
    return value


def _bool(value: object) -> bool:
    if type(value) is not bool:
        raise DoctorConfigError("invalid doctor config")
    return value

def _check_finding_fields(finding: DoctorFinding) -> None:
    _safe_public_text(finding.code, "doctor finding code", "invalid doctor finding")
    _safe_public_text(finding.failure_code, "doctor finding failure_code", "invalid doctor finding")
    _safe_public_text(finding.message, "doctor finding message", "invalid doctor finding")
    if finding.failure_code not in DOCTOR_FAILURE_CODES:
        raise TypeError("invalid doctor finding")
    if type(finding.severity) is not str or finding.severity not in ("blocker", "warning", "info"):
        raise TypeError("invalid doctor finding")
    if (finding.severity == "blocker") == (finding.failure_code == "ok"):
        raise TypeError("invalid doctor finding")


def _check_report_fields(report: DoctorReport) -> None:
    if type(report.ok) is not bool or type(report.findings) is not tuple:
        raise TypeError("invalid doctor report")
    _safe_public_text(report.failure_code, "doctor report failure_code", "invalid doctor report")
    _safe_public_text(report.message, "doctor report message", "invalid doctor report")
    if report.failure_code not in DOCTOR_FAILURE_CODES:
        raise TypeError("invalid doctor report")
    if any(type(finding) is not DoctorFinding for finding in report.findings):
        raise TypeError("invalid doctor findings")
    for finding in report.findings:
        _check_finding_fields(finding)
    _check_finding_order(report.findings)
    blockers = [finding for finding in report.findings if finding.severity == "blocker"]
    if report.ok != (report.failure_code == "ok" and not blockers):
        raise TypeError("invalid doctor report")
    if blockers and report.failure_code != blockers[0].failure_code:
        raise TypeError("invalid doctor report")


def _has_control(value: str) -> bool:
    return "\0" in value or any(ord(char) < 32 or ord(char) == 127 for char in value)


def _snapshot_public_data(data: object, message: str) -> object:
    try:
        _check_public_data(data, message)
        return snapshot_data(data)
    except TypeError:
        raise TypeError(message) from None


def _check_public_data(data: object, message: str) -> None:
    require_serializable_data(data, message)
    _scan_public_value(thaw_mapping_or_none(data), message)


def _scan_public_value(value: object, message: str) -> None:
    if type(value) is str:
        _safe_public_text(value, "doctor data", message)
    elif type(value) is dict:
        for key, item in value.items():
            _safe_public_text(key, "doctor data key", message)
            _scan_public_value(item, message)
    elif type(value) is list:
        for item in value:
            _scan_public_value(item, message)


def _safe_public_text(value: object, name: str, message: str) -> str:
    try:
        text = safe_text(value, name)
        findings = scan_text(text, source_id="doctor-public")
    except Exception:
        raise TypeError(message) from None
    if findings:
        raise TypeError(message)
    return text


def _scan_config_text(value: str) -> None:
    try:
        findings = scan_text(value, source_id="doctor-config")
    except Exception:
        raise DoctorConfigError("invalid doctor config") from None
    if findings:
        raise DoctorConfigError("invalid doctor config")

def _check_finding_order(findings: tuple[DoctorFinding, ...]) -> None:
    priorities = [100 if finding.severity != "blocker" else DOCTOR_FAILURE_PRIORITY[finding.failure_code] for finding in findings]
    if priorities != sorted(priorities):
        raise TypeError("invalid doctor report")

__all__ = ("DoctorConfig", "DoctorConfigError", "DoctorFinding", "DoctorReport", "DOCTOR_FAILURE_PRIORITY",
           "JsonLine", "SourceParseError", "check_doctor_finding", "check_doctor_report",
           "snapshot_doctor_config", "strict_jsonl_objects", "utf8_text")
