"""Injected execution boundaries for the cross-harness executor."""
from __future__ import annotations
from dataclasses import asdict, replace
import base64, binascii, json, math, os, re, shlex, shutil, time, urllib.error, urllib.request
from pathlib import Path; from typing import Any, Callable
from urllib.parse import urlsplit
from .cross_harness_artifacts import canonical_sha256
from .cross_harness_types import AdapterResult, AvailabilityResult, EnforcementResult
from .endpoint_registry import BackendProposer
from .local_agent import MalformedBackendOutput, OllamaBackend, ServeBackend
from .local_loop import run_agent
from .local_session import SessionLedger
from .local_tools import TOOLS_SYSTEM, ToolExecutor, ToolGate
from .proposer import ProposerOutput, prompt_hash
from .router_agent import RouterAgent
from .cross_harness_process import ProcessOutcome, run_process; from .cross_harness_provider_error import ProviderRejected, inspect_provider_events; from .cross_harness_usage import attempt_usage, usage_from_events
MAX_TRACE_EVENTS, MAX_TRACE_BYTES, MAX_LINE_BYTES, MAX_FIELD_BYTES, MAX_DEPTH = 1000, 1 << 20, 1 << 16, 1 << 14, 16
READ_ONLY_SYSTEM = ("You are the outer Flywheel text-tool agent. Inspect the supplied workspace and return the requested artifact envelope. "
    "The following TOOL protocol is visible, but write, exec, and MCP calls are denied.\n\n" + TOOLS_SYSTEM + "\n\nRead-only override: never emit write_file, edit_file, apply_patch, run, or MCP tools.")
class MalformedProviderOutput(RuntimeError): pass
def _resolve_codex() -> str:
    candidates = ("codex.cmd", "codex") if os.name == "nt" else ("codex",)
    for name in candidates:
        found = shutil.which(name)
        if found and not found.lower().endswith(".ps1"): return found
    return ""
_BEARER, _ASSIGN = re.compile(r"(?i)(bearer\s+)[^\s,;\"']+"), re.compile(r"(?i)((?:api[_-]?key|token|password|secret|authorization)\s*[:=]\s*)[^\s,;\"']+")
_JWT, _API_KEY = re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{3,}\b"), re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{12,}\b", re.I)
_URL_CREDS, _SECRET_KEY = re.compile(r"(https?://)[^/@\s:]+:[^/@\s]+@", re.I), re.compile(r"authorization|credential|password|secret|token|api[_ -]?key|jwt", re.I)
def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        named_secret = _SECRET_KEY.search(str(value.get("name", "")))
        return {str(k): ("[REDACTED]" if (k == "value" and named_secret) or (_SECRET_KEY.search(str(k)) and type(v) is not int)  # plain-int values are token COUNTS (usage *_tokens); credentials are strings
                         else _clean(v)) for k, v in value.items()}
    if isinstance(value, list): return [_clean(item) for item in value[:MAX_TRACE_EVENTS]]
    if not isinstance(value, str): return value
    text = _ASSIGN.sub(r"\1[REDACTED]", _BEARER.sub(r"\1[REDACTED]", value))
    text = _API_KEY.sub("[REDACTED]", _JWT.sub("[REDACTED]", text))
    return _URL_CREDS.sub(r"\1[REDACTED]@", text)
def _run_process(argv: list[str], **kwargs) -> ProcessOutcome:
    return run_process(argv, **kwargs)
def _json_pairs(rows):
    if len(rows) != len({key for key, _ in rows}): raise ValueError("duplicate JSON key")
    return dict(rows)
def _nonfinite(value: str): raise ValueError(f"non-finite JSON number: {value}")
def _bounded(value: Any, depth: int = 0) -> bool:
    if depth > MAX_DEPTH: return False
    if isinstance(value, str):
        try: return len(value.encode("utf-8")) <= MAX_FIELD_BYTES
        except UnicodeEncodeError: return False
    if isinstance(value, list): return len(value) <= MAX_TRACE_EVENTS and all(_bounded(item, depth + 1) for item in value)
    if isinstance(value, dict):
        return len(value) <= MAX_TRACE_EVENTS and all(_bounded(str(key), depth + 1) and _bounded(item, depth + 1) for key, item in value.items())
    return value is None or isinstance(value, (bool, int)) or (isinstance(value, float) and math.isfinite(value))
def _json_object(text: str) -> dict[str, Any]:
    try: item = json.loads(text, object_pairs_hook=_json_pairs, parse_constant=_nonfinite)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc: raise MalformedProviderOutput("malformed provider JSON") from exc
    if not isinstance(item, dict) or not _bounded(item): raise MalformedProviderOutput("unbounded provider JSON object")
    return item
def _parse_jsonl(text: str, source: str) -> tuple[list[dict[str, Any]], bool]:
    events, malformed, total = [], False, 0
    for line in text.splitlines():
        if not line.strip(): continue
        size = len(line.encode("utf-8")); total += size
        if size > MAX_LINE_BYTES or total > MAX_TRACE_BYTES: malformed = True; continue
        try: item = _json_object(line)
        except MalformedProviderOutput: malformed = True; continue
        if len(events) < MAX_TRACE_EVENTS: events.append({**_clean(item), "source": source})
        else: malformed = True
    return events, malformed
def _final_message(events: list[dict[str, Any]]) -> str:
    found: list[str] = []
    for event in events:
        if event.get("type") != "item.completed": continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "agent_message": continue
        text = item.get("text")
        if not isinstance(text, str) or not text: raise MalformedProviderOutput("malformed final agent message")
        found.append(text)
    if not found: raise MalformedProviderOutput("final agent message missing")
    return found[-1]
def _audit(events: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    observed: set[str] = set()
    def visit(value: Any) -> None:
        if isinstance(value, dict):
            metadata = " ".join(str(value.get(k, "")) for k in ("type", "name", "tool")); text = metadata + " " + str(value.get("command", ""))
            low = text.lower()
            if any(word in low for word in ("read", "list", "grep", "glob")): observed.add("read")
            if any(word in low for word in ("command", "shell", "exec", "run")): observed.add("shell")
            if "mcp" in low: observed.add("mcp")
            command = str(value.get("command", "")); operators = re.sub(r"'[^']*'|\"[^\"]*\"", "", command)
            wrapped = _wrapper_payload(command)
            if wrapped: operators = _operator_text(*wrapped)
            if ("file_change" in low or any(word in metadata.lower() for word in ("write", "edit", "patch", "delete", "remove"))
                    or re.search(r"(?:^|\s)(?:rm|del|erase|move|mv|copy|cp|tee|touch|mkdir|set-content|out-file)\b", command, re.I) or re.search(r"(?<![<>=])(?:\d|[*&])?>{1,2}(?![=])", operators)): observed.add("write")
            for item in value.values(): visit(item)
        elif isinstance(value, list):
            for item in value: visit(item)
    visit(events)
    order = [name for name in ("read", "shell", "mcp", "write") if name in observed]
    violations = (["exec_not_allowed"] if "shell" in observed else []) + (["mcp_not_allowed"] if "mcp" in observed else []) + (["write_not_allowed"] if "write" in observed else [])
    return order, violations
def _wrapper_payload(command: str) -> tuple[str, str] | None:
    try: words = shlex.split(command, posix=True)
    except ValueError: return ""
    if not words: return None
    executable = words[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
    def is_executable(*names: str) -> bool: return any(executable == name or executable.endswith(name + ".exe") for name in names)
    shells = {"sh", "bash", "dash", "zsh", "ksh", "ash"}
    if is_executable(*shells):
        for index, word in enumerate(words[1:], 1):
            if word.startswith("-") and not word.startswith("--") and "c" in word[1:] and index + 1 < len(words): return "posix", words[index + 1]
    if is_executable("powershell", "pwsh"):
        for index, word in enumerate(words[1:], 1):
            option = word.lower()
            named = "-" + option[1:] if option.startswith("/") else option
            command = option in {"-c", "-command", "-commandwithargs", "/c", "/command"} or (len(named) >= 3 and "-command".startswith(named))
            encoded = named in {"-e", "-ec"} or (len(named) >= 3 and "-encodedcommand".startswith(named))
            if command: return "powershell", " ".join(words[index + 1:])
            if encoded and index + 1 < len(words):
                try: return "powershell", base64.b64decode(words[index + 1], validate=True).decode("utf-16le", "strict")
                except (binascii.Error, ValueError, UnicodeDecodeError): return None
    if is_executable("cmd"):
        raw = re.search(r"(?i)(?:^|\s)/[ck](.*)$", command)
        if raw and raw.group(1).lstrip().startswith(('"', "'")): return "cmd", raw.group(1).lstrip().strip('"')
        for index, word in enumerate(words[1:], 1):
            if word.lower() in {"/c", "/k"}: return "cmd", " ".join(words[index + 1:])
    return None
def _operator_text(kind: str, payload: str) -> str:
    if kind == "cmd": return re.sub(r"\^.", "", re.sub(r'"[^"]*"', "", payload))
    if kind == "powershell": return re.sub(r"`.", "", re.sub(r"'[^']*'|\"[^\"]*\"", "", payload)).replace('"', '')
    return re.sub(r"\\.|'[^']*'|\"[^\"]*\"", "", payload)
def _codex_argv(executable: str, model: str, workspace: Path) -> list[str]:
    return [executable, "exec", "--model", model, "--sandbox", "read-only", "--cd", str(workspace), "--ephemeral", "--ignore-user-config",
            "--skip-git-repo-check", "--json", "-"]
def _enforcement(description: dict[str, Any]) -> EnforcementResult:
    return EnforcementResult(description, canonical_sha256(description), "unverified_claim", "non_equivalent")
def _freeze_identities(value: dict[str, dict[str, Any]] | None) -> dict[str, str]:
    return {str(key): json.dumps(item, sort_keys=True, separators=(",", ":")) for key, item in (value or {}).items()}
def _identity(request, identities: dict[str, str]) -> tuple[str, dict[str, Any]]:
    if not identities: return "", {}
    try: expected = json.loads(identities[request.task_id])
    except (KeyError, json.JSONDecodeError): return "task_identity_missing", {}
    evidence = {"oracle_spec_sha256": str(expected.get("oracle_spec_sha256", ""))}
    if request.raw_prompt_sha256 != expected.get("raw_prompt_sha256"): return "task_prompt_identity_mismatch", evidence
    if request.input_sha256s != expected.get("input_sha256s"): return "task_input_identity_mismatch", evidence
    if not evidence["oracle_spec_sha256"]: return "task_oracle_identity_missing", evidence
    return "", evidence
class DirectCodexAdapter:
    role, adapter_id = "codex_harness", "codex_cli_json/v1"
    def __init__(self, *, runner: Callable = _run_process, executable_resolver: Callable = _resolve_codex,
                 task_identity_by_id: dict[str, dict[str, Any]] | None = None):
        self.runner, self.executable_resolver = runner, executable_resolver
        self.task_identities = _freeze_identities(task_identity_by_id)
    def enforcement(self, request) -> EnforcementResult:
        return _enforcement({"boundary": "codex_exec", "sandbox": "read-only", "ephemeral": True,
            "ignore_user_config": True, "skip_git_repo_check": True, "shell": False, "prompt_transport": "stdin", "randomness_control": "unsupported",
            "max_output_control": None, "max_output_control_state": "unsupported"})
    def availability(self, request) -> AvailabilityResult:
        exe, identity, evidence = self.executable_resolver(), *_identity(request, self.task_identities)
        failure = identity or ("" if exe else "codex_cli_missing")
        return AvailabilityResult(not failure, failure, failure or "codex CLI present", {"process_present": bool(exe), "provider_called": False, **evidence})
    def execute(self, request) -> AdapterResult:
        process = self.runner(_codex_argv(self.executable_resolver(), request.requested_model_reference, request.workspace_root), cwd=request.workspace_root, stdin_text=request.prompt, timeout_seconds=request.timeout_seconds)
        events, malformed = _parse_jsonl(process.stdout, "codex_direct")
        rejection, terminal_malformed = inspect_provider_events(events); malformed |= terminal_malformed
        try: output_text = "" if rejection or terminal_malformed else _final_message(events)
        except MalformedProviderOutput: output_text, final_invalid = "", True
        else: final_invalid = False
        events.append({"source": "codex_direct", "type": "controls", "randomness": "unsupported", "max_output_control": None, "max_output_control_state": "unsupported"}); capabilities, violations = _audit(events)
        state, failure, detail = "returned", "", ""
        if process.timed_out: state, failure, detail = "timeout", "timeout", process.stderr
        elif malformed or process.malformed_output: state, failure, detail = "malformed", "malformed_jsonl", "provider output was not bounded UTF-8 JSONL"
        elif rejection: state, failure, detail = "internal_error", *rejection
        elif final_invalid: state, failure, detail = "malformed", "malformed_jsonl", "final agent message missing or malformed"
        elif process.returncode: state, failure, detail = "internal_error", "process_nonzero", process.stderr
        observed = next((event["model"] for event in reversed(events) if event.get("type") == "turn.completed" and isinstance(event.get("model"), str) and event["model"]), "")
        return AdapterResult(state, output_text if state == "returned" else "", events, process.elapsed_ms, observed, "unsupported", failure, _clean(detail), {}, {}, capabilities, violations, "structured_provider_event" if observed else "unknown")
class CodexCliProposer:
    def __init__(self, model_ref: str, *, workspace: Path, artifact_dir: Path, timeout_seconds: float, runner: Callable = _run_process,
                 executable_resolver: Callable = _resolve_codex, clock: Callable = time.monotonic):
        self.model_ref, self.workspace, self.artifact_dir = model_ref, workspace, artifact_dir
        self.runner, self.executable_resolver, self.clock = runner, executable_resolver, clock
        self.deadline, self.events, self.calls = clock() + timeout_seconds, [], 0
    def generate(self, prompt: str, *, seed: int, temperature: float, max_new_tokens: int, system: str = "") -> ProposerOutput:
        remaining = self.deadline - self.clock()
        if remaining <= 0: raise TimeoutError("shared attempt deadline expired")
        self.calls += 1
        process = self.runner(_codex_argv(self.executable_resolver(), self.model_ref, self.workspace), cwd=self.workspace,
            stdin_text=(f"{system}\n\n{prompt}" if system else prompt), timeout_seconds=remaining)
        events, malformed = _parse_jsonl(process.stdout, "codex_inner")
        rejection, terminal_malformed = inspect_provider_events(events); self.events.extend({**event, "inner_call": self.calls} for event in events)
        if process.timed_out: raise TimeoutError("codex inner call timed out")
        if malformed or process.malformed_output: raise MalformedProviderOutput("codex inner provider output was malformed")
        if terminal_malformed: raise MalformedProviderOutput("codex inner provider output was malformed")
        if rejection: raise ProviderRejected(*rejection)
        final = _final_message(events)
        if process.returncode: raise RuntimeError(f"codex inner process exited {process.returncode}: {_clean(process.stderr)}")
        return ProposerOutput(final, self.model_ref, seed, prompt_hash(prompt), "unsupported", served_model=next((event["model"] for event in reversed(events) if event.get("type") == "turn.completed" and isinstance(event.get("model"), str) and event["model"]), ""), usage=usage_from_events(events))
class _ObservedProposer:
    def __init__(self, inner, timeout: float, clock: Callable, response_model_attested: bool = False):
        self.inner, self.model_ref, self.observed, self.usage_records, self.basis, self.response_model_attested = inner, inner.model_ref, "", [], "unknown", response_model_attested
        self.clock, self.deadline = clock, clock() + timeout
    def generate(self, *args, **kwargs):
        remaining = self.deadline - self.clock()
        if remaining <= 0: raise TimeoutError("shared attempt deadline expired")
        backend = getattr(self.inner, "backend", None)
        if backend is not None and hasattr(backend, "timeout"): backend.timeout = min(backend.timeout, remaining)
        out = self.inner.generate(*args, **kwargs); self.usage_records.append(getattr(out, "usage", None))
        if self.clock() >= self.deadline: raise TimeoutError("shared attempt deadline expired")
        self.observed = out.served_model or (out.model_ref if self.response_model_attested else "")
        self.basis = "structured_provider_event" if out.served_model else "structured_provider_response" if self.observed else "unknown"; return out
def _router_result(request, proposer, source: str, clock: Callable = time.monotonic, response_model_attested: bool = False) -> AdapterResult:
    ledger, events = SessionLedger(), []
    tracked = _ObservedProposer(proposer, request.timeout_seconds, clock, response_model_attested)
    agent = RouterAgent(model=request.model_id, proposer=tracked, system=READ_ONLY_SYSTEM, max_tokens=request.tool_policy.get("max_output_tokens", 2048))
    executor = ToolExecutor(root=str(request.workspace_root), gate=ToolGate(False, False, False), external={})
    started = time.perf_counter()
    try:
        result = run_agent(agent, request.prompt, executor, ledger, max_steps=request.tool_policy.get("max_steps", 6),
                           on_event=lambda event: events.append({**_clean(event), "source": source}))
        state, failure, detail = "returned", "", ""
    except TimeoutError as exc: result, state, failure, detail = {"final": ""}, "timeout", "timeout", str(exc)
    except (MalformedProviderOutput, MalformedBackendOutput) as exc: result, state, failure, detail = {"final": ""}, "malformed", "malformed_provider_output", str(exc)
    except ProviderRejected as exc: result, state, failure, detail = {"final": ""}, "internal_error", exc.failure_class, str(exc)
    except Exception as exc: result, state, failure, detail = {"final": ""}, "internal_error", type(exc).__name__, str(exc)
    events.extend({**_clean(asdict(entry)), "source": source, "type": "ledger_entry"} for entry in ledger.entries)
    events.append({"source": source, "type": "ledger_checkpoint", "checkpoint": ledger.checkpoint(), "verified": ledger.verify(), "randomness": "unsupported",
                   "max_output_control": None, "max_output_control_state": "unsupported"})
    inner = [{**_clean(event), "source": "codex_inner"} for event in getattr(proposer, "events", []) if isinstance(event, dict)]; events = inner + events
    capabilities, violations = _audit(events)
    return AdapterResult(state, _clean(result.get("final", "")), events, max(0, round((time.perf_counter() - started) * 1000)), tracked.observed, "unsupported", failure, _clean(detail), {}, attempt_usage(tracked.usage_records), capabilities, violations, tracked.basis)
class FlywheelRouterAdapter:
    role, adapter_id = "flywheel_harness", "flywheel_router/v1"
    def __init__(self, *, proposer=None, runner: Callable = _run_process, executable_resolver: Callable = _resolve_codex,
                 clock: Callable = time.monotonic, task_identity_by_id: dict[str, dict[str, Any]] | None = None):
        self.proposer, self.runner, self.executable_resolver, self.clock = proposer, runner, executable_resolver, clock
        self.task_identities = _freeze_identities(task_identity_by_id)
    def enforcement(self, request) -> EnforcementResult:
        return _enforcement({"boundary": "flywheel_outer_plus_codex_inner", "outer_tool_gate": {"allow_write": False, "allow_exec": False, "allow_mcp": False},
            "inner_codex_sandbox": "read-only", "denied_tools_visible": True, "randomness_control": "unsupported", "max_output_control": None})
    def availability(self, request) -> AvailabilityResult:
        present = self.proposer is not None or bool(self.executable_resolver()); failure, evidence = _identity(request, self.task_identities)
        failure = failure or ("" if present else "codex_cli_missing")
        return AvailabilityResult(not failure, failure, failure or "adapter metadata ready", {"process_present": present, "provider_called": False, **evidence})
    def execute(self, request) -> AdapterResult:
        proposer = self.proposer or CodexCliProposer(request.requested_model_reference, workspace=request.workspace_root, artifact_dir=request.artifact_dir, timeout_seconds=request.timeout_seconds, runner=self.runner, executable_resolver=self.executable_resolver)
        return _router_result(request, proposer, "flywheel_outer", self.clock)
def _profile_error(profile: dict[str, Any]) -> str:
    if profile.get("backend") not in {"serve", "ollama"}: return "unsupported_local_backend"
    parsed = urlsplit(str(profile.get("endpoint_url", "")))
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or parsed.query or parsed.fragment: return "unsafe_endpoint_url"
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}: return "endpoint_not_loopback"
    if not profile.get("profile_id") or not profile.get("model_ref"): return "endpoint_profile_incomplete"
    if profile.get("supports_agentic_workflow") is not True: return "endpoint_not_agentic_ready"
    if profile.get("root_exists") is not True: return "endpoint_root_missing"
    expected = canonical_sha256({key: value for key, value in profile.items() if key != "profile_sha256"})
    if profile.get("profile_sha256") != expected: return "endpoint_profile_hash_mismatch"
    return ""
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None
def _local_http(method: str, url: str, body: bytes | None, timeout: float) -> tuple[int, dict]:
    if _profile_error({"backend": "serve", "endpoint_url": url.rsplit("/", 1)[0], "profile_id": "transport", "model_ref": "transport", "profile_sha256": "",
                       "supports_agentic_workflow": True, "root_exists": True}) not in {"", "endpoint_profile_hash_mismatch"}: raise OSError("unsafe local transport URL")
    request = urllib.request.Request(url, data=body, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect()).open(request, timeout=timeout) as response: raw, status = response.read(MAX_TRACE_BYTES + 1), response.status
    except urllib.error.HTTPError as exc: raw, status = exc.read(MAX_TRACE_BYTES + 1), exc.code
    if len(raw) > MAX_TRACE_BYTES: raise MalformedProviderOutput("local response too large")
    if not raw: raise MalformedProviderOutput("empty local provider response")
    try: return status, _json_object(raw.decode("utf-8", "strict"))
    except UnicodeDecodeError as exc: raise MalformedProviderOutput("malformed provider JSON") from exc
def _backend(profile: dict[str, Any], timeout: float):
    if profile["backend"] == "ollama":
        return OllamaBackend(base_url=profile["endpoint_url"], model=profile["model_ref"], timeout=timeout, transport=_local_http)
    return ServeBackend(base_url=profile["endpoint_url"], timeout=timeout, transport=_local_http)
class LocalRouterAdapter:
    adapter_id = "openai_compatible_local/v1"
    def __init__(self, role: str, profile: dict[str, Any], *, backend_factory: Callable = _backend, clock: Callable = time.monotonic,
                 task_identity_by_id: dict[str, dict[str, Any]] | None = None):
        self.role, self.profile, self.backend_factory, self.clock = role, dict(profile), backend_factory, clock
        self.task_identities = _freeze_identities(task_identity_by_id)
    def enforcement(self, request) -> EnforcementResult:
        return _enforcement({"boundary": "flywheel_outer_plus_local_backend", "profile_id": self.profile.get("profile_id", ""), "backend": self.profile.get("backend", ""),
            "outer_tool_gate": {"allow_write": False, "allow_exec": False, "allow_mcp": False}, "denied_tools_visible": True})
    def availability(self, request) -> AvailabilityResult:
        failure, evidence = _identity(request, self.task_identities); failure = failure or _profile_error(self.profile)
        if not failure and request.provider_role != self.role: failure = "endpoint_role_mismatch"
        elif not failure and request.adapter_id != self.adapter_id: failure = "endpoint_adapter_mismatch"
        elif not failure and request.requested_model_reference != self.profile.get("model_ref"): failure = "endpoint_model_mismatch"
        return AvailabilityResult(not failure, failure, failure or "exact local profile selected", {"profile_id": self.profile.get("profile_id", ""), "profile_sha256": self.profile.get("profile_sha256", ""), "provider_called": False, **evidence})
    def execute(self, request) -> AdapterResult:
        available = self.availability(request); failure = available.failure_class
        if failure: return AdapterResult("unavailable", "", [], 0, "", "unsupported", failure, failure, {}, {}, [], [])
        backend = self.backend_factory(self.profile, request.timeout_seconds)
        proposer = BackendProposer(backend, model_ref="", extract=False)
        result = _router_result(request, proposer, "flywheel_outer", self.clock, response_model_attested=True)
        if result.execution_state == "returned" and result.model_observed and result.model_observed != self.profile["model_ref"]:
            return replace(result, execution_state="malformed", failure_class="observed_model_drift", failure_detail="observed model did not match exact endpoint profile")
        return result
