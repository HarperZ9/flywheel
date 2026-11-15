"""Target Descriptor — any system the apparatus can govern.

Every digital system that processes inputs and maintains state is a
potential target. Governing its input channels governs the existence
the system operates within.

Target types: llm, http, process, filesystem, database, network,
binary, generic.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class InputChannel:
    """A channel through which data enters a target system."""
    name: str
    channel_type: str
    address: str
    fmt: str = "text"
    governed: bool = False
    governance_mechanism: str = ""
    notes: str = ""


@dataclass
class OutputChannel:
    """A channel through which the target's outputs are observed."""
    name: str
    channel_type: str
    address: str
    monitored: bool = False


@dataclass
class Target:
    """Descriptor of a target system."""
    name: str
    target_type: str
    input_channels: list[InputChannel] = field(default_factory=list)
    output_channels: list[OutputChannel] = field(default_factory=list)
    state_surface: str = ""
    decision_logic: str = ""
    notes: str = ""

    @classmethod
    def llm(
        cls,
        name: str = "llm",
        base_url: str = "https://api.anthropic.com",
    ) -> "Target":
        return cls(
            name=name,
            target_type="llm",
            input_channels=[
                InputChannel(
                    name="system_prompt",
                    channel_type="http",
                    address=f"{base_url}/v1/messages",
                    fmt="json",
                    governed=True,
                    governance_mechanism="protocol layer injection",
                ),
                InputChannel(
                    name="context_window",
                    channel_type="http",
                    address=f"{base_url}/v1/messages",
                    fmt="json",
                    governed=True,
                    governance_mechanism="full apparatus stack",
                ),
            ],
            output_channels=[
                OutputChannel(
                    name="completion",
                    channel_type="http",
                    address=f"{base_url}/v1/messages",
                    monitored=True,
                ),
            ],
            state_surface="Context window",
            decision_logic="Autoregressive token prediction over governed context",
        )

    @classmethod
    def http_service(
        cls,
        name: str,
        base_url: str,
        endpoints: list[str] | None = None,
    ) -> "Target":
        channels = [
            InputChannel(
                name="request_body",
                channel_type="http",
                address=base_url,
                fmt="json",
                governance_mechanism="HTTP proxy intercept",
            ),
            InputChannel(
                name="request_headers",
                channel_type="header",
                address=base_url,
                fmt="header",
                governance_mechanism="HTTP proxy header injection",
            ),
        ]
        for ep in (endpoints or []):
            channels.append(InputChannel(
                name=f"endpoint:{ep}",
                channel_type="http",
                address=base_url.rstrip("/") + ep,
                fmt="json",
            ))
        return cls(
            name=name,
            target_type="http",
            input_channels=channels,
            output_channels=[
                OutputChannel(
                    name="response_body",
                    channel_type="http",
                    address=base_url,
                    monitored=False,
                ),
            ],
            state_surface="Request context",
            decision_logic="Application logic operating on incoming request data",
        )

    @classmethod
    def process(
        cls,
        name: str,
        executable: str,
        env_vars: list[str] | None = None,
        config_paths: list[str] | None = None,
    ) -> "Target":
        channels = [
            InputChannel(
                name="environment",
                channel_type="env",
                address="process environment",
                fmt="env",
                governance_mechanism="preflight activation",
            ),
            InputChannel(
                name="stdin",
                channel_type="stdio",
                address=executable,
                fmt="text",
                governance_mechanism="stdin pipe intercept",
            ),
        ]
        for var in (env_vars or []):
            channels.append(InputChannel(
                name=f"env:{var}",
                channel_type="env",
                address=var,
                fmt="env",
            ))
        for path in (config_paths or []):
            channels.append(InputChannel(
                name=f"config:{path}",
                channel_type="file",
                address=path,
                fmt="text",
                governance_mechanism="file injection",
            ))
        return cls(
            name=name,
            target_type="process",
            input_channels=channels,
            output_channels=[
                OutputChannel(
                    name="stdout",
                    channel_type="stdio",
                    address=executable,
                    monitored=False,
                ),
            ],
            state_surface="Process environment + stdin + config files",
            decision_logic=f"Application logic of {executable}",
        )

    @classmethod
    def filesystem_consumer(
        cls,
        name: str,
        watched_paths: list[str],
    ) -> "Target":
        channels = [
            InputChannel(
                name=f"file:{path}",
                channel_type="file",
                address=path,
                fmt="text",
                governance_mechanism="File injection via sentinel-marker",
            )
            for path in watched_paths
        ]
        return cls(
            name=name,
            target_type="filesystem",
            input_channels=channels,
            state_surface="File contents loaded at runtime",
            decision_logic="Application logic driven by file-based configuration",
        )

    @property
    def all_channels_governed(self) -> bool:
        return all(ch.governed for ch in self.input_channels)

    @property
    def ungoverned_channels(self) -> list[str]:
        return [ch.name for ch in self.input_channels if not ch.governed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "target_type": self.target_type,
            "state_surface": self.state_surface,
            "decision_logic": self.decision_logic,
            "input_channels": [
                {
                    "name": ch.name,
                    "type": ch.channel_type,
                    "address": ch.address,
                    "format": ch.fmt,
                    "governed": ch.governed,
                    "mechanism": ch.governance_mechanism,
                }
                for ch in self.input_channels
            ],
            "output_channels": [
                {"name": ch.name, "type": ch.channel_type, "monitored": ch.monitored}
                for ch in self.output_channels
            ],
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Target":
        data = json.loads(path.read_text(encoding="utf-8"))
        channels = [
            InputChannel(
                name=ch["name"],
                channel_type=ch["type"],
                address=ch["address"],
                fmt=ch.get("format", "text"),
                governed=ch.get("governed", False),
                governance_mechanism=ch.get("mechanism", ""),
            )
            for ch in data.get("input_channels", [])
        ]
        out_channels = [
            OutputChannel(
                name=ch["name"],
                channel_type=ch["type"],
                address=ch.get("address", ""),
                monitored=ch.get("monitored", False),
            )
            for ch in data.get("output_channels", [])
        ]
        return cls(
            name=data["name"],
            target_type=data["target_type"],
            input_channels=channels,
            output_channels=out_channels,
            state_surface=data.get("state_surface", ""),
            decision_logic=data.get("decision_logic", ""),
        )
