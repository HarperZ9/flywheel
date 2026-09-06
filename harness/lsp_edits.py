"""lsp_edits.py -- a WorkspaceEdit becomes changes on disk, or it is refused.

Everything else this client does is a question. This is the one place a language
server's answer turns into a write, so the shape is a plan first and a write
second. A plan names every file it would touch, the text it would leave there,
and the digest either side of the change, which lets a caller record or decline
the edit while nothing on disk has moved yet.

`lsp_text_edits` handles the part that is only string manipulation, including
the two silent failures that live there: offsets shifting under earlier edits,
and ranges counted in the wrong encoding. What this module adds is everything
about the filesystem.

A URI can leave the workspace. Nothing stops a server naming a path outside the
root it was started in, and an edit that walks out of the tree is refused here
rather than resolved.

A stamped version means the server was looking at a different file. Applying an
edit computed against version 4 to a buffer now at version 7 writes a change for
text that is no longer there.

A resource operation is not a text edit at all. `create`, `rename`, and `delete`
in `documentChanges` are filesystem mutations, and they are refused rather than
performed.

Writes are default-deny, the posture the agent's file tools already take. A plan
costs nothing and needs no permission. Applying one takes a caller who said so.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from .lsp_documents import from_uri
from .lsp_positions import DEFAULT_ENCODING, check_encoding
from .lsp_text_edits import REFUSALS, EditRefused, rebuilt, spans_of

EDIT_SCHEMA = "flywheel.lsp-edit/v1"

__all__ = ["EDIT_SCHEMA", "REFUSALS", "EditPlan", "EditRefused", "FileChange",
           "apply_plan", "apply_workspace_edit", "does_not_prove", "plan_edit"]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class FileChange:
    """One document the plan would rewrite, and the text it would leave.

    The text is here because the write needs it. It is kept out of `summary`
    because a record of a change should not carry a second copy of the file.
    """

    uri: str
    path: Path
    before: str = ""
    after: str = ""
    edits: int = 0

    def changed(self) -> bool:
        return self.before != self.after

    def summary(self) -> dict:
        return {"uri": self.uri, "edits": self.edits,
                "changed": self.changed(),
                "before_sha256": _sha(self.before),
                "after_sha256": _sha(self.after)}


@dataclass
class EditPlan:
    """What a WorkspaceEdit amounts to, before any of it has happened."""

    files: list = field(default_factory=list)
    encoding: str = DEFAULT_ENCODING
    root: Path | None = None
    applied: bool = False
    written: list = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "schema": EDIT_SCHEMA,
            "encoding": self.encoding,
            "documents": len(self.files),
            "edits": sum(change.edits for change in self.files),
            "changed": sum(1 for change in self.files if change.changed()),
            "applied": self.applied,
            "written": list(self.written),
            "files": [change.summary() for change in self.files],
            "does_not_prove": does_not_prove(),
        }


def _resolve(uri: str, root: Path | None) -> Path:
    """The path a document URI names, refused if it leaves the workspace."""
    try:
        path = from_uri(uri).resolve()
    except ValueError as e:
        raise EditRefused("not-a-file-uri", str(e)) from None
    if root is not None and not path.is_relative_to(Path(root).resolve()):
        raise EditRefused("outside-root", uri)
    return path


def _read(path: Path) -> str:
    """The file as the server sees it, line endings left exactly as found.

    Reading in universal-newline mode turns every CRLF into LF, and writing
    that back rewrites every line of the file to apply a one-word change. The
    diff would be the whole document and the edit would be lost in it.
    """
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return handle.read()
    except FileNotFoundError:
        raise EditRefused("no-such-file", str(path)) from None
    except (OSError, UnicodeDecodeError) as e:
        raise EditRefused("unreadable", f"{path.name}: {e}") from None


def _check_version(uri: str, stamped: object, documents) -> None:
    """Refuse an edit computed against a buffer that has since moved.

    A null version is legal and says the server is not claiming to know which
    revision it read. There is nothing to check against then, so nothing is
    checked, and the same holds for a document this client never opened.
    """
    if documents is None or not isinstance(stamped, int) \
            or isinstance(stamped, bool):
        return
    if uri in documents and not documents.is_current(uri, stamped):
        raise EditRefused("stale-version",
                          f"{uri} was computed against version {stamped}")


def _documents_of(edit: dict, documents):
    """(uri, edits) per document, from whichever shape the server sent.

    `documentChanges` wins when present. It is the shape carrying versions and
    resource operations, and a server sending both is expected to have put the
    same content in each.
    """
    changes = edit.get("documentChanges")
    if isinstance(changes, list):
        for entry in changes:
            if not isinstance(entry, dict):
                raise EditRefused("malformed-edit",
                                  "a documentChange is not an object")
            if "kind" in entry:
                raise EditRefused("resource-operation", str(entry["kind"]))
            document = entry.get("textDocument") or {}
            uri = str(document.get("uri", ""))
            _check_version(uri, document.get("version"), documents)
            yield uri, list(entry.get("edits") or [])
        return
    legacy = edit.get("changes")
    if isinstance(legacy, dict):
        for uri in sorted(legacy):
            yield str(uri), list(legacy[uri] or [])


def plan_edit(edit: dict, *, root: Path | str | None = None,
              encoding: str = DEFAULT_ENCODING, documents=None,
              confirmed=()) -> EditPlan:
    """What a WorkspaceEdit would do, worked out without touching the disk.

    `root` of None means no containment check, for a caller doing their own.
    The client passes its workspace root and refuses when it has none, so the
    policy sits where the decision is rather than in here.
    """
    check_encoding(encoding)
    annotations = (edit or {}).get("changeAnnotations") or {}
    confirmed = frozenset(confirmed)
    plan = EditPlan(encoding=encoding,
                    root=Path(root).resolve() if root is not None else None)
    for uri, edits in _documents_of(edit or {}, documents):
        path = _resolve(uri, root)
        before = _read(path)
        spans = spans_of(before, edits, encoding, annotations, confirmed)
        plan.files.append(FileChange(uri=uri, path=path, before=before,
                                     after=rebuilt(before, spans),
                                     edits=len(spans)))
    return plan


def apply_plan(plan: EditPlan, *, allow_write: bool = False) -> dict:
    """Write the plan, or refuse. Nothing is opened for writing before here.

    A file the edit did not actually change is left alone rather than
    rewritten, so an edit that amounted to nothing does not move a modification
    time and does not read as a change to anything watching the tree.

    A write that fails part way leaves the files before it changed. The refusal
    names them, because a caller who has to clean up needs to know which ones.
    """
    if not allow_write:
        raise EditRefused("write-not-allowed",
                          f"{len(plan.files)} document(s) planned")
    for change in plan.files:
        if not change.changed():
            continue
        try:
            with change.path.open("w", encoding="utf-8", newline="") as handle:
                handle.write(change.after)
        except OSError as e:
            raise EditRefused(
                "write-failed",
                f"{change.path.name}: {e}; already written: "
                f"{plan.written or 'nothing'}") from None
        plan.written.append(change.uri)
    plan.applied = True
    return plan.summary()


def apply_workspace_edit(edit: dict, *, root: Path | str | None = None,
                         encoding: str = DEFAULT_ENCODING, documents=None,
                         allow_write: bool = False, confirmed=()) -> dict:
    """Plan and apply in one call, the shape a server's request wants."""
    plan = plan_edit(edit, root=root, encoding=encoding, documents=documents,
                     confirmed=confirmed)
    return apply_plan(plan, allow_write=allow_write)


def does_not_prove() -> list[str]:
    """What an applied edit leaves open. Never empty."""
    return [
        "the digests cover the text this process read and wrote, so a file "
        "changed by something else between the plan and the write is not seen",
        "each file is written on its own, so a failure part way through leaves "
        "the earlier documents changed and the later ones untouched",
        "the edit is the server's proposal, and applying it says the ranges "
        "were consistent, not that the change is correct",
        "resource operations (create, rename, delete) are refused rather than "
        "performed, so an edit needing one is not applied at all",
    ]
