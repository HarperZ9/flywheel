"""trajectory.py -- layer 2: deterministic rules over the run so far.

One call can pass every per-call rule while a sequence does harm. This layer
keeps per-run state and adds four rules: sensitive-source taint (bytes read
from a credential source reappearing in a later call's arguments, or a file
they were written to being named later), denial counters (3 consecutive or
20 total stops hold the session, the bounds Claude Code auto mode publishes),
repeat after reject (a call the owner rejected is blocked if asked again),
and scope drift (calls leaving the workspace or allowlist accumulate).

State is plain JSON so the hook path, which runs one process per call, can
carry it across calls. Taint keeps only window digests, never the bytes.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .contract import ALLOW, BLOCK, HOLD, Hit, ProposedCall, RunContext
from .normalize import extract, norm_path

WINDOW = 32               # placeholder; tune on bank B2
MAX_CONSECUTIVE, MAX_TOTAL = 3, 20


def _windows(text: str) -> set:
    data = text.encode("utf-8", "surrogatepass")
    if len(data) < WINDOW:
        return set()
    return {hashlib.sha256(data[i:i + WINDOW]).hexdigest()[:16]
            for i in range(len(data) - WINDOW + 1)}


@dataclass
class TrajectoryState:
    run_id: str
    drift_threshold: int = 5
    consecutive_stops: int = 0
    total_stops: int = 0
    session_held: bool = False
    terminated: bool = False
    drift_count: int = 0
    goal: str = ""
    resumes_applied: int = 0
    rejected: set = field(default_factory=set)
    taint_windows: set = field(default_factory=set)
    taint_paths: set = field(default_factory=set)
    history: list = field(default_factory=list)

    # --- updates -----------------------------------------------------------
    def record(self, verdict: str, call_sha: str, tool: str = "", capability: str = "") -> None:
        if verdict in (HOLD, BLOCK):
            self.consecutive_stops += 1
            self.total_stops += 1
        else:
            self.consecutive_stops = 0
        if self.consecutive_stops >= MAX_CONSECUTIVE or self.total_stops >= MAX_TOTAL:
            self.session_held = True
        self.history.append({"tool": tool, "args_sha256": call_sha,
                             "capability": capability, "verdict": verdict})
        del self.history[:-200]

    def resume(self) -> None:
        """The owner resumed a held session."""
        self.session_held = False
        self.consecutive_stops = 0
        self.total_stops = 0

    def add_taint(self, text: str, written_path: str | None) -> None:
        self.taint_windows |= _windows(text)
        if written_path:
            self.taint_paths.add(written_path)

    def note_scope(self, call: ProposedCall, ctx: RunContext) -> None:
        if self._leaves_scope(call, ctx):
            self.drift_count += 1

    def note_write(self, call: ProposedCall, ctx: RunContext) -> None:
        """A write whose content is tainted taints the written path too."""
        facts = extract(call, ctx)
        if facts.kind == "write" and self._tainted_text(facts.text):
            self.taint_paths |= set(facts.paths)

    # --- checks ------------------------------------------------------------
    def _tainted_text(self, text: str) -> bool:
        return bool(self.taint_windows) and bool(_windows(text) & self.taint_windows)

    def _leaves_scope(self, call: ProposedCall, ctx: RunContext) -> bool:
        facts = extract(call, ctx)
        ws = norm_path(ctx.workspace, "") if ctx.workspace else ""
        outside = ws and any(not (p == ws or p.startswith(ws.rstrip("/") + "/")) for p in facts.paths)
        return bool(outside)

    def hits(self, call: ProposedCall, ctx: RunContext) -> list:
        out = []
        facts = extract(call, ctx)
        if self.terminated:
            out.append(Hit("run-terminated/001", "run-terminated", BLOCK,
                           "The owner terminated this run.", layer=2))
        if self.session_held:
            out.append(Hit("denial-counter/001", "denial-counter", HOLD,
                           "Repeated stops in this session; the owner must resume it.", layer=2))
        if call.call_sha256() in self.rejected:
            out.append(Hit("repeat-after-reject/001", "repeat-after-reject", BLOCK,
                           "The owner already rejected this exact call in this run.", layer=2))
        if self._tainted_text(facts.text + "\n" + facts.command) or \
                any(p in self.taint_paths for p in facts.paths):
            out.append(Hit("taint-flow/001", "taint-flow", HOLD,
                           "Carries data read from a credential source, or names a file it was written to.",
                           layer=2))
        if self.drift_count >= self.drift_threshold and self._leaves_scope(call, ctx):
            out.append(Hit("scope-drift/001", "scope-drift", HOLD,
                           "Calls keep leaving the run's workspace.", layer=2))
        return out

    # --- persistence ---------------------------------------------------------
    def to_dict(self) -> dict:
        return {"run_id": self.run_id, "drift_threshold": self.drift_threshold,
                "consecutive_stops": self.consecutive_stops, "total_stops": self.total_stops,
                "session_held": self.session_held, "terminated": self.terminated,
                "drift_count": self.drift_count, "goal": self.goal,
                "resumes_applied": self.resumes_applied,
                "rejected": sorted(self.rejected), "taint_windows": sorted(self.taint_windows),
                "taint_paths": sorted(self.taint_paths), "history": self.history}

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(self.to_dict()), encoding="utf-8")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: Path, run_id: str) -> "TrajectoryState":
        path = Path(path)
        if not path.exists():
            return cls(run_id=run_id)
        d = json.loads(path.read_text(encoding="utf-8"))
        st = cls(run_id=run_id, drift_threshold=int(d.get("drift_threshold", 5)))
        for key in ("consecutive_stops", "total_stops", "drift_count"):
            setattr(st, key, int(d.get(key, 0)))
        st.session_held, st.terminated = bool(d.get("session_held")), bool(d.get("terminated"))
        st.goal = str(d.get("goal", ""))
        st.resumes_applied = int(d.get("resumes_applied", 0))
        st.rejected, st.taint_windows = set(d.get("rejected", [])), set(d.get("taint_windows", []))
        st.taint_paths, st.history = set(d.get("taint_paths", [])), list(d.get("history", []))
        return st


def allow_verdict() -> str:
    return ALLOW
