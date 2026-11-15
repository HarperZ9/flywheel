from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

_PROTECTED_NAMES = frozenset({
    ".env",
    ".env.local",
    ".env.production",
    "credentials",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
    "known_hosts",
    "cookies.sqlite",
    "login data",
})

_PROTECTED_PARTS = (
    (".ssh",),
    (".gnupg",),
    (".aws",),
    (".azure",),
    (".config", "gcloud"),
    ("appdata", "local", "google", "chrome", "user data"),
    ("appdata", "roaming", "mozilla", "firefox", "profiles"),
    ("library", "application support", "google", "chrome"),
)

_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


@dataclass(frozen=True, slots=True)
class PathPolicyViolation:
    code: str
    path: str
    reason: str


class PathPolicyError(ValueError):
    def __init__(self, violations: tuple[PathPolicyViolation, ...]) -> None:
        self.violations = violations
        joined = "; ".join(f"{v.code}: {v.path} ({v.reason})" for v in violations)
        super().__init__(joined)


def _violation(code: str, path: str, reason: str) -> PathPolicyViolation:
    return PathPolicyViolation(code=code, path=path, reason=reason)


def _raise(code: str, path: str, reason: str) -> None:
    raise PathPolicyError((_violation(code, path, reason),))


def _coerce_path(value: object, *, role: str) -> tuple[Path, str]:
    try:
        raw = os.fspath(value)
    except TypeError:
        _raise(f"invalid-{role}", type(value).__name__, "path must be str or Path")
    if not isinstance(raw, str):
        _raise(f"invalid-{role}", type(value).__name__, "path must be text")
    if "\0" in raw:
        _raise(f"invalid-{role}", raw, "path contains NUL")
    return Path(raw), raw


def _is_drive_designator(part: str) -> bool:
    return len(part) == 2 and part[1] == ":" and part[0].isalpha()


def _split_raw_parts(raw: str) -> tuple[str, ...]:
    return tuple(part for part in raw.replace("/", "\\").split("\\") if part)


def _has_windows_drive(raw: str) -> bool:
    return len(raw) >= 2 and raw[1] == ":" and raw[0].isalpha()


def _drop_windows_drive(raw: str) -> str:
    return raw[2:] if _has_windows_drive(raw) else raw


def _is_windows_qualified(raw: str) -> bool:
    return _has_windows_drive(raw) or raw.replace("/", "\\").startswith("\\\\")


def _target_path(path: Path, raw: str, root: Path) -> Path:
    if path.is_absolute():
        return path
    if _is_windows_qualified(raw):
        _raise("outside-root", raw, "qualified path is not root-relative")
    return root / path


def _resolve_root(root: Path, raw: str) -> Path:
    try:
        resolved = root.resolve(strict=True)
    except FileNotFoundError:
        _raise("missing-root", raw, "root does not exist")
    except (OSError, RuntimeError, ValueError) as exc:
        _raise("invalid-root", raw, f"cannot resolve root: {exc}")
    try:
        is_dir = resolved.is_dir()
    except OSError as exc:
        _raise("invalid-root", str(resolved), f"cannot inspect root: {exc}")
    if not is_dir:
        _raise("invalid-root", str(resolved), "root must be a directory")
    return resolved


def _resolve_target(target: Path) -> Path:
    try:
        return target.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        _raise("invalid-path", str(target), f"cannot resolve path: {exc}")


def _is_under(target: Path, root: Path) -> bool:
    root_text = os.path.normcase(str(root))
    target_text = os.path.normcase(str(target))
    try:
        return os.path.commonpath((root_text, target_text)) == root_text
    except ValueError:
        return False


def _exists_or_link(path: Path) -> bool:
    try:
        return path.exists() or path.is_symlink()
    except OSError:
        return True


def _exists_resolved(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _check_reparse_chain(root: Path, target: Path) -> None:
    try:
        relative = target.relative_to(root)
    except ValueError:
        return
    current = root
    candidates = [current]
    for part in relative.parts:
        if part in ("", "."):
            continue
        current = current / part
        candidates.append(current)
    for candidate in candidates:
        if not _exists_or_link(candidate):
            return
        if is_reparse_point(candidate):
            _raise("reparse", str(candidate), "symlink or reparse point")


def is_windows_ads_path(path: str | Path) -> bool:
    _path, raw = _coerce_path(path, role="path")
    raw = _drop_windows_drive(raw)
    for part in _split_raw_parts(raw):
        if not _is_drive_designator(part) and ":" in part:
            return True
    return False


def is_reparse_point(path: str | Path) -> bool:
    candidate, _raw = _coerce_path(path, role="path")
    try:
        if candidate.is_symlink():
            return True
        attrs = getattr(candidate.lstat(), "st_file_attributes", None)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    if attrs is None:
        return os.name == "nt"
    return bool(attrs & _REPARSE_POINT)


def classify_protected_path(path: str | Path) -> tuple[PathPolicyViolation, ...]:
    _path, raw = _coerce_path(path, role="path")
    classified = _drop_windows_drive(raw)
    parts = tuple(
        part.casefold()
        for part in _split_raw_parts(classified)
        if not _is_drive_designator(part)
    )
    violations: list[PathPolicyViolation] = []
    for part in parts:
        if part in _PROTECTED_NAMES:
            violations.append(_violation("protected-path", raw, "protected name"))
    for protected in _PROTECTED_PARTS:
        size = len(protected)
        for index in range(len(parts) - size + 1):
            if parts[index:index + size] == protected:
                violations.append(_violation("protected-path", raw, "protected directory"))
                break
    return tuple(violations)


def resolve_under_root(
    path: str | Path,
    *,
    root: str | Path,
    must_exist: bool = False,
    reject_reparse: bool = True,
) -> Path:
    target_input, target_raw = _coerce_path(path, role="path")
    root_input, root_raw = _coerce_path(root, role="root")
    if is_windows_ads_path(target_raw):
        _raise("ads", target_raw, "alternate data stream path")

    root_resolved = _resolve_root(root_input, root_raw)
    target_unresolved = _target_path(target_input, target_raw, root_input)
    target_resolved = _resolve_target(target_unresolved)
    if target_resolved == root_resolved:
        _raise("root-target", str(target_resolved), "target is the root")

    if reject_reparse:
        _check_reparse_chain(root_input.absolute(), target_unresolved.absolute())
    if not _is_under(target_resolved, root_resolved):
        _raise("outside-root", str(target_resolved), "target resolves outside root")
    if must_exist and not _exists_resolved(target_resolved):
        _raise("missing-target", str(target_unresolved), "target does not exist")
    return target_resolved


def assert_not_protected(path: str | Path) -> None:
    violations = classify_protected_path(path)
    if violations:
        raise PathPolicyError(violations)


def assert_operational_surface_path(path: str | Path, *, root: str | Path) -> Path:
    resolved = resolve_under_root(path, root=root)
    assert_not_protected(resolved)
    return resolved


def assert_operational_vault_path(path: str | Path, *, vault: str | Path) -> Path:
    resolved = resolve_under_root(path, root=vault)
    assert_not_protected(resolved)
    return resolved
