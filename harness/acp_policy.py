"""acp_policy.py -- what a Flywheel ACP client will let a delegated agent do.

An ACP agent asks its client for permission before acting, and asks it to read
and write files on its behalf. Those requests are the whole of the agent's reach
into the machine, so this is the grant boundary, and it is written as a separate
module because a boundary buried inside a transport is a boundary nobody audits.

The default is DenyAll. A harness whose job is to witness a run should not also
be the thing that authorized it by omission, and an agent that is refused says
so in its own transcript, which is a better record than a silent allow. Callers
who want the agent to work choose a policy by name and the name says what they
chose.

Every decision is recorded on the policy object. The witness reads those records
back, so a receipt can say what was asked for and what was refused rather than
only what happened to succeed.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Protocol

ALLOW_ONCE = "allow_once"
ALLOW_ALWAYS = "allow_always"
REJECT_ONCE = "reject_once"
REJECT_ALWAYS = "reject_always"
ALLOW_KINDS = (ALLOW_ONCE, ALLOW_ALWAYS)
REJECT_KINDS = (REJECT_ONCE, REJECT_ALWAYS)

SELECTED = "selected"
CANCELLED = "cancelled"


class OutsideRoot(PermissionError):
    """A path the agent asked for that lies outside the session directory."""


@dataclass(frozen=True)
class Decision:
    """One thing the agent asked for and what this client answered."""

    method: str
    detail: str
    allowed: bool
    reason: str = ""


class Policy(Protocol):
    """The three questions an ACP agent can ask its client.

    `reads` and `writes` are what the client advertises during initialize. They
    are declared rather than probed, because probing a write policy means
    writing something, and a capability check should not be an action.
    """

    reads: bool
    writes: bool

    def permission(self, params: dict) -> dict: ...

    def read_text_file(self, params: dict) -> dict: ...

    def write_text_file(self, params: dict) -> dict: ...


def _pick(options: Any, kinds: tuple[str, ...]) -> str | None:
    """The first offered option whose kind is in `kinds`, by the agent's order."""
    if not isinstance(options, list):
        return None
    for option in options:
        if isinstance(option, dict) and option.get("kind") in kinds:
            option_id = option.get("optionId")
            if isinstance(option_id, str) and option_id:
                return option_id
    return None


def _outcome(option_id: str | None) -> dict:
    """The permission result. No matching option means the request is cancelled.

    Inventing an optionId the agent did not offer would be worse than declining:
    the agent would act on an authorization that was never expressed.
    """
    if option_id is None:
        return {"outcome": {"outcome": CANCELLED}}
    return {"outcome": {"outcome": SELECTED, "optionId": option_id}}


class DenyAll:
    """Refuse every request, record each one, and let the agent decide what next.

    This is the default policy. It is the honest one for a harness that exists to
    observe: an agent driven under DenyAll produces a transcript of what it
    wanted, which is exactly the material a receipt should carry.
    """

    name = "deny-all"
    reads = False
    writes = False

    def __init__(self) -> None:
        self.decisions: list[Decision] = []

    def _record(self, method: str, detail: str, allowed: bool,
                reason: str = "") -> None:
        self.decisions.append(Decision(method, detail, allowed, reason))

    def permission(self, params: dict) -> dict:
        title = str(params.get("title", ""))
        chosen = _pick(params.get("options"), REJECT_KINDS)
        self._record("session/request_permission", title, False,
                     "policy denies every request")
        return _outcome(chosen)

    def read_text_file(self, params: dict) -> dict:
        self._record("fs/read_text_file", str(params.get("path", "")), False,
                     "policy denies every request")
        raise PermissionError("this client does not read files for the agent")

    def write_text_file(self, params: dict) -> dict:
        self._record("fs/write_text_file", str(params.get("path", "")), False,
                     "policy denies every request")
        raise PermissionError("this client does not write files for the agent")


class WorkspacePolicy(DenyAll):
    """Reads and writes inside one directory; permission answered by a flag.

    The root check resolves symlinks before comparing, because a link inside the
    workspace pointing out of it is the ordinary way a path check that compares
    strings gets walked through.
    """

    name = "workspace"
    reads = True

    def __init__(self, root: Path | str, *, allow_writes: bool = False,
                 allow_permission: bool = False) -> None:
        super().__init__()
        self.root = Path(root).resolve()
        self.allow_writes = allow_writes
        self.writes = allow_writes
        self.allow_permission = allow_permission

    def _inside(self, raw: Any) -> Path:
        if not isinstance(raw, str) or not raw:
            raise OutsideRoot("the agent named no path")
        candidate = Path(raw)
        if not candidate.is_absolute():
            raise OutsideRoot("ACP paths are absolute")
        # resolve() on a path that does not exist yet still normalizes it, which
        # is what a write to a new file needs.
        resolved = candidate.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise OutsideRoot(f"{resolved} is outside {self.root}")
        return resolved

    def permission(self, params: dict) -> dict:
        if not self.allow_permission:
            return DenyAll.permission(self, params)
        chosen = _pick(params.get("options"), ALLOW_KINDS)
        self._record("session/request_permission", str(params.get("title", "")),
                     chosen is not None,
                     "" if chosen else "the agent offered no allow option")
        return _outcome(chosen)

    def read_text_file(self, params: dict) -> dict:
        path = self._guard("fs/read_text_file", params, needed=True)
        text = path.read_text(encoding="utf-8")
        line, limit = params.get("line"), params.get("limit")
        if isinstance(line, int) or isinstance(limit, int):
            lines = text.splitlines(keepends=True)
            start = max(int(line) - 1, 0) if isinstance(line, int) else 0
            end = start + int(limit) if isinstance(limit, int) else len(lines)
            text = "".join(lines[start:end])
        return {"content": text}

    def write_text_file(self, params: dict) -> dict:
        if not self.allow_writes:
            self._record("fs/write_text_file", str(params.get("path", "")),
                         False, "this policy is read-only")
            raise PermissionError("this policy is read-only")
        path = self._guard("fs/write_text_file", params, needed=False)
        content = params.get("content")
        if not isinstance(content, str):
            raise ValueError("fs/write_text_file carries text content")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {}

    def _guard(self, method: str, params: dict, *, needed: bool) -> Path:
        raw = params.get("path")
        try:
            path = self._inside(raw)
        except OutsideRoot as exc:
            self._record(method, str(raw), False, str(exc))
            raise
        if needed and not path.is_file():
            self._record(method, str(path), False, "no such file")
            raise FileNotFoundError(os.fspath(path))
        self._record(method, str(path), True)
        return path


class AllowAll(DenyAll):
    """Answer yes to everything. Named so that nobody reaches it by accident."""

    name = "allow-all"
    reads = True
    writes = True

    def permission(self, params: dict) -> dict:
        chosen = _pick(params.get("options"), ALLOW_KINDS)
        self._record("session/request_permission", str(params.get("title", "")),
                     chosen is not None,
                     "" if chosen else "the agent offered no allow option")
        return _outcome(chosen)

    def read_text_file(self, params: dict) -> dict:
        path = Path(str(params.get("path", "")))
        self._record("fs/read_text_file", str(path), True)
        return {"content": path.read_text(encoding="utf-8")}

    def write_text_file(self, params: dict) -> dict:
        path = Path(str(params.get("path", "")))
        content = params.get("content")
        if not isinstance(content, str):
            raise ValueError("fs/write_text_file carries text content")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self._record("fs/write_text_file", str(path), True)
        return {}
