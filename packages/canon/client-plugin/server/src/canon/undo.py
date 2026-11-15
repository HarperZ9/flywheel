from __future__ import annotations

import json
from pathlib import Path

from .canonical_json import canonical_json_text, sha256_bytes
from .cli_artifacts import ArtifactError, WorkspaceRoot, checked_workspace
from .undo_io import (
    checked_receipt_target,
    ensure_undo_root,
    list_receipt_files,
    read_receipt_file,
    read_regular_file,
    read_workspace_file,
    receipt_path,
    replace_file_guarded,
    replace_workspace_file,
    undo_root_path,
    write_receipt_file,
    write_new_or_same,
)
from .undo_receipts import UNDO_RECEIPT_SCHEMA, UndoApplyResult, UndoError, UndoReceipt, valid_receipt_id


class UndoStore:
    def __init__(self, workspace: str | Path | WorkspaceRoot) -> None:
        self._workspace = _checked_workspace(workspace)
        self._root = self._workspace.path

    def write(self, receipt: UndoReceipt) -> str:
        data = canonical_json_text(receipt.to_dict()).encode("utf-8")
        return write_receipt_file(self._workspace, receipt.receipt_id, data)

    def load(self, receipt_id: str) -> UndoReceipt:
        if not valid_receipt_id(receipt_id):
            raise UndoError("invalid_args")
        data = read_receipt_file(self._workspace, receipt_id)
        try:
            text = data.decode("utf-8")
            value = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise UndoError("conflict") from None
        if text != canonical_json_text(value):
            raise UndoError("conflict")
        return UndoReceipt.from_dict(value, expected_id=receipt_id)

    def list_metadata(self) -> list[dict[str, object]]:
        return [self.load(Path(name).stem).metadata() for name in list_receipt_files(self._workspace)]

    def apply(self, receipt_id: str, *, workspace: WorkspaceRoot) -> UndoApplyResult:
        receipt = self.load(receipt_id)
        checked_receipt_target(receipt, workspace=workspace)
        current = read_workspace_file(workspace, receipt.target_path)
        current_hash = sha256_bytes(current)
        if current_hash == receipt.preimage_sha256:
            return UndoApplyResult(receipt.receipt_id, receipt.target_path, False, True)
        if current_hash != receipt.postimage_sha256:
            raise UndoError("conflict")
        replace_workspace_file(workspace, receipt.target_path, receipt.postimage_sha256, receipt.preimage_text.encode("utf-8"))
        return UndoApplyResult(receipt.receipt_id, receipt.target_path, True, False)


def _checked_workspace(workspace: str | Path | WorkspaceRoot) -> WorkspaceRoot:
    if type(workspace) is WorkspaceRoot:
        return workspace
    try:
        return checked_workspace(str(Path(workspace)))
    except (ArtifactError, TypeError, OSError) as exc:
        raise UndoError("unsafe_path") from exc


__all__ = [
    "UNDO_RECEIPT_SCHEMA",
    "UndoApplyResult",
    "UndoError",
    "UndoReceipt",
    "UndoStore",
    "checked_receipt_target",
    "read_regular_file",
    "replace_file_guarded",
]
