"""bisect.py -- git-bisect for a witnessed agent run.

run_view localizes a broken HASH; this localizes broken BEHAVIOR. Given a run whose
witnessed edit-set ends in a failing acceptance check, replay the recorded edits in
order onto a clean copy of the pre-run tree and bisect for the FIRST edit that flips
the check from pass to fail. The model is never re-run -- only the recorded edits are
replayed (through the same ToolExecutor that applied them) against a deterministic
check -- so the localization is re-derivable offline and reuses the witnessed ledger.

Honest null: bisection needs the PRE-run tree state (a clean checkout) and a
deterministic acceptance check; it copies the tree per probe (fine for a normal
edit-set; use a git worktree for a huge repo), and it assumes the failure is monotonic
in the edit prefix -- git-bisect's own assumption. A non-replayable edit (its ``old``
text absent in the reconstructed tree) is skipped, so the verdict reflects the tree as
faithfully as the ledger allows.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from .local_tools import WRITE_TOOLS, ToolExecutor, ToolGate

SCHEMA = "relay.bisect/v1"
_EDIT_TOOLS = WRITE_TOOLS
_CHECK_TIMEOUT = 600


def edit_set(ledger) -> list:
    """The ordered (seq, name, args) of the file edits a run witnessed."""
    out = []
    for e in ledger.entries:
        if getattr(e, "kind", "") != "tool_call":
            continue
        name, _, rest = (getattr(e, "content", "") or "").partition(" ")
        if name not in _EDIT_TOOLS:
            continue
        try:
            args = json.loads(rest) if rest else {}
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(args, dict) and args.get("path"):
            out.append((getattr(e, "seq", None), name, args))
    return out


def _default_runner(check: str, root: str, guard: "str | None" = None):
    """Run ``check`` in ``root``. PATH entries that reach ``guard`` (``root`` when it
    is None) leave the shell's PATH, so a program planted there is never found."""
    from .child_env import shell_env
    proc = subprocess.run(check, shell=True, cwd=root, capture_output=True,
                          text=True, timeout=_CHECK_TIMEOUT, env=shell_env(cwd=guard or root))
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


def _tree_at_prefix(base_root: str, edits: list, k: int) -> str:
    """Copy the pre-run tree and replay the first k edits through a real executor."""
    holder = tempfile.mkdtemp(prefix="relay-bisect-")
    dst = Path(holder) / "tree"
    shutil.copytree(base_root, dst)
    executor = ToolExecutor(root=str(dst), gate=ToolGate(allow_write=True))
    for _, name, args in edits[:k]:
        executor.execute(name, args)
    return str(dst)


def _result(**kw) -> dict:
    return {"schema": SCHEMA, **kw}


def bisect_run(ledger, base_root: str, check: str, *, runner=None) -> dict:
    """Localize the first witnessed edit that breaks ``check``, replaying edits onto a
    clean copy of ``base_root``. ``runner(check, root) -> (ok, output)`` is injectable."""
    # Each check runs in a fresh copy whose name no PATH entry can hold in advance.
    # The project it copies is the folder a PATH entry can reach, so guard that one.
    runner = runner or (lambda check, tree: _default_runner(check, tree, guard=base_root))
    edits = edit_set(ledger)
    n = len(edits)
    cache: dict = {}

    def verdict(k: int) -> bool:
        if k not in cache:
            tree = _tree_at_prefix(base_root, edits, k)
            try:
                ok, _ = runner(check, tree)
            finally:
                shutil.rmtree(Path(tree).parent, ignore_errors=True)
            cache[k] = bool(ok)
        return cache[k]

    if n == 0:
        return _result(first_bad_seq=None, checks_run=0, note="no witnessed edits to bisect")
    if not verdict(0):
        return _result(first_bad_seq=None, checks_run=len(cache),
                       note="the pre-run tree already fails the check; nothing to localize")
    if verdict(n):
        return _result(first_bad_seq=None, checks_run=len(cache),
                       note="the full edit-set still passes; no bad edit")
    lo, hi = 0, n
    while lo + 1 < hi:                       # first-bad prefix in (lo, hi]
        mid = (lo + hi) // 2
        if verdict(mid):
            lo = mid
        else:
            hi = mid
    seq, name, args = edits[hi - 1]
    from .integrity import DEFAULT_PROTECTED, _matches
    return _result(
        first_bad_seq=seq, first_bad_edit={"tool": name, "path": args.get("path")},
        n_edits=n, checks_run=len(cache),
        edited_protected=_matches(str(args.get("path", "")), DEFAULT_PROTECTED),
        note=f"first edit that breaks the check: seq {seq} ({name} {args.get('path')})")
