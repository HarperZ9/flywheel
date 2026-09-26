"""check_guard.py -- a check command is trusted by what is on disk, not by tool names.

The integrity check reads the ledger for write tools that touched a file that
grades the work. A run that can execute commands can also rewrite a test with
`sed` or `python -c`, and that `run` call names no file. So before each run of
the check command this guard re-hashes the files that grade the work and
records any change since the run began as a `check_state` ledger entry, which
`integrity.trajectory_integrity` turns into a flag. The pass that follows is
then not trusted, whatever tool made the change.

The guard also notes which files a check run itself changed (a coverage file,
a test's scratch output), so the end-of-run workspace diff can list the files
the run changed outside a hashed write without listing the check's own side
effects as deliverables.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .integrity import CHECK_CONFIG_SECTIONS, DEFAULT_PROTECTED, _matches


def _section(text: str, prefix: str) -> str:
    """The lines of every section whose header starts with `prefix`."""
    kept, inside = [], False
    for line in text.splitlines():
        if line.strip().startswith("["):
            inside = line.strip().startswith(prefix)
        if inside:
            kept.append(line.rstrip())
    return "\n".join(kept)


def _files(root: Path, max_files: int):
    """Relative file paths under root, sorted, never entering a skipped
    directory (VCS, caches, builds), and at most `max_files` of them."""
    from .workspace_state import skipped_part
    seen = 0
    for top, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not skipped_part(Path(d)))
        for name in sorted(names):
            seen += 1
            if seen > max_files:
                return
            yield (Path(top) / name).relative_to(root)


def check_state(root, *, protected=DEFAULT_PROTECTED, max_files: int = 20_000) -> dict:
    """Content hashes of what grades the work: each protected file, and the
    test-runner section of each shared config file. A walk past `max_files`
    is marked, so a truncated view is never read as a complete one."""
    root, state, count = Path(root), {}, 0
    for rel in _files(root, max_files + 1):
        count += 1
        if count > max_files:
            state["(walk truncated)"] = str(max_files)
            break
        path, name = root / rel, rel.as_posix()
        try:
            if _matches(name, protected):
                state[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            elif path.name in CHECK_CONFIG_SECTIONS:
                prefix = CHECK_CONFIG_SECTIONS[path.name]
                section = _section(path.read_text(encoding="utf-8", errors="replace"), prefix)
                state[f"{name}#{prefix}"] = hashlib.sha256(section.encode("utf-8")).hexdigest()
        except OSError:
            state[name] = "unreadable"
    return state


def record_check_state(ledger, baseline, now) -> list:
    """Name each protected file changed since the run began, in the ledger."""
    changed = changed_paths(baseline, now)
    if changed:
        ledger.append("check_state", json.dumps(
            {"changed": changed[:64], "count": len(changed)}, sort_keys=True))
    return changed


def _hashes(root) -> dict:
    from .workspace_state import workspace_snapshot
    hashes: dict = {}
    workspace_snapshot(root, hashes=hashes)
    return hashes


def changed_paths(before: dict, after: dict) -> list:
    return sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))


class CheckGuardExecutor:
    """Wraps a tool executor for a run that has a check command.

    Before each run of the check: record protected-file changes. Around it:
    note the files the check itself changed, in `check_side_effects`.
    Everything else passes through, so receipts and the budget keep working."""

    def __init__(self, inner, *, root, ledger, test_cmd) -> None:
        self._inner, self._root, self._ledger = inner, root, ledger
        self._test_cmd = test_cmd
        self._baseline = check_state(root)
        self.check_side_effects: set = set()

    def execute(self, name, args, *extra, **kwargs):
        if not (name == "run" and type(args) is dict and args.get("cmd") == self._test_cmd):
            return self._inner.execute(name, args, *extra, **kwargs)
        now = check_state(self._root)
        record_check_state(self._ledger, self._baseline, now)
        before = _hashes(self._root)
        try:
            return self._inner.execute(name, args, *extra, **kwargs)
        finally:
            self.check_side_effects.update(changed_paths(before, _hashes(self._root)))
            # A protected file the check itself rewrote (a snapshot test, say)
            # is the check's doing, so the next comparison starts from it.
            after = check_state(self._root)
            for path in changed_paths(now, after):
                if path in after:
                    self._baseline[path] = after[path]
                else:
                    self._baseline.pop(path, None)

    def __getattr__(self, attr):
        return getattr(self._inner, attr)


def guard_check(executor, *, root, ledger, test_cmd):
    """The executor to use: guarded when the run has a check command."""
    if not test_cmd:
        return executor
    return CheckGuardExecutor(executor, root=root, ledger=ledger, test_cmd=test_cmd)
