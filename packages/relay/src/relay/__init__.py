"""relay — a zero-dep, accountable coding agent that runs on any model endpoint.

Reaches local models (a served 14B/32B, or Ollama) and online providers (codex /
claude / gemini / deepseek, via your own keys, subscription CLI, or a gateway),
fails over across them, and runs a gated agentic loop whose every step is written
to a hash-chained, re-verifiable session ledger. No dependencies; legitimate
credentials only (nothing forged, harvested, or metered around).
"""
from .endpoints import build_endpoints
from .local_agent import (
    BackendError,
    LocalAgent,
    OllamaBackend,
    ServeBackend,
    available_backends,
    health_report,
)
from .local_loop import run_agent
from .local_session import SessionLedger
from .local_tools import ToolExecutor, ToolGate

__version__ = "0.7.0"

__all__ = [
    "LocalAgent", "available_backends", "health_report", "BackendError",
    "ServeBackend", "OllamaBackend", "build_endpoints",
    "run_agent", "SessionLedger", "ToolExecutor", "ToolGate",
    "__version__",
]
