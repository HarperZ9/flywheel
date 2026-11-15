from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import re

from .canonical_json import canonical_json_text, canonical_sha256, is_sha256_ref, sha256_text

UNDO_RECEIPT_SCHEMA = "canon.undo-receipt/v1"
_RECEIPT_RE = re.compile(r"^undo-[0-9a-f]{64}$")
_DOES_NOT_PROVE = (
    "This undo receipt does not prove external host acceptance.",
    "This undo receipt does not prove model use.",
    "This undo receipt does not prove semantic compliance.",
)


class UndoError(OSError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class UndoApplyResult:
    receipt_id: str
    target_path: str
    changed: bool
    already_restored: bool

    def to_metadata(self) -> dict[str, object]:
        return {
            "already_restored": self.already_restored,
            "changed": self.changed,
            "receipt_id": self.receipt_id,
            "target_path": self.target_path,
        }


@dataclass(frozen=True, slots=True)
class UndoReceipt:
    receipt_id: str
    target_path: str
    target_adapter: str
    target_surface: str
    scope: str
    preimage_sha256: str
    postimage_sha256: str
    preimage_text: str
    postimage_region_sha256: str
    capsule_id: str | None
    manifest_sha256: str
    source_state: Mapping[str, object]
    created_by: str
    does_not_prove: tuple[str, ...]

    @classmethod
    def for_region(
        cls,
        *,
        target_path: str,
        target_adapter: str,
        target_surface: str,
        scope: str,
        preimage_text: str,
        postimage_sha256: str,
        postimage_region_sha256: str,
        manifest_sha256: str,
        source_state: Mapping[str, object],
        capsule_id: str | None = None,
    ) -> "UndoReceipt":
        preimage_sha256 = sha256_text(_safe_preimage(preimage_text))
        source = _json_object(source_state)
        receipt_id = _receipt_id(
            target_path, target_adapter, target_surface, scope, preimage_sha256,
            postimage_sha256, postimage_region_sha256, manifest_sha256, source, capsule_id,
        )
        return cls(
            receipt_id, target_path, target_adapter, target_surface, scope,
            preimage_sha256, postimage_sha256, preimage_text, postimage_region_sha256,
            capsule_id, manifest_sha256, source, "canon export --apply-region", _DOES_NOT_PROVE,
        )

    @classmethod
    def from_dict(cls, value: object, *, expected_id: str | None = None) -> "UndoReceipt":
        if type(value) is not dict or value.get("schema") != UNDO_RECEIPT_SCHEMA:
            raise UndoError("conflict")
        try:
            receipt = cls(
                value["receipt_id"], value["target_path"], value["target_adapter"],
                value["target_surface"], value["scope"], value["preimage_sha256"],
                value["postimage_sha256"], value["preimage_text"],
                value["postimage_region_sha256"], value.get("capsule_id"),
                value["manifest_sha256"], _json_object(value["source_state"]),
                value["created_by"], _does_not_prove(value["does_not_prove"]),
            )
        except (KeyError, TypeError):
            raise UndoError("conflict") from None
        receipt.validate(expected_id=expected_id)
        return receipt

    def to_dict(self) -> dict[str, object]:
        self.validate()
        result = {
            "created_by": self.created_by,
            "does_not_prove": list(self.does_not_prove),
            "manifest_sha256": self.manifest_sha256,
            "postimage_region_sha256": self.postimage_region_sha256,
            "postimage_sha256": self.postimage_sha256,
            "preimage_sha256": self.preimage_sha256,
            "preimage_text": self.preimage_text,
            "receipt_id": self.receipt_id,
            "schema": UNDO_RECEIPT_SCHEMA,
            "scope": self.scope,
            "source_state": _json_object(self.source_state),
            "target_adapter": self.target_adapter,
            "target_path": self.target_path,
            "target_surface": self.target_surface,
        }
        if self.capsule_id is not None:
            result["capsule_id"] = self.capsule_id
        return result

    def metadata(self) -> dict[str, object]:
        self.validate()
        return {
            "manifest_sha256": self.manifest_sha256,
            "postimage_sha256": self.postimage_sha256,
            "preimage_sha256": self.preimage_sha256,
            "receipt_id": self.receipt_id,
            "scope": self.scope,
            "target_adapter": self.target_adapter,
            "target_path": self.target_path,
            "target_surface": self.target_surface,
        }

    def validate(self, *, expected_id: str | None = None) -> None:
        if expected_id is not None and self.receipt_id != expected_id:
            raise UndoError("conflict")
        for text in (self.target_adapter, self.target_surface, self.scope, self.created_by):
            _safe_text(text)
        _safe_target_path(self.target_path)
        for digest in (self.preimage_sha256, self.postimage_sha256,
                       self.postimage_region_sha256, self.manifest_sha256):
            if not is_sha256_ref(digest):
                raise UndoError("conflict")
        if self.capsule_id is not None and not is_sha256_ref(self.capsule_id):
            raise UndoError("conflict")
        if sha256_text(_safe_preimage(self.preimage_text)) != self.preimage_sha256:
            raise UndoError("conflict")
        if self.created_by != "canon export --apply-region" or self.does_not_prove != _DOES_NOT_PROVE:
            raise UndoError("conflict")
        if not valid_receipt_id(self.receipt_id) or self.receipt_id != self.deterministic_id():
            raise UndoError("conflict")

    def deterministic_id(self) -> str:
        return _receipt_id(
            self.target_path, self.target_adapter, self.target_surface, self.scope,
            self.preimage_sha256, self.postimage_sha256, self.postimage_region_sha256,
            self.manifest_sha256, _json_object(self.source_state), self.capsule_id,
        )


def valid_receipt_id(value: object) -> bool:
    return type(value) is str and _RECEIPT_RE.fullmatch(value) is not None


def _receipt_id(*fields: object) -> str:
    keys = ("target_path", "target_adapter", "target_surface", "scope", "preimage_sha256",
            "postimage_sha256", "postimage_region_sha256", "manifest_sha256", "source_state", "capsule_id")
    return "undo-" + canonical_sha256(dict(zip(keys, fields))).removeprefix("sha256:")


def _json_object(value: object) -> dict[str, object]:
    if type(value) is not dict:
        raise UndoError("conflict")
    try:
        return json.loads(canonical_json_text(value))
    except Exception:
        raise UndoError("conflict") from None


def _does_not_prove(value: object) -> tuple[str, ...]:
    if type(value) is not list:
        raise UndoError("conflict")
    return tuple(_safe_text(item) for item in value)


def _safe_target_path(value: object) -> str:
    text = _safe_text(value)
    parts = text.replace("\\", "/").split("/")
    if text.startswith("/") or ":" in text or any(part in ("", ".", "..") for part in parts):
        raise UndoError("conflict")
    return text


def _safe_text(value: object) -> str:
    if type(value) is not str or value == "" or "\0" in value or any(ord(ch) < 32 for ch in value):
        raise UndoError("conflict")
    return value


def _safe_preimage(value: object) -> str:
    if type(value) is not str or "\0" in value:
        raise UndoError("conflict")
    return value


__all__ = ["UNDO_RECEIPT_SCHEMA", "UndoApplyResult", "UndoError", "UndoReceipt", "valid_receipt_id"]
