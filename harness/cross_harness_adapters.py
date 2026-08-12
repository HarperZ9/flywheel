"""Injected execution boundaries for the cross-harness executor."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib, json, os, re, shutil, signal, subprocess, time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from .cross_harness_artifacts import canonical_sha256
from .cross_harness_types import AdapterResult, AvailabilityResult, EnforcementResult
from .endpoint_registry import BackendProposer
from .local_agent import OllamaBackend, ServeBackend
from .local_loop import run_agent
from .local_session import SessionLedger
from .local_tools import TOOLS_SYSTEM, ToolExecutor, ToolGate
from .proposer import ProposerOutput, prompt_hash
from .router_agent import RouterAgent

MAX_TRACE_EVENTS = 1000
READ_ONLY_SYSTEM = (
    "You are the outer Flywheel text-tool agent. Inspect the supplied workspace and return the requested "
    "artifact envelope. The following TOOL protocol is visible, but write, exec, and MCP calls are denied.\n\n"
    + TOOLS_SYSTEM + "\n\nRead-only override: never emit write_file, edit_file, apply_patch, run, or MCP tools."
)


@dataclass(frozen=True)
class ProcessOutcome:
    returncode: int
    stdout: str
    stderr: str
    output_text: str
    elapsed_ms: int
    timed_out: bool


def _child_env() -> dict[str, str]:
    keep = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP", "TMP",
            "USERPROFILE", "LOCALAPPDATA", "APPDATA", "PROGRAMDATA", "LANG", "LC_ALL"}
    return {key: value for key, value in os.environ.items() if key.upper() in keep}


def _stop_group(proc: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=1)
    except (OSError, ProcessLookupError, subprocess.TimeoutExpired):
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                               capture_output=True, timeout=3, check=False)
            else:
                os.killpg(proc.pid, signal.SIGKILL)
        except (OSError, subprocess.SubprocessError):
            proc.kill()


def _run_process(argv: list[str], *, cwd: Path, stdin_text: str, timeout_seconds: float,
                 output_path: Path) -> ProcessOutcome:
    output_path.unlink(missing_ok=True)
    options: dict[str, Any] = {"cwd": str(cwd), "env": _child_env(), "stdin": subprocess.PIPE,
                               "stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True,
                               "encoding": "utf-8", "errors": "strict", "shell": False}
    if os.name == "nt": options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else: options["start_new_session"] = True
    started = time.perf_counter(); proc = subprocess.Popen(argv, **options)
    try:
        stdout, stderr = proc.communicate(stdin_text, timeout=timeout_seconds); timed_out = False
    except subprocess.TimeoutExpired as exc:
        _stop_group(proc); stdout, stderr = proc.communicate(); timed_out = True
        stdout = (exc.stdout or "") + (stdout or ""); stderr = (exc.stderr or "") + (stderr or "")
    elapsed = max(0, round((time.perf_counter() - started) * 1000))
    output = output_path.read_text(encoding="utf-8", errors="strict") if output_path.is_file() else ""
    return ProcessOutcome(proc.returncode if not timed_out else -1, stdout or "", stderr or "", output,
                          elapsed, timed_out)


def _resolve_codex() -> str:
    candidates = ("codex.cmd", "codex") if os.name == "nt" else ("codex",)
    for name in candidates:
        found = shutil.which(name)
        if found and not found.lower().endswith(".ps1"): return found
    return ""


_BEARER = re.compile(r"(?i)(bearer\s+)[^\s,;\"']+")
_ASSIGN = re.compile(r"(?i)((?:api[_-]?key|token|password|secret|authorization)\s*[:=]\s*)[^\s,;\"']+")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{3,}\b")
_API_KEY = re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{12,}\b", re.I)
_URL_CREDS = re.compile(r"(https?://)[^/@\s:]+:[^/@\s]+@", re.I)
_SECRET_KEY = re.compile(r"authorization|credential|password|secret|token|api[_ -]?key|jwt", re.I)


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        named_secret = _SECRET_KEY.search(str(value.get("name", "")))
        return {str(k): ("[REDACTED]" if _SECRET_KEY.search(str(k)) or (k == "value" and named_secret)
                         else _clean(v)) for k, v in value.items()}
    if isinstance(value, list): return [_clean(item) for item in value[:MAX_TRACE_EVENTS]]
    if not isinstance(value, str): return value
    text = _BEARER.sub(r"\1[REDACTED]", value)
    text = _ASSIGN.sub(r"\1[REDACTED]", text)
    text = _JWT.sub("[REDACTED]", text)
    text = _API_KEY.sub("[REDACTED]", text)
    return _URL_CREDS.sub(r"\1[REDACTED]@", text)


def _parse_jsonl(text: str, source: str) -> tuple[list[dict[str, Any]], bool]:
    events, malformed = [], False
    for line in text.splitlines():
        if not line.strip(): continue
        try: item = json.loads(line)
        except json.JSONDecodeError: malformed = True; continue
        if not isinstance(item, dict): malformed = True; continue
        if len(events) < MAX_TRACE_EVENTS: events.append({"source": source, **_clean(item)})
    return events, malformed


def _audit(events: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    observed: set[str] = set()
    def visit(value: Any) -> None:
        if isinstance(value, dict):
            text = " ".join(str(value.get(k, "")) for k in ("type", "name", "tool", "command"))
            low = text.lower()
            if any(word in low for word in ("read", "list", "grep", "glob")): observed.add("read")
            if any(word in low for word in ("command", "shell", "exec", "run")): observed.add("shell")
            if "mcp" in low: observed.add("mcp")
            if (any(word in low for word in ("write", "edit", "patch", "delete", "remove")) or
                    re.search(r"(?:^|\s)(?:rm|del|erase|move|mv|copy|cp|set-content|out-file)\b|(?:^|[^<])>(?:>|\s|$)", str(value.get("command", "")), re.I)): observed.add("write")
            for item in value.values(): visit(item)
        elif isinstance(value, list):
            for item in value: visit(item)
    visit(events)
    order = [name for name in ("read", "shell", "mcp", "write") if name in observed]
    violations = (["exec_not_allowed"] if "shell" in observed else []) + \
                 (["mcp_not_allowed"] if "mcp" in observed else []) + \
                 (["write_not_allowed"] if "write" in observed else [])
    return order, violations


def _codex_argv(executable: str, model: str, workspace: Path, output: Path) -> list[str]:
    return [executable, "exec", "--model", model, "--sandbox", "read-only", "--cd", str(workspace),
            "--ephemeral", "--ignore-user-config", "--skip-git-repo-check", "--json",
            "--output-last-message", str(output), "-"]


def _enforcement(description: dict[str, Any]) -> EnforcementResult:
    return EnforcementResult(description, canonical_sha256(description), "unverified_claim", "non_equivalent")


class DirectCodexAdapter:
    role, adapter_id = "codex_harness", "codex_cli_json/v1"
    def __init__(self, *, runner: Callable = _run_process, executable_resolver: Callable = _resolve_codex):
        self.runner, self.executable_resolver = runner, executable_resolver
    def enforcement(self, request) -> EnforcementResult:
        return _enforcement({"boundary": "codex_exec", "sandbox": "read-only", "ephemeral": True,
            "ignore_user_config": True, "skip_git_repo_check": True, "shell": False,
            "prompt_transport": "stdin", "randomness_control": "unsupported",
            "max_output_control": None, "max_output_control_state": "unsupported"})
    def availability(self, request) -> AvailabilityResult:
        exe = self.executable_resolver()
        return AvailabilityResult(bool(exe), "" if exe else "codex_cli_missing",
                                  "codex CLI present" if exe else "codex CLI absent",
                                  {"process_present": bool(exe), "provider_called": False})
    def execute(self, request) -> AdapterResult:
        output = request.artifact_dir / "last-message.txt"
        process = self.runner(_codex_argv(self.executable_resolver(), request.model_id,
                              request.workspace_root, output), cwd=request.workspace_root,
                              stdin_text=request.prompt, timeout_seconds=request.timeout_seconds,
                              output_path=output)
        events, malformed = _parse_jsonl(process.stdout, "codex_direct")
        controls = {"source": "codex_direct", "type": "controls", "randomness": "unsupported",
                    "max_output_control": None, "max_output_control_state": "unsupported"}
        events.append(controls); capabilities, violations = _audit(events)
        state, failure, detail = "returned", "", ""
        if process.timed_out: state, failure, detail = "timeout", "timeout", process.stderr
        elif process.returncode: state, failure, detail = "internal_error", "process_nonzero", process.stderr
        elif malformed: state, failure, detail = "malformed", "malformed_jsonl", "nonblank stdout was not JSONL"
        return AdapterResult(state, _clean(process.output_text), events, process.elapsed_ms, request.model_id,
            "unsupported", failure, _clean(detail), {}, {}, capabilities, violations)


class CodexCliProposer:
    def __init__(self, model_ref: str, *, workspace: Path, artifact_dir: Path,
                 timeout_seconds: float, runner: Callable = _run_process,
                 executable_resolver: Callable = _resolve_codex, clock: Callable = time.monotonic):
        self.model_ref, self.workspace, self.artifact_dir = model_ref, workspace, artifact_dir
        self.runner, self.executable_resolver, self.clock = runner, executable_resolver, clock
        self.deadline, self.events, self.calls = clock() + timeout_seconds, [], 0
    def generate(self, prompt: str, *, seed: int, temperature: float,
                 max_new_tokens: int, system: str = "") -> ProposerOutput:
        remaining = self.deadline - self.clock()
        if remaining <= 0: raise TimeoutError("shared attempt deadline expired")
        self.calls += 1; output = self.artifact_dir / f"codex-inner-{self.calls:03d}.txt"
        process = self.runner(_codex_argv(self.executable_resolver(), self.model_ref, self.workspace, output),
            cwd=self.workspace, stdin_text=(f"{system}\n\n{prompt}" if system else prompt),
            timeout_seconds=remaining, output_path=output)
        events, malformed = _parse_jsonl(process.stdout, "codex_inner"); self.events.extend(events)
        if process.timed_out: raise TimeoutError("codex inner call timed out")
        if process.returncode: raise RuntimeError(f"codex inner process exited {process.returncode}: {_clean(process.stderr)}")
        if malformed: raise RuntimeError("codex inner trace was malformed")
        return ProposerOutput(_clean(process.output_text), self.model_ref, seed, prompt_hash(prompt),
                              "unsupported", served_model=self.model_ref, usage=None)


class _ObservedProposer:
    def __init__(self, inner): self.inner, self.model_ref, self.observed, self.usage = inner, inner.model_ref, inner.model_ref, None
    def generate(self, *args, **kwargs):
        out = self.inner.generate(*args, **kwargs); self.observed, self.usage = out.model_ref, out.usage; return out


def _router_result(request, proposer, source: str) -> AdapterResult:
    ledger, events = SessionLedger(), []
    tracked = _ObservedProposer(proposer)
    agent = RouterAgent(model=request.model_id, proposer=tracked, system=READ_ONLY_SYSTEM,
                        max_tokens=request.tool_policy.get("max_output_tokens", 2048))
    executor = ToolExecutor(root=str(request.workspace_root), gate=ToolGate(False, False, False), external={})
    started = time.perf_counter()
    try:
        result = run_agent(agent, request.prompt, executor, ledger,
                           max_steps=request.tool_policy.get("max_steps", 6),
                           on_event=lambda event: events.append({"source": source, **_clean(event)}))
        state, failure, detail = "returned", "", ""
    except TimeoutError as exc: result, state, failure, detail = {"final": ""}, "timeout", "timeout", str(exc)
    except Exception as exc: result, state, failure, detail = {"final": ""}, "internal_error", type(exc).__name__, str(exc)
    events.extend({"source": source, "type": "ledger_entry", **_clean(asdict(entry))} for entry in ledger.entries)
    events.append({"source": source, "type": "ledger_checkpoint", "checkpoint": ledger.checkpoint(),
                   "verified": ledger.verify(), "randomness": "unsupported",
                   "max_output_control": None, "max_output_control_state": "unsupported"})
    inner = getattr(proposer, "events", []); events = list(inner) + events
    capabilities, violations = _audit(events)
    return AdapterResult(state, _clean(result.get("final", "")), events,
        max(0, round((time.perf_counter() - started) * 1000)), tracked.observed, "unsupported",
        failure, _clean(detail), {}, tracked.usage or {}, capabilities, violations)


class FlywheelRouterAdapter:
    role, adapter_id = "flywheel_harness", "flywheel_router/v1"
    def __init__(self, *, proposer=None, runner: Callable = _run_process,
                 executable_resolver: Callable = _resolve_codex):
        self.proposer, self.runner, self.executable_resolver = proposer, runner, executable_resolver
    def enforcement(self, request) -> EnforcementResult:
        return _enforcement({"boundary": "flywheel_outer_plus_codex_inner",
            "outer_tool_gate": {"allow_write": False, "allow_exec": False, "allow_mcp": False},
            "inner_codex_sandbox": "read-only", "denied_tools_visible": True,
            "randomness_control": "unsupported", "max_output_control": None})
    def availability(self, request) -> AvailabilityResult:
        present = self.proposer is not None or bool(self.executable_resolver())
        return AvailabilityResult(present, "" if present else "codex_cli_missing",
            "adapter metadata ready" if present else "codex CLI absent",
            {"process_present": present, "provider_called": False})
    def execute(self, request) -> AdapterResult:
        proposer = self.proposer or CodexCliProposer(request.model_id, workspace=request.workspace_root,
            artifact_dir=request.artifact_dir, timeout_seconds=request.timeout_seconds,
            runner=self.runner, executable_resolver=self.executable_resolver)
        return _router_result(request, proposer, "flywheel_outer")


def _profile_error(profile: dict[str, Any]) -> str:
    if profile.get("backend") not in {"serve", "ollama"}: return "unsupported_local_backend"
    parsed = urlsplit(str(profile.get("endpoint_url", "")))
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or parsed.query or parsed.fragment:
        return "unsafe_endpoint_url"
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}: return "endpoint_not_loopback"
    if not profile.get("profile_id") or not profile.get("model_ref"): return "endpoint_profile_incomplete"
    return ""


def _backend(profile: dict[str, Any], timeout: float):
    if profile["backend"] == "ollama":
        return OllamaBackend(base_url=profile["endpoint_url"], model=profile["model_ref"], timeout=timeout)
    return ServeBackend(base_url=profile["endpoint_url"], timeout=timeout)


class LocalRouterAdapter:
    adapter_id = "openai_compatible_local/v1"
    def __init__(self, role: str, profile: dict[str, Any], *, backend_factory: Callable = _backend):
        self.role, self.profile, self.backend_factory = role, dict(profile), backend_factory
    def enforcement(self, request) -> EnforcementResult:
        return _enforcement({"boundary": "flywheel_outer_plus_local_backend",
            "profile_id": self.profile.get("profile_id", ""), "backend": self.profile.get("backend", ""),
            "outer_tool_gate": {"allow_write": False, "allow_exec": False, "allow_mcp": False},
            "denied_tools_visible": True})
    def availability(self, request) -> AvailabilityResult:
        failure = _profile_error(self.profile)
        return AvailabilityResult(not failure, failure, failure or "exact local profile selected",
                                  {"profile_id": self.profile.get("profile_id", ""),
                                   "profile_sha256": self.profile.get("profile_sha256", ""),
                                   "provider_called": False})
    def execute(self, request) -> AdapterResult:
        failure = _profile_error(self.profile)
        if failure: return AdapterResult("unavailable", "", [], 0, "", "unsupported", failure,
                                         failure, {}, {}, [], [])
        backend = self.backend_factory(self.profile, request.timeout_seconds)
        proposer = BackendProposer(backend, model_ref=self.profile["model_ref"], extract=False)
        return _router_result(request, proposer, "flywheel_outer")
