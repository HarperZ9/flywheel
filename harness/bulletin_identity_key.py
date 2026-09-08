"""Ed25519 JWK parsing and generation for Bulletin identity setup."""
from __future__ import annotations

from dataclasses import dataclass
import base64
from pathlib import Path

from .bulletin_identity_contract import (
    BULLETIN_CREDENTIAL_NAME,
    DEFAULT_HANDLE,
    IDENTITY_SCHEMA,
    MAX_KEY_BYTES,
    BulletinIdentityError,
)
from .bulletin_signed_transport import (
    _parse_key,
    BulletinSignedTransportError,
)
from .evidence_json import canonical_bytes, strict_load_json


@dataclass(frozen=True, repr=False)
class BulletinIdentity:
    credential_name: str
    thumbprint: str
    raw_json: str
    public_jwk: dict[str, str]
    _signing_key: object

    def signer(self) -> dict[str, object]:
        return {"thumbprint": self.thumbprint, "key": self._signing_key}

    def public_summary(self, *, handle: str = DEFAULT_HANDLE) -> dict:
        return {
            "schema": IDENTITY_SCHEMA,
            "credential_name": self.credential_name,
            "handle": normalize_handle(handle),
            "thumbprint": self.thumbprint,
            "key": {"kind": "ed25519-jwk", "signing_pair": "valid",
                    "public_key": "verified"},
        }


def load_identity_file(path: str | Path) -> BulletinIdentity:
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_KEY_BYTES + 1)
    except OSError:
        raise BulletinIdentityError("KEY_FILE_UNAVAILABLE") from None
    if len(raw) > MAX_KEY_BYTES:
        raise BulletinIdentityError("KEY_FILE_TOO_LARGE")
    return parse_identity_json(raw, invalid_code="KEY_FILE_INVALID")


def parse_identity_json(
        raw: bytes | str, *, invalid_code: str = "KEY_FILE_INVALID") -> BulletinIdentity:
    try:
        value = strict_load_json(raw, max_bytes=MAX_KEY_BYTES, max_depth=8)
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise BulletinIdentityError(invalid_code) from None
    if set(value) != {"public", "private"}:
        raise BulletinIdentityError(invalid_code)
    public = _public_jwk(value.get("public"), invalid_code)
    private = _private_jwk(value.get("private"), public, invalid_code)
    record = {"public": public, "private": private}
    raw_json = canonical_bytes(record).decode("utf-8")
    try:
        parsed = _parse_key(raw_json)
    except BulletinSignedTransportError as exc:
        code = "SIGNING_UNAVAILABLE" if exc.code == "SIGNING_UNAVAILABLE" else invalid_code
        raise BulletinIdentityError(code) from None
    return BulletinIdentity(
        credential_name=BULLETIN_CREDENTIAL_NAME,
        thumbprint=str(parsed["thumbprint"]),
        raw_json=raw_json,
        public_jwk=public,
        _signing_key=parsed["key"],
    )


def generate_identity_json() -> str:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ImportError:
        raise BulletinIdentityError("SIGNING_UNAVAILABLE") from None
    key = ed25519.Ed25519PrivateKey.generate()
    secret = key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    public_jwk = {"kty": "OKP", "crv": "Ed25519", "x": _b64u(public)}
    private_jwk = {**public_jwk, "d": _b64u(secret)}
    return canonical_bytes({"public": public_jwk, "private": private_jwk}).decode("utf-8")


def normalize_handle(handle: str) -> str:
    if not isinstance(handle, str):
        raise BulletinIdentityError("HANDLE_INVALID")
    cleaned = _strip_invisible(handle).strip()
    if not cleaned or len(cleaned) > 40:
        raise BulletinIdentityError("HANDLE_INVALID")
    return cleaned


def _public_jwk(value: object, code: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"kty", "crv", "x"}:
        raise BulletinIdentityError(code)
    if value.get("kty") != "OKP" or value.get("crv") != "Ed25519":
        raise BulletinIdentityError(code)
    if not isinstance(value.get("x"), str) or not value["x"]:
        raise BulletinIdentityError(code)
    return {"kty": "OKP", "crv": "Ed25519", "x": value["x"]}


def _private_jwk(value: object, public: dict[str, str], code: str) -> dict[str, str]:
    allowed = {"kty", "crv", "x", "d"}
    if not isinstance(value, dict) or not {"kty", "crv", "d"}.issubset(value):
        raise BulletinIdentityError(code)
    if not set(value).issubset(allowed):
        raise BulletinIdentityError(code)
    if value.get("kty") != "OKP" or value.get("crv") != "Ed25519":
        raise BulletinIdentityError(code)
    if not isinstance(value.get("d"), str) or not value["d"]:
        raise BulletinIdentityError(code)
    if "x" in value and value["x"] != public["x"]:
        raise BulletinIdentityError(code)
    out = {"kty": "OKP", "crv": "Ed25519", "d": value["d"]}
    if "x" in value:
        out["x"] = value["x"]
    return out


def _strip_invisible(value: str) -> str:
    out = []
    for ch in value:
        cp = ord(ch)
        invisible = (
            cp <= 0x1f
            or 0x7f <= cp <= 0x9f
            or 0x200b <= cp <= 0x200f
            or 0x202a <= cp <= 0x202e
            or 0x2066 <= cp <= 0x2069
            or cp == 0xfeff
        )
        if not invisible:
            out.append(ch)
    return "".join(out)


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")
