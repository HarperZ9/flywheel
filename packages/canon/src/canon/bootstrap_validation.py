from __future__ import annotations

import math
import re
from collections.abc import Mapping

from .adapter import INTEGRATION_TIERS
from .secret_quarantine import SecretQuarantineError, scan_text

_ADAPTER_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class BootstrapConfigError(ValueError):
    def __init__(self, message: str = "invalid bootstrap config", *, code: str = "invalid_args") -> None:
        self.code = code
        super().__init__(message)


class _FrozenBootstrapMapping(Mapping[str, object]):
    __slots__ = ("_items", "__weakref__")

    def __init__(self, items: tuple[tuple[str, object], ...]) -> None:
        object.__setattr__(self, "_items", items)
        _require_frozen_items(self, TypeError)

    def __getitem__(self, key: str) -> object:
        for item_key, value in _require_frozen_items(self, TypeError):
            if item_key == key:
                return value
        raise KeyError(key)

    def __iter__(self):
        return (key for key, _ in _require_frozen_items(self, TypeError))

    def __len__(self) -> int:
        return len(_require_frozen_items(self, TypeError))

    def __setattr__(self, name: str, value: object) -> None:
        raise TypeError("frozen bootstrap mapping")


def snapshot_config_values(
    *,
    workspace: object,
    state_dir: object,
    target: object,
    tier: object,
    profile: object,
    offline: object,
    run_id: object,
    readiness_response: object,
) -> dict[str, object]:
    return {
        "workspace": config_text(_path_text(workspace), "workspace"),
        "state_dir": config_text(_path_text(state_dir), "state_dir"),
        "target": config_text(_adapter_id(target), "target"),
        "tier": config_text(_tier(tier), "tier"),
        "profile": config_text(_token(profile, "profile"), "profile"),
        "offline": _exact_bool(offline),
        "run_id": config_text(_token(run_id, "run_id"), "run_id"),
        "readiness_response": snapshot_response(readiness_response),
    }


def snapshot_data(data: Mapping[str, object] | None) -> Mapping[str, object] | None:
    if data is None:
        return None
    if type(data) is not dict:
        raise TypeError("invalid bootstrap data")
    return _snapshot_mapping(data, TypeError)


def snapshot_response(value: object) -> object:
    if value is None:
        return None
    try:
        if type(value) is dict:
            return _snapshot_mapping(value, BootstrapConfigError)
        if type(value) is _FrozenBootstrapMapping:
            _require_serializable_mapping(value)
            return value
    except TypeError:
        raise BootstrapConfigError("invalid bootstrap config") from None
    raise BootstrapConfigError("invalid bootstrap config")


def thaw_mapping_or_none(data: Mapping[str, object] | None) -> dict[str, object] | None:
    require_serializable_data(data, "invalid bootstrap data")
    if data is None:
        return None
    return _thaw_mapping(data)


def require_serializable_data(data: object, message: str) -> None:
    try:
        _require_serializable_data_shape(data)
    except TypeError:
        raise TypeError(message) from None


def require_bool(value: object, name: str) -> None:
    if type(value) is not bool:
        raise TypeError(f"invalid bootstrap {name}")


def safe_text(value: object, name: str) -> str:
    if type(value) is not str or value == "" or _has_control(value):
        raise TypeError(f"invalid bootstrap {name}")
    return value


def config_text(value: str, name: str) -> str:
    try:
        if scan_text(value, source_id=f"bootstrap-config-{name}"):
            raise BootstrapConfigError("invalid bootstrap config", code="secret_quarantine")
    except SecretQuarantineError as exc:
        raise BootstrapConfigError("invalid bootstrap config") from exc
    return value


def _snapshot_mapping(data: dict[object, object], error: type[Exception]) -> Mapping[str, object]:
    items: list[tuple[str, object]] = []
    for key, value in data.items():
        items.append((_safe_key(key, error), _snapshot_value(value, error)))
    return _FrozenBootstrapMapping(tuple(items))


def _snapshot_value(value: object, error: type[Exception]) -> object:
    if value is None or type(value) in (str, bool):
        return value
    if type(value) is int:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) is dict:
        return _snapshot_mapping(value, error)
    if type(value) in (list, tuple):
        return tuple(_snapshot_value(item, error) for item in value)
    raise error("invalid bootstrap config" if error is BootstrapConfigError else "invalid bootstrap data")


def _thaw_value(value: object) -> object:
    if type(value) is dict or type(value) is _FrozenBootstrapMapping:
        return _thaw_mapping(value)
    if type(value) in (list, tuple):
        return [_thaw_value(item) for item in value]
    return value


def _thaw_mapping(data: object) -> dict[str, object]:
    if type(data) is dict:
        return {key: _thaw_value(item) for key, item in data.items()}
    return {key: _thaw_value(item) for key, item in _require_frozen_items(data, TypeError)}


def _require_serializable_data_shape(data: object) -> None:
    if data is None:
        return
    _require_serializable_mapping(data)


def _require_serializable_mapping(data: object) -> None:
    if type(data) is dict:
        items = data.items()
    elif type(data) is _FrozenBootstrapMapping:
        items = _require_frozen_items(data, TypeError)
    else:
        raise TypeError("invalid bootstrap data")
    for key, value in items:
        _safe_key(key, TypeError)
        _require_serializable_value(value)


def _require_serializable_value(value: object) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is dict or type(value) is _FrozenBootstrapMapping:
        _require_serializable_mapping(value)
        return
    if type(value) in (list, tuple):
        for item in value:
            _require_serializable_value(item)
        return
    raise TypeError("invalid bootstrap data")


def _require_frozen_items(value: object, error: type[Exception]) -> tuple[tuple[str, object], ...]:
    message = _error_message(error)
    if type(value) is not _FrozenBootstrapMapping:
        raise error(message) from None
    try:
        items = object.__getattribute__(value, "_items")
    except AttributeError:
        raise error(message) from None
    if type(items) is not tuple:
        raise error(message) from None
    for item in items:
        if type(item) is not tuple or len(item) != 2:
            raise error(message) from None
        _safe_key(item[0], error)
    return items


def _error_message(error: type[Exception]) -> str:
    return "invalid bootstrap config" if error is BootstrapConfigError else "invalid bootstrap data"


def _path_text(value: object) -> str:
    if type(value) is not str or value == "" or _has_control(value):
        raise BootstrapConfigError("invalid bootstrap config")
    return value


def _adapter_id(value: object) -> str:
    if type(value) is not str or _ADAPTER_ID_RE.fullmatch(value) is None:
        raise BootstrapConfigError("invalid bootstrap config")
    return value


def _tier(value: object) -> str:
    if type(value) is not str or value not in INTEGRATION_TIERS:
        raise BootstrapConfigError("invalid bootstrap config")
    return value


def _token(value: object, name: str) -> str:
    if type(value) is not str or _TOKEN_RE.fullmatch(value) is None:
        raise BootstrapConfigError(f"invalid bootstrap {name}")
    return value


def _exact_bool(value: object) -> bool:
    if type(value) is not bool:
        raise BootstrapConfigError("invalid bootstrap config")
    return value


def _safe_key(value: object, error: type[Exception]) -> str:
    if type(value) is not str or value == "" or _has_control(value):
        raise error("invalid bootstrap config" if error is BootstrapConfigError else "invalid bootstrap data")
    return value


def _has_control(value: str) -> bool:
    return "\0" in value or any(ord(char) < 32 or ord(char) == 127 for char in value)
