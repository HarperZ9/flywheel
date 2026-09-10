"""Process-local browser registrations with immutable configuration metadata."""
from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True)
class Driver:
    name: str
    run: object
    binding_sha256: str


_LOCK = RLock()
_DRIVERS: dict[str, Driver] = {}


def valid_binding(value) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict) or set(value) != {'name', 'binding_sha256'}:
        return False
    name, digest = value['name'], value['binding_sha256']
    return (isinstance(name, str) and 1 <= len(name) <= 64 and name.isascii()
            and all(c.isalnum() or c in '_.:-' for c in name)
            and isinstance(digest, str) and len(digest) == 64
            and all(c in '0123456789abcdef' for c in digest))


def register(name, run, *, binding_sha256):
    if not callable(run):
        raise ValueError('a driver must be callable')
    descriptor = {'name': name, 'binding_sha256': binding_sha256}
    if not valid_binding(descriptor):
        raise ValueError('driver name and binding_sha256 must be valid immutable identifiers')
    with _LOCK:
        _DRIVERS[name] = Driver(name, run, binding_sha256)


def clear_drivers():
    with _LOCK:
        _DRIVERS.clear()


def unregister_driver(name):
    """Remove future captures; this does not cancel an already captured call."""
    with _LOCK:
        _DRIVERS.pop(name, None)


def snapshot():
    with _LOCK:
        return next(iter(_DRIVERS.values())) if len(_DRIVERS) == 1 else None


def binding(driver):
    return ({'name': driver.name, 'binding_sha256': driver.binding_sha256}
            if driver is not None else None)


def bound_driver():
    driver = snapshot()
    return (driver.name, driver.run) if driver is not None else (None, None)
