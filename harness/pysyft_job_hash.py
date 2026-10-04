"""pysyft_job_hash.py -- PySyft's job fingerprint, recomputed with the stdlib.

PySyft's syft-job package hashes a job submission when it arrives and again when
the data owner approves it, and the runner executes only a copy that matches the
approved hash. That landed in OpenMined/PySyft PR #9536, merge commit
36e65162ad2cfbae66d714db8d5c711e19a3a185 (2026-10-01), in
packages/syft-job/src/syft_job/submission.py.

This module recomputes the same value so that a person outside the run can check
that published job code is the code that was approved, without installing syft.
It is a clean-room restatement of the format, not a copy of PySyft's code:

    digest = SHA-256 over, for each file in sorted relative-path order:
        relative POSIX path as UTF-8, one 0x00 byte, SHA-256(file bytes) (raw 32 bytes)

Files skipped, as in PySyft: any path with a part in SYNC_EXCLUDED_NAMES, and the
permission file `syft.pub.yaml` (compared case-insensitively). `submission_hash`
covers every file (code/, run.sh, config.yaml); `code_hash` covers code/ and
run.sh only. The data owner records `submission_hash` as `approved_hash`.

Two known edges where this restatement and PySyft can differ, both stated rather
than hidden:
- Order. PySyft sorts `Path` objects. On POSIX that matches sorting the relative
  POSIX strings, which is what this does. On Windows `Path` ordering folds case
  and uses backslashes, so two names that differ only in case, or a name that
  sorts differently around a separator, can order differently.
- `code_hash(as_sent=True)` in PySyft reads text files with universal newlines in
  the locale encoding. This module hashes bytes as they are on disk, which is the
  data owner's side, the side that writes `approved_hash`.

PySyft is Apache-2.0. Nothing from it is vendored here; the constants below are
facts about its format, named with their source. Standard library only.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

PYSYFT_SOURCE = ("OpenMined/PySyft@36e65162ad2cfbae66d714db8d5c711e19a3a185:"
                 "packages/syft-job/src/syft_job/submission.py")
HASH_RULE = "pysyft-submission-hash/1"
PERMISSION_FILE_NAME = "syft.pub.yaml"
SYNC_EXCLUDED_NAMES = frozenset({
    ".venv", ".git", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "node_modules", ".DS_Store",
})
CODE_ENTRIES = frozenset({"code", "run.sh"})
SUBMISSION_ENTRIES = frozenset({"code", "run.sh", "config.yaml"})


class JobHashError(ValueError):
    """A job folder that cannot be hashed honestly (missing, or holds a symlink)."""


def _skipped(rel_parts: tuple, name: str) -> bool:
    if name.casefold() == PERMISSION_FILE_NAME.casefold():
        return True
    return any(part in SYNC_EXCLUDED_NAMES for part in rel_parts)


def _files(job_dir: Path, entries) -> list:
    """(relative posix path, absolute path) pairs that the hash covers, sorted."""
    if not job_dir.is_dir():
        raise JobHashError(f"not a job folder: {job_dir}")
    out = []
    for path in job_dir.rglob("*"):
        rel = path.relative_to(job_dir)
        if path.is_symlink():
            raise JobHashError(f"symlink in job folder: {rel.as_posix()}")
        if not path.is_file() or _skipped(rel.parts, rel.name):
            continue
        if entries is not None and rel.parts[0] not in entries:
            continue
        out.append((rel.as_posix(), path))
    return sorted(out, key=lambda pair: pair[0])


def digest_files(pairs) -> str:
    """The PySyft digest over (relative posix path, bytes) pairs, sorted by path."""
    h = hashlib.sha256()
    for rel, content in sorted(pairs, key=lambda pair: pair[0]):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(hashlib.sha256(content).digest())
    return h.hexdigest()


def submission_hash(job_dir) -> str:
    """The value PySyft records as `received_hash` and `approved_hash`."""
    return digest_files((rel, p.read_bytes()) for rel, p in _files(Path(job_dir), None))


def code_hash(job_dir) -> str:
    """PySyft's hash over run.sh and code/ only, as the data owner computes it."""
    return digest_files((rel, p.read_bytes())
                        for rel, p in _files(Path(job_dir), CODE_ENTRIES))
