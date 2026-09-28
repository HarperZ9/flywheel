from typing import Any


class InspectImportError(ValueError): pass


def _object(value: object, pointer: str) -> dict:
    if type(value) is not dict: raise InspectImportError(f"{pointer} must be an object")
    return value


def _optional_object(value: object, pointer: str) -> dict:
    if value is None: return {}
    return _object(value, pointer)


def _exact_bool(value: object, pointer: str) -> bool:
    if type(value) is not bool: raise InspectImportError(f"{pointer} must be a boolean")
    return value


def _exact_int(value: object, pointer: str) -> int:
    if type(value) is not int: raise InspectImportError(f"{pointer} must be an integer")
    return value


def _optional_int(value: object, pointer: str) -> int | None:
    if value is None: return None
    return _exact_int(value, pointer)


def _exact_str(value: object, pointer: str) -> str:
    if type(value) is not str: raise InspectImportError(f"{pointer} must be a string")
    return value


def _optional_str(value: object, pointer: str) -> str | None:
    if value is None: return None
    return _exact_str(value, pointer)


def _sample_id(value: object, pointer: str) -> str | int:
    if type(value) in (str, int): return value
    raise InspectImportError(f"{pointer} must be a string or integer")


def _json_scalar(value: object) -> bool:
    return type(value) in (str, bool, int, float)


def _score_value(value: object) -> bool:
    if _json_scalar(value): return True
    if type(value) is list: return all(_json_scalar(item) for item in value)
    return type(value) is dict and all(type(key) is str and (item is None or _json_scalar(item)) for key, item in value.items())


def _add(pointers: list[dict[str, Any]], pointer: str, value: object) -> None:
    pointers.append({"json_pointer": pointer, "source_value": value})


def _escape(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")
