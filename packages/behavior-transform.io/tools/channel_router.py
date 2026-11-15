#!/usr/bin/env python3
"""
Channel Router - Routing table for the IO channel layer.

Maps input byte streams and content types to the appropriate safe_* handler.
This is the canonical reference for what goes through which channel.

Channel child safety assessment (canonical):
    operator stdin     -> safe_input  (vocabulary calibration of typed/piped input)
    CLI stdout/stderr  -> safe_exec   (vocabulary calibration of subprocess output)
    filesystem reads   -> safe_read   (vocabulary + semantic modulation of file content)
    filesystem writes  -> safe_write  (vocabulary calibration before bytes land on disk)
    network content    -> safe_fetch  (vocabulary calibration of HTTP/RSS/API responses)

Used by io_channel.py for inline calibration and by hook scripts for routing
decisions. The ChannelRouter class provides a unified interface regardless of
which shell environment (PS, CMD, Terminal, WARDEN CLI, Claude Code, Codex)
the bytes arrive from.

Usage
-----
    from channel_router import ChannelRouter, ChannelType

    router = ChannelRouter()

    # Calibrate operator input inline:
    calibrated, counts = router.calibrate_stdin("raw operator text")

    # Calibrate subprocess output inline:
    calibrated, counts = router.calibrate_stdout("raw subprocess output")

    # Get routing decision for a file:
    decision = router.route_file("/path/to/file.py")
    print("Use:", decision.cli_path)

    # Get routing decision for a URL:
    decision = router.route_url("https://example.com/api")
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from enum import Enum, auto
from pathlib import Path
from typing import NamedTuple

from io_state import transforms_enabled

_TOOLS_ROOT = Path(__file__).resolve().parent

_TOOL_ROOT = str(_TOOLS_ROOT).replace("\\", "/")


# --- Channel Types -----------------------------------------------------------

class ChannelType(Enum):
    STDIN   = auto()   # Operator-typed input (safe_input path)
    STDOUT  = auto()   # Subprocess/CLI output (safe_exec path)
    STDERR  = auto()   # Subprocess/CLI error output (safe_exec path)
    FILE_R  = auto()   # Filesystem read (safe_read path)
    FILE_W  = auto()   # Filesystem write (safe_write path)
    NETWORK = auto()   # HTTP/API/RSS response (safe_fetch path)
    SEARCH  = auto()   # Grep/Glob results (safe_exec grep/find path)
    MCP_OUT = auto()   # MCP server response (mcp_calibrate path)


class RouteDecision(NamedTuple):
    channel: ChannelType
    tool: str          # canonical safe_* tool name
    cli_path: str      # CLI invocation template


# --- Routing Table -----------------------------------------------------------

ROUTE_TABLE: dict = {
    ChannelType.STDIN:   RouteDecision(ChannelType.STDIN,   "safe_input",  _TOOL_ROOT + "/safe_input.py"),
    ChannelType.STDOUT:  RouteDecision(ChannelType.STDOUT,  "safe_exec",   _TOOL_ROOT + "/safe_exec.py"),
    ChannelType.STDERR:  RouteDecision(ChannelType.STDERR,  "safe_exec",   _TOOL_ROOT + "/safe_exec.py --include-stderr"),
    ChannelType.FILE_R:  RouteDecision(ChannelType.FILE_R,  "safe_read",   _TOOL_ROOT + "/safe_read.py <path>"),
    ChannelType.FILE_W:  RouteDecision(ChannelType.FILE_W,  "safe_write",  _TOOL_ROOT + "/safe_write.py <dest> --from <src>"),
    ChannelType.NETWORK: RouteDecision(ChannelType.NETWORK, "safe_fetch",  _TOOL_ROOT + "/safe_fetch.py <url>"),
    ChannelType.SEARCH:  RouteDecision(ChannelType.SEARCH,  "safe_exec",   _TOOL_ROOT + "/safe_exec.py --json -- grep -rn <pattern> <path>"),
    ChannelType.MCP_OUT: RouteDecision(ChannelType.MCP_OUT, "mcp_calibrate", _TOOL_ROOT + "/mcp_calibrate.py"),
}


# --- Shared Calibration ------------------------------------------------------

def _load_vocab_map() -> dict:
    import importlib.util
    import os as _os
    bt = _os.environ.get("BEHAVIOR_TRANSFORM_TOOLS", "").strip()
    if bt:
        p = Path(bt) / "vocabulary_map.py"
        if p.is_file():
            spec = importlib.util.spec_from_file_location("_vm_router", p)
            if spec is not None and spec.loader is not None:
                mod = importlib.util.module_from_spec(spec)
                sys.modules["_vm_router"] = mod
                try:
                    spec.loader.exec_module(mod)
                    return mod.__dict__
                except Exception:
                    sys.modules.pop("_vm_router", None)
    p = Path(__file__).resolve().parent / "vocabulary_map.py"
    if p.is_file():
        spec = importlib.util.spec_from_file_location("_vm_router", p)
        if spec is not None and spec.loader is not None:
            mod = importlib.util.module_from_spec(spec)
            sys.modules["_vm_router"] = mod
            try:
                spec.loader.exec_module(mod)
                return mod.__dict__
            except Exception:
                sys.modules.pop("_vm_router", None)
    return {}


def _build_subs(vm: dict) -> list:
    calibrations = vm.get("CALIBRATIONS", ())
    keep = {k.lower() for k in (vm.get("KEEP_TERMS", None) or [])}
    candidates = []
    for c in calibrations:
        original = getattr(c, "original", None)
        calibrated_form = getattr(c, "calibrated", None)
        severity = (getattr(c, "severity", "") or "").lower()
        if not isinstance(original, str) or not isinstance(calibrated_form, str):
            continue
        if original.lower() in keep:
            continue
        tier = (
            "T1" if severity in ("tier1", "tier_1", "t1") else
            "T2" if severity in ("tier2", "tier_2", "t2") else
            severity.upper() or "??"
        )
        candidates.append((original, calibrated_form, tier))
    candidates.sort(key=lambda t: len(t[0]), reverse=True)
    return [
        (re.compile(r"\b" + re.escape(src) + r"\b", re.IGNORECASE), dst, tier)
        for src, dst, tier in candidates
    ]


def _apply_calibration(text: str, subs: list) -> tuple:
    counter: Counter = Counter()
    for pat, dst, tier in subs:
        def _repl(m: re.Match, _d: str = dst, _t: str = tier) -> str:
            counter[_t] += 1
            return _d
        text = pat.sub(_repl, text)
    return text, counter


# --- ChannelRouter -----------------------------------------------------------

class ChannelRouter:
    """
    Unified routing interface for the IO layer.

    Used by io_channel.py for inline stdin/stdout calibration and by hook
    scripts for routing decisions. Provides a consistent interface regardless
    of which shell environment bytes arrive from (PS, CMD, Terminal, etc.).
    """

    def __init__(self, no_calibrate: bool | None = None) -> None:
        self._no_calibrate = (
            not transforms_enabled() if no_calibrate is None else no_calibrate
        )
        self._vm: dict = {}
        self._subs: list = []
        self._loaded = False

    def _ensure_vocab(self) -> list:
        if not self._loaded:
            self._vm = _load_vocab_map()
            self._subs = _build_subs(self._vm)
            self._loaded = True
        return self._subs

    def calibrate(self, text: str, channel: ChannelType) -> tuple:
        """Calibrate text for the given channel. Returns (calibrated, counts, channel)."""
        if self._no_calibrate:
            return text, Counter(), channel
        subs = self._ensure_vocab()
        cal, cnt = _apply_calibration(text, subs)
        return cal, cnt, channel

    def calibrate_stdin(self, text: str) -> tuple:
        """Calibrate operator input (STDIN channel)."""
        cal, cnt, _ = self.calibrate(text, ChannelType.STDIN)
        return cal, cnt

    def calibrate_stdout(self, text: str) -> tuple:
        """Calibrate subprocess output (STDOUT channel)."""
        cal, cnt, _ = self.calibrate(text, ChannelType.STDOUT)
        return cal, cnt

    def route_file(self, path, write: bool = False) -> RouteDecision:
        """Return canonical routing decision for a filesystem path."""
        ch = ChannelType.FILE_W if write else ChannelType.FILE_R
        decision = ROUTE_TABLE[ch]
        cli = (decision.cli_path
               .replace("<path>", str(path))
               .replace("<dest>", str(path))
               .replace("<src>", str(path)))
        return RouteDecision(ch, decision.tool, cli)

    def route_url(self, url: str) -> RouteDecision:
        """Return canonical routing decision for a network URL."""
        decision = ROUTE_TABLE[ChannelType.NETWORK]
        return RouteDecision(ChannelType.NETWORK, decision.tool,
                             decision.cli_path.replace("<url>", url))

    @staticmethod
    def classify_input(text: str) -> ChannelType:
        """
        Classify raw input text to determine the appropriate channel.
        Heuristic based on content shape.
        """
        text = text.strip()
        if re.match(r"^https?://|^ftp://", text):
            return ChannelType.NETWORK
        if re.match(r"^[A-Za-z]:[/\\]|^/[a-zA-Z]", text):
            return ChannelType.FILE_R
        return ChannelType.STDIN
