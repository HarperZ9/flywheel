"""Output formatting primitives for canon command results."""
from __future__ import annotations

import io
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TextIO

from .canonical_json import CanonicalJSONError, canonical_json_text
from .exit_codes import EX_OK, exit_code_for

_GREEN = "\x1b[32m"
_RED = "\x1b[31m"
_RESET = "\x1b[0m"


@dataclass(frozen=True, slots=True)
class CliResult:
    ok: bool
    command: str
    failure_code: str
    message: str
    data: Mapping[str, object] | None = field(repr=False)
    exit_code: int

    def __post_init__(self) -> None:
        _validate_bool(self.ok, "ok")
        _safe_result_text(self.command, "command")
        _safe_result_text(self.failure_code, "failure_code")
        _safe_result_text(self.message, "message")
        _validate_exit_code(self.exit_code)
        object.__setattr__(self, "data", _snapshot_data(self.data))
        _validate_invariants(self.ok, self.failure_code, self.exit_code)

    def to_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "data": _thaw_data(self.data),
            "exit_code": self.exit_code,
            "failure_code": self.failure_code,
            "message": self.message,
            "ok": self.ok,
        }


def make_result(
    *,
    ok: bool,
    command: str,
    failure_code: str,
    message: str,
    data: Mapping[str, object] | None = None,
) -> CliResult:
    """Create a validated, snapshot command result."""
    _validate_bool(ok, "ok")
    command = _safe_result_text(command, "command")
    failure_code = _safe_result_text(failure_code, "failure_code")
    message = _safe_result_text(message, "message")
    result_data = _snapshot_data(data)
    exit_code = EX_OK if ok else exit_code_for(failure_code)
    return CliResult(
        ok=ok,
        command=command,
        failure_code=failure_code,
        message=message,
        data=result_data,
        exit_code=exit_code,
    )


def write_result(
    result: CliResult,
    *,
    stdout: TextIO,
    stderr: TextIO,
    json_output: bool,
    color: bool,
    width: int = 80,
) -> int:
    """Write a command result and return its process exit code."""
    _validate_result(result)
    _validate_bool(json_output, "json_output")
    _validate_bool(color, "color")
    if type(width) is not int or isinstance(width, bool) or width <= 0:
        raise TypeError("invalid CLI output width")

    if json_output:
        _write_json_result(stdout, _json_result_text(result))
        return result.exit_code

    target = stdout if result.ok else stderr
    target.write(_human_result_text(result, color))
    return result.exit_code


def color_enabled(*, environ: Mapping[str, str], no_color: bool, is_tty: bool) -> bool:
    """Return whether human CLI output may use ANSI color."""
    if not isinstance(environ, Mapping):
        return False
    if type(no_color) is not bool or type(is_tty) is not bool:
        return False
    try:
        no_color_env = "NO_COLOR" in environ
    except Exception:
        return False
    return is_tty and not no_color and not no_color_env


def _json_result_text(result: CliResult) -> str:
    try:
        return canonical_json_text(result.to_dict())
    except CanonicalJSONError:
        raise TypeError("invalid CLI result data") from None


def _write_json_result(stdout: TextIO, text: str) -> None:
    if isinstance(stdout, io.TextIOWrapper):
        stdout.flush()
        stdout.buffer.write(text.encode("utf-8"))
        stdout.buffer.flush()
        return
    stdout.write(text)


def _human_result_text(result: CliResult, color: bool) -> str:
    label = "PASS" if result.ok else "FAIL"
    if color:
        code = _GREEN if result.ok else _RED
        label = f"{code}{label}{_RESET}"
    return f"{label} {result.command}: {result.message}\n"


def _validate_result(result: CliResult) -> None:
    if type(result) is not CliResult:
        raise TypeError("invalid CLI result")
    _validate_bool(result.ok, "ok")
    _safe_result_text(result.command, "command")
    _safe_result_text(result.failure_code, "failure_code")
    _safe_result_text(result.message, "message")
    _validate_exit_code(result.exit_code)
    try:
        _thaw_data(result.data)
    except TypeError:
        raise TypeError("invalid CLI result") from None
    _validate_invariants(result.ok, result.failure_code, result.exit_code)


def _validate_bool(value: object, name: str) -> None:
    if type(value) is not bool:
        raise TypeError(f"invalid CLI result {name}")


def _validate_exit_code(value: object) -> None:
    if type(value) is not int or isinstance(value, bool):
        raise TypeError("invalid CLI result")


def _validate_invariants(ok: bool, failure_code: str, exit_code: int) -> None:
    mapped = exit_code_for(failure_code)
    if ok and (failure_code != "ok" or exit_code != EX_OK):
        raise TypeError("invalid CLI result")
    if not ok and (failure_code == "ok" or mapped == EX_OK or exit_code != mapped):
        raise TypeError("invalid CLI result")


def _safe_result_text(value: object, name: str) -> str:
    if type(value) is not str or value == "" or _has_control(value):
        raise TypeError(f"invalid CLI result {name}")
    return value


def _snapshot_data(data: Mapping[str, object] | None) -> Mapping[str, object] | None:
    if data is None:
        return None
    if not isinstance(data, Mapping):
        raise TypeError("invalid result data")
    return _snapshot_mapping(data)


def _snapshot_mapping(data: Mapping[object, object]) -> Mapping[str, object]:
    try:
        snapshot = {_snapshot_key(key): _snapshot_value(value) for key, value in data.items()}
    except Exception:
        raise TypeError("invalid result data") from None
    return MappingProxyType(snapshot)


def _snapshot_key(key: object) -> str:
    if type(key) is not str:
        raise TypeError("invalid result data")
    return key


def _snapshot_value(value: object) -> object:
    if value is None or type(value) in (str, bool):
        return value
    if type(value) is int:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise TypeError("invalid result data")
        return value
    if isinstance(value, Mapping):
        return _snapshot_mapping(value)
    if type(value) in (list, tuple):
        return tuple(_snapshot_value(item) for item in value)
    raise TypeError("invalid result data")


def _thaw_data(data: Mapping[str, object] | None) -> dict[str, object] | None:
    if data is None:
        return None
    if not isinstance(data, Mapping):
        raise TypeError("invalid CLI result data")
    return _thaw_mapping(data)


def _thaw_mapping(data: Mapping[object, object]) -> dict[str, object]:
    try:
        return {_snapshot_key(key): _thaw_value(value) for key, value in data.items()}
    except Exception:
        raise TypeError("invalid CLI result data") from None


def _thaw_value(value: object) -> object:
    if value is None or type(value) in (str, bool):
        return value
    if type(value) is int:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise TypeError("invalid CLI result data")
        return value
    if isinstance(value, Mapping):
        return _thaw_mapping(value)
    if type(value) in (list, tuple):
        return [_thaw_value(item) for item in value]
    raise TypeError("invalid CLI result data")


def _has_control(value: str) -> bool:
    return "\0" in value or any(ord(char) < 32 or ord(char) == 127 for char in value)


__all__ = ["CliResult", "make_result", "write_result", "color_enabled"]
