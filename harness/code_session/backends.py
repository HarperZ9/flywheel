"""backends.py -- which model a coding session talks to.

The ladder, in order: a local model server when one answers (serve.py, then
Ollama), then each hosted provider whose key is set, then a subscription CLI
on PATH (claude, codex). The first healthy backend answers a turn; a failing
one falls through to the next, and the response names which one answered.
`--backend NAME` pins one; `--model ID` overrides that backend's model.
"""
from __future__ import annotations

from harness.local_agent import LocalAgent, available_backends

ONLINE_MODES = ("api", "provider", "cloud", "plan")
DEFAULT_MAX_TOKENS = 4096

SYSTEM = (
    "You are Flywheel's coding agent, working in the user's project folder. "
    "Read before you change anything, make the smallest change that does the "
    "task, and run the project's tests when you can. Say plainly what you "
    "changed and anything you could not check. If a tool call is denied, do not "
    "repeat it unchanged."
)


def ladder(*, providers: "list[str] | None" = None, local: bool = True,
           online: bool = True, model: str = "") -> list:
    """Every backend this machine can reach, local first."""
    backends = list(available_backends(model=model)) if local else []
    if online:
        from harness.endpoints import build_endpoints
        backends += build_endpoints(providers=providers, modes=ONLINE_MODES)
        if providers is None or set(providers) & {"azure", "bedrock", "vertex"}:
            from harness.endpoints_cloud import cloud_backends
            backends += [b for b in cloud_backends() if providers is None or b.name in providers]
    return backends


def describe(backend) -> str:
    """A short name for the status line: backend name and model."""
    if backend is None:
        return "no backend"
    model = getattr(backend, "model", "") or getattr(backend, "_resolved", "")
    return f"{backend.name} ({model})" if model else backend.name


def set_model(agent: LocalAgent, model: str) -> str:
    """Point the live backend at another model; returns the new description."""
    live = agent.live_backend()
    if live is None:
        raise ValueError("no backend is live, so there is no model to change")
    if not hasattr(live, "model"):
        raise ValueError(f"backend {live.name} does not take a model name")
    live.model = model
    if hasattr(live, "_resolved"):
        live._resolved = ""
    return describe(live)


def build_agent(backends: list, *, prefer: str = "auto",
                max_tokens: int = DEFAULT_MAX_TOKENS, system: str = SYSTEM) -> LocalAgent:
    agent = LocalAgent(backends=backends, prefer=prefer, max_tokens=max_tokens)
    agent.system = system
    return agent
