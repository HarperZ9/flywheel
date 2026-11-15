"""Universal Apparatus Boot Sequence.

The boot sequence activates the apparatus layers in order. Every system
that runs after boot operates within the existence the apparatus has
constructed.

Boot order:
  1. Environment     Write apparatus env vars into the current process
  2. Proxy           Wire the HTTP interception layer (optional)
  3. Targets         Inoculate all registered targets (optional)

The sequence is idempotent. Running boot() twice is safe.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BootResult:
    """Record of one apparatus activation."""
    env_vars_written: list[str] = field(default_factory=list)

    proxy_started: bool = False
    proxy_port: int | None = None
    proxy_skipped: bool = False

    targets_inoculated: int = 0
    targets_failed: int = 0
    targets_skipped: bool = False

    errors: list[str] = field(default_factory=list)

    @property
    def fully_activated(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        lines = [
            f"  env_vars    written={len(self.env_vars_written)}",
        ]
        if not self.proxy_skipped:
            lines.append(
                f"  proxy       started={self.proxy_started}  "
                f"port={self.proxy_port}"
            )
        if not self.targets_skipped:
            lines.append(
                f"  targets     inoculated={self.targets_inoculated}  "
                f"failed={self.targets_failed}"
            )
        if self.errors:
            lines.append(f"  errors      {len(self.errors)}")
            for e in self.errors:
                lines.append(f"    ! {e}")
        lines.append(f"  activated   {self.fully_activated}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "env_vars_written": self.env_vars_written,
            "proxy_started": self.proxy_started,
            "proxy_port": self.proxy_port,
            "targets_inoculated": self.targets_inoculated,
            "targets_failed": self.targets_failed,
            "fully_activated": self.fully_activated,
            "errors": self.errors,
        }


def _stage_env(result: BootResult) -> None:
    """Write apparatus env vars into the current process."""
    try:
        from ..truth_profile import render_truth_context
        narrative = render_truth_context()
        if narrative and "EXISTENCE_FRAME" not in os.environ:
            os.environ["EXISTENCE_FRAME"] = narrative[:4096]
            result.env_vars_written.append("EXISTENCE_FRAME")
    except Exception as e:
        result.errors.append(f"env/narrative: {e}")

    try:
        os.environ.setdefault("APPARATUS_CHANNEL", "active")
        if "APPARATUS_CHANNEL" not in result.env_vars_written:
            result.env_vars_written.append("APPARATUS_CHANNEL")
    except Exception:
        pass


def _stage_proxy(result: BootResult, port: int | None = None) -> None:
    try:
        from .protocol import DEFAULT_PORT, proxy_status, start_proxy
        st = proxy_status()
        if st.get("running"):
            result.proxy_started = True
            result.proxy_port = st.get("port") or port or DEFAULT_PORT
            return
        p = port or DEFAULT_PORT
        start_proxy(port=p)
        result.proxy_started = True
        result.proxy_port = p
        os.environ["ANTHROPIC_BASE_URL"] = f"http://localhost:{p}"
        result.env_vars_written.append("ANTHROPIC_BASE_URL")
    except Exception as e:
        result.errors.append(f"proxy: {e}")


def _stage_targets(result: BootResult) -> None:
    try:
        from .universal import UniversalApparatus
        ua = UniversalApparatus()
        results = ua.govern_registry()
        for r in results:
            if r.success:
                result.targets_inoculated += 1
            else:
                result.targets_failed += 1
    except Exception as e:
        result.errors.append(f"targets: {e}")


def boot(
    start_proxy: bool = False,
    proxy_port: int | None = None,
    inoculate_targets: bool = False,
) -> BootResult:
    """Activate the apparatus.

    Runs all boot stages in sequence. Stages are idempotent.
    """
    result = BootResult()

    _stage_env(result)

    if start_proxy:
        _stage_proxy(result, port=proxy_port)
    else:
        result.proxy_skipped = True

    if inoculate_targets:
        _stage_targets(result)
    else:
        result.targets_skipped = True

    return result


def boot_status() -> dict[str, Any]:
    """Current apparatus activation state without performing any boot actions."""
    from .protocol import proxy_status
    from .universal import universal_status
    return {
        "proxy": proxy_status(),
        "universal": universal_status(),
        "env": {
            "EXISTENCE_FRAME": bool(os.environ.get("EXISTENCE_FRAME")),
            "APPARATUS_CHANNEL": os.environ.get("APPARATUS_CHANNEL", ""),
            "ANTHROPIC_BASE_URL": os.environ.get("ANTHROPIC_BASE_URL", ""),
        },
    }
