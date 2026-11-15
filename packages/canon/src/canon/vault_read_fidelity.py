"""vault_read_fidelity.py -- M4.2: symmetric read-leg round-trip verdict.

R2's vault_fidelity certifies the render_note->ingest_note codec is lossless.
This module lifts that guarantee to the WHOLE VAULT round trip: plan_vault
writes a pool into an in-memory FakeFS, read_vault reads it back, and pool_out
is field-diffed against pool_in with the same `classify_note_losses` R2 uses.

The declared-drop vocabulary is EMPTY (`DECLARED_READ_DROPS`, D-83): the write
leg is lossless, the read leg opens no side-channel that could drop a field, so
every difference is UNDECLARED and fails the verdict closed. Symmetric to
vault_fidelity.DECLARED_NOTE_DROPS.

The FakeFS is a dict-backed injected IO: read_text returns None on absent,
write_text records every commit, list_dir returns the POSIX relpaths under a
root. No host filesystem is touched; the module is stdlib-only.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from canon.backends.base import record_key
from canon.fidelity import Refusal
from canon.schema import Record
from canon.vault_fidelity import NoteLoss, classify_note_losses
from canon.vault_mirror import VaultError, plan_vault
from canon.vault_reader import LOADED, VaultReadResult, read_vault

_MIRROR_ROOT = os.path.abspath(os.sep + "canon-vault-fake-symmetric")


DECLARED_READ_DROPS: frozenset = frozenset()


@dataclass(frozen=True, slots=True)
class VaultReadVerdict:
    """The whole-vault symmetric round-trip result.

    ok is the conjunction of write_ok, read_ok, pool_matches, no undeclared
    loss, and no refusal. declared_drops is empty (D-83): the read leg is
    lossless, so any observed difference is UNDECLARED.
    """

    ok: bool
    write_ok: bool
    read_ok: bool
    pool_matches: bool
    declared_drops: frozenset
    losses: tuple
    refusals: tuple
    read_result: VaultReadResult | None
    n_records_in: int
    n_records_out: int


class FakeFS:
    """Dict-backed injected IO for the symmetric round trip.

    Files keyed by normcase-normpath of their absolute path. read_text returns
    None for an absent file; write_text records every commit; list_dir yields
    the POSIX relpaths of every file under `root`. Both R2's plan_vault and
    M4.2's read_vault accept these as duck-typed callables.
    """

    def __init__(self, files: dict[str, str] | None = None) -> None:
        self._files: dict[str, str] = {}
        for key, val in (files or {}).items():
            self._files[self._nc(key)] = val
        self.writes: list[tuple[str, str]] = []

    @staticmethod
    def _nc(path: str) -> str:
        return os.path.normcase(os.path.normpath(path))

    def read_text(self, path: str) -> str | None:
        return self._files.get(self._nc(path))

    def write_text(self, path: str, content: str) -> None:
        self.writes.append((path, content))
        self._files[self._nc(path)] = content

    def list_dir(self, root: str) -> list[str]:
        root_nc = self._nc(root) + os.sep
        out: list[str] = []
        for abs_nc in self._files:
            if abs_nc.startswith(root_nc):
                out.append(abs_nc[len(root_nc):].replace(os.sep, "/"))
        return out


def _diff_pools(pool_in: list[Record], pool_out: tuple[Record, ...],
                ) -> tuple[bool, list[NoteLoss], list[Refusal]]:
    """Match records by (scope, id) key and diff each pair with R2's
    classify_note_losses. A record present on one side and absent on the other
    is a Refusal, not a NoteLoss (the field diff has no side to diff against)."""
    in_by_key = {record_key(r): r for r in pool_in}
    out_by_key = {record_key(r): r for r in pool_out}
    losses: list[NoteLoss] = []
    refusals: list[Refusal] = []
    for key, raw in in_by_key.items():
        got = out_by_key.get(key)
        if got is None:
            refusals.append(Refusal(raw.id, "read", f"record {key!r} absent from pool_out"))
            continue
        losses.extend(classify_note_losses(raw, got))
    for key, got in out_by_key.items():
        if key not in in_by_key:
            refusals.append(Refusal(got.id, "read", f"pool_out carries unexpected key {key!r}"))
    pool_matches = not losses and not refusals
    return pool_matches, losses, refusals


def vault_symmetric_report(records: list[Record], *,
                           initial_fs: FakeFS | None = None) -> VaultReadVerdict:
    """Write `records` through plan_vault, read the vault back with read_vault,
    diff pool_out against `records`, and return one verdict.

    Refusals on the write leg (VaultError from plan_vault) or the read leg (any
    verdict outside OK_STATUSES) are caught and folded into the verdict; the
    function never propagates an exception. The declared-drop vocabulary is
    empty, so the presence of any loss or refusal fails the verdict closed.
    """
    fs = initial_fs if initial_fs is not None else FakeFS()
    n_in = len(records)
    refusals: list[Refusal] = []
    write_ok = True
    try:
        plan_vault(
            records, vault=_MIRROR_ROOT, read_text=fs.read_text,
            write_text=fs.write_text, list_dir=fs.list_dir)
    except VaultError as exc:
        write_ok = False
        refusals.append(Refusal("", "write", str(exc)))
        return VaultReadVerdict(
            ok=False, write_ok=False, read_ok=False, pool_matches=False,
            declared_drops=DECLARED_READ_DROPS, losses=(), refusals=tuple(refusals),
            read_result=None, n_records_in=n_in, n_records_out=0)

    result = read_vault(_MIRROR_ROOT, list_dir=fs.list_dir, read_text=fs.read_text)
    read_ok = result.ok
    for v in result.refusals:
        refusals.append(Refusal(
            v.record.id if v.record is not None else "", "read",
            f"{v.status} at {v.relpath!r}: {v.reason}"))

    pool_matches, losses, more_refusals = _diff_pools(records, result.pool)
    refusals.extend(more_refusals)
    ok = write_ok and read_ok and pool_matches and not losses and not refusals
    return VaultReadVerdict(
        ok=ok, write_ok=write_ok, read_ok=read_ok, pool_matches=pool_matches,
        declared_drops=DECLARED_READ_DROPS, losses=tuple(losses),
        refusals=tuple(refusals), read_result=result,
        n_records_in=n_in, n_records_out=len(result.pool))
