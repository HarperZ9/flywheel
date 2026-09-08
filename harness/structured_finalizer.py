"""Optional final-only structured output adapter for local Ollama runs."""
from __future__ import annotations

import base64
import hashlib
import json
import urllib.error
from typing import Any

from .local_agent import BackendError, OllamaBackend, _ollama_native_model
from .local_serving import generation_config
from .local_usage import ollama_native_usage
from .proposer import ProposerOutput, prompt_hash


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _history(agent, candidate_text: str) -> list[dict[str, str]]:
    rows = []
    for item in getattr(agent, "history", []) or []:
        if isinstance(item, dict) and isinstance(item.get("content"), str):
            rows.append({"role": str(item.get("role", "user")), "content": item["content"]})
    if not rows or rows[-1] != {"role": "assistant", "content": candidate_text}:
        rows.append({"role": "assistant", "content": candidate_text})
    return rows


def finalized_candidate_text(finalize_candidate, *, candidate_text: str,
                             candidate_state: str, step: int, ledger, agent,
                             system: str, goal: str, tests_pass=None, emit=None) -> str:
    if finalize_candidate is None:
        return candidate_text
    ctx = {"candidate_text": candidate_text, "candidate_state": candidate_state,
           "candidate_sha256": _sha(candidate_text), "step": step,
           "pre_finalizer_checkpoint": ledger.checkpoint(),
           "system": system, "goal": goal, "tests_pass": tests_pass,
           "history": _history(agent, candidate_text)}
    result = finalize_candidate(ctx)
    if not isinstance(result, dict):
        raise TypeError("finalize_candidate must return a dict")
    state = str(result.get("state", "returned"))
    selected = result.get("selected_text", "")
    selected = selected if isinstance(selected, str) else ""
    evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
    record = {"state": state, "candidate_state": candidate_state, "step": step,
              "candidate_sha256": ctx["candidate_sha256"], "selected_sha256": _sha(selected) if selected else "",
              "failure_class": str(result.get("failure_class", "")),
              "failure_detail": str(result.get("failure_detail", "")), "evidence": evidence}
    ledger.append("structured_finalization", json.dumps(record, sort_keys=True),
                  {"state": state, "candidate_state": candidate_state})
    if emit is not None:
        emit(type="structured_finalization", **record)
    return selected


class StructuredFinalizerFailure(RuntimeError):
    def __init__(self, state: str, detail: str = "", evidence: dict[str, Any] | None = None):
        super().__init__(detail or state)
        self.state, self.detail, self.evidence = state, detail or state, evidence or {}


class OllamaStructuredFinalProposer:
    def __init__(self, backend: OllamaBackend, *, schema: dict[str, Any] | None,
                 messages: list[dict[str, str]], model_ref: str,
                 retain_private_payloads: bool = False):
        self.backend, self.schema, self.messages, self.model_ref = backend, schema, messages, model_ref
        self.retain_private_payloads = retain_private_payloads
        self.last_request_body = b""
        self.last_evidence: dict[str, Any] = {}

    def request_body(self, *, seed: int, temperature: float,
                     max_new_tokens: int) -> tuple[str, bytes]:
        model = _ollama_native_model(self.backend._resolved or self.backend.model)
        body: dict[str, Any] = {"model": model, "messages": self.messages,
                                "stream": False}
        if self.schema is not None:
            body["format"] = self.schema
        body["options"] = generation_config(
            self.backend, max_new_tokens, temperature, seed)
        self.last_request_body = json.dumps(body).encode()
        return model, self.last_request_body

    def generate(self, prompt: str, *, seed: int, temperature: float,
                 max_new_tokens: int, system: str = "") -> ProposerOutput:
        model, body = self.request_body(
            seed=seed, temperature=temperature, max_new_tokens=max_new_tokens)
        try:
            status, obj = self.backend.transport("POST", f"{self.backend.base_url}/api/chat",
                                                 body, self.backend.timeout)
        except (urllib.error.URLError, OSError, ConnectionError) as exc:
            raise StructuredFinalizerFailure("transport_error", str(exc)) from exc
        except json.JSONDecodeError as exc:
            raise StructuredFinalizerFailure("provider_json_invalid", str(exc)) from exc
        if status != 200:
            raise StructuredFinalizerFailure("request_rejected", f"ollama returned {status}")
        if not isinstance(obj, dict):
            raise StructuredFinalizerFailure("provider_json_invalid", "provider response is not an object")
        message = obj.get("message") or {}
        content = message.get("content") if isinstance(message, dict) else None
        usage = ollama_native_usage(obj)
        evidence = {"model": str(obj.get("model", "")), "done": obj.get("done"),
                    "done_reason": str(obj.get("done_reason", "")),
                    "raw_output_sha256": _sha(content) if isinstance(content, str) else "",
                    "raw_http_response_state": "unavailable_transport_returns_parsed_json"}
        if usage is not None:
            evidence["native_usage"] = usage
        if self.retain_private_payloads and isinstance(content, str):
            evidence["raw_output_b64"] = _b64(content.encode("utf-8"))
        self.last_evidence = evidence
        if obj.get("model") != model:
            raise StructuredFinalizerFailure("model_mismatch", "response model mismatch", evidence)
        if obj.get("done") is not True:
            raise StructuredFinalizerFailure("incomplete_response", "response did not report done", evidence)
        if obj.get("done_reason") != "stop":
            state = "generation_length_stop" if obj.get("done_reason") == "length" else "incomplete_response"
            raise StructuredFinalizerFailure(state, "response did not end with normal stop", evidence)
        if not isinstance(content, str):
            raise StructuredFinalizerFailure("missing_content", "assistant content missing", evidence)
        return ProposerOutput(content, f"ollama:{model}", seed, prompt_hash(prompt), "miss",
                              usage=usage)


def _cfg(tool_policy: dict[str, Any]) -> dict[str, Any] | None:
    cfg = tool_policy.get("structured_final_output")
    return cfg if isinstance(cfg, dict) and cfg.get("enabled") is True else None


def _messages(ctx: dict[str, Any], cfg: dict[str, Any]) -> list[dict[str, str]]:
    system = str(cfg.get("system") or "Return only the requested final artifact envelope.")
    instruction = "Re-render the preceding candidate as the final artifact envelope. Add no facts."
    return [{"role": "system", "content": system}, *ctx.get("history", []),
            {"role": "user", "content": instruction}]


def _int(value, default: int) -> int:
    return value if type(value) is int and value >= 0 else default


def _mode(cfg: dict[str, Any]) -> str:
    mode = cfg.get("format_mode", "schema")
    return mode if mode in {"schema", "unconstrained"} else "schema"


def local_structured_finalizer_factory(profile: dict[str, Any], request):
    cfg = _cfg(request.tool_policy)
    if cfg is None:
        return None, None, None
    normal = _int(request.tool_policy.get("max_steps"), 6)
    total = normal + 1
    resource = {"enabled": True, "normal_loop_invocations_max": normal,
                "structured_finalizer_invocations_max": 1,
                "total_provider_invocations_max": total,
                "format_mode": _mode(cfg),
                "capability": profile.get("structured_final_output", {})}

    def factory(tracked):
        def finalize(ctx: dict[str, Any]) -> dict[str, Any]:
            cap = profile.get("structured_final_output")
            mode = _mode(cfg)
            use_schema = mode == "schema"
            if use_schema:
                if not isinstance(cap, dict) or cap.get("state") == "unsupported":
                    return {"state": "unsupported", "failure_class": "unsupported"}
                if cap.get("state") == "unverified" and cfg.get("allow_unverified") is not True:
                    return {"state": "unverified_not_enabled", "failure_class": "unverified_not_enabled"}
                if cap.get("transport") != "ollama_chat_format_json_schema":
                    return {"state": "unsupported", "failure_class": "unsupported"}
            if profile.get("backend") != "ollama":
                return {"state": "unsupported", "failure_class": "unsupported"}
            schema = cfg.get("schema") if use_schema else None
            if use_schema and not isinstance(schema, dict):
                return {"state": "request_rejected", "failure_class": "schema_missing"}
            messages = _messages(ctx, cfg)
            max_output = _int(cfg.get("max_output_tokens"), 1024)
            context = {"messages": messages, "format": schema,
                       "max_output_tokens": max_output}
            context_bytes = len(_canonical(context))
            cap_bytes = cfg.get("context_max_bytes")
            request_field = "format" if use_schema else ""
            request_body = b""
            evidence = {"context_bytes": context_bytes, "context_max_bytes": cap_bytes,
                        "format_mode": mode, "request_field": request_field,
                        "schema_sha256": hashlib.sha256(_canonical(schema)).hexdigest() if use_schema else "",
                        "messages_sha256": hashlib.sha256(_canonical(messages)).hexdigest(),
                        "provider_role": request.provider_role,
                        "adapter_id": request.adapter_id,
                        "profile_id": str(profile.get("profile_id", "")),
                        "requested_model_reference": request.requested_model_reference,
                        "originating_upstream_call_index": getattr(tracked, "calls", None),
                        "total_provider_invocations_max": getattr(tracked, "max_calls", None),
                        "remaining_invocations_before_call": tracked.remaining_calls(),
                        "remaining_deadline_ms_before_call": max(0, int(tracked.remaining_seconds() * 1000)),
                        "max_output_tokens": max_output,
                        "pre_finalizer_checkpoint": ctx.get("pre_finalizer_checkpoint", "")}
            if type(cap_bytes) is int and context_bytes > cap_bytes:
                return {"state": "context_not_admitted", "failure_class": "context_not_admitted",
                        "evidence": evidence}
            if tracked.remaining_seconds() <= 0:
                return {"state": "deadline_exhausted", "failure_class": "deadline_exhausted",
                        "evidence": evidence}
            if tracked.remaining_calls() == 0:
                return {"state": "budget_exhausted", "failure_class": "budget_exhausted",
                        "evidence": evidence}
            backend = getattr(getattr(tracked, "inner", None), "backend", None)
            if not isinstance(backend, OllamaBackend):
                return {"state": "unsupported", "failure_class": "unsupported", "evidence": evidence}
            proposer = OllamaStructuredFinalProposer(
                backend, schema=schema, messages=messages, model_ref=profile["model_ref"],
                retain_private_payloads=cfg.get("retain_private_finalizer_payloads") is True)
            _, request_body = proposer.request_body(
                seed=0, temperature=0.0, max_new_tokens=max_output)
            evidence["request_body_sha256"] = hashlib.sha256(request_body).hexdigest()
            if cfg.get("retain_private_finalizer_payloads") is True:
                evidence.update({"candidate_text_b64": _b64(ctx["candidate_text"].encode("utf-8")),
                                 "messages": messages, "schema": schema,
                                 "request_body_b64": _b64(request_body)})
            prompt = _canonical({"messages": messages, "format": schema}).decode("utf-8")
            try:
                out = tracked.generate_with(proposer, prompt, seed=0,
                                            temperature=0.0,
                                            max_new_tokens=max_output,
                                            system="")
            except StructuredFinalizerFailure as exc:
                return {"state": exc.state, "failure_class": exc.state,
                        "failure_detail": exc.detail, "evidence": {**evidence, **exc.evidence}}
            except TimeoutError as exc:
                return {"state": "timeout", "failure_class": "timeout",
                        "failure_detail": str(exc), "evidence": evidence}
            return {"state": "returned", "selected_text": out.text,
                    "evidence": {**evidence, **proposer.last_evidence}}
        return finalize, resource
    return factory, resource, total
