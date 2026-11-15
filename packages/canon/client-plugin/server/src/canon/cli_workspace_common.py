"""Shared plumbing for the workspace commands: the project context every
command starts from, the mapping from a refusal to a stable failure code, and
one way to print a result.

Every refusal a workspace command meets becomes a named failure code with the
refusal's own text as the message. Nothing is swallowed: an exception this
module does not know is re-raised.
"""
from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from .cli_format import make_result, write_result
from .concurrency import LockError
from .workspace.authoring import AuthoringError
from .workspace.identity import ProjectIdentity, ProjectIdentityError, derive_identity
from .workspace.rows import RowError
from .workspace.store import (
    AcceptConflict,
    IsolationError,
    ProjectStore,
    SecretRefused,
    StoreError,
    default_store_root,
)

_FAILURES: tuple[tuple[type[BaseException], str], ...] = (
    (IsolationError, "isolation_refused"),
    (SecretRefused, "secret_quarantine"),
    (AcceptConflict, "conflict"),
    (RowError, "store_invalid"),
    (LockError, "store_busy"),
    (ProjectIdentityError, "invalid_args"),
    (StoreError, "invalid_args"),
    (AuthoringError, "invalid_args"),
)


@dataclass(frozen=True, slots=True)
class WorkspaceContext:
    identity: ProjectIdentity
    store: ProjectStore
    workspace: Path


@dataclass(frozen=True, slots=True)
class Output:
    stdout: TextIO
    stderr: TextIO
    json_output: bool
    color: bool


class CommandFailure(Exception):
    """A handler's own refusal, carrying the failure code to report."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def build_context(parsed: argparse.Namespace, environ: Mapping[str, str],
                  out: "Output | None" = None) -> WorkspaceContext:
    """The project context. With `out`, a checkout new to an existing project
    is announced on stderr, so a merge the identity rules cannot see (two
    repositories sharing one remote) is never silent."""
    workspace = Path(parsed.workspace)
    identity = derive_identity(workspace, remote_url=parsed.remote)
    root = Path(parsed.store) if parsed.store else default_store_root(environ)
    store = ProjectStore(root, identity)
    notice = store.checkout_notice() if out is not None else None
    if notice:
        out.stderr.write(f"notice: {notice}\n")
    return WorkspaceContext(identity, store, workspace.resolve())


def one_line(text: str, limit: int = 400) -> str:
    """A result message is one printable line."""
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 3] + "..."


def emit(out: Output, *, command: str, message: str, data: dict,
         text: str | None = None) -> int:
    """Print a successful result: the human text on stdout, or the JSON result."""
    if out.json_output or text is None:
        result = make_result(ok=True, command=command, failure_code="ok",
                             message=one_line(message), data=data)
        return write_result(result, stdout=out.stdout, stderr=out.stderr,
                            json_output=out.json_output, color=out.color)
    out.stdout.write(text if text.endswith("\n") else text + "\n")
    return 0


def fail(out: Output, *, command: str, code: str, message: str,
         data: dict | None = None) -> int:
    result = make_result(ok=False, command=command, failure_code=code,
                         message=one_line(message), data=data)
    return write_result(result, stdout=out.stdout, stderr=out.stderr,
                        json_output=out.json_output, color=out.color)


def guarded(command: str, out: Output, action: Callable[[], int]) -> int:
    """Run `action`, mapping each known refusal to its failure code."""
    try:
        return action()
    except CommandFailure as exc:
        return fail(out, command=command, code=exc.code, message=str(exc))
    except tuple(kind for kind, _ in _FAILURES) as exc:
        code = next(c for kind, c in _FAILURES if isinstance(exc, kind))
        return fail(out, command=command, code=code, message=str(exc))
