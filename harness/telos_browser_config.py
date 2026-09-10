"""Immutable, explicit configuration for one existing Telos browser target."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import re
from urllib.parse import urlsplit

from .evidence_json import canonical_sha256, strict_load_json

SCHEMA = "flywheel.telos-browser-config/v1"
MAX_CONFIG_BYTES = 16_384
MAX_MODULE_BYTES = 262_144
# Telos b53daedf cdp.mjs has no imports. Permit only its reviewed LF/CRLF bytes.
SUPPORTED_CDP_SHA256 = "d2d43363842b3f84e4f4562c6f7d74c1ff0d98054c456c172d9a0e70db9b1413"
_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z", re.ASCII)


class ConfigError(ValueError):
    """Fixed, content-free configuration failure."""


def canonical_origin(value: object) -> str:
    try:
        if not isinstance(value, str) or len(value) > 2048:
            raise ValueError
        if any(ord(c) < 33 or ord(c) > 126 for c in value) or "\\" in value:
            raise ValueError
        parts = urlsplit(value)
        if (parts.scheme not in ("http", "https") or not parts.hostname
                or parts.username is not None or parts.password is not None):
            raise ValueError
        port = parts.port
        host = parts.hostname.lower()
        if ":" in host:
            host = f"[{host}]"
        suffix = "" if port is None or port == (443 if parts.scheme == "https" else 80) else f":{port}"
        return f"{parts.scheme}://{host}{suffix}"
    except (ValueError, UnicodeError):
        raise ConfigError("invalid_browser_origin") from None


def _absolute_file(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ConfigError("invalid_runtime_path")
    if any(ord(c) < 32 for c in value):
        raise ConfigError("invalid_runtime_path")
    path = Path(value)
    if not path.is_absolute() or not path.is_file():
        raise ConfigError("runtime_unavailable")
    return str(path.resolve())


@dataclass(frozen=True)
class BrowserConfig:
    schema: str
    node_path: str
    cdp_module: str
    cdp_sha256: str
    port: int
    browser_instance: str
    target_id: str
    allowed_origin: str

    @classmethod
    def from_dict(cls, raw: dict) -> BrowserConfig:
        if not isinstance(raw, dict) or set(raw) != set(cls.__dataclass_fields__):
            raise ConfigError("invalid_browser_config")
        if raw["schema"] != SCHEMA:
            raise ConfigError("invalid_browser_config")
        port = raw["port"]
        if type(port) is not int or not 1 <= port <= 65535:
            raise ConfigError("invalid_debugger_port")
        target, instance = raw["target_id"], raw["browser_instance"]
        if not isinstance(target, str) or not _ID.fullmatch(target):
            raise ConfigError("invalid_target_identity")
        prefix = "/devtools/browser/"
        if (not isinstance(instance, str) or not instance.startswith(prefix)
                or not _ID.fullmatch(instance[len(prefix):])):
            raise ConfigError("invalid_browser_identity")
        digest = raw["cdp_sha256"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ConfigError("invalid_runtime_digest")
        origin = canonical_origin(raw["allowed_origin"])
        if raw["allowed_origin"] != origin:
            raise ConfigError("origin_must_be_canonical")
        return cls(SCHEMA, _absolute_file(raw["node_path"]),
                   _absolute_file(raw["cdp_module"]), digest, port, instance, target, origin)

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def binding_sha256(self) -> str:
        return canonical_sha256(self.as_dict())

    def verify_runtime(self) -> None:
        try:
            _absolute_file(self.node_path)
            with Path(self.cdp_module).open("rb") as stream:
                data = stream.read(MAX_MODULE_BYTES + 1)
            if len(data) > MAX_MODULE_BYTES or hashlib.sha256(data).hexdigest() != self.cdp_sha256:
                raise ConfigError("runtime_changed")
            if hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest() != SUPPORTED_CDP_SHA256:
                raise ConfigError("runtime_not_supported")
        except OSError:
            raise ConfigError("runtime_unavailable") from None


def load_config(path) -> BrowserConfig:
    try:
        with Path(_absolute_file(path)).open("rb") as stream:
            data = stream.read(MAX_CONFIG_BYTES + 1)
        if len(data) > MAX_CONFIG_BYTES:
            raise ConfigError("browser_config_too_large")
        config = BrowserConfig.from_dict(strict_load_json(data))
        config.verify_runtime()
        return config
    except (OSError, TypeError, ValueError):
        raise ConfigError("browser_config_unavailable") from None
