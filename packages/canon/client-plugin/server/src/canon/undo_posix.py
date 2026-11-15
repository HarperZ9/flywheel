from __future__ import annotations

from pathlib import Path

from .undo_posix_core import (
    close_child,
    close_root,
    ensure_undo,
    open_parent,
    open_root,
    open_undo,
    supported,
)
from .undo_posix_files import (
    list_names,
    read_at,
    replace_at,
    write_new_or_same,
)
from .undo_receipts import UndoError


def read_workspace_file(root_path: Path, root_key: tuple[int, int], relative: str) -> bytes:
    root = open_root(root_path, root_key)
    try:
        parent = open_parent(root, Path(relative).parent)
        try:
            data = read_at(parent, Path(relative).name, required=True)
            if data is None:
                raise UndoError("conflict")
            return data
        finally:
            close_child(parent, root)
    finally:
        close_root(root)


def replace_workspace_file(root_path: Path, root_key: tuple[int, int], relative: str, expected_hash: str, data: bytes) -> None:
    root = open_root(root_path, root_key)
    try:
        parent = open_parent(root, Path(relative).parent)
        try:
            replace_at(root, parent, Path(relative).name, expected_hash, data)
        finally:
            close_child(parent, root)
    finally:
        close_root(root)


def write_receipt(root_path: Path, root_key: tuple[int, int], name: str, data: bytes) -> str:
    root = open_root(root_path, root_key)
    try:
        undo = ensure_undo(root)
        try:
            return write_new_or_same(undo, name, data)
        finally:
            close_child(undo, root)
    finally:
        close_root(root)


def read_receipt(root_path: Path, root_key: tuple[int, int], name: str) -> bytes:
    root = open_root(root_path, root_key)
    try:
        undo = open_undo(root, required=True)
        if undo is None:
            raise UndoError("conflict")
        try:
            data = read_at(undo, name, required=True)
            if data is None:
                raise UndoError("conflict")
            return data
        finally:
            close_child(undo, root)
    finally:
        close_root(root)


def list_receipts(root_path: Path, root_key: tuple[int, int]) -> list[str]:
    root = open_root(root_path, root_key)
    try:
        undo = open_undo(root, required=False)
        if undo is None:
            return []
        try:
            return sorted(name for name in list_names(undo) if name.startswith("undo-") and name.endswith(".json"))
        finally:
            close_child(undo, root)
    finally:
        close_root(root)


def ensure_undo_root(root_path: Path, root_key: tuple[int, int]) -> Path:
    root = open_root(root_path, root_key)
    try:
        undo = ensure_undo(root)
        try:
            return undo.path
        finally:
            close_child(undo, root)
    finally:
        close_root(root)


__all__ = [
    "ensure_undo_root",
    "list_receipts",
    "read_receipt",
    "read_workspace_file",
    "replace_workspace_file",
    "supported",
    "write_receipt",
]
