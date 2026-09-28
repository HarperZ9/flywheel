"""One long-lived child per lane, for the lane tools whose work outlives a call.

Every lane call used to spawn a child, call one tool and kill the child tree
(``lane_caller._call``, ``mcp_client.StdioTransport.close``). That is right for
a tool that answers in one call, and it breaks the two that start work and
answer later:

- relay ``local_agent_start`` runs the agent in a thread of the relay child and
  keeps the run in that child's memory, so ``local_agent_status`` and
  ``local_agent_result`` sent to a fresh child answer "unknown run_id";
- index ``index.router.job.start`` spawns a worker process under the index
  child, and the tree kill that ends the call ends the worker with it.

For those tools (``SESSION_SPECS``) the engine keeps one child per lane and
sends every call to it. The session ends:

- after ``idle_timeout_s`` with no call, unless a run or job it started is
  still active: the reaper asks the status tool, and keeps the child until the
  work ends or ``busy_cap_s`` has passed since the last call;
- when the launch changes (a new pin, a new setting), since the child was
  started with the old one;
- when its child exits, or a call to it fails in transport (timeout, closed
  pipe), so the next call starts a fresh child;
- when the engine stops: the gateway closes every session as it stops serving,
  ``atexit`` does the same for any other exit, and a child whose engine was
  killed reads EOF on stdin and ends its serve loop (relay ``local_mcp.serve``,
  index ``mcp.serve``).

What a session does not change: which tools a call may reach, its tier, its
arguments and its timeout. ``lane_caller`` applies all of those before a call
reaches a session (``lane_session_calls``). The stated limit: work in flight
when a session ends is lost. relay keeps runs in memory only here, and an index
job whose worker was killed reads as stopped and can be resumed.
"""
from __future__ import annotations

import atexit
import json
import threading
import time
from dataclasses import dataclass, replace
from typing import Any, Callable

from .mcp_client import LaunchSpec, MCPClient

IDLE_TIMEOUT_S = 600
BUSY_CAP_S = 3600
_STATUS_TIMEOUT_S = 10
_TRANSPORT_FAILURES = ("no response within", "server closed", "server stdin is closed")


@dataclass(frozen=True)
class SessionSpec:
    """The tools that share a lane's session, and how to tell active work.

    ``status_tool`` answers for one id in ``id_arg``; the answer's
    ``state_key`` is one of ``active`` while the work runs."""
    tools: tuple[str, ...]
    status_tool: str
    id_arg: str
    state_key: str
    active: frozenset[str]


_JOB = "index.router.job."
SESSION_SPECS: dict[str, SessionSpec] = {
    "relay": SessionSpec(
        ("local_agent_start", "local_agent_status", "local_agent_result", "local_agent_runs"),
        "local_agent_status", "run_id", "state", frozenset(("running",))),
    "index": SessionSpec(
        tuple(_JOB + action for action in ("start", "status", "result", "cancel", "resume")),
        _JOB + "status", "job_id", "status",
        frozenset(("queued", "running", "cancellation_requested"))),
}


def session_tools(lane: str) -> tuple[str, ...]:
    spec = SESSION_SPECS.get(lane)
    return spec.tools if spec else ()


def is_session_tool(lane: str, tool: str) -> bool:
    return tool in session_tools(lane)


def launch_identity(launch: LaunchSpec) -> tuple:
    """What makes two launches the same child; the tool list is not part of it,
    since the engine checks admission per call before the session."""
    return (launch.argv, launch.cwd, launch.env_overrides, launch.inherit_env,
            launch.url, launch.hide_window)


class _Session:
    def __init__(self, lane: str, launch: LaunchSpec, client: MCPClient, now: float):
        self.lane, self.identity, self.client = lane, launch_identity(launch), client
        self.lock = threading.Lock()
        self.last_used = now
        self.active: set[str] = set()

    def alive(self) -> bool:
        proc = getattr(getattr(self.client, "_t", None), "proc", None)
        return proc is None or proc.poll() is None

    def pid(self) -> int | None:
        proc = getattr(getattr(self.client, "_t", None), "proc", None)
        return getattr(proc, "pid", None)

    def call(self, tool: str, args: dict, timeout: float) -> dict:
        transport = getattr(self.client, "_t", None)
        if transport is not None and hasattr(transport, "timeout"):
            transport.timeout = timeout
        return self.client.call_text(tool, args)


class LaneSessionPool:
    """The engine's lane sessions, one per lane (``SESSION_SPECS``)."""

    def __init__(self, *, idle_timeout_s: float = IDLE_TIMEOUT_S,
                 busy_cap_s: float = BUSY_CAP_S,
                 clock: Callable[[], float] = time.monotonic, reaper: bool = True):
        self.idle_timeout_s, self.busy_cap_s = idle_timeout_s, busy_cap_s
        self._clock = clock
        self._lock = threading.Lock()
        self._sessions: dict[str, _Session] = {}
        self._reaper_wanted = reaper
        self._stop = threading.Event()
        self._reaper: threading.Thread | None = None

    def call(self, lane: str, tool: str, launch: LaunchSpec, args: dict[str, Any],
             timeout: float) -> dict[str, Any]:
        """Call one session tool on the lane's session, opening it if needed.

        Answers in ``lane_caller._call``'s shapes: the parsed JSON, or an error
        dict reading "lane ... unavailable" (the child could not start) or
        "lane ... call failed" (it started and the call failed in transport)."""
        spec = SESSION_SPECS.get(lane)
        if spec is None or tool not in spec.tools:
            raise ValueError(f"{lane}.{tool} is not a session tool")
        try:
            session = self._session_for(lane, launch, spec, timeout)
        except Exception as e:
            return {"error": f"lane {lane!r} unavailable: {type(e).__name__}: {e}"}
        with session.lock:
            session.last_used = self._clock()
            try:
                res = session.call(tool, args, timeout)
            except Exception as e:
                if not session.alive() or any(m in str(e) for m in _TRANSPORT_FAILURES):
                    self._discard(lane, session)
                return {"error": f"lane {lane!r} call failed: {type(e).__name__}: {e}"}
            finally:
                session.last_used = self._clock()
            return _answer(lane, tool, res, spec, session)

    def _session_for(self, lane: str, launch: LaunchSpec, spec: SessionSpec,
                     timeout: float) -> _Session:
        with self._lock:
            session = self._sessions.get(lane)
            if session is not None and (session.identity != launch_identity(launch)
                                        or not session.alive()):
                self._sessions.pop(lane, None)
                session.client.close()
                session = None
            if session is None:
                client = MCPClient(replace(launch, allowed_tools=spec.tools),
                                   timeout=timeout, client_name=f"flywheel-{lane}-session")
                try:
                    client.start()
                except Exception:
                    client.close()
                    raise
                session = _Session(lane, launch, client, self._clock())
                self._sessions[lane] = session
                self._start_reaper()
            return session

    def _discard(self, lane: str, session: _Session) -> None:
        with self._lock:
            if self._sessions.get(lane) is session:
                self._sessions.pop(lane, None)
        session.client.close()

    def reap(self) -> list[str]:
        """Close every session past its idle timeout that holds no active work,
        and every one past the busy cap; return the lanes closed."""
        now = self._clock()
        with self._lock:
            idle = [(lane, s) for lane, s in self._sessions.items()
                    if now - s.last_used >= self.idle_timeout_s or not s.alive()]
        closed = []
        for lane, session in idle:
            if (session.alive() and now - session.last_used < self.busy_cap_s
                    and self._still_busy(lane, session)):
                continue
            self._discard(lane, session)
            closed.append(lane)
        return closed

    def _still_busy(self, lane: str, session: _Session) -> bool:
        spec = SESSION_SPECS[lane]
        with session.lock:
            for work_id in sorted(session.active):
                try:
                    res = session.call(spec.status_tool, {spec.id_arg: work_id},
                                       _STATUS_TIMEOUT_S)
                except Exception:
                    return False
                _answer(lane, spec.status_tool, res, spec, session)
            return bool(session.active)

    def close(self, lane: str) -> None:
        with self._lock:
            session = self._sessions.pop(lane, None)
        if session is not None:
            session.client.close()

    def close_all(self) -> None:
        self._stop.set()
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.client.close()

    def describe(self) -> dict[str, dict[str, Any]]:
        """Each open session: its child's pid, active work count and idle seconds."""
        now = self._clock()
        with self._lock:
            return {lane: {"pid": s.pid(), "active": len(s.active),
                           "idle_s": round(now - s.last_used, 1)}
                    for lane, s in self._sessions.items()}

    def _start_reaper(self) -> None:
        if not self._reaper_wanted or (self._reaper and self._reaper.is_alive()):
            return
        interval = max(1.0, min(30.0, self.idle_timeout_s / 4))

        def loop() -> None:
            while not self._stop.wait(interval):
                self.reap()

        self._reaper = threading.Thread(target=loop, name="lane-session-reaper", daemon=True)
        self._reaper.start()


def _answer(lane: str, tool: str, res: dict, spec: SessionSpec, session: _Session) -> dict:
    """The parsed answer, with the session's active work updated from it."""
    if not res["ok"]:
        return {"error": f"{lane}.{tool} error: {res['text'][:200]}"}
    try:
        parsed = json.loads(res["text"])
    except json.JSONDecodeError:
        return {"raw": res["text"][:500]}
    if isinstance(parsed, dict) and isinstance(parsed.get(spec.id_arg), str):
        if parsed.get(spec.state_key) in spec.active:
            session.active.add(parsed[spec.id_arg])
        else:
            session.active.discard(parsed[spec.id_arg])
    return parsed


_DEFAULT: LaneSessionPool | None = None
_DEFAULT_LOCK = threading.Lock()


def default_pool() -> LaneSessionPool:
    """The engine's pool, created on first use and closed at interpreter exit."""
    global _DEFAULT
    with _DEFAULT_LOCK:
        if _DEFAULT is None:
            _DEFAULT = LaneSessionPool()
            atexit.register(_DEFAULT.close_all)
        return _DEFAULT


def close_lane_sessions() -> None:
    """Close every lane session the engine holds (the gateway calls this on stop)."""
    if _DEFAULT is not None:
        _DEFAULT.close_all()
