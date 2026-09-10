"""Private snapshot copy for untrusted enterprise environment artifacts."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Any, Iterator

from harness.cross_harness_artifacts import snapshot_source_tree
from harness.private_artifact_fs import (
    NOT_FOUND,
    PrivateArtifactError,
    open_artifact_root,
    root_identity,
)

MAX_REVIEW_FILE_BYTES = 32 * 1024 * 1024
MAX_REVIEW_TOTAL_BYTES = 128 * 1024 * 1024
MAX_REVIEW_FILES = 256
_SERVICE_DESK_REVIEW_INPUTS = (
    "descriptor.json",
    "source-basis.json",
    "agent-view.json",
    "control-view.json",
    "domain-state-before.json",
    "domain-state-after.json",
    "action-log.json",
    "state-snapshot-before.json",
    "state-snapshot-after.json",
    "receipt.json",
    "review.html",
    "calibration/calibration-receipt.json",
)


class ArtifactSnapshotError(ValueError):
    """The artifact tree could not be copied through object-bound reads."""


@contextmanager
def snapshotted_artifact_dir(source: Path) -> Iterator[Path]:
    """Yield a private copy whose bytes were read through artifact custody."""
    temp: Path | None = None
    try:
        source = Path(source)
        identity = root_identity(source)
        if len(_SERVICE_DESK_REVIEW_INPUTS) > MAX_REVIEW_FILES:
            raise ArtifactSnapshotError("artifact tree contains too many files")
        temp = Path(tempfile.mkdtemp(prefix="flywheel-servicedesk-review-"))
        manifest = {"files": []}
        total = 0
        with open_artifact_root(source, expected=identity, writable=False) as opened:
            for name in _SERVICE_DESK_REVIEW_INPUTS:
                rel = _relative_file(name)
                remaining = MAX_REVIEW_TOTAL_BYTES - total
                if remaining < 0:
                    raise ArtifactSnapshotError("artifact tree is too large")
                try:
                    data = opened.read_bytes(
                        rel.as_posix(),
                        max_bytes=min(MAX_REVIEW_FILE_BYTES, remaining),
                    )
                except PrivateArtifactError as exc:
                    if exc.code == NOT_FOUND:
                        continue
                    raise
                total += len(data)
                if total > MAX_REVIEW_TOTAL_BYTES:
                    raise ArtifactSnapshotError("artifact tree is too large")
                target = temp / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                manifest["files"].append(
                    {"path": rel.as_posix(), "sha256": hashlib.sha256(data).hexdigest()}
                )
        copied = snapshot_source_tree(temp)
        if _file_index(copied) != _file_index(manifest):
            raise ArtifactSnapshotError("artifact snapshot copy mismatch")
        yield temp
    except ArtifactSnapshotError:
        raise
    except (PrivateArtifactError, OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ArtifactSnapshotError("artifact tree cannot be safely snapshotted") from exc
    finally:
        if temp is not None:
            shutil.rmtree(temp, ignore_errors=True)


def _rows(manifest: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = manifest.get(key)
    if type(value) is not list or not all(type(row) is dict for row in value):
        raise ArtifactSnapshotError("artifact snapshot manifest is malformed")
    return value


def _relative_file(value: Any) -> PurePosixPath:
    return PurePosixPath(_relative(value).as_posix())


def _relative(value: Any) -> Path:
    if type(value) is not str or not value or "\\" in value or ":" in value:
        raise ArtifactSnapshotError("artifact path is unsafe")
    posix = PurePosixPath(value)
    if posix.is_absolute() or any(part in ("", ".", "..") for part in posix.parts):
        raise ArtifactSnapshotError("artifact path is unsafe")
    return Path(*posix.parts)


def _sha(row: dict[str, Any]) -> str:
    value = row.get("sha256")
    if type(value) is not str or len(value) != 64 or any(
            char not in "0123456789abcdef" for char in value):
        raise ArtifactSnapshotError("artifact digest is malformed")
    return value


def _file_index(manifest: dict[str, Any]) -> dict[str, str]:
    return {row["path"]: row["sha256"] for row in _rows(manifest, "files")}
