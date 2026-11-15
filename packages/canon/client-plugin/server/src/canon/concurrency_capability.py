from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import weakref


@dataclass(slots=True)
class LockCapability:
    root: Path
    name: str
    lock_name: str
    token: str
    path: Path
    backend: str
    dir_ref: int
    file_ref: int
    file_id: tuple[int, ...]
    owner: object | weakref.ReferenceType | None = None
    released: bool = False
    registry_token: object = field(default_factory=object, repr=False)


_REGISTRY: dict[int, LockCapability] = {}


def register(owner: object, capability: LockCapability) -> None:
    capability.owner = owner
    capability.registry_token = object()
    _REGISTRY[id(owner)] = capability


def lookup(owner: object) -> LockCapability | None:
    owner_id = id(owner)
    capability = _REGISTRY.get(owner_id)
    if capability is None:
        return None
    registered_owner = _owner(capability)
    if registered_owner is owner:
        return capability
    if registered_owner is None:
        _drop_if_current(owner_id, capability.registry_token)
    return None


def mark_released(owner: object, capability: LockCapability) -> None:
    owner_id = id(owner)
    token = object()
    capability.released = True
    capability.registry_token = token
    capability.owner = weakref.ref(owner, lambda _ref: _drop_if_current(owner_id, token))


def _owner(capability: LockCapability) -> object | None:
    if isinstance(capability.owner, weakref.ReferenceType):
        return capability.owner()
    return capability.owner


def _drop_if_current(owner_id: int, token: object) -> None:
    current = _REGISTRY.get(owner_id)
    if current is None or current.registry_token is not token:
        return None
    _REGISTRY.pop(owner_id, None)


def unregister(owner: object) -> None:
    _REGISTRY.pop(id(owner), None)


def metadata_matches(
    capability: LockCapability,
    *,
    root: Path,
    name: str,
    token: str,
    path: Path,
) -> bool:
    return (
        capability.root == root
        and capability.name == name
        and capability.token == token
        and capability.path == path
    )
