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

import hashlib
import json
import time

from . import compaction
from .endpoint_registry import (
    make_authorized_endpoint_proposer,
    make_endpoint_proposer,
)
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
                 summarize=None, credential_bindings=None):
        self.endpoint = endpoint
        self.system = system or DEFAULT_AGENT_SYSTEM
        if proposer is not None:
            self._proposer = proposer
        elif credential_bindings is not None:
            self._proposer = make_authorized_endpoint_proposer(
                endpoint, model=model, base_url=base_url, extract=False,
                ledger=ledger, credential_bindings=credential_bindings)
        else:
            self._proposer = make_endpoint_proposer(
                endpoint, model=model, base_url=base_url, extract=False,
                ledger=ledger)
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


def _workspace_pre(root: str, enabled: bool, ledger):
    if not enabled:
        return None
    from .workspace_state import workspace_snapshot
    snapshot = workspace_snapshot(root)
    ledger.append("workspace_pre", json.dumps(snapshot, sort_keys=True))
    return snapshot


def _workspace_post(out: dict, root: str, before: dict | None, ledger) -> None:
    if before is None:
        return
    from .workspace_state import workspace_snapshot
    after = workspace_snapshot(root)
    ledger.append("workspace_post", json.dumps(after, sort_keys=True))
    out["workspace"] = {
        "pre": before, "post": after,
        "changed": before["workspace_sha256"] != after["workspace_sha256"]}
    out["checkpoint"] = ledger.checkpoint()
    out["verified"] = ledger.verify()


def _finalize_run(result, *, endpoint, agent, executor, receipt_dir,
                  duration, sign_key, pre_state, root, ledger) -> dict:
    out = {k: v for k, v in result.items() if k != "ledger"}
    out["endpoint"] = endpoint
    out["tool_authenticity"] = {
        "signed": True, "scheme": "HMAC-SHA256",
        "key_sha256": hashlib.sha256(sign_key).hexdigest(),
        "note": "each tool_result carries a sig; verify with the run-scoped "
                "key held out of band (never published here)"}
    out["last_compaction"] = agent.last_compaction
    out["duration_s"] = duration
    if receipt_dir and hasattr(executor, "receipt_chain_head"):
        out["tool_call_receipts"] = {
            "dir": receipt_dir,
            "count": executor._receipt_seq,
            "chain_head_sha256": executor.receipt_chain_head(),
            "schema": "flywheel.tool-call-receipt/v1",
        }
    from .behavioral_monitor import monitor_run
    out["behavioral_monitor"] = monitor_run(out)
    out["ttva_s"] = duration if result.get("tests_pass_trusted") is True else None
    _workspace_post(out, root, pre_state, ledger)
    from .provenance_trace import provenance_trace
    out["provenance"] = provenance_trace(
        ledger.entries, checkpoint=str(out.get("checkpoint", "")),
        author=f"model:{endpoint}")
    from .run_verdict import seal_verdict
    out["verdict"] = seal_verdict(ledger, result)     # re-derivable accept/reject
    out["ledger_jsonl"] = ledger.to_jsonl()           # so the run stays independently verifiable
    return out


def run_router_agent(goal: str, endpoint: str = "serve", *, root: str = ".",
                     allow_write: bool = False, allow_exec: bool = False,
                     allow_mcp: bool = False, external: "dict | None" = None,
                     max_steps: int = 6, test_cmd: "str | None" = None,
                     model: "str | None" = None, base_url: "str | None" = None,
                     max_tokens: int = 1024, temperature: float = 0.0, seed: int = 0,
                     compact_budget: int = 0, proposer=None, credential_bindings=None,
                     canaries: "list | None" = None, on_event=None,
                     receipt_dir: "str | None" = None) -> dict:
    """Run one gated agentic loop over a named or explicitly bound endpoint."""
    ledger = SessionLedger()
    agent = RouterAgent(
        endpoint, model=model, base_url=base_url, proposer=proposer,
        credential_bindings=credential_bindings, max_tokens=max_tokens,
        temperature=temperature, seed=seed, compact_budget=compact_budget)
    executor = ToolExecutor(
        root=root, external=external or {},
        gate=ToolGate(allow_write=allow_write, allow_exec=allow_exec,
                      allow_mcp=allow_mcp), receipt_dir=receipt_dir)
    pre_state = _workspace_pre(root, allow_write or allow_exec, ledger)
    from . import tool_receipts
    sign_key = tool_receipts.new_session_key()
    started = time.perf_counter()
    result = run_agent(
        agent, goal, executor, ledger, max_steps=max_steps, test_cmd=test_cmd,
        sign_key=sign_key, canaries=canaries, on_event=on_event)
    return _finalize_run(
        result, endpoint=endpoint, agent=agent, executor=executor,
        receipt_dir=receipt_dir, duration=round(time.perf_counter() - started, 3),
        sign_key=sign_key, pre_state=pre_state, root=root, ledger=ledger)
