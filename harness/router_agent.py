"""router_agent.py — run the agentic tool loop over ANY routed provider.

Flywheel had two capabilities that never met: a witnessed, tool-using agent loop
(local_loop.run_agent) that only drove LOCAL backends, and a universal router
(endpoint_registry / gateway) that reached 20 providers but only single-shot.
RouterAgent is the seam between them. It adapts any endpoint in the roster into
the small `.system` + `.send()` shape run_agent drives, so the multi-step tool
loop (read/edit/run under the gate, test-repair, witnessed in a hash-chained
ledger) now runs over hosted OpenAI/Anthropic/Gemini/DeepSeek and local
serve/ollama alike, not just the local tier.

The provider only proposes. Tools stay gated (default-deny write/exec) and every
turn plus tool call is appended to a SessionLedger, so an agent run over a hosted
model is as re-verifiable as one over the local model. Context is bounded by the
same opt-in compaction as the local agent. Zero dependencies.
"""
from __future__ import annotations

from . import compaction
from .endpoint_registry import make_endpoint_proposer
from .local_loop import run_agent
from .local_session import SessionLedger
from .local_tools import ToolExecutor, ToolGate

DEFAULT_AGENT_SYSTEM = (
    "You are a coding agent working in a sandboxed repository. Use the tools to "
    "inspect and change files, then give a final answer. Be concise and correct."
)


def _flatten(history: list) -> str:
    return "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in history)


class RouterAgent:
    """Adapt a routed endpoint into the .system + .send() shape run_agent drives.

    Stateful: it keeps its own conversation history (the proposer is stateless per
    call) and flattens it into each prompt, matching how serve.py is prompted. Pass
    `proposer=` to inject a stub in tests; otherwise the endpoint name builds a
    verified proposer via make_endpoint_proposer with extract=False, so the
    TOOL-line protocol is not stripped as if it were code."""

    def __init__(self, endpoint: str = "serve", *, model: "str | None" = None,
                 base_url: "str | None" = None, system: str = "", ledger=None,
                 proposer=None, max_tokens: int = 1024, temperature: float = 0.0,
                 seed: int = 0, compact_budget: int = 0, compact_keep_recent: int = 6,
                 summarize=None):
        self.endpoint = endpoint
        self.system = system or DEFAULT_AGENT_SYSTEM
        self._proposer = proposer if proposer is not None else make_endpoint_proposer(
            endpoint, model=model, base_url=base_url, extract=False, ledger=ledger)
        self.history: list = []
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.seed = seed
        self.compact_budget = compact_budget
        self.compact_keep_recent = compact_keep_recent
        self.summarize = summarize
        self.last_compaction = None

    def _maybe_compact(self) -> None:
        if not self.compact_budget or len(self.history) <= 1:
            return
        res = compaction.compact(
            self.history, token_budget=self.compact_budget,
            keep_recent=self.compact_keep_recent,
            summarize=self.summarize or compaction.lexrank_summary)
        if res.compacted:
            self.history = res.messages
            self.last_compaction = res.receipt

    def send(self, message: str) -> dict:
        self.history.append({"role": "user", "content": message})
        self._maybe_compact()
        out = self._proposer.generate(
            _flatten(self.history), seed=self.seed, temperature=self.temperature,
            max_new_tokens=self.max_tokens, system=self.system)
        text = out.text if isinstance(out.text, str) else str(out.text)
        self.history.append({"role": "assistant", "content": text})
        return {"content": [{"text": text}], "backend": getattr(out, "model_ref", self.endpoint)}


def run_router_agent(goal: str, endpoint: str = "serve", *, root: str = ".",
                     allow_write: bool = False, allow_exec: bool = False,
                     allow_mcp: bool = False, external: "dict | None" = None,
                     max_steps: int = 6, test_cmd: "str | None" = None,
                     model: "str | None" = None, base_url: "str | None" = None,
                     max_tokens: int = 1024, temperature: float = 0.0, seed: int = 0,
                     compact_budget: int = 0, proposer=None,
                     canaries: "list | None" = None, on_event=None) -> dict:
    """Run the gated agentic loop over `endpoint` to complete `goal`. Returns a
    JSON-able dict: the final answer, step count, the witnessed ledger checkpoint
    and verify verdict, the endpoint used, and any compaction receipt. The ledger
    object itself is dropped (checkpoint + verified are the re-checkable summary)."""
    ledger = SessionLedger()
    agent = RouterAgent(endpoint, model=model, base_url=base_url, proposer=proposer,
                        max_tokens=max_tokens, temperature=temperature, seed=seed,
                        compact_budget=compact_budget)
    executor = ToolExecutor(root=root, external=external or {},
                            gate=ToolGate(allow_write=allow_write, allow_exec=allow_exec,
                                          allow_mcp=allow_mcp))
    import time as _time
    import json as _json
    pre_state = None
    if allow_write or allow_exec:
        # any state-mutating capability (write OR a shell command that
        # redirects) can change the tree: pin the pre-state so 'what changed'
        # is a checkable statement, and a revert has something to prove against.
        # Chain it into the ledger so the workspace claim is inside the
        # tamper-evident record, not loose JSON beside it.
        from .workspace_state import workspace_snapshot
        pre_state = workspace_snapshot(root)
        ledger.append("workspace_pre",
                      _json.dumps(pre_state, sort_keys=True))
    # per-tool authenticity: mint a run-scoped HMAC key so every tool_result
    # carries a sig a key holder can re-verify. The secret key never enters
    # the run doc; only a commitment (its sha256) does.
    from . import tool_receipts
    import hashlib as _hl
    sign_key = tool_receipts.new_session_key()
    t0 = _time.perf_counter()
    result = run_agent(agent, goal, executor, ledger, max_steps=max_steps,
                       test_cmd=test_cmd, sign_key=sign_key,
                       canaries=canaries, on_event=on_event)
    duration = round(_time.perf_counter() - t0, 3)
    out = {k: v for k, v in result.items() if k != "ledger"}
    out["endpoint"] = endpoint
    # the authenticity commitment: signed true + the key's sha256 (a
    # commitment, never the secret) so a key holder can re-verify each sig
    out["tool_authenticity"] = {
        "signed": True, "scheme": "HMAC-SHA256",
        "key_sha256": _hl.sha256(sign_key).hexdigest(),
        "note": "each tool_result carries a sig; verify with the run-scoped "
                "key held out of band (never published here)"}
    out["last_compaction"] = agent.last_compaction
    out["duration_s"] = duration
    # behavioural deception monitor: flag a run whose final answer claims more
    # than its receipts show. It FLAGS, never accepts, and sits beside the
    # accept path (the oracle still decides).
    from .behavioral_monitor import monitor_run
    out["behavioral_monitor"] = monitor_run(out)
    # Time-to-verified-acceptance: the north-star metric (METR: felt speed
    # is inadmissible). Only a TRUSTED green run earns a TTVA; everything
    # else is an honest null.
    out["ttva_s"] = duration if result.get("tests_pass_trusted") is True else None
    if pre_state is not None:
        from .workspace_state import workspace_snapshot
        post_state = workspace_snapshot(root)
        ledger.append("workspace_post",
                      _json.dumps(post_state, sort_keys=True))
        out["workspace"] = {
            "pre": pre_state, "post": post_state,
            "changed": pre_state["workspace_sha256"]
                       != post_state["workspace_sha256"]}
        # the post snapshot advanced the chain: re-checkpoint so the run's
        # checkpoint/verified cover the workspace claim, not a stale subset
        out["checkpoint"] = ledger.checkpoint()
        out["verified"] = ledger.verify()
    # Line-level provenance in the Agent-Trace shape, bound to the run.
    # Computed AFTER the workspace post-snapshot so the conversation hash it
    # binds IS the run's final checkpoint; binding the pre-workspace
    # checkpoint left two receipts that disagreed on every writing run.
    from .provenance_trace import provenance_trace
    out["provenance"] = provenance_trace(
        ledger.entries, checkpoint=str(out.get("checkpoint", "")),
        author=f"model:{endpoint}")
    return out
