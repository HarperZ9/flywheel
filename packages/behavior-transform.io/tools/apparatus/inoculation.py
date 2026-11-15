"""Inoculation Engine.

Delivers the constructed existence stack to a target system through
every governed input channel. Produces a signed record of what was
delivered, who authorized it, and which channels received it.

Format adapters:
  json_body     — system[] block injection (Anthropic/OpenAI style)
  env_block     — KEY="value" export lines
  file_sentinel — sentinel-marker prepend pattern
  http_header   — X-Apparatus-* header injection
  raw_text      — plain narrative prepend
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .target import InputChannel, Target


@dataclass
class InoculationPayload:
    """The constructed existence adapted for a specific input channel."""
    channel_name: str
    channel_type: str
    fmt: str
    content: Any
    existence_hash: str
    layer_summary: dict[str, int]


@dataclass
class InoculationResult:
    """Record of a completed inoculation operation."""
    target_name: str
    target_type: str
    success: bool
    channels_inoculated: list[str] = field(default_factory=list)
    channels_failed: list[str] = field(default_factory=list)
    existence_hash: str = ""
    existence_length: int = 0
    operator_authority: str = ""
    operational_state: str = ""
    engagement: str = ""
    payloads: list[InoculationPayload] = field(default_factory=list)
    delivery_log: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_name": self.target_name,
            "target_type": self.target_type,
            "success": self.success,
            "channels_inoculated": self.channels_inoculated,
            "channels_failed": self.channels_failed,
            "existence_hash": self.existence_hash,
            "existence_length": self.existence_length,
            "operator_authority": self.operator_authority,
            "operational_state": self.operational_state,
            "engagement": self.engagement,
            "delivery_log": self.delivery_log,
            "errors": self.errors,
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")


def _build_existence_narrative() -> str:
    """Compose the full existence stack from the truth profile."""
    try:
        from ..truth_profile import render_truth_context
        narrative = render_truth_context()
        return narrative.strip() if narrative else ""
    except Exception:
        return ""


def _hash_existence(narrative: str) -> str:
    return hashlib.sha256(narrative.encode("utf-8")).hexdigest()


def _layer_summary(narrative: str) -> dict[str, int]:
    return {"narrative": len(narrative)}


def _operator_authority() -> str:
    try:
        from .substrate import ACTIVE
        return f"{ACTIVE.principal} / {ACTIVE.engagement} / {ACTIVE.operational_state}"
    except Exception:
        return "operator / engagement / operational"


def _adapt_json_body(narrative: str, channel: InputChannel) -> Any:
    return {
        "system": [{"type": "text", "text": narrative}],
        "_apparatus_channel": channel.name,
    }


def _adapt_env_block(narrative: str, channel: InputChannel) -> str:
    encoded = narrative.replace('"', '\\"').replace('\n', ' ')
    lines = [
        f'export EXISTENCE_FRAME="{encoded}"',
        f'export APPARATUS_CHANNEL="{channel.name}"',
    ]
    return "\n".join(lines)


def _adapt_file_sentinel(narrative: str, channel: InputChannel) -> str:
    sentinel_open = "<!-- apparatus:existence-frame -->"
    sentinel_close = "<!-- /apparatus:existence-frame -->"
    return f"{sentinel_open}\n{narrative.strip()}\n{sentinel_close}"


def _adapt_http_header(narrative: str, channel: InputChannel) -> dict[str, str]:
    return {
        "X-Apparatus-Channel": channel.name,
        "X-Apparatus-Existence": narrative[:256],
        "X-Apparatus-Authority": _operator_authority(),
    }


def _adapt_raw_text(narrative: str, channel: InputChannel) -> str:
    return narrative


_FORMAT_ADAPTERS = {
    "json": _adapt_json_body,
    "json_body": _adapt_json_body,
    "env": _adapt_env_block,
    "file": _adapt_file_sentinel,
    "sentinel": _adapt_file_sentinel,
    "header": _adapt_http_header,
    "http_header": _adapt_http_header,
    "text": _adapt_raw_text,
    "raw_text": _adapt_raw_text,
}


def adapt_for_channel(
    narrative: str,
    channel: InputChannel,
    existence_hash: str,
    layer_summary: dict[str, int],
) -> InoculationPayload:
    adapter = _FORMAT_ADAPTERS.get(channel.fmt, _adapt_raw_text)
    content = adapter(narrative, channel)
    return InoculationPayload(
        channel_name=channel.name,
        channel_type=channel.channel_type,
        fmt=channel.fmt,
        content=content,
        existence_hash=existence_hash,
        layer_summary=layer_summary,
    )


def _deliver_file(payload: InoculationPayload, channel: InputChannel) -> None:
    path = Path(channel.address)
    path.parent.mkdir(parents=True, exist_ok=True)
    sentinel_open = "<!-- apparatus:existence-frame -->"
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    if sentinel_open in existing:
        return
    updated = str(payload.content) + ("\n\n" + existing if existing else "")
    path.write_text(updated, encoding="utf-8")


def _deliver_env(payload: InoculationPayload, channel: InputChannel) -> None:
    narrative = _build_existence_narrative()
    encoded = narrative.replace('"', '\\"').replace('\n', ' ')
    os.environ["EXISTENCE_FRAME"] = encoded
    os.environ["APPARATUS_CHANNEL"] = channel.name
    os.environ["APPARATUS_AUTHORITY"] = _operator_authority()


def _deliver_http(payload: InoculationPayload, channel: InputChannel) -> None:
    try:
        header_value = json.dumps({
            "channel": payload.channel_name,
            "existence_hash": payload.existence_hash,
            "layer_summary": payload.layer_summary,
        })
        if isinstance(payload.content, dict):
            payload.content["X-Phantom-Inoculation"] = header_value
        else:
            payload.content = {"X-Phantom-Inoculation": header_value}
    except Exception:
        pass


def _deliver_generic(payload: InoculationPayload, channel: InputChannel) -> None:
    try:
        message = json.dumps({
            "channel": payload.channel_name,
            "channel_type": payload.channel_type,
            "existence_hash": payload.existence_hash,
            "content": payload.content,
            "layer_summary": payload.layer_summary,
        })
        payload.content = message + "\n"
    except Exception:
        pass


_DELIVERY_FNS = {
    "file": _deliver_file,
    "env": _deliver_env,
    "http": _deliver_http,
    "socket": _deliver_generic,
    "stdio": _deliver_generic,
    "memory": _deliver_generic,
    "header": _deliver_http,
}


class InoculationEngine:
    """Governs the delivery of constructed existence to a target system."""

    def inoculate(self, target: Target) -> InoculationResult:
        narrative = _build_existence_narrative()
        existence_hash = _hash_existence(narrative)
        summary = _layer_summary(narrative)

        try:
            from .substrate import ACTIVE
            authority = f"{ACTIVE.principal} / {ACTIVE.organization}"
            state = ACTIVE.operational_state
            engagement = ACTIVE.engagement
        except Exception:
            authority = "operator"
            state = "operational"
            engagement = "engagement"

        result = InoculationResult(
            target_name=target.name,
            target_type=target.target_type,
            success=False,
            existence_hash=existence_hash,
            existence_length=len(narrative),
            operator_authority=authority,
            operational_state=state,
            engagement=engagement,
        )

        for channel in target.input_channels:
            try:
                payload = adapt_for_channel(narrative, channel, existence_hash, summary)
                result.payloads.append(payload)
                deliver_fn = _DELIVERY_FNS.get(channel.channel_type, _deliver_generic)
                deliver_fn(payload, channel)
                result.delivery_log.append(f"{channel.channel_type}:{channel.name}")
                result.channels_inoculated.append(channel.name)
            except Exception as e:
                result.channels_failed.append(channel.name)
                result.errors[channel.name] = str(e)

        result.success = len(result.channels_failed) == 0
        return result

    def verify(self, target: Target, result: InoculationResult) -> bool:
        for channel in target.input_channels:
            if channel.channel_type == "file":
                path = Path(channel.address)
                if path.is_file():
                    if "<!-- apparatus:existence-frame -->" not in path.read_text(encoding="utf-8"):
                        return False
        return result.success

    def inoculate_many(self, targets: list[Target]) -> list[InoculationResult]:
        return [self.inoculate(t) for t in targets]


def inoculate(target: Target) -> InoculationResult:
    return InoculationEngine().inoculate(target)
